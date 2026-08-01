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
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from teslog.clients import TeslaMateApiClient
from teslog.db import DriveRouteComparison

# --- Distance (Teslog DB) ----------------------------------------------------


def drift_pct_series(session: Session, car_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Odometer drift %: (odometer_delta - osrm_route_distance) / osrm_route_distance * 100."""
    rows = session.execute(
        select(DriveRouteComparison.drive_start_at, DriveRouteComparison.drift_pct)
        .where(DriveRouteComparison.car_id == car_id, DriveRouteComparison.drift_pct.is_not(None))
        .order_by(DriveRouteComparison.drive_start_at)
        .limit(limit)
    ).all()
    return [{"date": row.drive_start_at.isoformat(), "drift_pct": round(row.drift_pct, 2)} for row in rows]


def distance_comparison_series(session: Session, car_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Odometer delta vs OSRM route distance vs GPS trace distance, per drive."""
    rows = session.execute(
        select(
            DriveRouteComparison.drive_start_at,
            DriveRouteComparison.odometer_delta,
            DriveRouteComparison.osrm_route_distance,
            DriveRouteComparison.gps_trace_distance,
        )
        .where(DriveRouteComparison.car_id == car_id)
        .order_by(DriveRouteComparison.drive_start_at)
        .limit(limit)
    ).all()
    return [
        {
            "date": row.drive_start_at.isoformat(),
            "odometer_km": row.odometer_delta,
            "osrm_km": row.osrm_route_distance,
            "gps_km": row.gps_trace_distance,
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
    result = []
    for row in reversed(_energy_rows(session, car_id, limit)):
        range_used_km = float(row.start_rated_range_km) - float(row.end_rated_range_km)
        kwh_used = max(0.0, range_used_km * row.efficiency / 1000)
        result.append({"date": row.start_date.isoformat(), "kwh_used": round(kwh_used, 2)})
    return result


def energy_efficiency_series(session: Session, car_id: int, limit: int = 200) -> list[dict[str, Any]]:
    """Actual Wh/km for each drive (vs. the car's nominal rated efficiency)."""
    result = []
    for row in reversed(_energy_rows(session, car_id, limit)):
        range_used_km = float(row.start_rated_range_km) - float(row.end_rated_range_km)
        kwh_used = max(0.0, range_used_km * row.efficiency / 1000)
        wh_per_km = (kwh_used * 1000) / row.distance
        result.append({"date": row.start_date.isoformat(), "wh_per_km": round(wh_per_km, 1)})
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
            DriveRouteComparison.drift_pct,
            DriveRouteComparison.odometer_delta,
            DriveRouteComparison.osrm_route_distance,
            DriveRouteComparison.gps_trace_distance,
        ).where(DriveRouteComparison.car_id == car_id)
    ).all()
    return {
        row.drive_id: {
            "date": row.drive_start_at.isoformat(),
            "drift_pct": round(row.drift_pct, 2) if row.drift_pct is not None else None,
            "odometer_km": row.odometer_delta,
            "osrm_km": row.osrm_route_distance,
            "gps_km": row.gps_trace_distance,
        }
        for row in rows
    }


def _drive_energy_by_id(session: Session, car_id: int) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in _energy_rows(session, car_id, limit=_EXPORT_LIMIT):
        range_used_km = float(row.start_rated_range_km) - float(row.end_rated_range_km)
        kwh_used = max(0.0, range_used_km * row.efficiency / 1000)
        result[row.id] = {
            "date": row.start_date.isoformat(),
            "kwh_used": round(kwh_used, 2),
            "wh_per_km": round((kwh_used * 1000) / row.distance, 1),
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
