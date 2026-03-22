from __future__ import annotations

import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

DayOfWeek = Literal[
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
]


class WeeklySlot(BaseModel):
    """A recurring weekly time slot assigned to a channel."""

    day: DayOfWeek
    hour: int = Field(ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    timezone: str = "America/Chicago"


class NetworkGrid(BaseModel):
    """The network-wide publishing grid: channel → weekly slots."""

    channel_slots: dict[uuid.UUID, list[WeeklySlot]]


class ScheduleSlot(BaseModel):
    """A concrete publish slot assigned to a video."""

    video_id: uuid.UUID
    channel_id: uuid.UUID
    publish_at: datetime
    day_of_week: str
    is_peak_slot: bool
    is_q4: bool

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ScheduleSlot:
        return cls.model_validate(row)


class CalendarEntry(BaseModel):
    """A single cell in the publishing calendar."""

    date: date
    time: time
    channel_id: uuid.UUID
    channel_name: str
    video_id: uuid.UUID | None = None
    video_title: str | None = None
    status: Literal["scheduled", "published", "open", "blocked"]


class PublishingCalendar(BaseModel):
    """The full multi-channel publishing calendar."""

    slots: list[CalendarEntry]
    open_slots: list[datetime]
    conflicts: list[str]


class VideoForReview(BaseModel):
    """A video in the human review queue."""

    video_id: uuid.UUID
    title: str
    channel_name: str
    thumbnail_url: str | None = None
    script_excerpt: str = ""
    total_cost_usd: Decimal = Decimal("0")
    pipeline_duration_minutes: float = 0.0
    self_cert_recommendation: dict[str, object] = Field(default_factory=dict)
    suggested_publish_slot: datetime | None = None
    assembled_at: datetime


# --- API request / response models ---


class ApproveRequest(BaseModel):
    reviewer_notes: str = ""


class RejectRequest(BaseModel):
    reason: str


class RescheduleRequest(BaseModel):
    new_datetime: datetime
