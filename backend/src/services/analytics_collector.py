"""YouTube Analytics collection service — daily + real-time metrics.

Implements two tiers of data collection from the project bible:

Tier 1 — Near-real-time (every 6 hours):
    YouTube Data API v3 ``videos.list?part=statistics`` for view/like/comment
    counts.  1 quota unit per 50 videos.

Tier 2 — Rich daily metrics (once per day at 06:00 UTC):
    YouTube Analytics API v2 ``reports`` for watch-time, retention, traffic
    sources, subscriber changes, and estimated revenue.  Data arrives with
    a 48-72 h delay; revenue finalises over ~60 days.

OAuth tokens are managed with the same pattern as the YouTube uploader:
refresh tokens live in ``channel_credentials``, access tokens are cached
in memory and refreshed 5 min before expiry.
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from psycopg.rows import dict_row

if TYPE_CHECKING:
    import uuid

    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings
    from src.models.analytics import (
        Anomaly,
        CollectionResult,
        DailyMetricRow,
        RetentionCurve,
        RetentionDataPoint,
        TrafficSourceBreakdown,
    )

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

YOUTUBE_API_BASE: str = "https://www.googleapis.com/youtube/v3"
YOUTUBE_ANALYTICS_BASE: str = "https://youtubeanalytics.googleapis.com/v2"
OAUTH_TOKEN_URL: str = "https://oauth2.googleapis.com/token"

DATA_API_BATCH_SIZE: int = 50  # max video IDs per videos.list call
MAX_API_RETRIES: int = 3
RETRY_CAP_SECONDS: float = 64.0
API_TIMEOUT: float = 30.0
TOKEN_REFRESH_BUFFER: int = 300  # refresh 5 min before expiry
RETENTION_CONCURRENCY: int = 5  # parallel retention/traffic calls

# Metrics requested from the YouTube Analytics API (Tier 2).
_DAILY_METRICS: str = ",".join(
    [
        "views",
        "estimatedMinutesWatched",
        "averageViewDuration",
        "averageViewPercentage",
        "subscribersGained",
        "subscribersLost",
        "likes",
        "dislikes",
        "comments",
        "shares",
        "estimatedRevenue",
    ]
)

# Map Analytics API column names → DailyMetricRow field names.
_METRIC_FIELD_MAP: dict[str, str] = {
    "views": "views",
    "estimatedMinutesWatched": "estimated_minutes_watched",
    "averageViewDuration": "average_view_duration_seconds",
    "averageViewPercentage": "average_view_percentage",
    "subscribersGained": "subscribers_gained",
    "subscribersLost": "subscribers_lost",
    "likes": "likes",
    "dislikes": "dislikes",
    "comments": "comments",
    "shares": "shares",
    "estimatedRevenue": "estimated_revenue",
}


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_GET_ACTIVE_CHANNELS: str = """
SELECT id, youtube_channel_id
FROM channels
WHERE status = 'active'
  AND youtube_channel_id != '';
"""

_GET_PUBLISHED_VIDEOS: str = """
SELECT id, youtube_video_id
FROM videos
WHERE channel_id = %(channel_id)s
  AND youtube_video_id IS NOT NULL
  AND status = 'published';
