from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class EpisodeMetadata(BaseModel):
    """Metadata for a podcast episode, generated from video data."""

    title: str
    description: str  # HTML allowed (Buzzsprout supports it)
    summary: str = Field(max_length=255)  # plain text
    tags: list[str] = Field(default_factory=list)
    season_number: int | None = None
    episode_number: int = Field(ge=1)
    explicit: bool = False
    published_at: datetime
    custom_url: str  # YouTube video URL for cross-linking
    ai_disclosure: str = (
        "This podcast uses AI-assisted production tools for narration and research."
    )


class BuzzsproutEpisode(BaseModel):
    """Response from Buzzsprout API after episode creation."""

    id: int
    title: str
    audio_url: str = ""
    artwork_url: str | None = None
    published_at: datetime | None = None
    duration: int = 0  # seconds


class PodcastEpisodeResult(BaseModel):
    """Full result of the podcast publishing pipeline."""

    video_id: uuid.UUID
    buzzsprout_episode_id: int
    audio_file_path: str
    duration_seconds: float = Field(ge=0)
    file_size_bytes: int = Field(ge=0)
    rss_feed_url: str = ""
    cost_usd: Decimal = Field(ge=0)  # hosting cost amortized


class PodcastStats(BaseModel):
    """Episode analytics from Buzzsprout."""

    episode_id: int
    total_downloads: int = 0
    downloads_30_day: int = 0


class PodcastEpisodeResponse(BaseModel):
    """Persisted podcast episode record from the database."""

    id: uuid.UUID
    video_id: uuid.UUID
    buzzsprout_episode_id: int | None
    title: str
    audio_storage_path: str | None
    duration_seconds: float | None
    file_size_bytes: int | None
    rss_feed_url: str | None
    total_downloads: int
    status: str
    published_at: datetime | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> PodcastEpisodeResponse:
        return cls.model_validate(row)
