from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

MusicSource = Literal["epidemic_sound", "suno", "royalty_free"]

MoodCategory = Literal[
    "suspenseful_investigation",
    "emotional_reflective",
    "dramatic_reveal",
    "establishing_neutral",
    "eerie_dark_ambient",
]


class MusicTrack(BaseModel):
    """A single track from the curated music library."""

    id: str
    title: str
    artist: str = ""
    source: str = "epidemic_sound"
    mood_category: MoodCategory = "establishing_neutral"
    bpm: int = 80
    duration_seconds: float = 0.0
    file_path: str = ""
    stems_path: str | None = None
    license_safe: bool = True
    content_id_safe: bool = True


class MusicResult(BaseModel):
    """Result of music selection for a video."""

    track: MusicTrack
    file_path: str
    cost_usd: Decimal = Decimal("0")
    selection_reason: str = ""


class MusicLibraryStatus(BaseModel):
    """Summary of the local music library."""

    total_tracks: int = 0
    total_duration_minutes: float = 0.0
    tracks_per_mood: dict[str, int] = Field(default_factory=dict)
    missing_files: list[str] = Field(default_factory=list)


class MusicTrackResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    track_name: str
    source: MusicSource
    audio_url: str
    duration_seconds: float
    bpm: int | None = None
    genre: str | None = None
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> MusicTrackResponse:
        return cls.model_validate(row)
