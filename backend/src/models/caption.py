from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CaptionWord(BaseModel):
    text: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class CaptionResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    words: list[CaptionWord]
    srt_url: str | None = None
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> CaptionResponse:
        return cls.model_validate(row)
