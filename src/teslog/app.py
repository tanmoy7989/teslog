import asyncio
import contextlib
import logging
import pathlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from teslog.config import get_settings
from teslog.db import init_teslog_db
from teslog.routes import public_router, router
from teslog.services.sync import sync_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("teslog")

STATIC_DIR = pathlib.Path(__file__).resolve().parent / "dashboard" / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_teslog_db()
    settings = get_settings()
    task = asyncio.create_task(sync_loop(settings.teslog_sync_interval_seconds))
    logger.info("Teslog started; syncing every %ss", settings.teslog_sync_interval_seconds)
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def create_app() -> FastAPI:
    app = FastAPI(title="Teslog", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(public_router)
    app.include_router(router)
    return app


app = create_app()
