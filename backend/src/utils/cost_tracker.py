from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from src.db.queries import INSERT_COST

if TYPE_CHECKING:
    import uuid
    from decimal import Decimal

    from psycopg import AsyncConnection

logger = structlog.get_logger()


async def track_cost(
    db: AsyncConnection[dict[str, object]],
    video_id: uuid.UUID,
    stage: str,
    provider: str,
    model: str,
    input_units: int,
    output_units: int,
    cost_usd: Decimal,
    latency_ms: int,
) -> None:
    """Record a generation cost entry for auditing and cost tracking."""
    await db.execute(
        INSERT_COST,
        {
            "video_id": video_id,
            "stage": stage,
            "provider": provider,
            "model": model,
            "input_units": input_units,
            "output_units": output_units,
            "cost_usd": cost_usd,
            "latency_ms": latency_ms,
        },
    )
    await logger.ainfo(
        "cost_tracked",
        video_id=str(video_id),
        stage=stage,
        provider=provider,
        cost_usd=str(cost_usd),
    )
