"""Series management API endpoints."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.series_planner import SeriesPlanner

import httpx
from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row
from pydantic import BaseModel

from src.db.queries import COUNT_SERIES, GET_SERIES, GET_SERIES_EPISODES, LIST_SERIES
from src.dependencies import DbDep, DbPoolDep, SettingsDep
from src.models.pagination import PaginatedResponse
from src.models.series import (
    CrossVideoHooks,
    SeriesAnalytics,
    SeriesArc,
    SeriesEpisodeResponse,
    SeriesInput,
    SeriesResponse,
    SeriesSuggestionResult,
    SeriesWithEpisodes,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_planner(settings: SettingsDep, pool: DbPoolDep) -> SeriesPlanner:
    """Construct a SeriesPlanner (lazy import to avoid circular deps)."""
    from src.services.series_planner import SeriesPlanner

    http = httpx.AsyncClient(timeout=120.0)
    return SeriesPlanner(settings, http, pool)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=SeriesResponse, status_code=201)
async def create_series(
    body: SeriesInput,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> SeriesResponse:
    """Create a new series."""
    planner = _get_planner(settings, pool)
    return await planner.create_series(body)


@router.get("", response_model=PaginatedResponse[SeriesResponse])
async def list_series(
    db: DbDep,
    channel_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[SeriesResponse]:
    """List series for a channel."""
    params = {
        "channel_id": channel_id,
        "status_filter": status,
        "limit": limit,
        "offset": offset,
    }
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(COUNT_SERIES, params)
        total = (await cur.fetchone() or {}).get("total", 0)
        await cur.execute(LIST_SERIES, params)
        rows = await cur.fetchall()

    return PaginatedResponse(
        items=[SeriesResponse.from_row(dict(r)) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{series_id}", response_model=SeriesWithEpisodes)
async def get_series(series_id: uuid.UUID, db: DbDep) -> SeriesWithEpisodes:
    """Get a series with all its episodes."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(GET_SERIES, {"series_id": series_id})
        series_row = await cur.fetchone()

    if series_row is None:
        raise HTTPException(status_code=404, detail="Series not found")

    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(GET_SERIES_EPISODES, {"series_id": series_id})
        episode_rows = await cur.fetchall()

    return SeriesWithEpisodes(
        series=SeriesResponse.from_row(dict(series_row)),
        episodes=[SeriesEpisodeResponse.from_row(dict(r)) for r in episode_rows],
    )


@router.post("/{series_id}/plan", response_model=SeriesArc)
async def plan_series_arc(
    series_id: uuid.UUID,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> SeriesArc:
    """Generate narrative arc for all episodes using Claude."""
    planner = _get_planner(settings, pool)
    return await planner.plan_series_arc(series_id)


@router.post(
    "/{series_id}/episodes/{episode_number}/hooks",
    response_model=CrossVideoHooks,
)
async def generate_hooks(
    series_id: uuid.UUID,
    episode_number: int,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> CrossVideoHooks:
    """Generate cross-video hooks for a specific episode."""
    planner = _get_planner(settings, pool)
    return await planner.generate_cross_video_hooks(series_id, episode_number)


@router.get("/{series_id}/analytics", response_model=SeriesAnalytics)
async def get_series_analytics(
    series_id: uuid.UUID,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> SeriesAnalytics:
    """Get aggregated analytics for a series."""
    planner = _get_planner(settings, pool)
    return await planner.get_series_analytics(series_id)


@router.post("/{series_id}/playlist")
async def create_playlist(
    series_id: uuid.UUID,
    settings: SettingsDep,
    pool: DbPoolDep,
    channel_id: uuid.UUID = Query(...),
) -> dict[str, str]:
    """Auto-create a YouTube playlist for the series."""
    planner = _get_planner(settings, pool)
    playlist_id = await planner.auto_create_playlist(series_id, channel_id)
    return {"playlist_id": playlist_id}


@router.post("/suggest/{channel_id}", response_model=SeriesSuggestionResult)
async def suggest_series(
    channel_id: uuid.UUID,
    settings: SettingsDep,
    pool: DbPoolDep,
    limit: int = Query(default=5, ge=1, le=10),
) -> SeriesSuggestionResult:
    """Suggest new series based on topic data and channel performance."""
    planner = _get_planner(settings, pool)
    return await planner.suggest_next_series(channel_id, limit=limit)


class LinkEpisodeBody(BaseModel):
    video_id: uuid.UUID
    status: str = "scripted"


@router.put(
    "/{series_id}/episodes/{episode_number}/link",
    response_model=SeriesEpisodeResponse,
)
async def link_episode(
    series_id: uuid.UUID,
    episode_number: int,
    body: LinkEpisodeBody,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> SeriesEpisodeResponse:
    """Link a video to a series episode."""
    planner = _get_planner(settings, pool)
    return await planner.link_episode_to_video(
        series_id,
        episode_number,
        body.video_id,
        body.status,
    )
