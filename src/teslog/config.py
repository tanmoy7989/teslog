import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    return int(raw) if raw else default


def _env_bool(key: str) -> bool:
    return os.getenv(key, "").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    tm_db_host: str
    tm_db_port: int
    tm_db_user: str
    tm_db_pass: str
    tm_db_name: str
    teslog_db_host: str
    teslog_db_port: int
    teslog_db_user: str
    teslog_db_pass: str
    teslog_db_name: str
    teslamate_api_url: str
    osrm_base_url: str
    teslog_car_id: int
    teslog_host: str
    teslog_port: int
    tm_tz: str
    teslog_reload: bool
    teslog_sync_interval_seconds: int

    @property
    def tm_db_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.tm_db_user}:{self.tm_db_pass}"
            f"@{self.tm_db_host}:{self.tm_db_port}/{self.tm_db_name}"
        )

    @property
    def teslog_db_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.teslog_db_user}:{self.teslog_db_pass}"
            f"@{self.teslog_db_host}:{self.teslog_db_port}/{self.teslog_db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings(
        tm_db_host=_env("TM_DB_HOST", "database"),
        tm_db_port=_env_int("TM_DB_PORT", 5432),
        tm_db_user=_env("TM_DB_USER", "teslamate"),
        tm_db_pass=_env("TM_DB_PASS", ""),
        tm_db_name=_env("TM_DB_NAME", "teslamate"),
        teslog_db_host=_env("TESLOG_DB_HOST", "database"),
        teslog_db_port=_env_int("TESLOG_DB_PORT", 5432),
        teslog_db_user=_env("TESLOG_DB_USER", "teslog"),
        teslog_db_pass=_env("TESLOG_DB_PASS", ""),
        teslog_db_name=_env("TESLOG_DB_NAME", "teslog"),
        teslamate_api_url=_env("TESLAMATE_API_URL", "http://teslamateapi:8080"),
        osrm_base_url=_env("OSRM_BASE_URL", "https://router.project-osrm.org"),
        teslog_car_id=_env_int("TESLOG_CAR_ID", 1),
        teslog_host=_env("TESLOG_HOST", "0.0.0.0"),
        teslog_port=_env_int("TESLOG_PORT", 8080),
        tm_tz=_env("TM_TZ", "America/Los_Angeles"),
        teslog_reload=_env_bool("TESLOG_RELOAD"),
        teslog_sync_interval_seconds=_env_int("TESLOG_SYNC_INTERVAL_SECONDS", 900),
    )
