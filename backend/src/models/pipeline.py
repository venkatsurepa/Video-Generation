from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

JobStatus = Literal["pending", "in_progress", "completed", "failed", "dead_letter"]


class PipelineJobResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": 42,
                "video_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "stage": "script_generation",
                "status": "completed",
                "priority": 10,
                "retry_count": 0,
                "max_retries": 3,
                "error_message": None,
                "created_at": "2026-03-15T10:00:00Z",
                "started_at": "2026-03-15T10:00:05Z",
                "completed_at": "2026-03-15T10:02:30Z",
            }
        }
    )

    id: int
    video_id: uuid.UUID
    stage: str
    status: JobStatus
    priority: int
    retry_count: int
    max_retries: int
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @classmethod
    def from_row(cls, row: dict[str, object]) -> PipelineJobResponse:
        return cls.model_validate(row)


class PipelineStatusResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "video_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "video_status": "script_generated",
                "jobs": [],
            }
        }
    )

    video_id: uuid.UUID
    video_status: str
    jobs: list[PipelineJobResponse]
