"""Performance analytics and prompt optimization models."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Retention analysis
# ---------------------------------------------------------------------------


class RetentionPattern(BaseModel):
    """Retention curve analysis for a single video."""

    video_id: uuid.UUID
    title: str | None = None
    curve_shape: Literal[
        "cliff_drop",
        "mid_lull",
        "spike",
        "healthy",
        "insufficient_data",
    ]
    first_30s_retention: float = Field(
        ge=0,
        le=1,
        description="Retention at ~20% elapsed (first-30s proxy)",
    )
    mid_retention: float = Field(
        ge=0,
        le=1,
        description="Retention at ~60% elapsed",
    )
    end_retention: float = Field(
        ge=0,
        le=1,
        description="Retention at ~90% elapsed",
    )
    hook_type: str | None = None
    open_loop_count: int = 0
    has_pattern_interrupts: bool = False
    ad_break_count: int = 0


class RetentionAnalysis(BaseModel):
    """Channel-level retention analysis across multiple videos."""

    channel_id: uuid.UUID
    videos_analyzed: int
    patterns: list[RetentionPattern] = Field(default_factory=list)
    hook_retention_ranking: dict[str, float] = Field(
        default_factory=dict,
        description="hook_type → avg first_30s_retention",
    )
    curve_shape_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="shape → count",
    )
    recommendations: list[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------


class ScoreBreakdown(BaseModel):
    """Per-component breakdown of the composite video score."""

    # Short-term (40%)
    ctr_score: float = Field(ge=0, le=100)
    first_48h_views_score: float = Field(ge=0, le=100)
    avg_view_duration_score: float = Field(ge=0, le=100)
    short_term_total: float = Field(ge=0, le=40)

    # Medium-term (35%)
    subscriber_conversion_score: float = Field(ge=0, le=100)
    thirty_day_views_score: float = Field(ge=0, le=100)
    returning_viewer_score: float = Field(ge=0, le=100)
    medium_term_total: float = Field(ge=0, le=35)

    # Long-term (25%)
    comment_sentiment_score: float = Field(ge=0, le=100)
    like_ratio_score: float = Field(ge=0, le=100)
    search_traffic_score: float = Field(ge=0, le=100)
    evergreen_score: float = Field(ge=0, le=100)
    long_term_total: float = Field(ge=0, le=25)


class VideoPerformanceScore(BaseModel):
    """Multi-objective composite score for a single video."""

    video_id: uuid.UUID
    composite_score: float = Field(ge=0, le=100)
    breakdown: ScoreBreakdown
    percentile_rank: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Percentile vs channel's other videos",
    )
    scored_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Goodhart's Law detection
# ---------------------------------------------------------------------------


class GoodhartAlert(BaseModel):
    """Alert when optimizing one metric degrades another."""

    alert_type: Literal[
        "clickbait_drift",
        "audience_mismatch",
        "controversy_farming",
    ]
    severity: Literal["warning", "critical"]
    metric_rising: str
    metric_falling: str
    recent_avg: float = Field(description="5-video rolling average")
    baseline_avg: float = Field(description="20-video baseline")
    delta_pct: float
    message: str
    recommendation: str


# ---------------------------------------------------------------------------
# Feature rankings
# ---------------------------------------------------------------------------


class FeatureRank(BaseModel):
    """Performance ranking for a single feature value."""

    feature_name: str
    feature_value: str
    sample_count: int = Field(ge=0)
    mean_score: float
    ci_lower: float
    ci_upper: float
    trend: Literal["improving", "declining", "stable"]
    trend_delta: float = 0.0


class FeatureRankings(BaseModel):
    """Ranked content features correlated with performance."""

    channel_id: uuid.UUID
    total_videos_analyzed: int
    rankings: dict[str, list[FeatureRank]] = Field(
        default_factory=dict,
        description="feature_category → ranked values",
    )
    top_recommendations: list[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Prompt optimization
# ---------------------------------------------------------------------------


class WeightChange(BaseModel):
    """A single proposed or applied weight change."""

    feature: str = Field(description="e.g. hook_type_weights.cold_open")
    old_value: float
    new_value: float
    reason: str
    risk_level: Literal["low", "medium", "high"]


class OptimizationReport(BaseModel):
    """Weekly optimization report with recommendations."""

    channel_id: uuid.UUID
    retention_analysis: RetentionAnalysis
    feature_rankings: FeatureRankings
    goodhart_alerts: list[GoodhartAlert] = Field(default_factory=list)
    recommended_changes: list[WeightChange] = Field(default_factory=list)
    auto_applied: list[WeightChange] = Field(default_factory=list)
    requires_approval: list[WeightChange] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Thompson Sampling
# ---------------------------------------------------------------------------


class ThompsonVariant(BaseModel):
    """Beta-distribution state for a single variant."""

    name: str
    alpha: float = Field(ge=0, description="Successes + 1 prior")
    beta_param: float = Field(ge=0, description="Failures + 1 prior")
    mean: float = Field(ge=0, le=1)
    sampled_value: float
    sample_count: int = Field(ge=0)


class ThompsonResult(BaseModel):
    """Result of Thompson Sampling for one feature dimension."""

    feature: str
    variants: dict[str, ThompsonVariant]
    selected: str = Field(description="Variant sampled highest")
    exploration_ratio: float = Field(
        ge=0,
        le=1,
        description="Fraction of total samples from least-tried variant",
    )
