"""Audio processing handler."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.pipeline.handlers._helpers import _TMP_ROOT

if TYPE_CHECKING:
    import uuid

    from src.pipeline.worker import PipelineWorker


async def handle_audio_processing(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Process voiceover, duck music, and produce final audio mix."""
    from src.services.audio_processor import AudioProcessor

    assert worker._http is not None

    video = await worker._get_video_info(video_id)
    channel_id = video["channel_id"]

    vo_data = payload.get("voiceover_generation", {})
    music_data = payload.get("music_selection", {})

    vo_r2_key = vo_data.get("voiceover_r2_key", "")
    music_r2_key = music_data.get("music_r2_key", "")

    # Download voiceover from R2
    vo_local = str(_TMP_ROOT / f"{video_id}_voiceover.wav")
    worker._download_from_r2(vo_r2_key, vo_local)

    proc = AudioProcessor(worker._settings, worker._http)

    # Process voiceover (EQ, normalize)
    processed_vo = str(_TMP_ROOT / f"{video_id}_vo_processed.wav")
    await proc.process_voiceover(vo_local, processed_vo)

    # If music is available, duck and mix
    mixed_path = processed_vo
    if music_r2_key:
        music_local = str(_TMP_ROOT / f"{video_id}_music.wav")
        worker._download_from_r2(music_r2_key, music_local)

        mixed_path = str(_TMP_ROOT / f"{video_id}_final_audio.wav")
        await proc.mix_final_audio(
            voice_path=processed_vo,
            music_path=music_local,
            output_path=mixed_path,
        )

    # Upload final audio
    r2_key = await worker._upload_to_r2(
        channel_id,
        video_id,
        "final_audio.wav",
        mixed_path,
        "audio/wav",
    )

    audio_info = await proc.get_audio_info(mixed_path)

    return {
        "audio_r2_key": r2_key,
        "duration_seconds": audio_info.duration_seconds,
        "sample_rate": audio_info.sample_rate,
    }
