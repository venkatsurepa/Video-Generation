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
        json_encoders={datetime: lambda v: v.isoformat()},
        ser_json_bytes="base64",
    )

    title: str | None = Field(default=None, max_length=500)
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    topic: dict[str, object] = Field(default_factory=dict)
    channel_id: uuid.UUID


class VideoCreate(VideoBase):
    pass


class VideoUpdate(BaseModel):
    status: VideoStatus


class VideoResponse(VideoBase):
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
