"""Caption and subtitle models.

Two kinds of model live here:

* In-memory pipeline shapes — ``WordTimestamp``, ``GroqTranscriptResponse``,
  ``CaptionWord``, ``CaptionResult``, ``CaptionResponse``. Used by the caption
  generator while a video is being assembled.
* DB-backed records — ``CaptionRecordBase`` / ``CaptionRecordCreate`` /
  ``CaptionRecordResponse``. Mirrors the introspected ``captions`` Supabase
  table (one persistent row per (video, format, language) tuple).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CaptionFormat = Literal["srt", "vtt", "json"]

# ---------------------------------------------------------------------------
# Word-level timestamp (from Groq Whisper)
# ---------------------------------------------------------------------------


class WordTimestamp(BaseModel):
    """A single word with time-based start/end from transcription."""

    word: str
    start: float
    end: float


class GroqTranscriptResponse(BaseModel):
    """Parsed response from Groq Whisper transcription API."""

    text: str
    words: list[WordTimestamp]
    language: str = "en"
    duration: float = 0.0


# ---------------------------------------------------------------------------
# Remotion frame-based caption word
# ---------------------------------------------------------------------------


class CaptionWord(BaseModel):
    """A single captioned word with Remotion frame timing."""

    text: str
    start_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------


class CaptionResult(BaseModel):
    """Full result of the caption generation pipeline."""

    srt_content: str
    srt_file_path: str
    caption_words: list[CaptionWord]
    word_timestamps: list[WordTimestamp]
    total_words: int
    duration_seconds: float
    cost_usd: Decimal
    transcription_time_seconds: float
    needs_human_review: bool = True


# ---------------------------------------------------------------------------
# DB response
# ---------------------------------------------------------------------------


class CaptionResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    words: list[CaptionWord]
    srt_url: str | None = None
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> CaptionResponse:
        return cls.model_validate(row)


# ---------------------------------------------------------------------------
# DB-backed caption record — mirrors the ``captions`` Supabase table
# ---------------------------------------------------------------------------


class CaptionRecordBase(BaseModel):
    video_id: uuid.UUID
    format: CaptionFormat = "srt"
    language: str = "en"
    content: str
    word_count: int | None = Field(default=None, ge=0)
    duration_seconds: Decimal | None = None
    model: str | None = None
    provider: str = "groq"
    cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    storage_bucket: str | None = None
    storage_path: str | None = None


class CaptionRecordCreate(CaptionRecordBase):
    pass


class CaptionRecordResponse(CaptionRecordBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "11111111-2222-3333-4444-555555555555",
                "video_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "format": "srt",
                "language": "en",
                "content": "1\n00:00:00,000 --> 00:00:02,500\nWelcome back to Street Level.\n",
                "word_count": 5,
                "duration_seconds": "2.500",
                "model": "whisper-large-v3-turbo",
                "provider": "groq",
                "cost_usd": "0.000088",
                "storage_bucket": "crimemill-assets",
                "storage_path": "captions/<video-uuid>.srt",
                "created_at": "2026-05-04T18:00:00Z",
                "updated_at": "2026-05-04T18:00:00Z",
            }
        }
    )

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> CaptionRecordResponse:
        return cls.model_validate(row)


# Bare-name alias for convention parity with the other DB-backed models.
CaptionRecord = CaptionRecordBase

__all__ = [
    "CaptionFormat",
    "CaptionRecord",
    "CaptionRecordBase",
    "CaptionRecordCreate",
    "CaptionRecordResponse",
    "CaptionResponse",
    "CaptionResult",
    "CaptionWord",
    "GroqTranscriptResponse",
    "WordTimestamp",
]
