"""Pipeline stage handlers — extracted from worker.py for maintainability."""

from __future__ import annotations

from typing import Any

from src.pipeline.handlers.assembly import handle_video_assembly
from src.pipeline.handlers.audio import handle_audio_processing
from src.pipeline.handlers.captions import handle_caption_generation
from src.pipeline.handlers.images import handle_image_generation, handle_image_processing
from src.pipeline.handlers.music import handle_music_selection
from src.pipeline.handlers.post_upload import (
    handle_community_post,
    handle_cross_platform_distribution,
    handle_discord_notification,
    handle_localization,
    handle_podcast_publish,
    handle_shorts_generation,
)
from src.pipeline.handlers.script import handle_script_generation
from src.pipeline.handlers.thumbnails import handle_thumbnail_generation
from src.pipeline.handlers.upload import handle_content_classification, handle_youtube_upload
from src.pipeline.handlers.voiceover import handle_voiceover_generation

__all__ = [
    "STAGE_HANDLERS",
    "handle_audio_processing",
    "handle_caption_generation",
    "handle_community_post",
    "handle_content_classification",
    "handle_cross_platform_distribution",
    "handle_discord_notification",
    "handle_image_generation",
    "handle_image_processing",
    "handle_localization",
    "handle_music_selection",
    "handle_podcast_publish",
    "handle_script_generation",
    "handle_shorts_generation",
    "handle_thumbnail_generation",
    "handle_video_assembly",
    "handle_voiceover_generation",
    "handle_youtube_upload",
]

# Stage name → handler function mapping
STAGE_HANDLERS: dict[str, Any] = {
    "script_generation": handle_script_generation,
    "voiceover_generation": handle_voiceover_generation,
    "image_generation": handle_image_generation,
    "music_selection": handle_music_selection,
    "audio_processing": handle_audio_processing,
    "image_processing": handle_image_processing,
    "caption_generation": handle_caption_generation,
    "video_assembly": handle_video_assembly,
    "thumbnail_generation": handle_thumbnail_generation,
    "content_classification": handle_content_classification,
    "youtube_upload": handle_youtube_upload,
    "podcast_publish": handle_podcast_publish,
    "shorts_generation": handle_shorts_generation,
    "localization": handle_localization,
    "cross_platform_distribution": handle_cross_platform_distribution,
    "community_post": handle_community_post,
    "discord_notification": handle_discord_notification,
}
