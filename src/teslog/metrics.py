"""Dashboard metrics — one function per metric shown on the Teslog dashboard.

Distance metrics read Teslog's own `drive_route_comparisons` table (already
computed by the sync loop). Energy and charging metrics read TeslaMate's
database directly, the same way the sync loop reads `drives`/`positions`.
Battery health comes from TeslaMateApi's live Tesla API query — that value
isn't stored history, so there's nothing to read from Postgres for it.
"""

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from teslog.clients import TeslaMateApiClient
from teslog.db import DriveRouteComparison, get_teslog_sessionmaker

# --- Distance (Teslog DB) ----------------------------------------------------

# Every distance is stored and computed internally in km — TeslaMate's own unit, and what OSRM/
# haversine already return. Only converted to miles at the point a series is handed to the API/
# dashboard/export; energy (kWh) and drift (%, a ratio) aren't distances and stay as-is.
_KM_TO_MI = 0.621371


def _mi(km: float | None) -> float | None:
    return round(km * _KM_TO_MI, 2) if km is not None else None


# Front-and-back garage shuffles, three-point turns, driving lessons: real movement, but not a
# "drive" worth tracking. Excluded wherever the smaller of OSRM route distance / odometer delta
# is below this, so a short GPS blip doesn't get counted just because the odometer briefly moved.
_MIN_DRIVE_KM = 0.5 * 1.609344  # 0.5 miles


def _not_short_trip():
    """SQLAlchemy predicate: false only when both distances are known AND their min is small.

    Missing data (OSRM failed, no GPS) never counts as "short" on its own — this only excludes
    drives positively confirmed to be tiny, not ones we simply couldn't measure.
    """
    return or_(
        DriveRouteComparison.odometer_delta.is_(None),
        DriveRouteComparison.osrm_route_distance.is_(None),
        func.least(DriveRouteComparison.odometer_delta, DriveRouteComparison.osrm_route_distance) > _MIN_DRIVE_KM,
    )


def _excluded_short_trip_ids(car_id: int) -> set[int]:
    """Drive ids `_not_short_trip` would filter out — for cross-referencing against TeslaMate's
    own `drives` table, which has no OSRM distance of its own to filter by directly."""
    with get_teslog_sessionmaker()() as session:
        return set(
            session.execute(
                select(DriveRouteComparison.drive_id).where(
                    DriveRouteComparison.car_id == car_id, ~_not_short_trip()
                )
            ).scalars()
        )


def _drift_pct(odometer_delta: float | None, baseline_distance: float | None) -> float | None:
    """(odometer_delta - baseline_distance) / baseline_distance * 100, or None if either is missing."""
    if odometer_delta is None or not baseline_distance:
        return None
    return round((odometer_delta - baseline_distance) / baseline_distance * 100, 2)


