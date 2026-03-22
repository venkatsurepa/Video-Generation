"""Video assembly models — scene layout, render input, and result."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from src.models.caption import CaptionWord

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

AssemblyStatus = Literal["pending", "rendering", "completed", "failed"]


# ---------------------------------------------------------------------------
# Scene layout
# ---------------------------------------------------------------------------


class SceneForAssembly(BaseModel):
    """A single scene positioned in the timeline for Remotion rendering."""

    scene_number: int = Field(ge=1)
    image_storage_path: str = Field(description="R2 key to the processed image")
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    narration_text: str = ""


# ---------------------------------------------------------------------------
# Render input
# ---------------------------------------------------------------------------


class AssemblyInput(BaseModel):
    """Everything the video assembler needs to trigger a Remotion Lambda render."""

    video_id: uuid.UUID
    channel_id: uuid.UUID
    title: str
    scenes: list[SceneForAssembly]
    audio_path: str = Field(description="R2 key to the mixed audio WAV")
    music_path: str = ""
    caption_words: list[CaptionWord] = Field(default_factory=list)
    audio_duration_seconds: float = Field(ge=0)
    fps: int = Field(default=30, ge=24, le=60)
    resolution: tuple[int, int] = (2560, 1440)


# ---------------------------------------------------------------------------
# Render status / result
# ---------------------------------------------------------------------------


class RenderStatus(BaseModel):
    """Status of a Remotion Lambda render."""

    render_id: str = ""
    status: str = "pending"
    progress: float = Field(default=0.0, ge=0, le=1)
    output_url: str | None = None
    error_message: str | None = None


class AssemblyResult(BaseModel):
    """Final result of a successful render."""

    file_path: str = Field(description="R2 object key")
    file_url: str = ""
    youtube_ready: bool = True
    duration_seconds: float = Field(ge=0)
    resolution: str = "2560x1440"
    file_size_bytes: int = Field(ge=0)
    codec: str = "h264"
    render_time_seconds: float = Field(ge=0)
    cost_usd: Decimal = Decimal("0")
    render_id: str = ""


# ---------------------------------------------------------------------------
# DB response
# ---------------------------------------------------------------------------


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
