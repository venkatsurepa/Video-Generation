from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Literal

import httpx
import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from psycopg.rows import dict_row

from src.api.rate_limit import RATE_ANALYTICS_COLLECT, limiter
from src.dependencies import DbDep, DbPoolDep, SettingsDep
from src.models.analytics import (
    ChannelDailySummary,
    CollectionResult,
    DailyMetricResponse,
    VideoProfitability,
)

logger = structlog.get_logger()

router = APIRouter()

# ---------------------------------------------------------------------------
# SQL constants (read-only queries for the API layer)
# ---------------------------------------------------------------------------

_GET_CHANNEL_SUMMARY: str = """
SELECT channel_id, metric_date,
       total_views, total_watch_minutes, avg_ctr,
       total_likes, net_subscribers, total_revenue
FROM mv_channel_daily_summary
WHERE channel_id = %(channel_id)s
  AND metric_date >= %(start_date)s
  AND metric_date <= %(end_date)s
ORDER BY metric_date DESC;
"""

_GET_VIDEO_METRICS: str = """
SELECT video_id, metric_date,
       views, estimated_minutes_watched,
       average_view_duration_seconds, average_view_percentage,
       impressions, ctr,
       likes, dislikes, comments, shares,
       subscribers_gained, subscribers_lost,
       estimated_revenue,
       traffic_source_breakdown, audience_retention_curve,
       fetched_at
FROM video_daily_metrics
WHERE video_id = %(video_id)s
  AND metric_date >= %(start_date)s
  AND metric_date <= %(end_date)s
ORDER BY metric_date DESC;
"""

_GET_VIDEO_RETENTION: str = """
SELECT audience_retention_curve
FROM video_daily_metrics
WHERE video_id = %(video_id)s
  AND audience_retention_curve IS NOT NULL
ORDER BY metric_date DESC
LIMIT 1;
"""

_GET_VIDEO_PROFITABILITY: str = """
SELECT video_id, title, published_at,
       channel_id, channel_name,
       lifetime_views, lifetime_watch_minutes,
       lifetime_revenue, generation_cost,
       net_profit, roi_ratio, profitability_status
FROM mv_video_profitability
WHERE video_id = %(video_id)s;
"""

