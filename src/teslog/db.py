from collections.abc import Generator
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from teslog.config import get_settings


class Base(DeclarativeBase):
    pass


class DriveRouteComparison(Base):
    """Derived metric: OSRM driving distance vs Tesla odometer delta."""

    __tablename__ = "drive_route_comparisons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    drive_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    drive_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    drive_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_address: Mapped[str | None] = mapped_column(Text)
    end_address: Mapped[str | None] = mapped_column(Text)
    odometer_start: Mapped[float | None] = mapped_column(Float)
    odometer_end: Mapped[float | None] = mapped_column(Float)
    odometer_delta: Mapped[float | None] = mapped_column(Float)
    teslamate_distance: Mapped[float | None] = mapped_column(Float)
    osrm_route_distance: Mapped[float | None] = mapped_column(Float)
    gps_trace_distance: Mapped[float | None] = mapped_column(Float)
    drift_pct: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(8), default="km")
    status: Mapped[str] = mapped_column(String(32), default="complete")
    error_message: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


_engines: dict[str, object] = {}
_sessionmakers: dict[str, sessionmaker[Session]] = {}


def _get_engine(url: str):
    if url not in _engines:
        _engines[url] = create_engine(url, pool_pre_ping=True)
    return _engines[url]


def get_teslog_sessionmaker() -> sessionmaker[Session]:
    settings = get_settings()
    url = settings.teslog_db_url
    if url not in _sessionmakers:
        _sessionmakers[url] = sessionmaker(
            bind=_get_engine(url), autoflush=False, autocommit=False
        )
    return _sessionmakers[url]


def get_tm_sessionmaker() -> sessionmaker[Session]:
    settings = get_settings()
    url = settings.tm_db_url
    if url not in _sessionmakers:
        _sessionmakers[url] = sessionmaker(
            bind=_get_engine(url), autoflush=False, autocommit=False
        )
    return _sessionmakers[url]


def get_teslog_db() -> Generator[Session, None, None]:
    session = get_teslog_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def init_teslog_db() -> None:
    engine = _get_engine(get_settings().teslog_db_url)
    Base.metadata.create_all(bind=engine)
