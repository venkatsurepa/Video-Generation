"""Video assembly handler."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from src.pipeline.handlers._helpers import _TMP_ROOT

if TYPE_CHECKING:
    import uuid

    from src.pipeline.worker import PipelineWorker


async def handle_video_assembly(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the final video from all processed assets.

    Builds ``AssemblyInput`` from three upstream stage outputs:
    - ``audio_processing.audio_r2_key`` → audio_path
    - ``image_processing.processed_image_keys`` + ``script_generation.scenes`` → scenes
    - ``caption_generation.words_r2_key`` → caption_words (downloaded from R2)
    """
    from src.models.assembly import AssemblyInput, SceneForAssembly
    from src.models.caption import CaptionWord
    from src.services.video_assembler import VideoAssembler

    assert worker._http is not None

    # Gather upstream payloads
    script_data = payload.get("script_generation", {})
    audio_data = payload.get("audio_processing", {})
    image_data = payload.get("image_processing", {})
    caption_data = payload.get("caption_generation", {})

    async with worker._pool.connection() as conn:
        row = cast(
            "dict[str, Any] | None",
            await (
                await conn.execute(
                    "SELECT channel_id, title FROM videos WHERE id = %(id)s",
                    {"id": video_id},
                )
            ).fetchone(),
        )
    channel_id = row["channel_id"] if row else video_id
    title = row["title"] if row else ""

    # Build SceneForAssembly list from processed images + scene timings.
    # image_processing: {"processed_image_keys": ["ch/vid/scene_000_processed.jpg", ...]}
    # script_generation: {"scenes": [{scene_number, start_time_seconds, ...}, ...]}
    processed_keys = image_data.get("processed_image_keys", [])
    raw_scenes = script_data.get("scenes", [])
    scenes: list[SceneForAssembly] = []
    for i, r2_key in enumerate(processed_keys):
        scene_timing = raw_scenes[i] if i < len(raw_scenes) else {}
        scenes.append(
            SceneForAssembly(
                scene_number=scene_timing.get("scene_number", i + 1),
                image_storage_path=r2_key,
                start_seconds=float(scene_timing.get("start_time_seconds", 0)),
                end_seconds=float(scene_timing.get("end_time_seconds", 30)),
                narration_text=scene_timing.get("narration_text", ""),
            )
        )

    # Download caption words from R2 (stored as JSON by caption_generation)
    caption_words: list[CaptionWord] = []
    words_r2_key = caption_data.get("words_r2_key", "")
    if words_r2_key:
        words_local = str(_TMP_ROOT / f"{video_id}_caption_words.json")
        worker._download_from_r2(words_r2_key, words_local)
        raw_words = json.loads(Path(words_local).read_text(encoding="utf-8"))
        caption_words = [CaptionWord.model_validate(w) for w in raw_words]

    assembly_input = AssemblyInput(
        video_id=video_id,
        channel_id=channel_id,
        title=title,
        scenes=scenes,
        audio_path=audio_data.get("audio_r2_key", ""),
        music_path="",  # music is already mixed into final_audio.wav
        caption_words=caption_words,
        audio_duration_seconds=float(audio_data.get("duration_seconds", 300)),
    )

    gen = VideoAssembler(worker._settings, worker._http)
    result = await gen.render(assembly_input)

    return {
        "video_url": result.file_url,
        "video_r2_key": result.file_path,
        "duration_seconds": result.duration_seconds,
        "resolution": result.resolution,
        "file_size_bytes": result.file_size_bytes,
        "cost_usd": str(result.cost_usd),
    }
