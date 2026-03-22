"""Caption generation handler."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from src.pipeline.handlers._helpers import _TMP_ROOT
from src.utils.cost_tracker import track_cost

if TYPE_CHECKING:
    import uuid

    from psycopg import AsyncConnection

    from src.pipeline.worker import PipelineWorker


async def handle_caption_generation(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate captions (SRT + Remotion word data) from voiceover."""
    from src.services.caption_generator import CaptionGenerator

    assert worker._http is not None

    video = await worker._get_video_info(video_id)
    channel_id = video["channel_id"]

    vo_data = payload.get("voiceover_generation", {})
    vo_r2_key = vo_data.get("voiceover_r2_key", "")

    # Download voiceover
    vo_local = str(_TMP_ROOT / f"{video_id}_vo_for_captions.wav")
    worker._download_from_r2(vo_r2_key, vo_local)

    gen = CaptionGenerator(worker._settings, worker._http)
    result: Any = await worker._circuits["groq"].call(gen.generate_srt, vo_local)

    # Upload SRT to R2
    srt_key = await worker._upload_to_r2(
        channel_id,
        video_id,
        "captions.srt",
        result.srt_file_path,
        "text/srt",
    )

    # Upload word data as JSON
    words_data = [w.model_dump() for w in result.caption_words]
    words_path = _TMP_ROOT / f"{video_id}_caption_words.json"
    words_path.write_text(json.dumps(words_data), encoding="utf-8")
    words_key = await worker._upload_to_r2(
        channel_id,
        video_id,
        "caption_words.json",
        str(words_path),
        "application/json",
    )

    async with worker._pool.connection() as conn:
        await track_cost(
            cast("AsyncConnection[dict[str, object]]", conn),
            video_id,
            "caption_generation",
            "groq",
            "whisper-large-v3-turbo",
            input_units=int(result.duration_seconds),
            output_units=result.total_words,
            cost_usd=result.cost_usd,
            latency_ms=0,
        )
        await conn.commit()

    return {
        "srt_r2_key": srt_key,
        "words_r2_key": words_key,
        "total_words": result.total_words,
        "duration_seconds": result.duration_seconds,
        "cost_usd": str(result.cost_usd),
    }
