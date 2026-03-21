from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AssemblyStatus = Literal["pending", "rendering", "completed", "failed"]


class AssemblyResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    video_url: str
    duration_seconds: float
    resolution: str
    file_size_bytes: int
    status: AssemblyStatus
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> AssemblyResponse:
        return cls.model_validate(row)
