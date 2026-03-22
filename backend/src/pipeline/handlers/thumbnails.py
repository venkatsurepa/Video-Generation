"""Thumbnail generation handler."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

from src.utils.cost_tracker import track_cost

if TYPE_CHECKING:
    import uuid

    from psycopg import AsyncConnection

    from src.pipeline.worker import PipelineWorker


async def handle_thumbnail_generation(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate a YouTube thumbnail."""
    from src.models.thumbnail import ThumbnailInput
    from src.services.image_generator import ImageGenerator
    from src.services.thumbnail_generator import ThumbnailGenerator

    assert worker._http is not None

    video = await worker._get_video_info(video_id)
    channel_id = video["channel_id"]

    script_data = payload.get("script_generation", {})
    title = script_data.get("title", video.get("title", ""))

    image_gen = ImageGenerator(worker._settings, worker._http)
    gen = ThumbnailGenerator(worker._settings, image_gen, worker._http)

    thumb_input = ThumbnailInput(
        video_id=video_id,
        title=title,
        topic=video.get("topic") or {},
    )
    result: Any = await worker._circuits["fal_ai"].call(gen.generate_thumbnail, thumb_input)

    # Upload thumbnail to R2
    r2_key = await worker._upload_to_r2(
        channel_id,
        video_id,
        "thumbnail.jpg",
        result.file_path,
        "image/jpeg",
    )

    async with worker._pool.connection() as conn:
        await track_cost(
            cast("AsyncConnection[dict[str, object]]", conn),
            video_id,
            "thumbnail_generation",
            "fal.ai",
            "flux-pro-new",
            input_units=1,
            output_units=0,
            cost_usd=Decimal(str(result.cost_usd)),
            latency_ms=0,
        )
        await conn.commit()

    return {
        "thumbnail_r2_key": r2_key,
        "archetype": result.archetype,
        "file_size_bytes": result.file_size_bytes,
        "cost_usd": str(result.cost_usd),
    }
