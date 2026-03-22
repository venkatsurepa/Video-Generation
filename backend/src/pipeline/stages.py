"""Pipeline stage definitions as a directed acyclic graph.

Voiceover, images, music, and thumbnails all run in parallel after script
generation completes. Audio processing waits for voice + music. Video assembly
waits for audio + images + captions. Content classification runs after script
generation and thumbnail generation; YouTube upload waits for video + thumbnail
+ content classification (self-cert answers feed into upload metadata).
"""

from __future__ import annotations

from typing import TypedDict


class StageConfig(TypedDict, total=False):
    depends_on: list[str]
    service: str
    timeout_seconds: int
    max_retries: int
    optional: bool  # Optional stages don't block the pipeline on failure


PIPELINE_STAGES: dict[str, StageConfig] = {
    "script_generation": {
        "depends_on": [],
        "service": "script_generator",
        "timeout_seconds": 120,
        "max_retries": 3,
    },
    "voiceover_generation": {
        "depends_on": ["script_generation"],
        "service": "voiceover_generator",
        "timeout_seconds": 300,
        "max_retries": 3,
    },
    "image_generation": {
        "depends_on": ["script_generation"],
        "service": "image_generator",
        "timeout_seconds": 600,
        "max_retries": 3,
    },
    "music_selection": {
        "depends_on": ["script_generation"],
        "service": "music_selector",
        "timeout_seconds": 60,
        "max_retries": 2,
    },
    "audio_processing": {
        "depends_on": ["voiceover_generation", "music_selection"],
        "service": "audio_processor",
        "timeout_seconds": 180,
        "max_retries": 2,
    },
    "image_processing": {
        "depends_on": ["image_generation"],
        "service": "image_processor",
        "timeout_seconds": 120,
        "max_retries": 2,
    },
    "caption_generation": {
        "depends_on": ["voiceover_generation"],
        "service": "caption_generator",
        "timeout_seconds": 60,
        "max_retries": 2,
    },
    "video_assembly": {
        "depends_on": ["audio_processing", "image_processing", "caption_generation"],
        "service": "video_assembler",
        "timeout_seconds": 300,
        "max_retries": 2,
    },
    "thumbnail_generation": {
        "depends_on": ["script_generation"],
        "service": "thumbnail_generator",
        "timeout_seconds": 120,
        "max_retries": 2,
    },
    "content_classification": {
        "depends_on": ["script_generation", "thumbnail_generation"],
        "service": "content_classifier",
        "timeout_seconds": 60,
        "max_retries": 2,
    },
    "youtube_upload": {
        "depends_on": ["video_assembly", "content_classification"],
        "service": "youtube_uploader",
        "timeout_seconds": 600,
        "max_retries": 3,
    },
    "podcast_publish": {
        "depends_on": ["youtube_upload"],
        "service": "podcast_publisher",
        "timeout_seconds": 300,
        "max_retries": 2,
        "optional": True,
    },
    "shorts_generation": {
        "depends_on": ["youtube_upload"],
        "service": "shorts_generator",
        "timeout_seconds": 600,
        "max_retries": 2,
        "optional": True,
    },
    "localization": {
        "depends_on": ["youtube_upload"],
        "service": "localizer",
        "timeout_seconds": 900,
        "max_retries": 2,
        "optional": True,
    },
    "cross_platform_distribution": {
        "depends_on": ["shorts_generation"],
        "service": "cross_platform_distributor",
        "timeout_seconds": 120,
        "max_retries": 2,
        "optional": True,
    },
    "community_post": {
        "depends_on": ["youtube_upload"],
        "service": "cross_platform_distributor",
        "timeout_seconds": 30,
        "max_retries": 1,
        "optional": True,
    },
    "discord_notification": {
        "depends_on": ["youtube_upload"],
        "service": "community_manager",
        "timeout_seconds": 30,
        "max_retries": 1,
        "optional": True,
    },
}
