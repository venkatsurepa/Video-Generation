"""Content safety models for YouTube self-certification and ad-suitability."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------


class CategoryRating(BaseModel):
    """Classification of a single advertiser-unfriendly category."""

    category: str
    severity: Literal["none", "mild", "moderate", "severe"]
    confidence: float = Field(ge=0, le=1)
    reasoning: str
    edsa_mitigated: bool = Field(
        default=False,
        description="Would be flagged but EDSA (Educational/Documentary/Scientific/Artistic) exception applies",
    )


class FlaggedTerm(BaseModel):
    """A single term flagged during content analysis."""

    term: str
    location: Literal["title", "first_30_seconds", "script_body", "description"]
    category: str
    severity: Literal["none", "mild", "moderate", "severe"]
    safe_alternative: str | None = None


# ---------------------------------------------------------------------------
# Top-level classification results
# ---------------------------------------------------------------------------


class ContentClassification(BaseModel):
    """Result of classifying a script against YouTube's 14 advertiser-unfriendly categories."""

    video_id: uuid.UUID | None = None
    categories: dict[str, CategoryRating]
    overall_risk: Literal["low", "medium", "high"]
    edsa_eligible: bool
    edsa_reasoning: str
    recommended_self_cert: dict[str, str]
    flagged_terms: list[FlaggedTerm] = Field(default_factory=list)
    suggested_fixes: list[str] = Field(default_factory=list)
    classification_cost_usd: float = 0.0
    classified_at: datetime = Field(default_factory=datetime.utcnow)


class First30sCheck(BaseModel):
    """Analysis of the first 30 seconds of narration for demonetisation triggers."""

    passed: bool
    flagged_terms: list[FlaggedTerm] = Field(default_factory=list)
    coded_language_violations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class TitleSafetyCheck(BaseModel):
    """Title analysis against known demonetisation trigger words."""

    title: str
    is_safe: bool
    flagged_words: list[str] = Field(default_factory=list)
    safe_title_variant: str | None = None
    estimated_monetization: Literal["green", "yellow", "red"]


class ThumbnailClassification(BaseModel):
    """Result of thumbnail analysis against YouTube image policies."""

    thumbnail_path: str
    is_safe: bool
    overall_risk: Literal["low", "medium", "high"]
    flags: list[str] = Field(default_factory=list)
    reasoning: str = ""


class SelfCertAnswers(BaseModel):
    """Answers to fill in YouTube's self-certification questionnaire.

    CRITICAL: These must be honest.  Short-term pain (yellow icon) builds
    long-term trust score.  After ~20 honest ratings YouTube shifts from its
    own classifiers to trusting the channel's self-cert ratings.
    """

    inappropriate_language: Literal["none", "mild", "moderate", "severe"]
    violence: Literal["none", "mild", "moderate", "severe"]
    adult_content: Literal["none"] = "none"
    shocking: Literal["none", "mild"]
    harmful_acts: Literal["none"] = "none"
    hateful: Literal["none"] = "none"
    drugs: Literal["none"] = "none"
    firearms: Literal["none"] = "none"
    controversial: Literal["none", "mild", "moderate"]
    sensitive_events: Literal["none", "mild"]
    dishonest_behavior: Literal["none"] = "none"
    family_inappropriate: Literal["none"] = "none"
    incendiary: Literal["none"] = "none"
    tobacco: Literal["none"] = "none"
    confidence_score: float = Field(ge=0, le=1)
