"""Video destination model — one row per place mentioned in a video.

Mirrors the introspected ``video_destinations`` Supabase table:

    id UUID PK, video_id UUID NOT NULL FK->videos ON DELETE CASCADE,
    country_code TEXT NOT NULL, region_or_state TEXT, city TEXT, poi_name TEXT,
    relevance TEXT NOT NULL DEFAULT 'primary'
        CHECK (primary | secondary | mentioned),
    safepath_tags TEXT[] DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DestinationRelevance = Literal["primary", "secondary", "mentioned"]


class VideoDestinationBase(BaseModel):
    video_id: uuid.UUID
    country_code: str = Field(min_length=2, max_length=2)
    region_or_state: str | None = None
    city: str | None = None
    poi_name: str | None = None
    relevance: DestinationRelevance = "primary"
    safepath_tags: list[str] = Field(default_factory=list)


class VideoDestinationCreate(VideoDestinationBase):
    pass


class VideoDestinationResponse(VideoDestinationBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "11111111-2222-3333-4444-555555555555",
                "video_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "country_code": "IN",
                "region_or_state": "Telangana",
                "city": "Hyderabad",
                "poi_name": "Banjara Hills",
                "relevance": "primary",
                "safepath_tags": ["safety_briefing"],
                "created_at": "2026-04-14T12:00:00Z",
            }
        }
    )

    id: uuid.UUID
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> VideoDestinationResponse:
        return cls.model_validate(row)


# Bare-name alias for symmetry with imports that drop the *Base suffix.
VideoDestination = VideoDestinationBase

__all__ = [
    "DestinationRelevance",
    "VideoDestination",
    "VideoDestinationBase",
    "VideoDestinationCreate",
    "VideoDestinationResponse",
]
