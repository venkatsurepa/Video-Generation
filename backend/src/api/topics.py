from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row

from src.api.rate_limit import RATE_HEAVY_WRITE, limiter
from src.db.queries import COUNT_TOPICS
from src.dependencies import DbDep, DbPoolDep, SettingsDep
from src.models.pagination import PaginatedResponse
from src.models.topic import TopicResponse
from src.services.topic_selector import ARCHIVE_TOPIC, ASSIGN_TOPIC, GET_TOPIC, TopicSelector

router = APIRouter()


@router.get("", response_model=PaginatedResponse[TopicResponse])
async def list_topics(
    db_pool: DbPoolDep,
    settings: SettingsDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    priority: str | None = None,
    category: str | None = None,
) -> PaginatedResponse[TopicResponse]:
    """List top scored topics, filterable by priority and category."""
    # Count total
    async with db_pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(COUNT_TOPICS, {"priority_filter": priority})
        total = (await cur.fetchone() or {}).get("total", 0)

    async with httpx.AsyncClient() as http:
        selector = TopicSelector(settings, http, db_pool)
        rows = await selector.get_top_topics(
            limit=limit,
            offset=offset,
            priority=priority,
            category=category,
        )

    return PaginatedResponse(
        items=[TopicResponse.from_row(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{topic_id}", response_model=TopicResponse)
async def get_topic(topic_id: uuid.UUID, db: DbDep) -> TopicResponse:
    """Get a topic with full score breakdown."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(GET_TOPIC, {"topic_id": topic_id})
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return TopicResponse.from_row(row)


@router.post("/discover", response_model=list[TopicResponse], status_code=202)
@limiter.limit(RATE_HEAVY_WRITE)
async def trigger_discovery(
    request: Request,
    db_pool: DbPoolDep,
    settings: SettingsDep,
) -> list[TopicResponse]:
    """Manually trigger the five-layer discovery pipeline."""
    async with httpx.AsyncClient() as http:
        selector = TopicSelector(settings, http, db_pool)
        scored = await selector.discover_topics()

    # Re-read from DB to get the canonical rows
    async with db_pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        ids = [str(t.id) for t in scored]
        if ids:
            query = """
                    SELECT * FROM discovered_topics
                    WHERE id = ANY(%(ids)s::uuid[])
                    ORDER BY composite_score DESC NULLS LAST;
                """
            await cur.execute(query, {"ids": ids})
            rows = await cur.fetchall()
        else:
            rows = []

    return [TopicResponse.from_row(row) for row in rows]


@router.post("/{topic_id}/assign/{video_id}", response_model=TopicResponse)
async def assign_topic(
    topic_id: uuid.UUID,
    video_id: uuid.UUID,
    db: DbDep,
) -> TopicResponse:
    """Assign a topic to a video (marks topic as archived)."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(ASSIGN_TOPIC, {"topic_id": topic_id, "video_id": video_id})
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Topic not found or already assigned")
    await db.commit()
    return TopicResponse.from_row(row)


@router.delete("/{topic_id}", response_model=TopicResponse)
async def archive_topic(topic_id: uuid.UUID, db: DbDep) -> TopicResponse:
    """Archive a topic (soft-delete)."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(ARCHIVE_TOPIC, {"topic_id": topic_id})
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    await db.commit()
    return TopicResponse.from_row(row)
