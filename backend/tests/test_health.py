from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_expected_shape(client: AsyncClient) -> None:
    response = await client.get("/health")
    # Accept both 200 (db connected) and 503 (db unreachable in test env)
    assert response.status_code in (200, 503)
    data = response.json()
    assert "status" in data
    assert data["status"] in ("healthy", "unhealthy")
    assert "environment" in data
    assert "version" in data
    assert "db" in data
    assert data["db"] in ("connected", "disconnected")
