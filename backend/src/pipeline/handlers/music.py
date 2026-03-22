"""Music selection handler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    import uuid

    from src.pipeline.worker import PipelineWorker

logger = structlog.get_logger()


async def handle_music_selection(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Select and download background music."""
    # Budget degradation: skip music entirely if instructed
    if payload.get("_skip_music"):
        await logger.ainfo(
            "music_skipped_budget",
            video_id=str(video_id),
        )
        return {
            "track_name": "",
            "music_url": "",
            "duration_seconds": 0,
            "skipped": True,
        }

    from src.services.music_selector import MusicSelector

    assert worker._http is not None

    video = await worker._get_video_info(video_id)
    channel_id = video["channel_id"]

    gen = MusicSelector(worker._settings, worker._http)
    # Extract mood from script payload; use script duration since
    # music_selection runs in parallel with voiceover (not after it).
    script_data = payload.get("script_generation", {})
    mood = str(script_data.get("mood", "suspenseful_investigation"))
    duration = float(script_data.get("duration_seconds", 300))

    result: Any = await worker._circuits["fal_ai"].call(
        gen.select_track,
        mood=mood,
        duration_seconds=duration,
    )

    # Upload the selected track to R2 so audio_processing can download it
    music_r2_key = await worker._upload_to_r2(
        channel_id,
        video_id,
        "background_music.wav",
        result.file_path,
        "audio/wav",
    )

    return {
        "track_name": result.track.title,
        "music_r2_key": music_r2_key,
        "duration_seconds": result.track.duration_seconds,
        "cost_usd": str(result.cost_usd),
    }
