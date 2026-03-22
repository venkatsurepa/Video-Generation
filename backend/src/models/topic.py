from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

TopicPriority = Literal["immediate", "this_week", "low", "archived"]
TopicCategory = Literal[
    "corporate_fraud",
    "ponzi_scheme",
    "art_forgery",
    "cybercrime",
    "money_laundering",
    "embezzlement",
    "insurance_fraud",
    "identity_theft",
    "murder",
    "kidnapping",
    "organized_crime",
    "political_corruption",
    "environmental_crime",
    "trafficking",
    "other",
]


# ---------- Signal models (Layer 1-3 outputs) ----------


class TrendSignal(BaseModel):
    """Layer 1: Google Trends / YouTube autocomplete detection."""

    source: Literal["google_trends", "youtube_autocomplete"]
    query: str
    interest_score: int = Field(ge=0, le=100)
    growth_label: str | None = None  # "Breakout", "Rising", etc.
    detected_at: datetime = Field(default_factory=datetime.utcnow)


class RedditSignal(BaseModel):
    """Layer 2: Reddit crime story velocity detection."""

    subreddit: str
    title: str
    url: str
    upvotes: int = Field(ge=0)
    upvote_ratio: float = Field(ge=0, le=1)
    num_comments: int = Field(ge=0)
    num_crossposts: int = Field(ge=0)
    created_utc: datetime
    extracted_entities: list[str] = Field(default_factory=list)


class GDELTSignal(BaseModel):
    """Layer 3: GDELT breaking crime news signal."""

    title: str
    url: str
    source_name: str
    language: str = "English"
    theme: str = ""
    tone: float = 0.0
    published_at: datetime


# ---------- Layer 4: Competitor analysis ----------


class CompetitorVideo(BaseModel):
    channel_name: str
    video_title: str
    youtube_video_id: str
    published_at: datetime
    view_count: int = 0


class CoverageSaturation(BaseModel):
    """Layer 4: YouTube competitor coverage check result."""

    topic: str
    channels_covered: int = 0
    total_channels_tracked: int = 0
    saturation_score: float = Field(ge=0.0, le=1.0, default=0.0)
    competitor_videos: list[CompetitorVideo] = Field(default_factory=list)


# ---------- Layer 5: Scoring ----------

SignalUnion = Annotated[
    TrendSignal | RedditSignal | GDELTSignal,
    Field(discriminator=None),
]


class TopicCandidate(BaseModel):
    """Raw topic before scoring — aggregated from signal layers."""

    title: str
    description: str = ""
    category: TopicCategory = "other"
    source_signals: list[SignalUnion] = Field(default_factory=list)
    coverage: CoverageSaturation | None = None
    recency_days: int = Field(ge=0, default=0)
    severity_estimate: int = Field(ge=0, le=10, default=5)
    celebrity_involvement: int = Field(ge=0, le=10, default=0)
    geographic_relevance: int = Field(ge=0, le=10, default=5)
    has_ongoing_developments: bool = False
    emotional_resonance: int = Field(ge=0, le=10, default=5)
    media_coverage_level: int = Field(ge=0, le=10, default=5)
    social_media_buzz: int = Field(ge=0, le=10, default=5)
    search_volume_trend: int = Field(ge=0, le=10, default=5)


class ScoredTopic(BaseModel):
    """Final scored topic ready for ranking."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    title: str
    description: str = ""
    category: TopicCategory = "other"
    composite_score: float = Field(ge=0, le=130)  # up to 100 × 1.3 max multiplier
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    multipliers_applied: list[str] = Field(default_factory=list)
    priority: TopicPriority = "low"
    source_signals_count: int = 0
    competitor_saturation: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    used_in_video_id: uuid.UUID | None = None


# ---------- API request/response models ----------


class TopicListParams(BaseModel):
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
    priority: TopicPriority | None = None
    category: TopicCategory | None = None


class TopicResponse(BaseModel):
    """API response for a discovered topic."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
                "title": "The Wirecard Collapse",
                "description": "Germany's biggest post-war financial fraud involving a DAX-30 company.",
                "category": "corporate_fraud",
                "composite_score": 87.5,
                "score_breakdown": {
                    "trend_score": 22.0,
                    "social_velocity": 18.0,
                    "news_freshness": 15.0,
                    "severity": 17.5,
                    "saturation_penalty": -5.0,
                },
                "source_signals": [],
                "competitor_saturation": 0.35,
                "priority": "immediate",
                "used_in_video_id": None,
                "discovered_at": "2026-03-14T08:00:00Z",
                "expires_at": "2026-03-21T08:00:00Z",
                "created_at": "2026-03-14T08:00:00Z",
            }
        }
    )

    id: uuid.UUID
    title: str
    description: str | None
    category: str
    composite_score: float | None
    score_breakdown: dict[str, float] | None
    source_signals: list[dict[str, object]] | None
    competitor_saturation: float | None
    priority: str | None
    used_in_video_id: uuid.UUID | None
    discovered_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> TopicResponse:
        return cls.model_validate(row)


class TopicAssign(BaseModel):
    video_id: uuid.UUID
