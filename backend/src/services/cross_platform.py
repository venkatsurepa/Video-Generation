"""Cross-platform distribution — publish Shorts to TikTok, IG Reels, FB Reels,
and post to the YouTube Community tab.

Primary path: Repurpose.io API ($35/month trigger-based workflow).
Fallback: Ayrshare unified API ($49/month).
Manual fallback: direct platform APIs (complex, rate-limited).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import structlog

from src.models.distribution import (
    CommunityPost,
    CrossPlatformStats,
    DistributionResult,
    PlatformAnalytics,
    PlatformMetadata,
    PlatformPostResult,
    RepurposeResult,
)
from src.utils.retry import async_retry

if TYPE_CHECKING:
    import uuid

    import httpx
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Platform specs (from bible §7B.6)
# ---------------------------------------------------------------------------

_PLATFORM_SPECS: dict[str, dict[str, Any]] = {
    "tiktok": {
        "min_duration_seconds": 60,  # >1 min for monetization
        "max_caption_chars": 4000,
        "required_hashtags": ["#CrimeTok", "#TrueCrime"],
        "aspect_ratio": "9:16",
    },
    "instagram_reels": {
        "min_duration_seconds": 15,
        "max_duration_seconds": 90,
        "max_caption_chars": 2200,
        "required_hashtags": ["#TrueCrime", "#CriminalMinds"],
        "aspect_ratio": "9:16",
        "clear_zones": {"top_pct": 14, "bottom_pct": 35},
    },
    "facebook_reels": {
        "min_duration_seconds": 15,
        "max_duration_seconds": 90,
        "max_caption_chars": 5000,
        "aspect_ratio": "9:16",
        "clear_zones": {"top_pct": 14, "bottom_pct": 35},
    },
    "twitter": {
        "max_caption_chars": 280,
        "required_hashtags": [],
    },
}

# Optimal posting times per platform (hours in local time)
_OPTIMAL_HOURS: dict[str, list[int]] = {
    "tiktok": [19, 20],  # 7-9 PM (younger audience)
    "instagram_reels": [11, 12, 19, 20],  # 11 AM-1 PM and 7-9 PM
    "facebook_reels": [13, 14, 15],  # 1-4 PM weekdays
    "twitter": [12, 17],  # Noon and 5 PM
}

# Stagger offset in hours per platform to avoid simultaneous flood
_STAGGER_HOURS: dict[str, int] = {
    "tiktok": 0,
    "instagram_reels": 2,
    "facebook_reels": 4,
    "twitter": 3,
}

# ---------------------------------------------------------------------------
# SQL queries (distribution-specific)
# ---------------------------------------------------------------------------

_GET_SHORT_INFO = """
SELECT
    s.id AS short_id, s.parent_video_id, s.title, s.voiceover_r2_key,
    s.render_r2_key, s.duration_seconds,
    v.channel_id, v.youtube_video_id,
    c.name AS channel_name, c.handle AS channel_handle
FROM shorts s
JOIN videos v ON v.id = s.parent_video_id
JOIN channels c ON c.id = v.channel_id
WHERE s.id = %(short_id)s;
"""

_INSERT_DISTRIBUTION = """
INSERT INTO cross_platform_distributions
    (short_id, video_id, platform, method, post_id, post_url, status, scheduled_at)
VALUES
    (%(short_id)s, %(video_id)s, %(platform)s, %(method)s,
     %(post_id)s, %(post_url)s, %(status)s, %(scheduled_at)s)
ON CONFLICT (short_id, platform) DO UPDATE SET
    post_id = EXCLUDED.post_id,
    post_url = EXCLUDED.post_url,
    status = EXCLUDED.status,
    updated_at = now()
