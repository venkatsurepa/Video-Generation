"""Partner app conversion-funnel model — one row per video per app per day.

Mirrors the introspected ``partner_app_metrics`` Supabase table:

    id UUID PK,
    video_id UUID NOT NULL FK->videos,
    partner_app TEXT NOT NULL,
    referral_code TEXT NOT NULL,
    deep_link TEXT,
    metric_date DATE NOT NULL,
    clicks/installs/signups/paid_conversions INT DEFAULT 0,
    revenue_usd NUMERIC(10,4) DEFAULT 0

Note: the live DB does NOT currently have the
``UNIQUE(video_id, partner_app, metric_date)`` constraint that the spec
mentions — to be added in a follow-up migration. Application code MUST
treat ``(video_id, partner_app, metric_date)`` as the logical PK and
upsert by it.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class PartnerAppMetricBase(BaseModel):
    video_id: uuid.UUID
    partner_app: str
    referral_code: str
    deep_link: str | None = None
    metric_date: date
    clicks: int = Field(default=0, ge=0)
    installs: int = Field(default=0, ge=0)
    signups: int = Field(default=0, ge=0)
    paid_conversions: int = Field(default=0, ge=0)
    revenue_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


class PartnerAppMetricCreate(PartnerAppMetricBase):
    pass


class PartnerAppMetricResponse(PartnerAppMetricBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "11111111-2222-3333-4444-555555555555",
                "video_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "partner_app": "safepath",
                "referral_code": "RHYO123",
                "deep_link": "rhyo://referral/RHYO123",
                "metric_date": "2026-04-14",
                "clicks": 320,
                "installs": 27,
                "signups": 18,
                "paid_conversions": 4,
                "revenue_usd": "19.9600",
            }
        }
    )

    id: uuid.UUID

    @classmethod
    def from_row(cls, row: dict[str, object]) -> PartnerAppMetricResponse:
        return cls.model_validate(row)


# Bare-name alias for symmetry with imports that drop the *Base suffix.
PartnerAppMetric = PartnerAppMetricBase

__all__ = [
    "PartnerAppMetric",
    "PartnerAppMetricBase",
    "PartnerAppMetricCreate",
    "PartnerAppMetricResponse",
]
