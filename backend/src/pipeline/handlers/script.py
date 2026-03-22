"""Script generation handler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import structlog

from src.pipeline.handlers._helpers import _TMP_ROOT
from src.utils.cost_tracker import track_cost

if TYPE_CHECKING:
    import uuid

    from psycopg import AsyncConnection

    from src.pipeline.worker import PipelineWorker

logger = structlog.get_logger()


async def handle_script_generation(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate script, scene breakdown, image prompts, titles, and description."""
    from src.models.script import (
        BrandSettings,
        ChannelSettings,
        TopicInput,
    )
    from src.services.script_generator import ScriptGenerator

    assert worker._http is not None

    video = await worker._get_video_info(video_id)
    channel_id = video["channel_id"]

    topic_data = video.get("topic") or {}
    topic = TopicInput(
        topic=topic_data.get("topic", payload.get("topic", "")),
        video_length_minutes=topic_data.get("video_length_minutes", 15),
        angle=topic_data.get("angle"),
        region=topic_data.get("region"),
        era=topic_data.get("era"),
    )
    channel_settings = ChannelSettings(
        channel_name=video.get("channel_name", ""),
        channel_id=channel_id,
    )

    gen = ScriptGenerator(worker._settings, worker._http)

    # 1. Generate the script
    script_output: Any = await worker._circuits["anthropic"].call(
        gen.generate_script,
        topic,
        channel_settings,
    )

    # 2. Scene breakdown
    breakdown = await gen.generate_scene_breakdown(
        script_output.script_text, topic.video_length_minutes
    )

    # 3. Image prompts
    brand = BrandSettings()
    image_prompts_result = await gen.generate_image_prompts(breakdown.scenes, brand)

    # 4. Titles
    summary = script_output.script_text[:500]
    titles = await gen.generate_titles(topic, summary)

    # Pick best title
    best_title = titles.variants[0].title if titles.variants else video.get("title", "")

    # 5. YouTube description (deterministic — no LLM call)
    from src.models.description import (
        AffiliateConfig,
        ChannelLinks,
        DescriptionInput,
    )
    from src.services.description_generator import DescriptionGenerator

    desc_gen = DescriptionGenerator(worker._settings)
    desc_input = DescriptionInput(
        video_id=video_id,
        title=best_title,
        case_summary=summary,
        scenes=breakdown.scenes,
        sources=[],
        affiliate_config=AffiliateConfig(),
        channel_links=ChannelLinks(),
        hashtags=topic_data.get("hashtags", []),
        related_book_title=topic_data.get("related_book_title"),
        related_book_asin=topic_data.get("related_book_asin"),
    )
    description_text = desc_gen.generate_description(desc_input)

    # Upload script JSON to R2
    script_data = {
        "script_text": script_output.script_text,
        "word_count": script_output.word_count,
        "estimated_duration_seconds": script_output.estimated_duration_seconds,
        "hook_type": script_output.hook_type.value,
        "scenes": [s.model_dump() for s in breakdown.scenes],
        "image_prompts": [p.model_dump() for p in image_prompts_result.prompts],
        "titles": [t.model_dump() for t in titles.variants],
        "description": description_text,
    }
    script_path = _TMP_ROOT / f"{video_id}_script.json"
    script_path.write_text(json.dumps(script_data), encoding="utf-8")
    await worker._upload_to_r2(
        channel_id,
        video_id,
        "script.json",
        str(script_path),
        "application/json",
    )

    # Track costs
    total_cost = (
        script_output.cost.cost_usd
        + breakdown.cost.cost_usd
        + image_prompts_result.cost.cost_usd
        + titles.cost.cost_usd
    )
    async with worker._pool.connection() as conn:
        await track_cost(
            cast("AsyncConnection[dict[str, object]]", conn),
            video_id,
            "script_generation",
            "anthropic",
            "claude",
            input_units=script_output.cost.input_tokens,
            output_units=script_output.cost.output_tokens,
            cost_usd=total_cost,
            latency_ms=0,
        )
        # Update video title, description, and word count
        from src.db.queries import UPDATE_VIDEO_FIELDS

        await conn.execute(
            UPDATE_VIDEO_FIELDS,
            {
                "video_id": video_id,
                "status": "script_generated",
                "title": best_title,
                "description": description_text,
                "script_word_count": script_output.word_count,
                "video_length_seconds": int(script_output.estimated_duration_seconds),
                "error_message": None,
            },
        )
        await conn.commit()

    return {
        "script_text": script_output.script_text,
        "word_count": script_output.word_count,
        "duration_seconds": script_output.estimated_duration_seconds,
        "hook_type": script_output.hook_type.value,
        "scene_count": len(breakdown.scenes),
        "image_prompt_count": len(image_prompts_result.prompts),
        "title": best_title,
        "description": description_text,
        "titles": [t.model_dump() for t in titles.variants],
        "scenes": [s.model_dump() for s in breakdown.scenes],
        "image_prompts": [p.model_dump() for p in image_prompts_result.prompts],
        "r2_script_key": worker._r2_key(channel_id, video_id, "script.json"),
        "cost_usd": str(total_cost),
    }
