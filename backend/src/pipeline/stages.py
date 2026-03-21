"""Pipeline stage definitions as a directed acyclic graph.

Voiceover, images, music, and thumbnails all run in parallel after script
generation completes. Audio processing waits for voice + music. Video assembly
waits for audio + images + captions. YouTube upload waits for video + thumbnail.
"""

from __future__ import annotations

from typing import TypedDict


class StageConfig(TypedDict):
    depends_on: list[str]
    service: str
    timeout_seconds: int
    max_retries: int


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
    "youtube_upload": {
        "depends_on": ["video_assembly", "thumbnail_generation"],
        "service": "youtube_uploader",
        "timeout_seconds": 600,
        "max_retries": 3,
    },
}
