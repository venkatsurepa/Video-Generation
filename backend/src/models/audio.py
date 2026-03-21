from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AudioMixResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    mixed_audio_url: str
    voice_volume: float
    music_volume: float
    duration_seconds: float
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> AudioMixResponse:
        return cls.model_validate(row)
