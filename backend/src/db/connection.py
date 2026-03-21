from __future__ import annotations

import structlog
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


async def create_pool(
    dsn: str,
    min_size: int = 2,
    max_size: int = 10,
) -> AsyncConnectionPool:
    """Create and open an async connection pool with dict row factory.

    Uses Supabase direct connection (session mode, port 5432).
    """
    pool = AsyncConnectionPool(
        conninfo=dsn,
        min_size=min_size,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
        check=AsyncConnectionPool.check_connection,
        open=False,
    )
    await pool.open()
    await logger.ainfo("database_pool_opened", min_size=min_size, max_size=max_size)
    return pool
