"""YouTube competitor channel scanner.

Monitors competitor true crime and travel channels for trending videos.
High-view videos on topics we haven't covered = opportunity signals.
Requires YouTube Data API key (YOUTUBE_API_KEY env var).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .base import DiscoveryChannel, DiscoverySource, TopicCandidate

# Competitor channels to seed (YouTube channel IDs)
# These can also be managed via the competitor_channels table
DEFAULT_CRIME_COMPETITORS = [
    # Add YouTube channel IDs here. Examples:
    # {"youtube_channel_id": "UC...", "name": "Coffeezilla", "category": "financial_crime"},
    # {"youtube_channel_id": "UC...", "name": "JCS Criminal Psychology", "category": "true_crime"},
]
DEFAULT_TRAVEL_COMPETITORS = [
    # {"youtube_channel_id": "UC...", "name": "Bright Trip", "category": "travel_safety"},
]

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# View count thresholds for considering a competitor video as a topic signal
VIEW_THRESHOLD_7D = 100_000  # 100K views in first 7 days = strong signal
VIEW_THRESHOLD_30D = 500_000  # 500K views in 30 days = proven topic


class CompetitorScanner(DiscoverySource):
    """Scans competitor YouTube channels for trending video topics."""

    name = "competitor"

    def __init__(self, supabase_client: Any, config: Any | None = None):
        super().__init__(supabase_client, config)
        # CrimeMill Settings is nested: config.youtube.api_key
        youtube = getattr(config, "youtube", None) if config else None
        self.api_key = getattr(youtube, "api_key", None) or None

    async def scan(self) -> list[TopicCandidate]:
        """Scan all tracked competitor channels for high-performing videos."""
        if not self.api_key:
            self.logger.warning("No YOUTUBE_API_KEY configured — skipping competitor scan")
            return []

        candidates: list[TopicCandidate] = []
        competitors = await self._get_competitor_channels()

        async with httpx.AsyncClient(timeout=30.0) as client:
            for comp in competitors:
                try:
                    videos = await self._fetch_recent_videos(client, comp["youtube_channel_id"])
                    for video in videos:
                        candidate = self._evaluate_video(video, comp)
                        if candidate:
                            candidates.append(candidate)
                        # Save video to competitor_videos for tracking
                        await self._save_competitor_video(video, comp["id"])

                    # Update last_scanned_at
                    self.supabase.table("competitor_channels").update(
                        {"last_scanned_at": datetime.now(UTC).isoformat()}
                    ).eq("id", comp["id"]).execute()

                except Exception as e:
                    self.logger.warning(f"Failed to scan competitor {comp.get('name')}: {e}")

        self.logger.info(f"Competitor scan found {len(candidates)} candidates from {len(competitors)} channels")
        return candidates

    async def _get_competitor_channels(self) -> list[dict]:
        """Fetch active competitor channels from DB."""
        result = self.supabase.table("competitor_channels").select("*").eq(
            "is_active", True
        ).execute()
        channels = result.data or []

        # Seed defaults if none exist
        if not channels:
            self.logger.info("No competitor channels configured — seed them via DB or CLI")
        return channels

    async def _fetch_recent_videos(
        self, client: httpx.AsyncClient, channel_id: str, max_results: int = 20
    ) -> list[dict]:
        """Fetch recent videos from a YouTube channel using the Search endpoint."""
        # First get recent video IDs via search
        search_url = f"{YOUTUBE_API_BASE}/search"
        params = {
            "key": self.api_key,
            "channelId": channel_id,
            "part": "snippet",
            "order": "date",
            "maxResults": max_results,
            "type": "video",
            "publishedAfter": (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        resp = await client.get(search_url, params=params)
        resp.raise_for_status()
        search_data = resp.json()

        video_ids = [
            item["id"]["videoId"]
            for item in search_data.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return []

        # Now get statistics for those videos
        stats_url = f"{YOUTUBE_API_BASE}/videos"
        stats_params = {
            "key": self.api_key,
            "id": ",".join(video_ids),
            "part": "snippet,statistics",
        }
        stats_resp = await client.get(stats_url, params=stats_params)
        stats_resp.raise_for_status()
        stats_data = stats_resp.json()

        videos = []
        for item in stats_data.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            videos.append({
                "youtube_video_id": item["id"],
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:1000],
                "published_at": snippet.get("publishedAt", ""),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "comment_count": int(stats.get("commentCount", 0)),
                "channel_title": snippet.get("channelTitle", ""),
            })
        return videos

    def _evaluate_video(self, video: dict, competitor: dict) -> TopicCandidate | None:
        """Evaluate if a competitor video represents a topic we should cover."""
        views = video["view_count"]

        # Calculate days since publish
        try:
            pub_date = datetime.fromisoformat(video["published_at"].replace("Z", "+00:00"))
            days_old = (datetime.now(UTC) - pub_date).days
        except (ValueError, TypeError):
            days_old = 30

        # Check view thresholds
        if days_old <= 7 and views < VIEW_THRESHOLD_7D:
            return None
        if days_old <= 30 and views < VIEW_THRESHOLD_30D:
            return None
        if days_old > 30:
            return None  # Too old to be a fresh signal

        # Determine channel based on competitor category
        comp_category = competitor.get("category", "true_crime")
        if comp_category in ("travel_safety", "travel"):
            channel = DiscoveryChannel.STREET_LEVEL
            category = "destination_safety"
        else:
            channel = DiscoveryChannel.CRIMEMILL
            category = "other"  # Will be refined by scorer

        # Score based on velocity (views per day)
        views_per_day = views / max(days_old, 1)
        score = min(100, (
            min(views_per_day / 5000, 50) +  # Velocity component
            min(video["comment_count"] / 500, 25) +  # Engagement
            min(video["like_count"] / 10000, 25)  # Approval signal
        ))

        return TopicCandidate(
            title=f"Competitor trending: {video['title'][:150]}",
            description=(
                f"Competitor {video['channel_title']} got {views:,} views in {days_old} days on: "
                f"{video['title']}. {video['description'][:300]}"
            ),
            category=category,
            channel=channel,
            source="competitor",
            source_url=f"https://youtube.com/watch?v={video['youtube_video_id']}",
            raw_signals={
                "competitor_name": competitor.get("name"),
                "competitor_channel_id": competitor.get("youtube_channel_id"),
                "views": views,
                "days_old": days_old,
                "views_per_day": round(views_per_day),
                "likes": video["like_count"],
                "comments": video["comment_count"],
            },
            score=score,
        )

    async def _save_competitor_video(self, video: dict, competitor_id: str) -> None:
        """Save or update a competitor video record."""
        try:
            self.supabase.table("competitor_videos").upsert(
                {
                    "competitor_channel_id": competitor_id,
                    "youtube_video_id": video["youtube_video_id"],
                    "title": video["title"][:500],
                    "published_at": video["published_at"],
                    "view_count": video["view_count"],
                    "scanned_at": datetime.now(UTC).isoformat(),
                },
                on_conflict="youtube_video_id",
            ).execute()
        except Exception as e:
            self.logger.debug(f"Failed to save competitor video: {e}")
