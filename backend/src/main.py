from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from importlib.metadata import version
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.errors import APIError, api_error_handler, http_error_handler, validation_error_handler
from src.api.middleware import RequestIDMiddleware
from src.api.rate_limit import limiter
from src.api.router import api_router
from src.config import get_settings
from src.db.connection import create_pool
from src.pipeline.worker import create_worker
from src.utils.logging import setup_logging

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def _discovery_cron(settings: object) -> None:
    """Optional periodic topic discovery loop (every 6 hours).

    Gated behind ``ENABLE_DISCOVERY_CRON=true`` so it never runs by default.
    Calls ``DiscoveryOrchestrator.run_all(score=False)`` — scoring is expensive
    and only runs on demand via CLI/API.
    """
    log = structlog.get_logger()
    interval_seconds = 6 * 60 * 60  # 6 hours
    try:
        from supabase import create_client

        from src.services.discovery import DiscoveryOrchestrator

        supabase = create_client(
            settings.database.url, settings.database.service_role_key,  # type: ignore[attr-defined]
        )
        orchestrator = DiscoveryOrchestrator(supabase, settings)
    except Exception as exc:
        await log.aerror("discovery_cron_init_failed", error=str(exc))
        return

    while True:
        try:
            result = await orchestrator.run_all(score=False, triggered_by="cron")
            await log.ainfo(
                "discovery_cron_run",
                candidates=result.get("total_candidates", 0),
                saved=result.get("total_saved", 0),
                errors=len(result.get("errors", [])),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await log.aerror("discovery_cron_failed", error=str(exc))
        await asyncio.sleep(interval_seconds)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
    """Initialize and tear down application resources."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.is_production)

    pool = await create_pool(settings.database.db_url)

    # Start the pipeline worker as a background task
    worker = create_worker(settings, pool)
    worker_task = asyncio.create_task(worker.start())

    # Optional periodic discovery loop — opt-in via ENABLE_DISCOVERY_CRON.
    discovery_task: asyncio.Task[None] | None = None
    import os

    if os.environ.get("ENABLE_DISCOVERY_CRON", "").lower() in {"1", "true", "yes"}:
        discovery_task = asyncio.create_task(_discovery_cron(settings))

    # Expose worker on app.state so health check can inspect it
    app.state.worker = worker

    try:
        yield {"db_pool": pool, "worker": worker}
    finally:
        log = structlog.get_logger()
        await worker.stop()
        try:
            await asyncio.wait_for(worker_task, timeout=30.0)
            await log.ainfo("worker_drained_gracefully")
        except TimeoutError:
            await log.awarning("worker_drain_timeout_forcing_cancel")
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task
        if discovery_task is not None:
            discovery_task.cancel()
            with suppress(asyncio.CancelledError):
                await discovery_task
        await pool.close()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="CrimeMill API",
        description="Automated true-crime documentary pipeline — topic discovery, "
        "script generation, media assembly, YouTube publishing, and analytics.",
        version=_get_version(),
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
    )

    # --- Error handlers (structured JSON envelope) ---
    app.add_exception_handler(APIError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

    # --- Rate limiting ---
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # --- Middleware (order matters: first added = outermost) ---
    # CORS must be outermost so preflight requests get correct headers
    cors_origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Request ID is inner — runs after CORS
    app.add_middleware(RequestIDMiddleware)

    # --- Routes ---
    app.include_router(api_router)

    return app


def _get_version() -> str:
    try:
        return version("crimemill")
    except Exception:
        return "0.1.0"


app = create_app()