"""

_GET_CHANNEL_FOR_VIDEOS: str = """
SELECT DISTINCT v.channel_id, c.youtube_channel_id
FROM videos v
JOIN channels c ON c.id = v.channel_id
WHERE v.youtube_video_id = ANY(%(yt_ids)s);
"""

_UPSERT_DAILY_METRIC: str = """
INSERT INTO video_daily_metrics (
    video_id, metric_date,
    views, estimated_minutes_watched, average_view_duration_seconds,
    average_view_percentage, impressions, ctr,
    likes, dislikes, comments, shares,
    subscribers_gained, subscribers_lost, estimated_revenue,
    traffic_source_breakdown, audience_retention_curve,
    fetched_at
)
VALUES (
    %(video_id)s, %(metric_date)s,
    %(views)s, %(estimated_minutes_watched)s,
    %(average_view_duration_seconds)s, %(average_view_percentage)s,
    %(impressions)s, %(ctr)s,
    %(likes)s, %(dislikes)s, %(comments)s, %(shares)s,
    %(subscribers_gained)s, %(subscribers_lost)s, %(estimated_revenue)s,
    %(traffic_source_breakdown)s, %(audience_retention_curve)s,
    now()
)
ON CONFLICT (video_id, metric_date) DO UPDATE SET
    views                         = EXCLUDED.views,
    estimated_minutes_watched     = EXCLUDED.estimated_minutes_watched,
    average_view_duration_seconds = EXCLUDED.average_view_duration_seconds,
    average_view_percentage       = EXCLUDED.average_view_percentage,
    impressions                   = EXCLUDED.impressions,
    ctr                           = EXCLUDED.ctr,
    likes                         = EXCLUDED.likes,
    dislikes                      = EXCLUDED.dislikes,
    comments                      = EXCLUDED.comments,
    shares                        = EXCLUDED.shares,
    subscribers_gained            = EXCLUDED.subscribers_gained,
    subscribers_lost              = EXCLUDED.subscribers_lost,
    estimated_revenue             = EXCLUDED.estimated_revenue,
    traffic_source_breakdown      = COALESCE(EXCLUDED.traffic_source_breakdown,
                                             video_daily_metrics.traffic_source_breakdown),
    audience_retention_curve      = COALESCE(EXCLUDED.audience_retention_curve,
                                             video_daily_metrics.audience_retention_curve),
    fetched_at                    = now();
"""

_GET_RECENT_METRICS: str = """
SELECT video_id, metric_date, views, estimated_revenue,
       subscribers_gained, subscribers_lost