_GET_TOP_VIDEOS: str = """
SELECT video_id, title, published_at,
       channel_id, channel_name,
       lifetime_views, lifetime_watch_minutes,
       lifetime_revenue, generation_cost,
       net_profit, roi_ratio, profitability_status
FROM mv_video_profitability
WHERE channel_id = %(channel_id)s
ORDER BY {sort_col} DESC
LIMIT %(limit)s;
"""

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/channel/{channel_id}/summary",
    response_model=list[ChannelDailySummary],
)
async def get_channel_summary(
    channel_id: uuid.UUID,
    db: DbDep,
    start_date: date = Query(
        default_factory=lambda: date.today() - timedelta(days=30),
    ),
    end_date: date = Query(default_factory=date.today),
) -> list[ChannelDailySummary]:
    """Return daily aggregated metrics for a channel."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            _GET_CHANNEL_SUMMARY,
            {
                "channel_id": channel_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        rows = await cur.fetchall()
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No summary data found for this channel",
        )
    return [ChannelDailySummary.from_row(r) for r in rows]


@router.get(
    "/video/{video_id}/metrics",
    response_model=list[DailyMetricResponse],
)
async def get_video_metrics(
    video_id: uuid.UUID,
    db: DbDep,
    start_date: date = Query(
        default_factory=lambda: date.today() - timedelta(days=30),
    ),
    end_date: date = Query(default_factory=date.today),
) -> list[DailyMetricResponse]:
    """Return a time-series of daily metrics for a single video."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            _GET_VIDEO_METRICS,
            {
                "video_id": video_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        rows = await cur.fetchall()
    return [DailyMetricResponse.from_row(r) for r in rows]


@router.get("/video/{video_id}/retention")
async def get_video_retention(
    video_id: uuid.UUID,
    db: DbDep,
) -> dict[str, object]:
    """Return the latest audience retention curve for a video.

    The curve is stored as a JSONB array of ~100 data-points, each with
    ``elapsed_ratio``, ``absolute_retention``, and ``relative_retention``.
    """
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(_GET_VIDEO_RETENTION, {"video_id": video_id})
        row = await cur.fetchone()
    if row is None or row["audience_retention_curve"] is None:
        raise HTTPException(
            status_code=404,
            detail="No retention data available for this video",
        )
    return {
        "video_id": str(video_id),
        "retention_curve": row["audience_retention_curve"],
    }


@router.get(
    "/video/{video_id}/profitability",
    response_model=VideoProfitability,
)
async def get_video_profitability(
    video_id: uuid.UUID,
    db: DbDep,
) -> VideoProfitability:
    """Return lifetime profitability data for a video."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            _GET_VIDEO_PROFITABILITY,
            {"video_id": video_id},
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Profitability data not found",
        )
    return VideoProfitability.from_row(row)


@router.get(
    "/channel/{channel_id}/top-videos",
    response_model=list[VideoProfitability],
)
async def get_top_videos(
    channel_id: uuid.UUID,
    db: DbDep,
    sort_by: Literal[
        "lifetime_views",
        "lifetime_revenue",
        "roi_ratio",
        "net_profit",
    ] = "lifetime_views",
    limit: int = Query(default=20, ge=1, le=100),
) -> list[VideoProfitability]:
    """Return top videos for a channel sorted by the chosen metric."""
    # sort_by is validated by Literal, safe to interpolate.
    query = _GET_TOP_VIDEOS.format(sort_col=sort_by)
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            query,
            {"channel_id": channel_id, "limit": limit},
        )
        rows = await cur.fetchall()
    return [VideoProfitability.from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Manual trigger endpoints
# ---------------------------------------------------------------------------


@router.post("/collect", response_model=CollectionResult, status_code=202)
@limiter.limit(RATE_ANALYTICS_COLLECT)
async def trigger_collection(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> CollectionResult:
    """Manually trigger a full daily analytics collection.

    Returns 202 immediately; the collection runs in the background.
    The response body contains a skeleton result — poll the analytics
    endpoints to see the collected data.
    """
    background_tasks.add_task(_run_daily_collection, settings, pool)
    return CollectionResult(
        videos_collected=0,
        channels_processed=0,
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() - timedelta(days=1),
        errors=[],
        duration_seconds=0,
    )


@router.post("/collect/realtime", status_code=202)
@limiter.limit(RATE_ANALYTICS_COLLECT)
async def trigger_realtime_collection(
    request: Request,
    background_tasks: BackgroundTasks,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> dict[str, str]:
    """Manually trigger a Tier-1 real-time stats collection."""
    background_tasks.add_task(_run_realtime_collection, settings, pool)
    return {"status": "realtime_collection_started"}


# ---------------------------------------------------------------------------
# Background task runners
# ---------------------------------------------------------------------------


async def _run_daily_collection(
    settings: object,
    pool: object,
) -> None:
    from src.services.analytics_collector import AnalyticsCollector

    async with httpx.AsyncClient() as client:
        collector = AnalyticsCollector(
            settings,  # type: ignore[arg-type]
            client,
            pool,  # type: ignore[arg-type]
        )
        result = await collector.collect_daily_metrics()
    await logger.ainfo(
        "manual_daily_collection_complete",
        videos=result.videos_collected,
        errors=len(result.errors),
    )


async def _run_realtime_collection(
    settings: object,
    pool: object,
) -> None:
    from src.services.analytics_collector import AnalyticsCollector

    async with httpx.AsyncClient() as client:
        collector = AnalyticsCollector(
            settings,  # type: ignore[arg-type]
            client,
            pool,  # type: ignore[arg-type]
        )
        updated = await collector.collect_realtime_stats()
    await logger.ainfo(
        "manual_realtime_collection_complete",
        updated=updated,
    )
