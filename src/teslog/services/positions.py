import math
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

EARTH_RADIUS_KM = 6371.0088


@dataclass
class Position:
    date: datetime
    latitude: float
    longitude: float
    odometer: float | None


def get_drive_positions(session: Session, drive_id: int) -> list[Position]:
    rows = session.execute(
        text(
            """
            SELECT date, latitude, longitude, odometer
            FROM positions
            WHERE drive_id = :drive_id
            ORDER BY date ASC
            """
        ),
        {"drive_id": drive_id},
    ).all()
    return [
        Position(date=row.date, latitude=row.latitude, longitude=row.longitude, odometer=row.odometer)
        for row in rows
    ]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def gps_trace_distance_km(positions: list[Position]) -> float | None:
    if len(positions) < 2:
        return None
    return sum(
        haversine_km(a.latitude, a.longitude, b.latitude, b.longitude)
        for a, b in zip(positions, positions[1:])
    )