FROM video_daily_metrics
WHERE video_id IN (
    SELECT id FROM videos WHERE channel_id = %(channel_id)s
)
AND metric_date >= %(since)s
ORDER BY video_id, metric_date DESC;
"""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AnalyticsCollectionError(Exception):
    """Raised on unrecoverable analytics collection failures."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AnalyticsCollector:
    """Collects YouTube analytics data on a daily schedule.

    Parameters
    ----------
    settings:
        Application settings (YouTube OAuth credentials, Supabase config).
    http_client:
        Shared ``httpx.AsyncClient`` for all HTTP calls.
    db_pool:
        Async connection pool for direct DB access (the collector runs
        outside of the request-response cycle).
    """

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
        db_pool: AsyncConnectionPool,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._pool = db_pool
        self._token_cache: dict[uuid.UUID, tuple[str, float]] = {}

    # ==================================================================
    # OAuth — same pattern as YouTubeUploader
    # ==================================================================

    async def _get_access_token(self, channel_id: uuid.UUID) -> str:
        """Return a valid OAuth access token, refreshing if necessary."""
        cached = self._token_cache.get(channel_id)
        if cached is not None:
            token, expires_at = cached
            if time.monotonic() < expires_at - TOKEN_REFRESH_BUFFER:
                return token

        refresh_token = await self._fetch_refresh_token(channel_id)
        access_token, expires_in = await self._exchange_refresh_token(
            refresh_token,
        )
        self._token_cache[channel_id] = (
            access_token,
            time.monotonic() + expires_in,
        )
        await logger.ainfo(
            "oauth_token_refreshed",
            channel_id=str(channel_id),
            expires_in=expires_in,
        )
        return access_token

    async def _fetch_refresh_token(self, channel_id: uuid.UUID) -> str:
        """Retrieve the YouTube OAuth refresh token from
        ``channel_credentials`` via the Supabase REST API.
        """
        supabase_url = self._settings.database.url
        service_key = self._settings.database.service_role_key

        resp = await self._http.get(
            f"{supabase_url}/rest/v1/channel_credentials",
            params={
                "select": "youtube_oauth_refresh_token_encrypted",
                "channel_id": f"eq.{channel_id}",
            },
            headers={
                "apikey": service_key,
                "Authorization": f"Bearer {service_key}",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        rows = resp.json()

        if not rows:
            raise AnalyticsCollectionError(f"No credentials found for channel {channel_id}")
        token: str | None = rows[0].get(
            "youtube_oauth_refresh_token_encrypted",
        )
        if not token:
            raise AnalyticsCollectionError(f"Refresh token is empty for channel {channel_id}")
        return token

    async def _exchange_refresh_token(
        self,
        refresh_token: str,
    ) -> tuple[str, int]:
        """Exchange a refresh token for a short-lived access token.

        Returns ``(access_token, expires_in_seconds)``.
        """
        resp = await self._http.post(
            OAUTH_TOKEN_URL,
            data={
                "client_id": self._settings.youtube.client_id,
                "client_secret": self._settings.youtube.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )
        if resp.status_code == 400:
            body = resp.json()
            if body.get("error") == "invalid_grant":
                raise AnalyticsCollectionError(
                    "Refresh token revoked or expired — re-authenticate the channel."
                )
            raise AnalyticsCollectionError(f"OAuth token exchange failed: {body}")
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"], int(data.get("expires_in", 3600))

    # ==================================================================
    # Authenticated API helpers
    # ==================================================================

    async def _api_get(
        self,
        url: str,
        *,
        channel_id: uuid.UUID,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Authenticated GET with retry + automatic token refresh.

        Retries on 401 (evicts cached token), 5xx, and network errors.
        Returns the parsed JSON body.
        """
        last_exc: BaseException | None = None

        for attempt in range(MAX_API_RETRIES):
            token = await self._get_access_token(channel_id)
            headers = {"Authorization": f"Bearer {token}"}

            try:
                resp = await self._http.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=API_TIMEOUT,
                )
            except (
                httpx.ConnectError,
                httpx.ReadTimeout,
                ConnectionError,
                TimeoutError,
            ) as exc:
                last_exc = exc
                if attempt < MAX_API_RETRIES - 1:
                    delay = min(
                        (2**attempt) * random.random(),
                        RETRY_CAP_SECONDS,
                    )
                    await logger.awarning(
                        "analytics_api_network_error",
                        attempt=attempt + 1,
                        delay=round(delay, 2),
                        error=str(exc),
                    )
                    await asyncio.sleep(delay)
                    continue
                raise AnalyticsCollectionError(
                    f"Network error after {MAX_API_RETRIES} attempts: {exc}"
                ) from exc

            if resp.status_code == 401:
                self._token_cache.pop(channel_id, None)
                if attempt < MAX_API_RETRIES - 1:
                    await logger.awarning("analytics_api_401_refreshing")
                    continue
                raise AnalyticsCollectionError("YouTube API returned 401 after token refresh")

            if resp.status_code >= 500:
                last_exc = httpx.HTTPStatusError(
                    f"Server error {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                if attempt < MAX_API_RETRIES - 1:
                    delay = min(
                        (2**attempt) * random.random(),
                        RETRY_CAP_SECONDS,
                    )
                    await logger.awarning(
                        "analytics_api_server_error",
                        status=resp.status_code,
                        delay=round(delay, 2),
                    )
                    await asyncio.sleep(delay)
                    continue

            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result

        if last_exc is not None:
            raise AnalyticsCollectionError(str(last_exc)) from last_exc
        raise AnalyticsCollectionError("API retry loop exited unexpectedly")

    async def _analytics_report(
        self,
        channel_id: uuid.UUID,
        yt_channel_id: str,
        start_date: date,
        end_date: date,
        metrics: str,
        dimensions: str,
        filters: str | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        """Execute a YouTube Analytics API v2 report query."""
        params: dict[str, str] = {
            "ids": f"channel=={yt_channel_id}",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "metrics": metrics,
            "dimensions": dimensions,
        }
        if filters:
            params["filters"] = filters
        if sort:
            params["sort"] = sort

        return await self._api_get(
            f"{YOUTUBE_ANALYTICS_BASE}/reports",
            channel_id=channel_id,
            params=params,
        )

    # ==================================================================
    # DB helpers
    # ==================================================================

    async def _get_active_channels(
        self,
    ) -> list[dict[str, Any]]:
        """Return all active channels with a linked YouTube channel ID."""
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_GET_ACTIVE_CHANNELS)
            rows: list[dict[str, Any]] = await cur.fetchall()
        return rows

    async def _get_video_mapping(
        self,
        channel_id: uuid.UUID,
    ) -> dict[str, uuid.UUID]:
        """Return ``{youtube_video_id: internal_video_id}`` for published
        videos in *channel_id*.
        """
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                _GET_PUBLISHED_VIDEOS,
                {"channel_id": channel_id},
            )
            rows = await cur.fetchall()
        return {
            str(row["youtube_video_id"]): row["id"] for row in rows if row.get("youtube_video_id")
        }

    async def _get_published_video_ids(
        self,
        channel_id: uuid.UUID,
    ) -> list[str]:
        """Return YouTube video IDs for published videos in *channel_id*."""
        mapping = await self._get_video_mapping(channel_id)
        return list(mapping.keys())

    async def _upsert_daily_metrics(
        self,
        metrics: list[DailyMetricRow],
    ) -> int:
        """Upsert rows into ``video_daily_metrics``.

        Uses ``ON CONFLICT (video_id, metric_date) DO UPDATE``.
        Returns the number of rows upserted.
        """
        if not metrics:
            return 0

        import orjson

        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                for m in metrics:
                    await cur.execute(
                        _UPSERT_DAILY_METRIC,
                        {
                            "video_id": m.video_id,
                            "metric_date": m.metric_date,
                            "views": m.views,
                            "estimated_minutes_watched": m.estimated_minutes_watched,
                            "average_view_duration_seconds": m.average_view_duration_seconds,
                            "average_view_percentage": m.average_view_percentage,
                            "impressions": m.impressions,
                            "ctr": m.ctr,
                            "likes": m.likes,
                            "dislikes": m.dislikes,
                            "comments": m.comments,
                            "shares": m.shares,
                            "subscribers_gained": m.subscribers_gained,
                            "subscribers_lost": m.subscribers_lost,
                            "estimated_revenue": m.estimated_revenue,
                            "traffic_source_breakdown": (
                                orjson.dumps(m.traffic_source_breakdown).decode()
                                if m.traffic_source_breakdown
                                else None
                            ),
                            "audience_retention_curve": (
                                orjson.dumps(m.audience_retention_curve).decode()
                                if m.audience_retention_curve
                                else None
                            ),
                        },
                    )
            await conn.commit()

        return len(metrics)

    # ==================================================================
    # Core collection — Tier 2 (daily, rich metrics)
    # ==================================================================

    async def collect_daily_metrics(self) -> CollectionResult:
        """Run the full daily collection across all active channels.

        Intended to run at 06:00 UTC via pg_cron or an external scheduler.
        Collects yesterday's metrics (data arrives with 48-72 h delay,
        so some back-fill is normal).
        """
        from src.models.analytics import CollectionResult

        t0 = time.monotonic()
        yesterday = date.today() - timedelta(days=1)
        errors: list[str] = []
        total_videos = 0

        channels = await self._get_active_channels()
        await logger.ainfo(
            "daily_collection_start",
            channels=len(channels),
            metric_date=yesterday.isoformat(),
        )

        for ch in channels:
            channel_id: uuid.UUID = ch["id"]
            yt_channel_id: str = ch["youtube_channel_id"]
            try:
                count = await self._collect_channel_daily(
                    channel_id,
                    yt_channel_id,
                    yesterday,
                )
                total_videos += count
            except Exception as exc:
                msg = f"channel {channel_id}: {exc}"
                errors.append(msg)
                await logger.aerror(
                    "daily_collection_channel_error",
                    channel_id=str(channel_id),
                    error=str(exc),
                )

        # Post-collection housekeeping
        try:
            await self.refresh_materialized_views()
        except Exception as exc:
            errors.append(f"matview refresh: {exc}")

        duration = time.monotonic() - t0
        result = CollectionResult(
            videos_collected=total_videos,
            channels_processed=len(channels),
            start_date=yesterday,
            end_date=yesterday,
            errors=errors,
            duration_seconds=round(duration, 2),
        )
        await logger.ainfo(
            "daily_collection_complete",
            videos=total_videos,
            channels=len(channels),
            errors=len(errors),
            duration=round(duration, 2),
        )
        return result

    async def _collect_channel_daily(
        self,
        channel_id: uuid.UUID,
        yt_channel_id: str,
        metric_date: date,
    ) -> int:
        """Collect daily metrics for one channel.  Returns video count."""
        from src.models.analytics import DailyMetricRow

        video_map = await self._get_video_mapping(channel_id)
        if not video_map:
            return 0

        # 1 — Main metrics report (all videos, one row each)
        report = await self._analytics_report(
            channel_id=channel_id,
            yt_channel_id=yt_channel_id,
            start_date=metric_date,
            end_date=metric_date,
            metrics=_DAILY_METRICS,
            dimensions="video",
            sort="-views",
        )

        columns = [h["name"] for h in report.get("columnHeaders", [])]
        rows: list[list[Any]] = report.get("rows", [])

        metrics: list[DailyMetricRow] = []
        yt_ids_collected: list[str] = []

        for row in rows:
            row_dict = dict(zip(columns, row, strict=False))
            yt_id = str(row_dict.get("video", ""))
            internal_id = video_map.get(yt_id)
            if internal_id is None:
                continue

            fields: dict[str, Any] = {
                "video_id": internal_id,
                "youtube_video_id": yt_id,
                "metric_date": metric_date,
            }
            for api_name, field_name in _METRIC_FIELD_MAP.items():
                if api_name in row_dict:
                    fields[field_name] = row_dict[api_name]

            metrics.append(DailyMetricRow.model_validate(fields))
            yt_ids_collected.append(yt_id)

        # 2 — Retention curves + traffic sources (concurrent, rate-limited)
        if yt_ids_collected:
            sem = asyncio.Semaphore(RETENTION_CONCURRENCY)

            async def _fetch_extras(yt_id: str) -> None:
                async with sem:
                    # Find the DailyMetricRow for this video
                    metric_row = next(
                        (m for m in metrics if m.youtube_video_id == yt_id),
                        None,
                    )
                    if metric_row is None:
                        return

                    try:
                        curves = await self._fetch_retention(
                            channel_id,
                            yt_channel_id,
                            yt_id,
                            metric_date,
                        )
                        if curves:
                            metric_row.audience_retention_curve = [
                                {
                                    "elapsed_ratio": p.elapsed_ratio,
                                    "absolute_retention": p.absolute_retention,
                                    "relative_retention": p.relative_retention,
                                }
                                for p in curves
                            ]
                    except Exception:
                        await logger.awarning(
                            "retention_fetch_failed",
                            video=yt_id,
                        )

                    try:
                        sources = await self._fetch_traffic(
                            channel_id,
                            yt_channel_id,
                            yt_id,
                            metric_date,
                        )
                        if sources:
                            metric_row.traffic_source_breakdown = sources
                    except Exception:
                        await logger.awarning(
                            "traffic_fetch_failed",
                            video=yt_id,
                        )

            await asyncio.gather(
                *[_fetch_extras(yt_id) for yt_id in yt_ids_collected],
            )

        # 3 — Upsert everything
        upserted = await self._upsert_daily_metrics(metrics)
        await logger.ainfo(
            "channel_daily_collected",
            channel_id=str(channel_id),
            videos=upserted,
        )
        return upserted

    async def _fetch_retention(
        self,
        channel_id: uuid.UUID,
        yt_channel_id: str,
        yt_video_id: str,
        metric_date: date,
    ) -> list[RetentionDataPoint]:
        """Fetch retention curve data for a single video."""
        from src.models.analytics import RetentionDataPoint

        report = await self._analytics_report(
            channel_id=channel_id,
            yt_channel_id=yt_channel_id,
            start_date=metric_date,
            end_date=metric_date,
            metrics="audienceWatchRatio,relativeRetentionPerformance",
            dimensions="elapsedVideoTimeRatio",
            filters=f"video=={yt_video_id}",
        )
        columns = [h["name"] for h in report.get("columnHeaders", [])]
        points: list[RetentionDataPoint] = []
        for row in report.get("rows", []):
            d = dict(zip(columns, row, strict=False))
            points.append(
                RetentionDataPoint(
                    elapsed_ratio=float(d.get("elapsedVideoTimeRatio", 0)),
                    absolute_retention=float(
                        d.get("audienceWatchRatio", 0),
                    ),
                    relative_retention=float(
                        d.get("relativeRetentionPerformance", 0),
                    ),
                )
            )
        return points

    async def _fetch_traffic(
        self,
        channel_id: uuid.UUID,
        yt_channel_id: str,
        yt_video_id: str,
        metric_date: date,
    ) -> dict[str, int]:
        """Fetch traffic source breakdown for a single video."""
        report = await self._analytics_report(
            channel_id=channel_id,
            yt_channel_id=yt_channel_id,
            start_date=metric_date,
            end_date=metric_date,
            metrics="views",
            dimensions="insightTrafficSourceType",
            filters=f"video=={yt_video_id}",
        )
        columns = [h["name"] for h in report.get("columnHeaders", [])]
        sources: dict[str, int] = {}
        for row in report.get("rows", []):
            d = dict(zip(columns, row, strict=False))
            source_type = str(d.get("insightTrafficSourceType", "UNKNOWN"))
            sources[source_type] = int(d.get("views", 0))
        return sources

    # ==================================================================
    # Public wrappers for retention / traffic (spec interface)
    # ==================================================================

    async def collect_retention_curves(
        self,
        video_ids: list[str],
    ) -> list[RetentionCurve]:
        """Fetch retention curves for a list of YouTube video IDs.

        Returns ~100 data-points per video (elapsed_ratio 0.0–1.0).
        """
        from src.models.analytics import RetentionCurve

        if not video_ids:
            return []

        # Look up channel for the first video
        channel_id, yt_channel_id = await self._resolve_channel(
            video_ids[0],
        )
        yesterday = date.today() - timedelta(days=1)
        sem = asyncio.Semaphore(RETENTION_CONCURRENCY)
        results: list[RetentionCurve] = []

        async def _fetch(yt_id: str) -> None:
            async with sem:
                points = await self._fetch_retention(
                    channel_id,
                    yt_channel_id,
                    yt_id,
                    yesterday,
                )
                results.append(
                    RetentionCurve(
                        video_id=yt_id,
                        data_points=points,
                    )
                )

        await asyncio.gather(*[_fetch(vid) for vid in video_ids])
        return results

    async def collect_traffic_sources(
        self,
        video_ids: list[str],
    ) -> list[TrafficSourceBreakdown]:
        """Fetch traffic source breakdown for a list of YouTube video IDs."""
        from src.models.analytics import TrafficSourceBreakdown

        if not video_ids:
            return []

        channel_id, yt_channel_id = await self._resolve_channel(
            video_ids[0],
        )
        yesterday = date.today() - timedelta(days=1)
        sem = asyncio.Semaphore(RETENTION_CONCURRENCY)
        results: list[TrafficSourceBreakdown] = []

        async def _fetch(yt_id: str) -> None:
            async with sem:
                sources = await self._fetch_traffic(
                    channel_id,
                    yt_channel_id,
                    yt_id,
                    yesterday,
                )
                results.append(
                    TrafficSourceBreakdown(
                        video_id=yt_id,
                        sources=sources,
                    )
                )

        await asyncio.gather(*[_fetch(vid) for vid in video_ids])
        return results

    async def _resolve_channel(
        self,
        youtube_video_id: str,
    ) -> tuple[uuid.UUID, str]:
        """Look up ``(channel_id, youtube_channel_id)`` for a video."""
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                _GET_CHANNEL_FOR_VIDEOS,
                {"yt_ids": [youtube_video_id]},
            )
            row = await cur.fetchone()
        if row is None:
            raise AnalyticsCollectionError(f"No channel found for video {youtube_video_id}")
        return row["channel_id"], row["youtube_channel_id"]

    # ==================================================================
    # Tier 1 — real-time stats via Data API v3
    # ==================================================================

    async def collect_realtime_stats(self) -> int:
        """Lightweight real-time collection via Data API v3 ``videos.list``.

        Fetches ``viewCount``, ``likeCount``, ``commentCount`` for all
        published videos.  1 quota unit per 50 videos.  Intended to run
        every 6 hours.

        Returns the number of videos updated.
        """
        channels = await self._get_active_channels()
        total_updated = 0

        for ch in channels:
            channel_id: uuid.UUID = ch["id"]
            try:
                updated = await self._collect_channel_realtime(channel_id)
                total_updated += updated
            except Exception as exc:
                await logger.aerror(
                    "realtime_collection_error",
                    channel_id=str(channel_id),
                    error=str(exc),
                )

        await logger.ainfo(
            "realtime_collection_complete",
            updated=total_updated,
        )
        return total_updated

    async def _collect_channel_realtime(
        self,
        channel_id: uuid.UUID,
    ) -> int:
        """Tier 1 stats for one channel.  Returns count of videos updated."""
        yt_ids = await self._get_published_video_ids(channel_id)
        if not yt_ids:
            return 0

        updated = 0
        # Batch into groups of 50
        for i in range(0, len(yt_ids), DATA_API_BATCH_SIZE):
            batch = yt_ids[i : i + DATA_API_BATCH_SIZE]
            data = await self._api_get(
                f"{YOUTUBE_API_BASE}/videos",
                channel_id=channel_id,
                params={
                    "part": "statistics",
                    "id": ",".join(batch),
                },
            )
            for item in data.get("items", []):
                stats = item.get("statistics", {})
                yt_id = item["id"]
                await logger.adebug(
                    "realtime_stat",
                    video=yt_id,
                    views=stats.get("viewCount"),
                )
                updated += 1

        return updated

    # ==================================================================
    # Post-collection
    # ==================================================================

    async def refresh_materialized_views(self) -> None:
        """Refresh the channel-summary and video-profitability matviews.

        Uses ``CONCURRENTLY`` so reads are not blocked during refresh.
        """
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "REFRESH MATERIALIZED VIEW CONCURRENTLY mv_channel_daily_summary;"
                )
                await cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY mv_video_profitability;")
            await conn.commit()
        await logger.ainfo("materialized_views_refreshed")

    async def detect_anomalies(
        self,
        channel_id: uuid.UUID,
    ) -> list[Anomaly]:
        """Post-collection anomaly detection for a single channel.

        Checks:
        - View count dropped >50 % day-over-day on any video
        - Revenue per view dropped >50 % (CPM collapse)
        - Net subscriber loss for the day
        """
        from src.models.analytics import Anomaly

        since = date.today() - timedelta(days=3)
        now_dt = datetime.now(tz=UTC)

        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                _GET_RECENT_METRICS,
                {"channel_id": channel_id, "since": since},
            )
            rows = await cur.fetchall()

        # Group by video_id, ordered by date desc (most recent first)
        from collections import defaultdict

        by_video: dict[uuid.UUID, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            by_video[row["video_id"]].append(row)

        anomalies: list[Anomaly] = []

        for video_id, days in by_video.items():
            if len(days) < 2:
                continue
            today_row = days[0]
            yesterday_row = days[1]

            today_views = int(today_row["views"] or 0)
            yesterday_views = int(yesterday_row["views"] or 0)

            # Views drop > 50 %
            if yesterday_views > 100 and today_views > 0:
                drop_pct = (yesterday_views - today_views) / yesterday_views
                if drop_pct > 0.5:
                    anomalies.append(
                        Anomaly(
                            video_id=video_id,
                            anomaly_type="views_drop",
                            severity="warning",
                            message=(
                                f"Views dropped {drop_pct:.0%} day-over-day "
                                f"({yesterday_views} → {today_views})"
                            ),
                            current_value=str(today_views),
                            previous_value=str(yesterday_views),
                            detected_at=now_dt,
                        )
                    )

            # CPM collapse
            today_rev = float(today_row["estimated_revenue"] or 0)
            yest_rev = float(yesterday_row["estimated_revenue"] or 0)
            if yesterday_views > 100 and yest_rev > 0 and today_views > 0:
                today_cpm = (today_rev / today_views) * 1000
                yest_cpm = (yest_rev / yesterday_views) * 1000
                if yest_cpm > 0 and (yest_cpm - today_cpm) / yest_cpm > 0.5:
                    anomalies.append(
                        Anomaly(
                            video_id=video_id,
                            anomaly_type="cpm_collapse",
                            severity="critical",
                            message=(f"CPM dropped from ${yest_cpm:.2f} to ${today_cpm:.2f}"),
                            current_value=f"${today_cpm:.2f}",
                            previous_value=f"${yest_cpm:.2f}",
                            detected_at=now_dt,
                        )
                    )

            # Subscriber loss
            gained = int(today_row["subscribers_gained"] or 0)
            lost = int(today_row["subscribers_lost"] or 0)
            if lost > gained and lost > 10:
                anomalies.append(
                    Anomaly(
                        video_id=video_id,
                        anomaly_type="subscriber_loss",
                        severity="info",
                        message=(f"Net subscriber loss: gained {gained}, lost {lost}"),
                        current_value=str(gained - lost),
                        previous_value=f"+{gained}/-{lost}",
                        detected_at=now_dt,
                    )
                )

        if anomalies:
            await logger.awarning(
                "anomalies_detected",
                channel_id=str(channel_id),
                count=len(anomalies),
            )

        return anomalies
