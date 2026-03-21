from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row

from src.db.queries import GET_VIDEO_STATUS, INSERT_VIDEO, LIST_VIDEOS, UPDATE_VIDEO
from src.dependencies import DbDep
from src.models.video import VideoCreate, VideoResponse, VideoUpdate

router = APIRouter()


@router.post("", response_model=VideoResponse, status_code=201)
async def create_video(body: VideoCreate, db: DbDep) -> VideoResponse:
    """Create a new video record."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            INSERT_VIDEO,
            {
                "channel_id": body.channel_id,
                "title": body.title,
                "topic": body.topic,
            },
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create video")
    await db.commit()
    return VideoResponse.from_row(row)


@router.get("", response_model=list[VideoResponse])
async def list_videos(
    db: DbDep,
    limit: int = 20,
    offset: int = 0,
) -> list[VideoResponse]:
    """List videos with pagination."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(LIST_VIDEOS, {"limit": limit, "offset": offset})
        rows = await cur.fetchall()
    return [VideoResponse.from_row(row) for row in rows]


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(video_id: uuid.UUID, db: DbDep) -> VideoResponse:
    """Get a single video by ID."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(GET_VIDEO_STATUS, {"video_id": video_id})
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return VideoResponse.from_row(row)


@router.patch("/{video_id}", response_model=VideoResponse)
async def update_video(
    video_id: uuid.UUID,
    body: VideoUpdate,
    db: DbDep,
) -> VideoResponse:
    """Update a video's status."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            UPDATE_VIDEO,
            {"video_id": video_id, "status": body.status},
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Video not found")
    await db.commit()
    return VideoResponse.from_row(row)
