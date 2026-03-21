from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SceneScript(BaseModel):
    scene_number: int = Field(ge=1)
    narration: str
    image_prompt: str
    duration_seconds: float = Field(gt=0)


class ScriptResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    title: str
    hook: str
    scenes: list[SceneScript]
    outro: str
    total_duration_seconds: float
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ScriptResponse:
        return cls.model_validate(row)
