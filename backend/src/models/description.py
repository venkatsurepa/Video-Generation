from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from src.models.script import SceneBreakdown


class SourceCitation(BaseModel):
    """A single source reference for the video description."""

    title: str = Field(min_length=1, max_length=300)
    source_type: Literal[
        "court_document",
        "news_article",
        "government_report",
        "academic",
        "other",
    ]
    url: str | None = None
    publication_date: date | None = None
    timestamp_reference: str | None = Field(
        default=None,
        description='Video timestamp where this source is cited, e.g. "3:45"',
    )


class AffiliateConfig(BaseModel):
    """Per-channel affiliate link configuration.

    All links should be Geniuslink URLs for automatic geo-localisation
    across 19+ Amazon storefronts.
    """

    vpn_link: str | None = None
    vpn_name: str = "NordVPN"
    audible_link: str | None = None
    security_link: str | None = None
    security_name: str = "SimpliSafe"
    amazon_tag: str | None = Field(default=None, description="Amazon Associates tag")
    geniuslink_base: str | None = None
    ko_fi_url: str | None = None
    discord_invite: str | None = None
    podcast_url: str | None = None


class ChannelLinks(BaseModel):
    """Static channel links that appear in every description."""

    subscribe_url: str | None = None
    podcast_url: str | None = None
    discord_invite: str | None = None
    ko_fi_url: str | None = None
    twitter_url: str | None = None
    instagram_url: str | None = None


class DescriptionInput(BaseModel):
    """Everything needed to generate a complete YouTube description."""

    video_id: uuid.UUID
    title: str = Field(max_length=100)
    case_summary: str = Field(description="3-5 sentence keyword-rich case summary")
    scenes: list[SceneBreakdown] = Field(description="Scene breakdown for chapter generation")
    sources: list[SourceCitation] = Field(default_factory=list)
    affiliate_config: AffiliateConfig = Field(
        default_factory=AffiliateConfig,
    )
    channel_links: ChannelLinks = Field(default_factory=ChannelLinks)
    hashtags: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="3-5 hashtags; first 3 appear above the video title",
    )
    related_book_title: str | None = None
    related_book_asin: str | None = None
