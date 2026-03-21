from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ThumbnailResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    image_url: str
    width: int
    height: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ThumbnailResponse:
        return cls.model_validate(row)