RETURNING *;
"""

_GET_DISTRIBUTION_STATS = """
SELECT platform, post_id, post_url, status, views, likes, comments, shares
FROM cross_platform_distributions
WHERE video_id = %(video_id)s AND status != 'cancelled';
"""

_GET_CHANNEL_CREDENTIALS = """
SELECT youtube_oauth_refresh_token_encrypted
FROM channel_credentials
WHERE channel_id = %(channel_id)s;
"""

_INSERT_COMMUNITY_POST = """
INSERT INTO community_posts (channel_id, post_type, text_content, youtube_post_id)
VALUES (%(channel_id)s, %(post_type)s, %(text)s, %(youtube_post_id)s)
RETURNING id;
"""

_GET_SCHEDULE_CONFIG = """
SELECT timezone FROM channel_schedule_config WHERE channel_id = %(channel_id)s;
"""


class CrossPlatformDistributor:
    """Distributes Shorts to TikTok, Instagram Reels, Facebook Reels,
    and manages YouTube Community tab posts."""

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
        db_pool: AsyncConnectionPool,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._pool = db_pool

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def distribute_short(
        self,
        short_video_id: uuid.UUID,
        platforms: list[str],
    ) -> DistributionResult:
        """Distribute a rendered Short to multiple platforms.

        Tries Repurpose.io first, then Ayrshare, then direct API calls.
        """
        # Load short info
        async with self._pool.connection() as conn:
            cur = await conn.execute(_GET_SHORT_INFO, {"short_id": short_video_id})
            short_row = cast("dict[str, Any] | None", await cur.fetchone())

        if short_row is None:
            raise ValueError(f"Short {short_video_id} not found")

        video_url = short_row.get("render_r2_key", "")
        yt_video_id = short_row.get("youtube_video_id", "")
        youtube_url = f"https://youtube.com/shorts/{yt_video_id}" if yt_video_id else ""

        metadata = PlatformMetadata(
            title=short_row["title"] or "",
            description=short_row["title"] or "",
            video_url=video_url,
            original_youtube_url=youtube_url,
        )

        results: list[PlatformPostResult] = []
        method = "repurpose_io"

        # Primary: Repurpose.io
        if self._settings.repurpose.api_key:
            try:
                rp_result = await self.distribute_via_repurpose(
                    youtube_url or video_url,
                    platforms,
                    metadata,
                )
                if rp_result.status != "failed":
                    for p in platforms:
                        results.append(
                            PlatformPostResult(
                                platform=p,  # type: ignore[arg-type]
                                success=True,
                                post_id=rp_result.job_id,
                                posted_at=datetime.utcnow(),
                            )
                        )
                    return self._build_result(
                        short_row["parent_video_id"],
                        results,
                        method,
                    )
            except Exception:
                await logger.awarning(
                    "repurpose_io_failed",
                    short_id=str(short_video_id),
                )

        # Fallback: Ayrshare
        method = "ayrshare"
        if self._settings.ayrshare.api_key:
            try:
                results = await self._distribute_via_ayrshare(
                    video_url or youtube_url,
                    platforms,
                    metadata,
                )
                return self._build_result(
                    short_row["parent_video_id"],
                    results,
                    method,
                )
            except Exception:
                await logger.awarning(
                    "ayrshare_failed",
                    short_id=str(short_video_id),
                )

        # Manual fallback: direct API (stub — each platform requires OAuth)
        method = "direct_api"
        for p in platforms:
            results.append(
                PlatformPostResult(
                    platform=p,  # type: ignore[arg-type]
                    success=False,
                    error="Direct API not configured; set REPURPOSE_IO_API_KEY or AYRSHARE_API_KEY",
                )
            )

        await logger.ainfo(
            "distribution_complete",
            short_id=str(short_video_id),
            method=method,
            succeeded=sum(1 for r in results if r.success),
        )

        # Persist results
        await self._persist_distribution(short_video_id, short_row, results, method)

        return self._build_result(short_row["parent_video_id"], results, method)

    @async_retry(max_attempts=2, base_delay=3.0)
    async def distribute_via_repurpose(
        self,
        video_url: str,
        platforms: list[str],
        metadata: PlatformMetadata,
    ) -> RepurposeResult:
        """Trigger a Repurpose.io workflow to distribute a video.

        Repurpose.io handles video reformatting, hashtag injection,
        scheduled posting, and caption adaptation per platform.
        """
        workflow_id = self._settings.repurpose.workflow_id
        if not workflow_id:
            raise ValueError("REPURPOSE_IO_WORKFLOW_ID not configured")

        resp = await self._http.post(
            "https://api.repurpose.io/v1/workflows/trigger",
            headers={
                "Authorization": f"Bearer {self._settings.repurpose.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "workflow_id": workflow_id,
                "video_url": video_url,
                "title": metadata.title,
                "description": metadata.description,
                "platforms": platforms,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

        return RepurposeResult(
            workflow_id=workflow_id,
            job_id=data.get("job_id", ""),
            status="queued",
            platforms_queued=platforms,
        )

    @async_retry(max_attempts=2, base_delay=3.0)
    async def post_community_update(
        self,
        channel_id: uuid.UUID,
        content: CommunityPost,
    ) -> str:
        """Post to YouTube Community tab.

        Community posts drive 10-15% of video views for engaged channels.
        Cost: 50 quota units per post.

        Types:
        1. Poll — "Which case should we cover next?"
        2. Image + text — "New video dropping [day]"
        3. Text bulletin — behind-the-scenes or case updates
        """
        access_token = await self._get_youtube_token(channel_id)

        # Build activity resource
        snippet: dict[str, Any] = {
            "description": content.text,
        }

        if content.video_id_link:
            # Bulletin that links to a video
            snippet["type"] = "bulletin"
            resource: dict[str, Any] = {
                "snippet": snippet,
                "contentDetails": {
                    "bulletin": {
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": content.video_id_link,
                        },
                    },
                },
            }
        else:
            snippet["type"] = "bulletin"
            resource = {"snippet": snippet}

        resp = await self._http.post(
            "https://www.googleapis.com/youtube/v3/activities",
            params={"part": "snippet,contentDetails"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=resource,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        post_id = data.get("id", "")

        # Persist community post
        async with self._pool.connection() as conn:
            await conn.execute(
                _INSERT_COMMUNITY_POST,
                {
                    "channel_id": channel_id,
                    "post_type": content.post_type,
                    "text": content.text,
                    "youtube_post_id": post_id,
                },
            )
            await conn.commit()

        await logger.ainfo(
            "community_post_created",
            channel_id=str(channel_id),
            post_id=post_id,
            post_type=content.post_type,
        )
        return str(post_id)

    async def generate_platform_captions(
        self,
        title: str,
        description: str,
        platform: str,
    ) -> str:
        """Adapt captions per platform using Claude Haiku.

        - TikTok: shorter, hashtag-heavy, hook question, max 4,000 chars
        - Instagram: storytelling, 5-10 hashtags at end, max 2,200 chars
        - Facebook: longer narrative, link to full video, minimal hashtags
        - Twitter/X: one-line hook + link, max 280 chars
        """
        spec = _PLATFORM_SPECS.get(platform, {})
        max_chars = spec.get("max_caption_chars", 2000)
        required_hashtags = spec.get("required_hashtags", [])
        hashtag_str = " ".join(required_hashtags) if required_hashtags else ""

        system_prompt = (
            "You write captions for true-crime video clips posted on social media. "
            "Be engaging, concise, and include a hook. Never fabricate case details. "
            f"Platform: {platform}. Max length: {max_chars} characters."
        )

        platform_instructions = {
            "tiktok": (
                "Write a short, punchy TikTok caption. Start with a hook question. "
                f"Include these hashtags: {hashtag_str} #FraudExposed #Scam. "
                "Keep it under 4,000 characters. Heavy on hashtags."
            ),
            "instagram_reels": (
                "Write a storytelling Instagram caption. Build intrigue in 2-3 sentences. "
                "Put 5-10 relevant hashtags at the end. Max 2,200 characters."
            ),
            "facebook_reels": (
                "Write a longer narrative Facebook caption. Tell the story hook, "
                "then invite viewers to watch the full video. Minimal hashtags. "
                "Max 5,000 characters."
            ),
            "twitter": (
                "Write a single-line hook for Twitter/X. Punchy, intriguing, "
                "max 250 characters (leave room for link). No hashtags needed."
            ),
        }

        user_prompt = (
            f"Title: {title}\nDescription: {description}\n\n"
            f"Instructions: {platform_instructions.get(platform, 'Write an engaging caption.')}"
        )

        resp = await self._http.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._settings.anthropic.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "system": [{"type": "text", "text": system_prompt}],
                "messages": [{"role": "user", "content": user_prompt}],
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

        caption: str = data["content"][0]["text"].strip()

        # Enforce platform character limit
        if len(caption) > max_chars:
            caption = caption[: max_chars - 3] + "..."

        return caption

    async def schedule_distribution(
        self,
        video_id: uuid.UUID,
        platform_schedule: dict[str, datetime],
    ) -> None:
        """Schedule cross-platform posting at platform-optimal times.

        Stagger by 2-4 hours per platform to avoid simultaneous flood.
        """
        async with self._pool.connection() as conn:
            for platform, scheduled_at in platform_schedule.items():
                await conn.execute(
                    _INSERT_DISTRIBUTION,
                    {
                        "short_id": video_id,
                        "video_id": video_id,
                        "platform": platform,
                        "method": "scheduled",
                        "post_id": "",
                        "post_url": "",
                        "status": "scheduled",
                        "scheduled_at": scheduled_at,
                    },
                )
            await conn.commit()

        await logger.ainfo(
            "distribution_scheduled",
            video_id=str(video_id),
            platforms=list(platform_schedule.keys()),
        )

    async def get_cross_platform_analytics(
        self,
        video_id: uuid.UUID,
    ) -> CrossPlatformStats:
        """Aggregate performance across platforms for a single piece of content."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                _GET_DISTRIBUTION_STATS,
                {"video_id": video_id},
            )
            rows = cast("list[dict[str, Any]]", await cur.fetchall())

        stats_by_platform: dict[str, PlatformAnalytics] = {}
        total_views = total_likes = total_comments = total_shares = 0

        for row in rows:
            pa = PlatformAnalytics(
                platform=row["platform"],
                post_id=row.get("post_id", ""),
                post_url=row.get("post_url", ""),
                views=row.get("views", 0) or 0,
                likes=row.get("likes", 0) or 0,
                comments=row.get("comments", 0) or 0,
                shares=row.get("shares", 0) or 0,
            )
            stats_by_platform[row["platform"]] = pa
            total_views += pa.views
            total_likes += pa.likes
            total_comments += pa.comments
            total_shares += pa.shares

        return CrossPlatformStats(
            video_id=video_id,
            stats_by_platform=stats_by_platform,
            total_views=total_views,
            total_likes=total_likes,
            total_comments=total_comments,
            total_shares=total_shares,
            fetched_at=datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # Optimal scheduling helpers
    # ------------------------------------------------------------------

    def compute_optimal_schedule(
        self,
        base_time: datetime,
        platforms: list[str],
    ) -> dict[str, datetime]:
        """Compute staggered optimal post times per platform.

        - TikTok: 7-9 PM local
        - Instagram: 11 AM-1 PM or 7-9 PM
        - Facebook: 1-4 PM weekdays
        - Stagger by 2-4 hours to avoid simultaneous flood
        """
        schedule: dict[str, datetime] = {}

        for platform in platforms:
            stagger = _STAGGER_HOURS.get(platform, 0)
            optimal_hours = _OPTIMAL_HOURS.get(platform, [14])

            # Pick the first optimal hour that's at least stagger hours after base
            target = base_time + timedelta(hours=stagger)

            # Move to the next optimal hour
            best_hour = optimal_hours[0]
            for h in optimal_hours:
                candidate = target.replace(hour=h, minute=0, second=0, microsecond=0)
                if candidate > target:
                    best_hour = h
                    break

            post_at = target.replace(hour=best_hour, minute=0, second=0, microsecond=0)
            if post_at <= base_time:
                post_at += timedelta(days=1)

            schedule[platform] = post_at

        return schedule

    # ------------------------------------------------------------------
    # Ayrshare fallback
    # ------------------------------------------------------------------

    @async_retry(max_attempts=2, base_delay=3.0)
    async def _distribute_via_ayrshare(
        self,
        video_url: str,
        platforms: list[str],
        metadata: PlatformMetadata,
    ) -> list[PlatformPostResult]:
        """Fallback: Ayrshare unified social media API ($49/month)."""
        # Map our platform names to Ayrshare's
        platform_map = {
            "tiktok": "tiktok",
            "instagram_reels": "instagram",
            "facebook_reels": "facebook",
            "twitter": "twitter",
        }
        ayrshare_platforms = [platform_map.get(p, p) for p in platforms if p in platform_map]

        resp = await self._http.post(
            "https://app.ayrshare.com/api/post",
            headers={
                "Authorization": f"Bearer {self._settings.ayrshare.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "post": metadata.description,
                "platforms": ayrshare_platforms,
                "mediaUrls": [video_url],
                "title": metadata.title,
                "isVideo": True,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()

        results: list[PlatformPostResult] = []
        post_ids = data.get("postIds", {})

        for p in platforms:
            ayrshare_name = platform_map.get(p, p)
            pid = post_ids.get(ayrshare_name, "")
            results.append(
                PlatformPostResult(
                    platform=p,  # type: ignore[arg-type]
                    success=bool(pid),
                    post_id=str(pid) if pid else "",
                    posted_at=datetime.utcnow() if pid else None,
                    error="" if pid else f"No post ID returned for {ayrshare_name}",
                )
            )

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_youtube_token(self, channel_id: uuid.UUID) -> str:
        """Fetch a fresh YouTube access token for the channel."""
        from src.services.youtube_uploader import YouTubeUploader

        uploader = YouTubeUploader(self._settings, self._http)
        return await uploader._get_access_token(channel_id)

    async def _persist_distribution(
        self,
        short_id: uuid.UUID,
        short_row: dict[str, Any],
        results: list[PlatformPostResult],
        method: str,
    ) -> None:
        """Persist distribution results to the database."""
        async with self._pool.connection() as conn:
            for r in results:
                await conn.execute(
                    _INSERT_DISTRIBUTION,
                    {
                        "short_id": short_id,
                        "video_id": short_row["parent_video_id"],
                        "platform": r.platform,
                        "method": method,
                        "post_id": r.post_id,
                        "post_url": r.post_url,
                        "status": "posted" if r.success else "failed",
                        "scheduled_at": r.posted_at,
                    },
                )
            await conn.commit()

    def _build_result(
        self,
        video_id: uuid.UUID,
        results: list[PlatformPostResult],
        method: str,
    ) -> DistributionResult:
        succeeded = sum(1 for r in results if r.success)
        return DistributionResult(
            video_id=video_id,
            platforms=results,
            total_attempted=len(results),
            total_succeeded=succeeded,
            method=method,  # type: ignore[arg-type]
        )
