from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Platform = Literal["tiktok", "instagram_reels", "facebook_reels", "youtube_community", "twitter"]


class PlatformMetadata(BaseModel):
    """Platform-specific metadata for a distributed video."""

    title: str
    description: str
    hashtags: list[str] = Field(default_factory=list)
    caption: str = ""
    thumbnail_url: str = ""
    video_url: str = ""
    original_youtube_url: str = ""


class PlatformPostResult(BaseModel):
    """Result from posting to a single platform."""

    platform: Platform
    success: bool
    post_id: str = ""
    post_url: str = ""
    error: str = ""
    posted_at: datetime | None = None


class DistributionResult(BaseModel):
    """Aggregate result of distributing content across platforms."""

    video_id: uuid.UUID
    platforms: list[PlatformPostResult]
    total_attempted: int
    total_succeeded: int
    method: Literal["repurpose_io", "ayrshare", "direct_api"]


class RepurposeResult(BaseModel):
    """Result from Repurpose.io workflow trigger."""

    workflow_id: str
    job_id: str = ""
    status: Literal["queued", "processing", "completed", "failed"] = "queued"
    platforms_queued: list[str] = Field(default_factory=list)
    error: str = ""


class CommunityPost(BaseModel):
    """YouTube Community tab post content."""

    post_type: Literal["text", "poll", "image"] = "text"
    text: str = Field(min_length=1, max_length=5000)
    image_url: str = ""
    poll_choices: list[str] = Field(default_factory=list, max_length=5)
    video_id_link: str = ""  # YouTube video ID to link


class CrossPlatformStats(BaseModel):
    """Aggregated analytics across platforms for a single piece of content."""

    video_id: uuid.UUID
    stats_by_platform: dict[str, PlatformAnalytics] = Field(default_factory=dict)
    total_views: int = 0
    total_likes: int = 0
    total_comments: int = 0
    total_shares: int = 0
    fetched_at: datetime | None = None


class PlatformAnalytics(BaseModel):
    """Analytics for a single platform post."""

    platform: str
    post_id: str = ""
    post_url: str = ""
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    reach: int = 0
    watch_time_seconds: float = 0.0
