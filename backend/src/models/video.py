from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

import orjson
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


def _orjson_dumps(v: object, *, default: object = None) -> str:  # noqa: ARG001
    return orjson.dumps(v).decode()


class VideoBase(BaseModel):
    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()},
        ser_json_bytes="base64",
    )

    title: str = Field(min_length=1, max_length=500)
    topic: str = Field(min_length=1, max_length=1000)
    channel_id: uuid.UUID


class VideoCreate(VideoBase):
    pass


class VideoUpdate(BaseModel):
    status: VideoStatus


class VideoResponse(VideoBase):
    id: uuid.UUID
    status: VideoStatus
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> VideoResponse:
        return cls.model_validate(row)
