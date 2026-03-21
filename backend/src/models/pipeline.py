from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

JobStatus = Literal["pending", "in_progress", "completed", "failed", "dead_letter"]


class PipelineJobResponse(BaseModel):
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
    video_id: uuid.UUID
    video_status: str
    jobs: list[PipelineJobResponse]
