"""Post-upload pipeline handlers.

Includes: podcast_publish, shorts_generation, discord_notification,
cross_platform_distribution, community_post, localization.
"""

from __future__ import annotations

import contextlib
import json
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import structlog

from src.pipeline.handlers._helpers import _TMP_ROOT
from src.utils.cost_tracker import track_cost

if TYPE_CHECKING:
    from psycopg import AsyncConnection

    from src.pipeline.worker import PipelineWorker

logger = structlog.get_logger()


async def handle_podcast_publish(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Publish the video's audio as a podcast episode via Buzzsprout.

    Runs after youtube_upload so we can cross-link the YouTube URL.
    Downloads the voiceover from R2, normalises to podcast standards,
    and uploads to Buzzsprout.
    """
    from src.db.queries import INSERT_PODCAST_EPISODE, UPDATE_PODCAST_EPISODE_PUBLISHED
    from src.services.podcast_publisher import PodcastPublisher

    assert worker._http is not None

    video = await worker._get_video_info(video_id)
    channel_id = video["channel_id"]
    title = video.get("title") or "Untitled"

    upload_data = payload.get("youtube_upload", {})
    youtube_video_id = upload_data.get("youtube_video_id", "")

    publisher = PodcastPublisher(worker._settings, worker._http)

    # Find the voiceover R2 key
    voiceover_r2_key = worker._r2_key(channel_id, video_id, "voiceover.wav")

    # Create podcast episode record
    async with worker._pool.connection() as conn:
        await conn.execute(
            INSERT_PODCAST_EPISODE,
            {"video_id": video_id, "title": title},
        )
        await conn.commit()

    try:
        result = await publisher.publish_episode(
            video_id=video_id,
            audio_storage_path=voiceover_r2_key,
            title=title,
            description=video.get("description") or "",
            tags=video.get("tags") or [],
            episode_number=1,
            youtube_video_id=youtube_video_id,
        )

        # Update episode record with Buzzsprout data
        async with worker._pool.connection() as conn:
            await conn.execute(
                UPDATE_PODCAST_EPISODE_PUBLISHED,
                {
                    "video_id": video_id,
                    "buzzsprout_episode_id": result.buzzsprout_episode_id,
                    "description": video.get("description") or "",
                    "audio_storage_path": result.audio_file_path,
                    "duration_seconds": result.duration_seconds,
                    "file_size_bytes": result.file_size_bytes,
                    "rss_feed_url": result.rss_feed_url,
                },
            )
            await conn.commit()

        return {
            "buzzsprout_episode_id": result.buzzsprout_episode_id,
            "duration_seconds": result.duration_seconds,
            "rss_feed_url": result.rss_feed_url,
            "cost_usd": str(result.cost_usd),
        }

    except Exception as exc:
        from src.db.queries import FAIL_PODCAST_EPISODE

        async with worker._pool.connection() as conn:
            await conn.execute(
                FAIL_PODCAST_EPISODE,
                {"video_id": video_id, "error_message": str(exc)[:500]},
            )
            await conn.commit()
        raise


async def handle_shorts_generation(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate 2-3 YouTube Shorts from the parent long-form video.

    This is an optional pipeline stage — failures are logged but do NOT
    block the parent video or mark it as failed.
    """
    from src.services.shorts_generator import ShortsGenerator

    assert worker._http is not None

    video = await worker._get_video_info(video_id)
    channel_id = video["channel_id"]

    # We need the script text and scene data — fetch from R2 script.json
    script_r2_key = worker._r2_key(channel_id, video_id, "script.json")
    script_local = str(_TMP_ROOT / f"{video_id}_script_for_shorts.json")
    worker._download_from_r2(script_r2_key, script_local)
    script_data = json.loads(Path(script_local).read_text(encoding="utf-8"))

    script_text = script_data.get("script_text", "")
    scenes = script_data.get("scenes", [])

    if not script_text or not scenes:
        await logger.awarn(
            "shorts_skipped_no_script",
            video_id=str(video_id),
        )
        return {"skipped": True, "reason": "no_script_data"}

    # Get processed image keys from the image_processing stage result
    # (walk completed jobs to find image_processing result)
    image_keys: list[str] = []
    async with worker._pool.connection() as conn:
        cur = await conn.execute(
            "SELECT result FROM pipeline_jobs "
            "WHERE video_id = %(video_id)s AND stage = 'image_processing' "
            "AND status = 'completed' LIMIT 1",
            {"video_id": video_id},
        )
        row = cast("dict[str, Any] | None", await cur.fetchone())
        if row and row["result"]:
            img_result = row["result"]
            if isinstance(img_result, str):
                img_result = json.loads(img_result)
            image_keys = img_result.get("processed_image_keys", [])

    if not image_keys:
        await logger.awarn(
            "shorts_skipped_no_images",
            video_id=str(video_id),
        )
        return {"skipped": True, "reason": "no_processed_images"}

    gen = ShortsGenerator(worker._settings, worker._http)
    result: Any = await worker._circuits["anthropic"].call(
        gen.generate_shorts,
        parent_video_id=video_id,
        channel_id=channel_id,
        script_text=script_text,
        scenes=scenes,
        parent_image_keys=image_keys,
    )

    # Persist Short records to DB
    async with worker._pool.connection() as conn:
        for short in result.shorts:
            await conn.execute(
                """
                INSERT INTO shorts (
                    id, parent_video_id, channel_id,
                    segment_index, hook_text, cliffhanger_text,
                    status, file_path, file_url,
                    duration_seconds, file_size_bytes,
                    render_time_seconds, cost_usd
                ) VALUES (
                    %(id)s, %(parent_video_id)s, %(channel_id)s,
                    %(segment_index)s, %(hook_text)s, %(cliffhanger_text)s,
                    'rendered', %(file_path)s, %(file_url)s,
                    %(duration_seconds)s, %(file_size_bytes)s,
                    %(render_time_seconds)s, %(cost_usd)s
                )
                ON CONFLICT (id) DO NOTHING
                """,
                {
                    "id": short.short_id,
                    "parent_video_id": video_id,
                    "channel_id": channel_id,
                    "segment_index": 0,
                    "hook_text": "",
                    "cliffhanger_text": "",
                    "file_path": short.file_path,
                    "file_url": short.file_url,
                    "duration_seconds": short.duration_seconds,
                    "file_size_bytes": short.file_size_bytes,
                    "render_time_seconds": short.render_time_seconds,
                    "cost_usd": short.cost_usd,
                },
            )

        await track_cost(
            cast("AsyncConnection[dict[str, object]]", conn),
            video_id,
            "shorts_generation",
            "mixed",
            "haiku+fish+whisper+lambda",
            input_units=result.candidates_found,
            output_units=result.shorts_rendered,
            cost_usd=result.total_cost_usd,
            latency_ms=0,
        )
        await conn.commit()

    # Clean up temp
    with contextlib.suppress(OSError):
        os.unlink(script_local)

    return {
        "candidates_found": result.candidates_found,
        "shorts_rendered": result.shorts_rendered,
        "short_ids": [str(s.short_id) for s in result.shorts],
        "cost_usd": str(result.total_cost_usd),
    }


async def handle_discord_notification(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Post Discord notification and create a discussion thread.

    Optional post-upload stage — failures do not block the pipeline.
    """
    from src.services.community import CommunityManager

    assert worker._http is not None

    mgr = CommunityManager(worker._settings, worker._http, worker._pool)

    # Gather video metadata from prior stages and DB
    upload_data = payload.get("youtube_upload", {})
    youtube_video_id = upload_data.get("youtube_video_id", "")

    async with worker._pool.connection() as conn:
        row = cast(
            "dict[str, Any] | None",
            await (
                await conn.execute(
                    "SELECT title, description, video_length_seconds, topic "
                    "FROM videos WHERE id = %(id)s",
                    {"id": video_id},
                )
            ).fetchone(),
        )

    title = row["title"] if row else ""
    description = row["description"] if row else ""
    duration = row["video_length_seconds"] if row else 0
    topic = row["topic"] if row and isinstance(row["topic"], dict) else {}
    category = topic.get("category", "")

    # Thumbnail URL from R2
    thumb_data = payload.get("thumbnail_generation", {})
    thumb_r2_key = thumb_data.get("thumbnail_r2_key", "")
    thumbnail_url = ""
    if thumb_r2_key and worker._settings.storage.public_url:
        thumbnail_url = f"{worker._settings.storage.public_url}/{thumb_r2_key}"

    # Send new video notification
    notif = await mgr.notify_discord_new_video(
        video_id=video_id,
        title=title,
        description=description,
        youtube_video_id=youtube_video_id,
        thumbnail_url=thumbnail_url,
        duration_seconds=duration or 0,
        category=category,
    )

    # Create discussion thread
    case_name = topic.get("case_name", title)
    thread_id = await mgr.create_case_discussion_thread(
        video_id=video_id,
        case_name=case_name,
    )

    return {
        "discord_notified": notif.success,
        "message_id": notif.message_id,
        "thread_id": thread_id,
    }


async def handle_localization(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Generate localised audio/subtitles for additional languages.

    Optional post-upload stage.  Reads the original script and voiceover,
    translates via Claude, generates localised TTS, and uploads subtitle
    files to R2.
    """
    from src.services.caption_generator import CaptionGenerator
    from src.services.localizer import Localizer
    from src.services.script_generator import ScriptGenerator
    from src.services.video_assembler import VideoAssembler
    from src.services.voiceover_generator import VoiceoverGenerator

    assert worker._http is not None
    localizer = Localizer(
        settings=worker._settings,
        script_generator=ScriptGenerator(worker._settings, worker._http),
        voiceover_generator=VoiceoverGenerator(worker._settings, worker._http),
        caption_generator=CaptionGenerator(worker._settings, worker._http),
        video_assembler=VideoAssembler(worker._settings, worker._http),
        http_client=worker._http,
        db_pool=worker._pool,
    )

    target_language = payload.get("target_language", "es")
    target_channel_id = payload.get("target_channel_id")
    if not target_channel_id:
        # Default: same channel
        from psycopg.rows import dict_row

        async with worker._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT channel_id FROM videos WHERE id = %(id)s",
                {"id": video_id},
            )
            row = await cur.fetchone()
            target_channel_id = row["channel_id"] if row else video_id

    result = await localizer.localize_video(
        source_video_id=video_id,
        target_language=target_language,
        target_channel_id=uuid.UUID(str(target_channel_id)),
    )

    async with worker._pool.connection() as conn:
        await track_cost(
            cast("AsyncConnection[dict[str, object]]", conn),
            video_id,
            "localization",
            "llm+tts",
            "claude+fish_audio",
            input_units=result.translated_word_count,
            output_units=1,
            cost_usd=result.total_cost_usd,
            latency_ms=0,
        )
        await conn.commit()

    return {
        "localized_video_id": str(result.localized_video_id),
        "target_language": result.target_language,
        "translated_words": result.translated_word_count,
        "cost_usd": str(result.total_cost_usd),
    }


async def handle_cross_platform_distribution(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Distribute Shorts and clips to TikTok, Instagram Reels, etc.

    Requires shorts_generation to have completed first.  Uses Repurpose.io
    or Ayrshare depending on config.
    """
    from src.services.cross_platform import CrossPlatformDistributor

    assert worker._http is not None
    distributor = CrossPlatformDistributor(
        worker._settings,
        worker._http,
        worker._pool,
    )

    shorts_data = payload.get("shorts_generation", {})
    short_ids = shorts_data.get("short_ids", [])
    platforms = payload.get("platforms", ["tiktok", "instagram_reels"])

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for sid in short_ids:
        try:
            result = await distributor.distribute_short(
                short_video_id=uuid.UUID(sid),
                platforms=platforms,
            )
            results.append(
                {
                    "short_id": sid,
                    "total_attempted": result.total_attempted,
                    "total_succeeded": result.total_succeeded,
                }
            )
        except Exception as exc:
            errors.append(f"{sid}: {exc}")

    return {
        "shorts_distributed": len(results),
        "total_errors": len(errors),
        "errors": errors,
    }


async def handle_community_post(
    worker: PipelineWorker,
    video_id: uuid.UUID,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Create community tab / social media teaser posts.

    Posts a teaser with thumbnail to YouTube community tab and configured
    social platforms after upload completes.
    """
    from src.models.distribution import CommunityPost
    from src.services.cross_platform import CrossPlatformDistributor

    assert worker._http is not None
    distributor = CrossPlatformDistributor(
        worker._settings,
        worker._http,
        worker._pool,
    )

    from psycopg.rows import dict_row

    async with worker._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT title, description, channel_id FROM videos WHERE id = %(id)s",
            {"id": video_id},
        )
        row = await cur.fetchone()

    if not row:
        return {"community_posted": False, "error": "Video not found"}

    upload_data = payload.get("youtube_upload", {})
    youtube_video_id = upload_data.get("youtube_video_id", "")
    yt_url = f"https://youtube.com/watch?v={youtube_video_id}" if youtube_video_id else ""

    post = CommunityPost(
        post_type="text",
        text=f"New video: {row['title']}\n\n{yt_url}",
    )

    try:
        post_id = await distributor.post_community_update(
            channel_id=row["channel_id"],
            content=post,
        )
        return {"community_posted": True, "post_id": post_id}
    except Exception as exc:
        await logger.awarning(
            "community_post_failed",
            video_id=str(video_id),
            error=str(exc),
        )
        return {"community_posted": False, "error": str(exc)}
