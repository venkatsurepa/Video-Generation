from __future__ import annotations

from typing import Any, Literal, cast

import structlog
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict

from src.config import get_settings
from src.dependencies import DbPoolDep

logger = structlog.get_logger()

router = APIRouter()


class DbPoolStats(BaseModel):
    pool_size: int
    pool_available: int
    requests_waiting: int


class WorkerStatus(BaseModel):
    running: bool
    active_tasks: int


class HealthResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "healthy",
                "environment": "production",
                "version": "0.1.0",
                "db": "connected",
                "db_pool": {"pool_size": 10, "pool_available": 8, "requests_waiting": 0},
                "worker": {"running": True, "active_tasks": 2},
                "queue_depth": 5,
                "r2": "reachable",
            }
        }
    )

    status: Literal["healthy", "degraded", "unhealthy"]
    environment: str
    version: str
    db: Literal["connected", "disconnected"]
    db_pool: DbPoolStats | None = None
    worker: WorkerStatus | None = None
    queue_depth: int | None = None
    r2: Literal["reachable", "unreachable", "unconfigured"] | None = None


@router.get("/health", response_model=HealthResponse)
async def health_check(
    request: Request,
    pool: DbPoolDep,
    response: Response,
) -> HealthResponse:
    """Comprehensive health check — DB, pool stats, worker, queue, R2."""
    settings = get_settings()
    db_status: Literal["connected", "disconnected"] = "disconnected"
    db_pool_stats: DbPoolStats | None = None
    worker_info: WorkerStatus | None = None
    queue_depth: int | None = None
    r2_status: Literal["reachable", "unreachable", "unconfigured"] | None = None
    issues: list[str] = []

    # --- DB connectivity + pool stats ---
    try:
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        db_status = "connected"

        pool_stats = pool.get_stats()
        db_pool_stats = DbPoolStats(
            pool_size=pool_stats.get("pool_size", 0),
            pool_available=pool_stats.get("pool_available", 0),
            requests_waiting=pool_stats.get("requests_waiting", 0),
        )
    except Exception:
        issues.append("db")

    # --- Queue depth ---
    if db_status == "connected":
        try:
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT COUNT(*) AS n FROM pipeline_jobs WHERE status = 'pending'"
                )
                row = cast("dict[str, Any]", await cur.fetchone())
                queue_depth = row["n"] if row else 0
        except Exception:
            pass  # table may not exist yet

    # --- Worker status ---
    app_state = request.app.state
    worker = getattr(app_state, "worker", None)
    if worker is not None:
        worker_info = WorkerStatus(
            running=getattr(worker, "_running", False),
            active_tasks=len(getattr(worker, "_tasks", set())),
        )
        if not worker_info.running:
            issues.append("worker")

    # --- R2 connectivity (HeadBucket via worker's authenticated client) ---
    if worker is not None and getattr(worker, "_r2", None) is not None:
        try:
            r2_health = await worker._r2.health_check(settings.storage.bucket_name)
            r2_status = "reachable" if r2_health["healthy"] else "unreachable"
            if not r2_health["healthy"]:
                issues.append("r2")
        except Exception:
            r2_status = "unreachable"
            issues.append("r2")
    else:
        r2_status = "unconfigured"

    # --- Overall status ---
    if "db" in issues:
        overall: Literal["healthy", "degraded", "unhealthy"] = "unhealthy"
        response.status_code = 503
    elif issues:
        overall = "degraded"
    else:
        overall = "healthy"

    return HealthResponse(
        status=overall,
        environment=settings.environment,
        version="0.1.0",
        db=db_status,
        db_pool=db_pool_stats,
        worker=worker_info,
        queue_depth=queue_depth,
        r2=r2_status,
    )
