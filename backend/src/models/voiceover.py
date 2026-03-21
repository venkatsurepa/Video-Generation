from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

VoiceoverStatus = Literal["pending", "generating", "completed", "failed"]


class VoiceoverResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    scene_number: int
    audio_url: str
    duration_seconds: float
    status: VoiceoverStatus
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> VoiceoverResponse:
        return cls.model_validate(row)
