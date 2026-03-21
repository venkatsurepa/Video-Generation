from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.router import api_router
from src.config import get_settings
from src.db.connection import create_pool
from src.utils.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
    """Initialize and tear down application resources."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.is_production)

    pool = await create_pool(settings.database.db_url)
    try:
        yield {"db_pool": pool}
    finally:
        await pool.close()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="CrimeMill API",
        version=_get_version(),
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )

    if settings.is_production:
        origins: list[str] = []
    else:
        origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    return app


def _get_version() -> str:
    try:
        return version("crimemill")
    except Exception:
        return "0.1.0"


app = create_app()
