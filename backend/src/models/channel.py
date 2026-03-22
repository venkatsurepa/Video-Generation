from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ChannelStatus = Literal["active", "paused", "suspended", "archived"]


class ChannelBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    youtube_channel_id: str = Field(default="", max_length=100)
    handle: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=2000)


class ChannelCreate(ChannelBase):
    pass


class ChannelCreateInput(ChannelBase):
    """Extended channel creation input with niche and branding options."""

    niche: str = "true_crime_general"
    color_palette: list[str] | None = None
    voice_id: str = ""
    voice_name: str = ""
    thumbnail_archetype: str = ""
    font_family: str = ""


class OAuthResult(BaseModel):
    """Result of YouTube OAuth setup."""

    success: bool = False
    channel_id: uuid.UUID | None = None
    youtube_channel_title: str = ""
    scopes: list[str] = Field(default_factory=list)
    expires_at: datetime | None = None


class VoiceCloneResult(BaseModel):
    """Result of Fish Audio voice cloning."""

    voice_id: str
    voice_name: str
    sample_audio_url: str = ""
    test_audio_url: str = ""


class ChannelHealth(BaseModel):
    """Comprehensive health check for a channel."""

    channel_id: uuid.UUID
    channel_name: str
    oauth_status: str = "not_configured"
    voice_status: str = "not_configured"
    last_published: datetime | None = None
    videos_in_queue: int = 0
    dead_letter_jobs: int = 0
    subscriber_trend: str = "flat"
    yellow_icon_rate: float = 0.0
    monthly_revenue: Decimal | None = None


class ChannelResponse(ChannelBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "11111111-2222-3333-4444-555555555555",
                "name": "CrimeMill",
                "youtube_channel_id": "UCxxxxxxxxxxxxxxxx",
                "handle": "@crimemill",
                "description": "True crime documentaries powered by AI.",
                "status": "active",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-03-15T10:00:00Z",
            }
        }
    )

    id: uuid.UUID
    status: ChannelStatus
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ChannelResponse:
        return cls.model_validate(row)
