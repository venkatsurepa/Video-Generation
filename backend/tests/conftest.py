from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.db.connection import create_pool
from src.main import create_app

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
async def db_pool(settings: Settings) -> AsyncIterator[AsyncConnectionPool]:
    pool = await create_pool(settings.database.db_url, min_size=1, max_size=2)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
