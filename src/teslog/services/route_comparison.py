import logging

from sqlalchemy.orm import Session

from teslog.clients import OSRMClient, OSRMError
from teslog.db import DriveRouteComparison
from teslog.services.drives import DriveRecord
from teslog.services.positions import get_drive_positions, gps_trace_distance_km

logger = logging.getLogger("teslog.sync")


async def build_comparison(
    tm_session: Session, drive: DriveRecord, osrm_client: OSRMClient
) -> DriveRouteComparison:
    positions = get_drive_positions(tm_session, drive.id)
    gps_distance = gps_trace_distance_km(positions)

    odometer_start = drive.start_km if drive.start_km is not None else (
        positions[0].odometer if positions else None
    )
    odometer_end = drive.end_km if drive.end_km is not None else (
        positions[-1].odometer if positions else None
    )
    odometer_delta = (
        odometer_end - odometer_start
        if odometer_start is not None and odometer_end is not None
        else None
    )

    osrm_distance = None
    error_message = None
    if not positions:
        error_message = "No GPS positions recorded for this drive"
    elif osrm_client.enabled:
        start, end = positions[0], positions[-1]
        try:
            osrm_distance = await osrm_client.route_distance_km(
                start.latitude, start.longitude, end.latitude, end.longitude
            )
        except OSRMError as exc:
            error_message = str(exc)
            logger.warning("OSRM route lookup failed for drive %s: %s", drive.id, exc)
    else:
        error_message = "OSRM_BASE_URL is not configured"

    drift_pct = None
    if osrm_distance and odometer_delta is not None:
        drift_pct = (odometer_delta - osrm_distance) / osrm_distance * 100

    status = "complete" if osrm_distance is not None else "partial"

    return DriveRouteComparison(
        car_id=drive.car_id,
        drive_id=drive.id,
        drive_start_at=drive.start_date,
        drive_end_at=drive.end_date,
        start_address=drive.start_address,
        end_address=drive.end_address,
        odometer_start=odometer_start,
        odometer_end=odometer_end,
        odometer_delta=odometer_delta,
        teslamate_distance=drive.teslamate_distance,
        osrm_route_distance=osrm_distance,
        gps_trace_distance=gps_distance,
        drift_pct=drift_pct,
        unit="km",
        status=status,
        error_message=error_message,
    )
