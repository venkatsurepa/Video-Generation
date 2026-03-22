"""YouTube upload and content classification handlers."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import structlog

from src.pipeline.handlers._helpers import _TMP_ROOT
from src.utils.cost_tracker import track_cost

if TYPE_CHECKING:
    import uuid

    from psycopg import AsyncConnection

    from src.pipeline.worker import PipelineWorker

logger = structlog.get_logger()


async def handle_content_classification(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Classify content against YouTube's 14 advertiser-unfriendly categories.

    Generates honest self-certification answers.  Runs after script_generation
    and thumbnail_generation so it can analyse both text and imagery.
    """
    from src.services.content_classifier import ContentClassifier

    assert worker._http is not None

    video = await worker._get_video_info(video_id)
    script_data = payload.get("script_generation", {})
    script_text = script_data.get("script_text", "")
    title = script_data.get("title", video.get("title", ""))
    description = script_data.get("description", "")

    classifier = ContentClassifier(worker._settings, worker._http)

    # Full script classification
    classification: Any = await worker._circuits["anthropic"].call(
        classifier.classify_script,
        script=script_text,
        title=title,
        description=description,
    )

    # Generate self-cert answers
    self_cert = classifier.generate_self_cert_answers(classification)

    # Title safety check
    title_check = await classifier.check_title_safety(title)

    # First 30 seconds check
    first_30s = await classifier.check_first_30_seconds(script_text)

    # Thumbnail classification (if thumbnail was generated)
    thumb_data = payload.get("thumbnail_generation", {})
    thumb_r2_key = thumb_data.get("thumbnail_r2_key")
    thumb_classification = None
    if thumb_r2_key:
        try:
            local_path = str(_TMP_ROOT / f"{video_id}_thumb_classify.jpg")
            worker._download_from_r2(thumb_r2_key, local_path)
            thumb_classification = await classifier.classify_thumbnail(local_path)
        except Exception as exc:
            await logger.awarning(
                "thumbnail_classification_failed",
                video_id=str(video_id),
                error=str(exc),
            )

    total_cost = classification.classification_cost_usd
    async with worker._pool.connection() as conn:
        await track_cost(
            cast("AsyncConnection[dict[str, object]]", conn),
            video_id,
            "content_classification",
            "anthropic",
            "claude-haiku-4-5",
            input_units=len(script_text),
            output_units=0,
            cost_usd=Decimal(str(total_cost)),
            latency_ms=0,
        )
        await conn.commit()

    return {
        "overall_risk": classification.overall_risk,
        "edsa_eligible": classification.edsa_eligible,
        "self_cert": self_cert.model_dump(),
        "title_safe": title_check.is_safe,
        "safe_title_variant": title_check.safe_title_variant,
        "estimated_monetization": title_check.estimated_monetization,
        "first_30s_passed": first_30s.passed,
        "flagged_terms_count": len(classification.flagged_terms),
        "suggested_fixes": classification.suggested_fixes,
        "thumbnail_safe": thumb_classification.is_safe if thumb_classification else None,
        "cost_usd": str(total_cost),
    }


async def handle_youtube_upload(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Upload the final video and thumbnail to YouTube.

    Downloads the rendered MP4, thumbnail, and SRT from R2 to local
    paths before handing to ``YouTubeUploader``, which expects local
    file paths (not R2 keys).  Tags are extracted from the title
    variants produced during script generation.
    """
    from src.models.youtube import VideoUploadInput
    from src.services.youtube_uploader import YouTubeUploader

    assert worker._http is not None

    # Gather metadata from prior stages
    assembly_data = payload.get("video_assembly", {})
    thumb_data = payload.get("thumbnail_generation", {})
    caption_data = payload.get("caption_generation", {})

    async with worker._pool.connection() as conn:
        row = cast(
            "dict[str, Any] | None",
            await (
                await conn.execute(
                    "SELECT channel_id, title, description, tags FROM videos WHERE id = %(id)s",
                    {"id": video_id},
                )
            ).fetchone(),
        )
    channel_id = row["channel_id"] if row else video_id
    title = row["title"] if row else ""
    description = row["description"] if row else ""
    tags = row["tags"] if row and row.get("tags") else []

    # Download video MP4 from R2 → local path
    video_r2_key = assembly_data.get("video_r2_key", "")
    video_local = str(_TMP_ROOT / f"{video_id}_final.mp4")
    worker._download_from_r2(video_r2_key, video_local)

    # Download thumbnail from R2 → local path (if available)
    thumb_r2_key = thumb_data.get("thumbnail_r2_key", "")
    thumb_local: str | None = None
    if thumb_r2_key:
        thumb_local = str(_TMP_ROOT / f"{video_id}_thumbnail.jpg")
        worker._download_from_r2(thumb_r2_key, thumb_local)

    # Download SRT from R2 → local path (if available)
    srt_r2_key = caption_data.get("srt_r2_key", "")
    srt_local: str | None = None
    if srt_r2_key:
        srt_local = str(_TMP_ROOT / f"{video_id}_captions.srt")
        worker._download_from_r2(srt_r2_key, srt_local)

    upload_input = VideoUploadInput(
        video_id=video_id,
        channel_id=channel_id,
        file_path=video_local,
        title=title,
        description=description,
        tags=tags,
        thumbnail_path=thumb_local,
        srt_path=srt_local,
    )

    gen = YouTubeUploader(worker._settings, worker._http)
    result: Any = await worker._circuits["youtube"].call(gen.upload_video, upload_input)

    return {
        "youtube_video_id": result.youtube_video_id,
        "youtube_url": result.youtube_url,
        "privacy_status": result.privacy_status,
        "ad_suitability": result.ad_suitability,
    }
