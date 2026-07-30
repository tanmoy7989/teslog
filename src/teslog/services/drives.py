from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class DriveRecord:
    id: int
    car_id: int
    start_date: datetime
    end_date: datetime | None
    start_km: float | None
    end_km: float | None
    teslamate_distance: float | None
    start_address: str | None
    end_address: str | None


def get_completed_drives(session: Session, car_id: int, limit: int = 200) -> list[DriveRecord]:
    """Completed drives for a car, read directly from TeslaMate's own database.

    TeslaMateApi doesn't expose raw GPS positions, and Teslog needs those for the GPS-trace
    comparison anyway, so drive metadata is read from the same source for consistency.
    """
    rows = session.execute(
        text(
            """
            SELECT d.id, d.car_id, d.start_date, d.end_date, d.start_km, d.end_km, d.distance,
                   sa.display_name AS start_address, ea.display_name AS end_address
            FROM drives d
            LEFT JOIN addresses sa ON sa.id = d.start_address_id
            LEFT JOIN addresses ea ON ea.id = d.end_address_id
            WHERE d.car_id = :car_id AND d.end_date IS NOT NULL
            ORDER BY d.start_date DESC
            LIMIT :limit
            """
        ),
        {"car_id": car_id, "limit": limit},
    ).all()
    return [
        DriveRecord(
            id=row.id,
            car_id=row.car_id,
            start_date=row.start_date,
            end_date=row.end_date,
            start_km=row.start_km,
            end_km=row.end_km,
            teslamate_distance=row.distance,
            start_address=row.start_address,
            end_address=row.end_address,
        )
        for row in rows
    ]
