"""Pydantic models for YouTube Shorts generation pipeline.

Shorts are 9:16 vertical videos (1080x1920) at 30fps, either 13s or 60s.
They reuse images from the parent long-form video — no new image generation.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field


class ShortCandidate(BaseModel):
    """A segment of the parent video identified as Short-worthy.

    Identified by Claude Haiku from the parent script, targeting
    moments with high emotional impact or cliffhanger potential.
    """

    segment_index: int = Field(ge=0, description="0-based index among candidates")
    start_time_seconds: float = Field(ge=0)
    end_time_seconds: float = Field(gt=0)
    hook_text: str = Field(
        max_length=80,
        description="Bold hook text overlaid in first 1-2s (max ~10 words)",
    )
    cliffhanger_text: str = Field(
        max_length=120,
        description="Cliffhanger text for end card driving to full video",
    )
    narration_text: str = Field(
        description="Narration script for this Short segment",
    )
    scene_numbers: list[int] = Field(
        description="Parent scene numbers whose images to reuse",
    )
    duration_type: Literal["13s", "60s"] = Field(
        default="60s",
        description="Target Short duration",
    )
    reasoning: str = Field(
        default="",
        description="Why this segment works as a Short",
    )


class ShortScript(BaseModel):
    """All assets needed to render one Short."""

    short_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    parent_video_id: uuid.UUID
    candidate: ShortCandidate
    audio_path: str = Field(default="", description="R2 key for voiceover WAV")
    image_paths: list[str] = Field(
        default_factory=list,
        description="R2 keys for reused parent images",
    )
    caption_words: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Remotion CaptionWord dicts from Groq whisper",
    )


class ShortRenderInput(BaseModel):
    """Input for a single Short's Remotion Lambda render."""

    short_id: uuid.UUID
    parent_video_id: uuid.UUID
    composition_id: str = "CrimeShort"
    scenes: list[dict[str, Any]] = Field(description="ShortScene props for Remotion")
    caption_words: list[dict[str, Any]] = Field(description="CaptionWord props for Remotion")
    audio_url: str
    hook_text: str
    cliffhanger_text: str
    total_duration_frames: int
    fps: int = 30


class ShortResult(BaseModel):
    """Result of rendering and optionally uploading one Short."""

    short_id: uuid.UUID
    parent_video_id: uuid.UUID
    youtube_short_id: str | None = None
    file_path: str = Field(description="R2 key of rendered MP4")
    file_url: str = ""
    duration_seconds: float = 0.0
    resolution: str = "1080x1920"
    file_size_bytes: int = 0
    render_time_seconds: float = 0.0
    cost_usd: Decimal = Field(default=Decimal("0"))


class ShortsGenerationResult(BaseModel):
    """Aggregate result for all Shorts generated from one parent video."""

    parent_video_id: uuid.UUID
    shorts: list[ShortResult] = Field(default_factory=list)
    candidates_found: int = 0
    shorts_rendered: int = 0
    total_cost_usd: Decimal = Field(default=Decimal("0"))
