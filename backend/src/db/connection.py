from __future__ import annotations

import time

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


def get_pool_stats(pool: AsyncConnectionPool) -> dict[str, object]:
    """Return connection pool statistics for monitoring."""
    raw = pool.get_stats()
    return {
        "pool_size": raw.get("pool_size", 0),
        "pool_available": raw.get("pool_available", 0),
        "pool_min": raw.get("pool_min", 0),
        "pool_max": raw.get("pool_max", 0),
        "requests_waiting": raw.get("requests_waiting", 0),
        "requests_num": raw.get("requests_num", 0),
        "requests_errors": raw.get("requests_errors", 0),
        "connections_lost": raw.get("connections_lost", 0),
    }


async def check_db_health(pool: AsyncConnectionPool) -> dict[str, object]:
    """Run a lightweight DB health check and return stats + latency."""
    t0 = time.monotonic()
    try:
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {
            "healthy": True,
            "latency_ms": latency_ms,
            "pool": get_pool_stats(pool),
            "error": "",
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {
            "healthy": False,
            "latency_ms": latency_ms,
            "pool": get_pool_stats(pool),
            "error": str(exc),
        }
