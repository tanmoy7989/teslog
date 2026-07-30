import asyncio
import logging

from sqlalchemy import select

from teslog.clients.osrm import OSRMClient
from teslog.config import get_settings
from teslog.db import DriveRouteComparison, get_teslog_sessionmaker, get_tm_sessionmaker
from teslog.services.drives import get_completed_drives
from teslog.services.route_comparison import build_comparison

logger = logging.getLogger("teslog.sync")


async def run_sync_once() -> dict[str, int]:
    settings = get_settings()
    tm_sessionmaker = get_tm_sessionmaker()
    teslog_sessionmaker = get_teslog_sessionmaker()
    osrm_client = OSRMClient()

    with tm_sessionmaker() as tm_session, teslog_sessionmaker() as teslog_session:
        existing_ids = set(
            teslog_session.execute(
                select(DriveRouteComparison.drive_id).where(
                    DriveRouteComparison.car_id == settings.teslog_car_id
                )
            ).scalars()
        )
        drives = get_completed_drives(tm_session, settings.teslog_car_id)
        new_drives = [drive for drive in drives if drive.id not in existing_ids]

        created = 0
        for drive in new_drives:
            comparison = await build_comparison(tm_session, drive, osrm_client)
            teslog_session.add(comparison)
            created += 1
        teslog_session.commit()

    logger.info("Sync complete: checked %d drive(s), created %d new comparison(s)", len(drives), created)
    return {"checked": len(drives), "created": created}


async def sync_loop(interval_seconds: int) -> None:
    while True:
        try:
            await run_sync_once()
        except Exception:
            logger.exception("Sync run failed")
        await asyncio.sleep(interval_seconds)
