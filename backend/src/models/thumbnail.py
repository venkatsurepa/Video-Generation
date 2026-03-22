"""Thumbnail generation models — archetypes, brand settings, input/output."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from src.models.script import BrandSettings

# ---------------------------------------------------------------------------
# Archetypes
# ---------------------------------------------------------------------------

ThumbnailArchetype = Literal[
    "interrogation",
    "storyteller",
    "duality",
    "case_file",
    "beauty_beast",
    "cold_case",
]

ALL_ARCHETYPES: list[ThumbnailArchetype] = [
    "interrogation",
    "storyteller",
    "duality",
    "case_file",
    "beauty_beast",
    "cold_case",
]

# ---------------------------------------------------------------------------
# Input / Output
# ---------------------------------------------------------------------------


class ThumbnailInput(BaseModel):
    """Input parameters for YouTube thumbnail generation."""

    video_id: uuid.UUID
    title: str
    topic: dict[str, object] = Field(default_factory=dict)
    brand_settings: BrandSettings = Field(default_factory=BrandSettings)
    text_overlay: str = Field(default="", max_length=30)
    archetype: ThumbnailArchetype | None = None
    recent_archetypes: list[str] = Field(default_factory=list)


class ThumbnailResult(BaseModel):
    """Result of YouTube thumbnail generation."""

    file_path: str
    archetype: ThumbnailArchetype
    resolution: tuple[int, int]
    file_size_bytes: int
    text_overlay: str
    background_prompt: str
    cost_usd: float
    generation_time_seconds: float
    validation_warnings: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# DB response
# ---------------------------------------------------------------------------


class ThumbnailResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    image_url: str
    width: int
    height: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ThumbnailResponse:
        return cls.model_validate(row)
