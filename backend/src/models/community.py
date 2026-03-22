"""Community ecosystem models — Discord, Patreon, and topic submissions."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Topic submissions
# ---------------------------------------------------------------------------

TopicSource = Literal["google_forms", "discord", "youtube_comment", "manual"]
SubmissionStatus = Literal["new", "reviewed", "accepted", "rejected", "produced"]


class TopicSubmission(BaseModel):
    """A community-submitted case/topic suggestion."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "f6a7b8c9-d0e1-2345-f012-456789012345",
                "source": "discord",
                "submitter_name": "CrimeWatcher42",
                "submitter_contact": "",
                "case_name": "The Theranos Blood-Testing Scam",
                "description": "Elizabeth Holmes built a $9B company on technology that never worked.",
                "why_interesting": "Celebrity founder, massive investor losses, ongoing sentencing drama.",
                "source_links": ["https://en.wikipedia.org/wiki/Theranos"],
                "score": "78.5",
                "status": "accepted",
                "assigned_topic_id": None,
                "assigned_video_id": None,
                "created_at": "2026-03-12T18:30:00Z",
            }
        }
    )

    id: uuid.UUID
    source: TopicSource
    submitter_name: str = ""
    submitter_contact: str = ""
    case_name: str
    description: str = ""
    why_interesting: str = ""
    source_links: list[str] = Field(default_factory=list)
    score: Decimal | None = None
    status: SubmissionStatus = "new"
    assigned_topic_id: uuid.UUID | None = None
    assigned_video_id: uuid.UUID | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def from_row(cls, row: dict[str, object]) -> TopicSubmission:
        return cls.model_validate(row)


class TopicSubmissionCreate(BaseModel):
    """Input for creating a new topic submission."""

    source: TopicSource
    submitter_name: str = ""
    submitter_contact: str = ""
    case_name: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=5000)
    why_interesting: str = Field(default="", max_length=2000)
    source_links: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Patreon
# ---------------------------------------------------------------------------


class PatreonTier(BaseModel):
    """A Patreon membership tier."""

    tier_id: str
    name: str
    amount_cents: int = Field(ge=0)
    patron_count: int = 0


class PatreonMember(BaseModel):
    """A synced Patreon member."""

    id: uuid.UUID
    patreon_id: str
    name: str
    email: str = ""
    tier_name: str = ""
    tier_amount_cents: int = 0
    is_active: bool = True
    show_in_credits: bool = True
    last_synced_at: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    def from_row(cls, row: dict[str, object]) -> PatreonMember:
        return cls.model_validate(row)


class PatreonSyncResult(BaseModel):
    """Result of a Patreon membership sync operation."""

    total_members: int = 0
    new_members: int = 0
    updated_members: int = 0
    churned_members: int = 0
    total_mrr_cents: int = 0


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------


class DiscordNotification(BaseModel):
    """Record of a Discord notification sent."""

    video_id: uuid.UUID
    notification_type: Literal["new_video", "upcoming", "case_discussion"]
    webhook_url: str
    message_id: str = ""
    thread_id: str = ""
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    success: bool = True
    error: str = ""


# ---------------------------------------------------------------------------
# Community metrics
# ---------------------------------------------------------------------------


class CommunityMetrics(BaseModel):
    """Aggregated community health metrics for a channel."""

    channel_id: uuid.UUID
    discord_members_total: int = 0
    discord_active_7d: int = 0
    patreon_patron_count: int = 0
    patreon_mrr_usd: Decimal = Decimal("0")
    submissions_this_month: int = 0
    community_sourced_videos: int = 0
    patron_retention_rate: float = Field(default=0.0, ge=0.0, le=1.0)
