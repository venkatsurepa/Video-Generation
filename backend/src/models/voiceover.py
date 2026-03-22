"""Voiceover generation models — voice metadata, TTS results, DB responses."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Voice info
# ---------------------------------------------------------------------------


class VoiceInfo(BaseModel):
    """Voice metadata from a TTS provider."""

    voice_id: str
    name: str
    description: str = ""
    preview_url: str = ""
    languages: list[str] = Field(default_factory=list)
    provider: str = ""
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


class VoiceoverResult(BaseModel):
    """Result of TTS synthesis for a full voiceover."""

    file_path: str
    duration_seconds: float
    sample_rate: int
    file_size_bytes: int
    character_count: int
    cost_usd: Decimal
    voice_id: str


# ---------------------------------------------------------------------------
# DB response
# ---------------------------------------------------------------------------

VoiceoverStatus = Literal["pending", "generating", "completed", "failed"]


class VoiceoverResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    audio_url: str
    duration_seconds: float
    status: VoiceoverStatus
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> VoiceoverResponse:
        return cls.model_validate(row)
