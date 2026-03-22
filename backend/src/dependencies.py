from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, cast

from fastapi import Depends, Request
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from src.config import Settings, get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from src.pipeline.worker import PipelineWorker


def get_db_pool(request: Request) -> AsyncConnectionPool:
    """Retrieve the connection pool from app lifespan state."""
    pool: AsyncConnectionPool = request.state.db_pool
    return pool


async def get_db(
    pool: Annotated[AsyncConnectionPool, Depends(get_db_pool)],
) -> AsyncIterator[AsyncConnection[dict[str, object]]]:
    """Check out a connection from the pool, auto-return on exit."""
    async with pool.connection() as conn:
        yield cast("AsyncConnection[dict[str, object]]", conn)


def get_worker(request: Request) -> PipelineWorker:
    """Retrieve the pipeline worker from app lifespan state."""
    return request.state.worker  # type: ignore[no-any-return]


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbPoolDep = Annotated[AsyncConnectionPool, Depends(get_db_pool)]
DbDep = Annotated[AsyncConnection[dict[str, object]], Depends(get_db)]
WorkerDep = Annotated["PipelineWorker", Depends(get_worker)]
