"""Voiceover generation handler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from src.utils.cost_tracker import track_cost

if TYPE_CHECKING:
    import uuid

    from psycopg import AsyncConnection

    from src.pipeline.worker import PipelineWorker


async def handle_voiceover_generation(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate TTS voiceover from the script."""
    from src.services.voiceover_generator import VoiceoverGenerator

    assert worker._http is not None

    video = await worker._get_video_info(video_id)
    channel_id = video["channel_id"]

    # Get script text from upstream result
    script_data = payload.get("script_generation", {})
    script_text = script_data.get("script_text", "")
    if not script_text:
        raise ValueError("No script text in payload")

    gen = VoiceoverGenerator(worker._settings, worker._http)
    voice_id = script_data.get("voice_id", "default")

    result: Any = await worker._circuits["fish_audio"].call(
        gen.generate_voiceover,
        script_text,
        voice_id,
    )

    # Upload voiceover to R2
    r2_key = await worker._upload_to_r2(
        channel_id,
        video_id,
        "voiceover.wav",
        result.file_path,
        "audio/wav",
    )

    async with worker._pool.connection() as conn:
        await track_cost(
            cast("AsyncConnection[dict[str, object]]", conn),
            video_id,
            "voiceover_generation",
            "fish_audio",
            "speech-01-turbo",
            input_units=result.character_count,
            output_units=0,
            cost_usd=result.cost_usd,
            latency_ms=0,
        )
        await conn.commit()

    return {
        "voiceover_r2_key": r2_key,
        "duration_seconds": result.duration_seconds,
        "character_count": result.character_count,
        "cost_usd": str(result.cost_usd),
    }
