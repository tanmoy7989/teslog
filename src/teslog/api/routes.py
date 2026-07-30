import csv
import io
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from teslog import metrics
from teslog.clients.teslamate_api import TeslaMateApiClient
from teslog.config import get_settings
from teslog.db import get_teslog_sessionmaker, get_tm_sessionmaker
from teslog.services.sync import run_sync_once
from teslog.templating import templates

public_router = APIRouter()
router = APIRouter()


@public_router.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html", context={})


@router.post("/api/sync")
async def trigger_sync() -> dict[str, int]:
    return await run_sync_once()


# metric name -> (function, which DB it reads, CSV column order)
_SERIES: dict[str, tuple[Callable[..., list[dict[str, Any]]], str, list[str]]] = {
    "drift": (metrics.drift_pct_series, "teslog", ["date", "drift_pct"]),
    "distance": (metrics.distance_comparison_series, "teslog", ["date", "odometer_km", "osrm_km", "gps_km"]),
    "energy-used": (metrics.energy_used_series, "tm", ["date", "kwh_used"]),
    "energy-efficiency": (metrics.energy_efficiency_series, "tm", ["date", "wh_per_km"]),
    "charging-energy": (metrics.charging_energy_series, "tm", ["date", "kwh_added"]),
    "charging-cost": (metrics.charging_cost_series, "tm", ["date", "cost"]),
}


def _session_for(kind: str) -> Session:
    sessionmaker = get_teslog_sessionmaker() if kind == "teslog" else get_tm_sessionmaker()
    return sessionmaker()


@router.get("/api/metrics/battery-health")
async def get_battery_health() -> dict[str, Any]:
    client = TeslaMateApiClient()
    result = await metrics.battery_health(client)
    return result or {}


@router.get("/api/metrics/{name}.csv")
async def export_metric_csv(name: str) -> Response:
    if name not in _SERIES:
        return Response(status_code=404)
    fn, kind, fieldnames = _SERIES[name]
    settings = get_settings()
    with _session_for(kind) as session:
        rows = fn(session, settings.teslog_car_id)

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
    )


@router.get("/api/metrics/{name}")
async def get_metric_series(name: str) -> list[dict[str, Any]]:
    if name not in _SERIES:
        return []
    fn, kind, _fields = _SERIES[name]
    settings = get_settings()
    with _session_for(kind) as session:
        return fn(session, settings.teslog_car_id)
