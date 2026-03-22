from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class VideoUploadInput(BaseModel):
    """Input for the 5-step safety upload flow."""

    video_id: uuid.UUID = Field(description="Internal CrimeMill video ID")
    channel_id: uuid.UUID
    file_path: str = Field(description="Local path to assembled MP4")
    title: str = Field(max_length=100)
    description: str = Field(description="Max 5000 bytes enforced at upload time")
    tags: list[str] = Field(default_factory=list, description="Max 500 chars total")
    category_id: int = Field(
        default=27,
        description="YouTube category: 27=Education, 22=People & Blogs",
    )
    thumbnail_path: str | None = None
    srt_path: str | None = None
    playlist_id: str | None = None
    scheduled_publish_at: datetime | None = Field(
        default=None,
        description="ISO 8601 scheduled publish time; None = publish immediately on green",
    )


class YouTubeUploadResult(BaseModel):
    """Result of the complete 5-step upload flow."""

    youtube_video_id: str
    youtube_url: str
    privacy_status: str = Field(description="private, public, or unlisted")
    ad_suitability: str = Field(description="green, yellow, red, or pending")
    content_id_claims: list[dict[str, object]] = Field(default_factory=list)
    thumbnail_set: bool = False
    playlist_added: bool = False
    captions_uploaded: bool = False
    quota_units_used: int = 0
    upload_duration_seconds: float = 0.0


class YouTubeVideoStatus(BaseModel):
    """Parsed response from YouTube videos.list with part=status,contentDetails."""

    youtube_video_id: str
    upload_status: str = Field(description="uploaded, processed, deleted, rejected, or failed")
    privacy_status: str
    ad_suitability: str = Field(description="green, yellow, red, or pending")
    made_for_kids: bool = False
    content_rating_flags: list[str] = Field(default_factory=list)
    failure_reason: str | None = None
    rejection_reason: str | None = None


class VideoStats(BaseModel):
    """YouTube video statistics from videos.list."""

    youtube_video_id: str
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    favorite_count: int = 0
