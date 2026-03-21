from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

MusicSource = Literal["epidemic_sound", "suno", "royalty_free"]


class MusicTrackResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    track_name: str
    source: MusicSource
    audio_url: str
    duration_seconds: float
    bpm: int | None = None
    genre: str | None = None
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> MusicTrackResponse:
        return cls.model_validate(row)
