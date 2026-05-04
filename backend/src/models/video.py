from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VideoStatus = Literal[
    "pending",
    "topic_selected",
    "script_generated",
    "media_generating",
    "media_complete",
    "assembling",
    "assembled",
    "uploading",
    "published",
    "failed",
    "cancelled",
]


class VideoBase(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        ser_json_bytes="base64",
    )

    title: str | None = Field(default=None, max_length=500)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    topic: dict[str, object] = Field(default_factory=dict)
    channel_id: uuid.UUID
    parent_video_id: uuid.UUID | None = None
    language: str = "en"
    # DB column is camelCase ("containsSyntheticMedia") to match the
    # YouTube API field; expose snake_case in Python with an alias so
    # row dicts from psycopg map cleanly via populate_by_name=True.
    contains_synthetic_media: bool = Field(default=True, alias="containsSyntheticMedia")


class VideoCreate(VideoBase):
    pass


class VideoUpdate(BaseModel):
    status: VideoStatus


class VideoResponse(VideoBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "title": "The Wirecard Scandal: Europe's Enron",
                "description": "How a $30 billion fintech darling turned out to be a house of cards.",
                "tags": ["corporate_fraud", "wirecard", "germany"],
                "topic": {},
                "channel_id": "11111111-2222-3333-4444-555555555555",
                "status": "published",
                "error_message": None,
                "youtube_video_id": "dQw4w9WgXcQ",
                "youtube_privacy_status": "public",
                "published_at": "2026-03-15T14:30:00Z",
                "script_word_count": 3200,
                "video_length_seconds": 1080,
                "created_at": "2026-03-10T09:00:00Z",
                "updated_at": "2026-03-15T14:30:00Z",
            }
        }
    )

    id: uuid.UUID
    status: VideoStatus
    error_message: str | None = None
    youtube_video_id: str | None = None
    youtube_privacy_status: str | None = None
    published_at: datetime | None = None
    script_word_count: int | None = None
    video_length_seconds: int | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> VideoResponse:
        return cls.model_validate(row)
