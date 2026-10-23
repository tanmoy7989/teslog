import csv
import io
import pathlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from teslog import metrics
from teslog.clients import TeslaMateApiClient
from teslog.config import get_settings
from teslog.db import get_teslog_sessionmaker, get_tm_sessionmaker
from teslog.services.sync import run_sync_once

TEMPLATES_DIR = pathlib.Path(__file__).resolve().parent / "dashboard" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

public_router = APIRouter()
router = APIRouter()


@public_router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    context = {
        "pre_tracking_odometer_mi": metrics.PRE_TRACKING_ODOMETER_MI,
        "pre_tracking_odometer_date": metrics.PRE_TRACKING_ODOMETER_DATE,
        "default_window_days": get_settings().teslog_chart_window_days,
    }
    return templates.TemplateResponse(request=request, name="index.html", context=context)


@router.post("/api/sync")
async def trigger_sync() -> dict[str, int]:
    return await run_sync_once()


# metric name -> (function, which DB it reads, CSV column order, whether it takes a chart window)
_SERIES: dict[str, tuple[Callable[..., list[dict[str, Any]]], str, list[str], bool]] = {
    "drift": (metrics.drift_pct_series, "teslog", ["date", "osrm_drift_pct", "haversine_drift_pct"], True),
    # Anchored to the start of tracking, so always all history — see metrics.cumulative_drift_series.
    "cumulative-drift": (metrics.cumulative_drift_series, "teslog", ["date", "cum_osrm_drift_pct", "cum_gps_drift_pct"], False),
    "distance": (metrics.distance_comparison_series, "teslog", ["date", "odometer_mi", "osrm_mi", "gps_mi"], True),
    "energy-used": (metrics.energy_used_series, "tm", ["date", "kwh_used"], True),
    "energy-efficiency": (metrics.energy_efficiency_series, "tm", ["date", "wh_per_mi"], True),
    "charging-energy": (metrics.charging_energy_series, "tm", ["date", "kwh_added"], True),
    "charging-cost": (metrics.charging_cost_series, "tm", ["date", "cost"], True),
}

# `?days=N` on a metric endpoint: only rows from the last N days. Omitted = all history.
_DaysQuery = Query(None, ge=1, description="Only include the last N days (omit for all history)")


def _fetch_series(name: str, days: int | None) -> list[dict[str, Any]]:
    fn, kind, _fields, windowed = _SERIES[name]
    settings = get_settings()
    with _session_for(kind) as session:
        if windowed and days is not None:
            return fn(session, settings.teslog_car_id, since=datetime.now(UTC) - timedelta(days=days))
        return fn(session, settings.teslog_car_id)


def _session_for(kind: str) -> Session:
    sessionmaker = get_teslog_sessionmaker() if kind == "teslog" else get_tm_sessionmaker()
    return sessionmaker()


@router.get("/api/metrics/battery-health")
async def get_battery_health() -> dict[str, Any]:
    client = TeslaMateApiClient()
    result = await metrics.battery_health(client)
    return result or {}


@router.get("/api/metrics/{name}.csv")
async def export_metric_csv(name: str, days: int | None = _DaysQuery) -> Response:
    if name not in _SERIES:
        return Response(status_code=404)
    fieldnames = _SERIES[name][2]
    rows = _fetch_series(name, days)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


_EXPORT_FIELDNAMES = [
    "type",
    "date",
    "osrm_drift_pct",
    "haversine_drift_pct",
    "odometer_mi",
    "osrm_mi",
    "gps_mi",
    "kwh_used",
    "wh_per_mi",
    "kwh_added",
    "cost",
    "battery_health_pct",
]


@router.get("/api/export/full.csv")
async def export_full_csv() -> Response:
    """Every dashboard metric's full history, combined into a single CSV (see metrics.export_rows)."""
    settings = get_settings()
    client = TeslaMateApiClient()
    with _session_for("teslog") as teslog_session, _session_for("tm") as tm_session:
        rows = await metrics.export_rows(teslog_session, tm_session, settings.teslog_car_id, client)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_EXPORT_FIELDNAMES, restval="")
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="teslog_export.csv"'},
    )


@router.get("/api/metrics/{name}")
async def get_metric_series(name: str, days: int | None = _DaysQuery) -> list[dict[str, Any]]:
    if name not in _SERIES:
        return []
    return _fetch_series(name, days)
