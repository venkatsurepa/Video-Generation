from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ImageStatus = Literal["pending", "generating", "completed", "failed"]


class ImageResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    scene_number: int
    prompt: str
    image_url: str
    width: int
    height: int
    status: ImageStatus
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ImageResponse:
        return cls.model_validate(row)
