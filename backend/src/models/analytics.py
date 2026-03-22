from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Internal / service-layer models
# ---------------------------------------------------------------------------


class DailyMetricRow(BaseModel):
    """One day of YouTube Analytics data for a single video.

    Used to build the INSERT payload for ``video_daily_metrics``.
    """

    video_id: uuid.UUID
    youtube_video_id: str
    metric_date: date
    views: int = 0
    estimated_minutes_watched: Decimal = Decimal("0")
    average_view_duration_seconds: Decimal = Decimal("0")
    average_view_percentage: Decimal = Decimal("0")
    impressions: int = 0
    ctr: Decimal = Decimal("0")
    likes: int = 0
    dislikes: int = 0
    comments: int = 0
    shares: int = 0
    subscribers_gained: int = 0
    subscribers_lost: int = 0
    estimated_revenue: Decimal = Decimal("0")
    traffic_source_breakdown: dict[str, int] | None = None
    audience_retention_curve: list[dict[str, float]] | None = None


class RetentionDataPoint(BaseModel):
    """A single point on a video's audience-retention curve."""

    elapsed_ratio: float = Field(ge=0, le=1)
    absolute_retention: float  # audienceWatchRatio
    relative_retention: float  # relativeRetentionPerformance (0-1 vs similar)


class RetentionCurve(BaseModel):
    """~100 data-points describing how viewers drop off throughout a video."""

    video_id: str
    data_points: list[RetentionDataPoint]


class TrafficSourceBreakdown(BaseModel):
    """Where views came from for one video on one day."""

    video_id: str
    sources: dict[str, int]  # {"YT_SEARCH": 1500, "SUGGESTED": 8000, …}


class CollectionResult(BaseModel):
    """Summary returned by :meth:`collect_daily_metrics`."""

    videos_collected: int
    channels_processed: int
    start_date: date
    end_date: date
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float


class Anomaly(BaseModel):
    """A detected anomaly after daily analytics collection."""

    video_id: uuid.UUID
    anomaly_type: str
    severity: Literal["info", "warning", "critical"]
    message: str
    current_value: str
    previous_value: str
    detected_at: datetime


# ---------------------------------------------------------------------------
# API response models
# ---------------------------------------------------------------------------


class DailyMetricResponse(BaseModel):
    """Row from ``video_daily_metrics`` returned via the API."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "video_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "metric_date": "2026-03-15",
                "views": 12500,
                "estimated_minutes_watched": "8750.50",
                "average_view_duration_seconds": "420.30",
                "average_view_percentage": "65.20",
                "impressions": 85000,
                "ctr": "14.70",
                "likes": 950,
                "dislikes": 12,
                "comments": 87,
                "shares": 145,
                "subscribers_gained": 320,
                "subscribers_lost": 15,
                "estimated_revenue": "48.75",
                "traffic_source_breakdown": {"YT_SEARCH": 4200, "SUGGESTED": 6100, "BROWSE": 2200},
                "audience_retention_curve": None,
                "fetched_at": "2026-03-16T02:00:00Z",
            }
        }
    )

    video_id: uuid.UUID
    metric_date: date
    views: int
    estimated_minutes_watched: Decimal
    average_view_duration_seconds: Decimal
    average_view_percentage: Decimal
    impressions: int
    ctr: Decimal
    likes: int
    dislikes: int
    comments: int
    shares: int
    subscribers_gained: int
    subscribers_lost: int
    estimated_revenue: Decimal
    traffic_source_breakdown: dict[str, Any] | None = None
    audience_retention_curve: list[float] | None = None
    fetched_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> DailyMetricResponse:
        return cls.model_validate(row)


class ChannelDailySummary(BaseModel):
    """Row from ``mv_channel_daily_summary``."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "channel_id": "11111111-2222-3333-4444-555555555555",
                "metric_date": "2026-03-15",
                "total_views": 45000,
                "total_watch_minutes": "31500.00",
                "avg_ctr": "12.50",
                "total_likes": 3200,
                "net_subscribers": 850,
                "total_revenue": "175.40",
            }
        }
    )

    channel_id: uuid.UUID
    metric_date: date
    total_views: int
    total_watch_minutes: Decimal
    avg_ctr: Decimal
    total_likes: int
    net_subscribers: int
    total_revenue: Decimal

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ChannelDailySummary:
        return cls.model_validate(row)


class VideoProfitability(BaseModel):
    """Row from ``mv_video_profitability``."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "video_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "title": "The Wirecard Scandal: Europe's Enron",
                "published_at": "2026-03-01T14:00:00Z",
                "channel_id": "11111111-2222-3333-4444-555555555555",
                "channel_name": "CrimeMill",
                "lifetime_views": 250000,
                "lifetime_watch_minutes": "175000.00",
                "lifetime_revenue": "1250.00",
                "generation_cost": "4.50",
                "net_profit": "1245.50",
                "roi_ratio": "276.78",
                "profitability_status": "profitable",
            }
        }
    )

    video_id: uuid.UUID
    title: str | None = None
    published_at: datetime | None = None
    channel_id: uuid.UUID
    channel_name: str
    lifetime_views: int
    lifetime_watch_minutes: Decimal
    lifetime_revenue: Decimal
    generation_cost: Decimal
    net_profit: Decimal
    roi_ratio: Decimal | None = None
    profitability_status: str

    @classmethod
    def from_row(cls, row: dict[str, object]) -> VideoProfitability:
        return cls.model_validate(row)
