"""Caption and subtitle models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

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
