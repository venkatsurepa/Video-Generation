from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.health import router
from src.dependencies import get_db_pool

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def _noop_lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
    yield {}


def _mock_pool_connected() -> MagicMock:
    """Return a mock pool whose connection context manager succeeds."""
    pool = MagicMock()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool.connection.return_value = cm
    return pool


@pytest.mark.asyncio
async def test_health_returns_expected_shape() -> None:
    app = FastAPI(lifespan=_noop_lifespan)
    app.include_router(router)
    app.dependency_overrides[get_db_pool] = _mock_pool_connected

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/health")

    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert data["status"] in ("healthy", "unhealthy")
    assert "environment" in data
    assert "version" in data
    assert "db" in data
    assert data["db"] in ("connected", "disconnected")
