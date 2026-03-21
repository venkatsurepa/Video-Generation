from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from src.config import get_settings
from src.dependencies import DbPoolDep

router = APIRouter()


class HealthResponse(BaseModel):
    status: Literal["healthy", "unhealthy"]
    environment: str
    version: str
    db: Literal["connected", "disconnected"]


@router.get("/health", response_model=HealthResponse)
async def health_check(pool: DbPoolDep, response: Response) -> HealthResponse:
    """Check API and database health."""
    settings = get_settings()
    db_status: Literal["connected", "disconnected"] = "disconnected"

    try:
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        db_status = "connected"
    except Exception:
        response.status_code = 503

    status: Literal["healthy", "unhealthy"] = (
        "healthy" if db_status == "connected" else "unhealthy"
    )

    return HealthResponse(
        status=status,
        environment=settings.environment,
        version="0.1.0",
        db=db_status,
    )
