"""Image generation and processing handlers."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog

from src.pipeline.handlers._helpers import _TMP_ROOT
from src.utils.cost_tracker import track_cost

if TYPE_CHECKING:
    import uuid

    from psycopg import AsyncConnection

    from src.pipeline.worker import PipelineWorker

logger = structlog.get_logger()


async def handle_image_generation(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate scene images via fal.ai."""
    from src.models.image import ImagePrompt
    from src.services.image_generator import ImageGenerator

    assert worker._http is not None

    video = await worker._get_video_info(video_id)
    channel_id = video["channel_id"]

    script_data = payload.get("script_generation", {})
    raw_prompts = script_data.get("image_prompts", [])
    prompts = [ImagePrompt.model_validate(p) for p in raw_prompts]

    if not prompts:
        raise ValueError("No image prompts in payload")

    # Budget degradation: cap image count if instructed
    max_images = payload.get("_max_images")
    if max_images is not None and len(prompts) > max_images:
        await logger.ainfo(
            "image_count_degraded",
            original=len(prompts),
            capped=max_images,
            video_id=str(video_id),
        )
        prompts = prompts[:max_images]

    gen = ImageGenerator(worker._settings, worker._http)
    results: Any = await worker._circuits["fal_ai"].call(gen.generate_batch, prompts)

    # Upload each image to R2
    image_keys: list[dict[str, Any]] = []
    total_cost = Decimal("0")
    for img_result in results:
        scene_num = img_result.local_path.split("_")[-1].split(".")[0]
        filename = f"scene_{scene_num}_raw.jpg"
        r2_key = await worker._upload_to_r2(
            channel_id,
            video_id,
            filename,
            img_result.local_path,
            "image/jpeg",
        )
        image_keys.append(
            {
                "r2_key": r2_key,
                "local_path": img_result.local_path,
                "prompt": img_result.prompt,
                "model": img_result.model,
            }
        )
        total_cost += img_result.cost.cost_usd

    async with worker._pool.connection() as conn:
        await track_cost(
            cast("AsyncConnection[dict[str, object]]", conn),
            video_id,
            "image_generation",
            "fal.ai",
            "flux",
            input_units=len(results),
            output_units=0,
            cost_usd=total_cost,
            latency_ms=0,
        )
        await conn.commit()

    return {
        "image_count": len(results),
        "image_keys": image_keys,
        "cost_usd": str(total_cost),
    }


async def handle_image_processing(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Apply documentary post-processing to generated images."""
    from src.services.image_processor import ImageProcessor

    video = await worker._get_video_info(video_id)
    channel_id = video["channel_id"]

    img_data = payload.get("image_generation", {})
    image_keys = img_data.get("image_keys", [])

    if not image_keys:
        raise ValueError("No image keys in payload")

    # Download raw images from R2
    local_paths: list[str] = []
    for img in image_keys:
        r2_key = img["r2_key"]
        local_path = str(_TMP_ROOT / f"{video_id}_{Path(r2_key).name}")
        worker._download_from_r2(r2_key, local_path)
        local_paths.append(local_path)

    proc = ImageProcessor(worker._settings)
    output_dir = str(_TMP_ROOT / f"{video_id}_processed")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    processed = await proc.process_batch(local_paths, output_dir=output_dir)

    # Upload processed images to R2
    processed_keys: list[str] = []
    for i, proc_path in enumerate(processed):
        filename = f"scene_{i:03d}_processed.jpg"
        r2_key = await worker._upload_to_r2(
            channel_id,
            video_id,
            filename,
            proc_path,
            "image/jpeg",
        )
        processed_keys.append(r2_key)

    return {
        "processed_image_count": len(processed_keys),
        "processed_image_keys": processed_keys,
    }
