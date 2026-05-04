"""Travel advisory model — one row per gov't / health source per country.

Mirrors the introspected ``travel_advisories`` Supabase table:

    id UUID PK, source TEXT NOT NULL CHECK
        (state_dept | cdc | osac | who | foreign_office_uk | other),
    country_code TEXT NOT NULL, country_name TEXT NOT NULL,
    advisory_level INT CHECK 1-4, advisory_type TEXT,
    title TEXT NOT NULL, summary TEXT, full_text TEXT, url TEXT,
    issued_date DATE, expires_date DATE,
    is_active BOOLEAN DEFAULT true,
    used_in_video_ids UUID[] DEFAULT '{}',
    fetched_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(source, country_code, issued_date)
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AdvisorySource = Literal[
    "state_dept",
    "cdc",
    "osac",
    "who",
    "foreign_office_uk",
    "other",
]


class TravelAdvisoryBase(BaseModel):
    source: AdvisorySource
    country_code: str = Field(min_length=2, max_length=2)
    country_name: str
    advisory_level: int | None = Field(default=None, ge=1, le=4)
    advisory_type: str | None = None
    title: str
    summary: str | None = None
    full_text: str | None = None
    url: str | None = None
    issued_date: date | None = None
    expires_date: date | None = None
    is_active: bool = True
    used_in_video_ids: list[uuid.UUID] = Field(default_factory=list)


class TravelAdvisoryCreate(TravelAdvisoryBase):
    pass


class TravelAdvisoryResponse(TravelAdvisoryBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "11111111-2222-3333-4444-555555555555",
                "source": "state_dept",
                "country_code": "IN",
                "country_name": "India",
                "advisory_level": 2,
                "advisory_type": "exercise_increased_caution",
                "title": "India - Level 2: Exercise Increased Caution",
                "summary": "Exercise increased caution in India due to crime and terrorism.",
                "url": "https://travel.state.gov/...",
                "issued_date": "2025-09-01",
                "is_active": True,
                "used_in_video_ids": [],
                "fetched_at": "2026-04-14T12:00:00Z",
            }
        }
    )

    id: uuid.UUID
    fetched_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> TravelAdvisoryResponse:
        return cls.model_validate(row)


# Bare-name alias for symmetry with imports that drop the *Base suffix.
TravelAdvisory = TravelAdvisoryBase

__all__ = [
    "AdvisorySource",
    "TravelAdvisory",
    "TravelAdvisoryBase",
    "TravelAdvisoryCreate",
    "TravelAdvisoryResponse",
]