def drift_pct_series(session: Session, car_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Odometer drift % against two different baselines, per drive:

    OSRMDrift — vs. OSRM's routed distance between the drive's start/end points (what the road
    network says the trip *should* have taken — diverges if you didn't take the shortest route).
    GPSDrift (haversine_drift_pct) — vs. the GPS trace distance (straight-line hops between every
    recorded point along the path actually driven) — should track the odometer closely, since
    both describe the same real path.
    """
    rows = session.execute(
        select(
            DriveRouteComparison.drive_start_at,
            DriveRouteComparison.odometer_delta,
            DriveRouteComparison.osrm_route_distance,
            DriveRouteComparison.gps_trace_distance,
        )
        .where(DriveRouteComparison.car_id == car_id, _not_short_trip())
        .order_by(DriveRouteComparison.drive_start_at)
        .limit(limit)
    ).all()
    result = []
    for row in rows:
        osrm_drift = _drift_pct(row.odometer_delta, row.osrm_route_distance)
        haversine_drift = _drift_pct(row.odometer_delta, row.gps_trace_distance)
        if osrm_drift is None and haversine_drift is None:
            continue
        result.append(
            {
                "date": row.drive_start_at.isoformat(),
                "osrm_drift_pct": osrm_drift,
                "haversine_drift_pct": haversine_drift,
            }
        )
    return result


def distance_comparison_series(session: Session, car_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Odometer delta vs OSRM route distance vs GPS trace distance, per drive (in miles)."""
    rows = session.execute(
        select(
            DriveRouteComparison.drive_start_at,
            DriveRouteComparison.odometer_delta,
            DriveRouteComparison.osrm_route_distance,
            DriveRouteComparison.gps_trace_distance,
        )
        .where(DriveRouteComparison.car_id == car_id, _not_short_trip())
        .order_by(DriveRouteComparison.drive_start_at)
        .limit(limit)
    ).all()
    return [
        {
            "date": row.drive_start_at.isoformat(),
            "odometer_mi": _mi(row.odometer_delta),
            "osrm_mi": _mi(row.osrm_route_distance),
            "gps_mi": _mi(row.gps_trace_distance),
        }
        for row in rows
    ]


# --- Energy (TeslaMate DB) ----------------------------------------------------


def _energy_rows(session: Session, car_id: int, limit: int) -> list[Any]:
    return session.execute(
        text(
            """
            SELECT d.id, d.start_date, d.distance, d.start_rated_range_km, d.end_rated_range_km,
                   c.efficiency
            FROM drives d
            JOIN cars c ON c.id = d.car_id
            WHERE d.car_id = :car_id AND d.end_date IS NOT NULL
              AND d.start_rated_range_km IS NOT NULL AND d.end_rated_range_km IS NOT NULL
              AND c.efficiency IS NOT NULL AND d.distance IS NOT NULL AND d.distance > 0
            ORDER BY d.start_date DESC
            LIMIT :limit
            """
        ),
        {"car_id": car_id, "limit": limit},
    ).all()


def energy_used_series(session: Session, car_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """kWh used per drive, from rated-range consumed x the car's rated efficiency (Wh/km)."""
    excluded = _excluded_short_trip_ids(car_id)
    result = []
    for row in reversed(_energy_rows(session, car_id, limit)):
        if row.id in excluded:
            continue
        range_used_km = float(row.start_rated_range_km) - float(row.end_rated_range_km)
        kwh_used = max(0.0, range_used_km * row.efficiency / 1000)
        result.append({"date": row.start_date.isoformat(), "kwh_used": round(kwh_used, 2)})
    return result


def energy_efficiency_series(session: Session, car_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Actual Wh/mi for each drive (vs. the car's nominal rated efficiency)."""
    excluded = _excluded_short_trip_ids(car_id)
    result = []
    for row in reversed(_energy_rows(session, car_id, limit)):
        if row.id in excluded:
            continue
        range_used_km = float(row.start_rated_range_km) - float(row.end_rated_range_km)
        kwh_used = max(0.0, range_used_km * row.efficiency / 1000)
        wh_per_mi = (kwh_used * 1000) / (row.distance * _KM_TO_MI)
        result.append({"date": row.start_date.isoformat(), "wh_per_mi": round(wh_per_mi, 1)})
    return result


# --- Charging (TeslaMate DB) --------------------------------------------------


def _charging_rows(session: Session, car_id: int, limit: int) -> list[Any]:
    return session.execute(
        text(
            """
            SELECT start_date, charge_energy_added, cost
            FROM charging_processes
            WHERE car_id = :car_id AND end_date IS NOT NULL
            ORDER BY start_date DESC
            LIMIT :limit
            """
        ),
        {"car_id": car_id, "limit": limit},
    ).all()


def charging_energy_series(session: Session, car_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """kWh added per charging session."""
    return [
        {
            "date": row.start_date.isoformat(),
            "kwh_added": float(row.charge_energy_added) if row.charge_energy_added is not None else None,
        }
        for row in reversed(_charging_rows(session, car_id, limit))
    ]


def charging_cost_series(session: Session, car_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Cost per charging session, where TeslaMate has pricing configured to track it."""
    return [
        {"date": row.start_date.isoformat(), "cost": float(row.cost) if row.cost is not None else None}
        for row in reversed(_charging_rows(session, car_id, limit))
    ]


# --- Battery (TeslaMateApi, live) ---------------------------------------------


async def battery_health(client: TeslaMateApiClient) -> dict[str, Any] | None:
    """Current battery health %, queried live from Tesla's API via TeslaMateApi."""
    try:
        payload = await client.get_battery_health()
    except httpx.HTTPError:
        return None
    health = payload.get("battery_health") or {}
    pct = health.get("battery_health_percentage")
    if not pct:
        return None
    return {"battery_health_pct": pct}


# --- Full export (all history, combined) --------------------------------------

_EXPORT_LIMIT = 1_000_000  # a full-history export, not a chart window — effectively unbounded


def _drive_comparisons_by_id(session: Session, car_id: int) -> dict[int, dict[str, Any]]:
    rows = session.execute(
        select(
            DriveRouteComparison.drive_id,
            DriveRouteComparison.drive_start_at,
            DriveRouteComparison.odometer_delta,
            DriveRouteComparison.osrm_route_distance,
            DriveRouteComparison.gps_trace_distance,
        ).where(DriveRouteComparison.car_id == car_id, _not_short_trip())
    ).all()
    return {
        row.drive_id: {
            "date": row.drive_start_at.isoformat(),
            "osrm_drift_pct": _drift_pct(row.odometer_delta, row.osrm_route_distance),
            "haversine_drift_pct": _drift_pct(row.odometer_delta, row.gps_trace_distance),
            "odometer_mi": _mi(row.odometer_delta),
            "osrm_mi": _mi(row.osrm_route_distance),
            "gps_mi": _mi(row.gps_trace_distance),
        }
        for row in rows
    }


def _drive_energy_by_id(session: Session, car_id: int) -> dict[int, dict[str, Any]]:
    excluded = _excluded_short_trip_ids(car_id)
    result: dict[int, dict[str, Any]] = {}
    for row in _energy_rows(session, car_id, limit=_EXPORT_LIMIT):
        if row.id in excluded:
            continue
        range_used_km = float(row.start_rated_range_km) - float(row.end_rated_range_km)
        kwh_used = max(0.0, range_used_km * row.efficiency / 1000)
        result[row.id] = {
            "date": row.start_date.isoformat(),
            "kwh_used": round(kwh_used, 2),
            "wh_per_mi": round((kwh_used * 1000) / (row.distance * _KM_TO_MI), 1),
        }
    return result


def drive_export_rows(teslog_session: Session, tm_session: Session, car_id: int) -> list[dict[str, Any]]:
    """One row per drive — route-comparison and energy metrics merged by drive id.

    The two halves live in different databases (no SQL join possible), but both are keyed off
    the same underlying TeslaMate drive, so merging by drive id — rather than matching the two
    sides' date strings — stays exact even when one side is missing a drive the other has.
    """
    comparisons = _drive_comparisons_by_id(teslog_session, car_id)
    energy = _drive_energy_by_id(tm_session, car_id)
    return [
        {"type": "drive", **comparisons.get(drive_id, {}), **energy.get(drive_id, {})}
        for drive_id in comparisons.keys() | energy.keys()
    ]


def charge_export_rows(session: Session, car_id: int) -> list[dict[str, Any]]:
    """One row per charging session — a separate event from a drive, its own timestamps."""
    return [
        {
            "type": "charge",
            "date": row.start_date.isoformat(),
            "kwh_added": float(row.charge_energy_added) if row.charge_energy_added is not None else None,
            "cost": float(row.cost) if row.cost is not None else None,
        }
        for row in _charging_rows(session, car_id, limit=_EXPORT_LIMIT)
    ]


async def export_rows(
    teslog_session: Session, tm_session: Session, car_id: int, client: TeslaMateApiClient
) -> list[dict[str, Any]]:
    """Every dashboard metric's full history, combined into one row-per-drive/row-per-charge log."""
    rows = drive_export_rows(teslog_session, tm_session, car_id)
    rows += charge_export_rows(tm_session, car_id)

    health = await battery_health(client)
    if health:
        rows.append(
            {
                "type": "battery",
                "date": datetime.now(UTC).isoformat(),
                "battery_health_pct": health["battery_health_pct"],
            }
        )

    return sorted(rows, key=lambda row: row["date"])
