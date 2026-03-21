from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row

from src.db.queries import GET_CHANNEL, INSERT_CHANNEL, LIST_CHANNELS
from src.dependencies import DbDep
from src.models.channel import ChannelCreate, ChannelResponse

router = APIRouter()


@router.post("", response_model=ChannelResponse, status_code=201)
async def create_channel(body: ChannelCreate, db: DbDep) -> ChannelResponse:
    """Create a new channel."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            INSERT_CHANNEL,
            {
                "name": body.name,
                "youtube_channel_id": body.youtube_channel_id,
                "description": body.description,
            },
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create channel")
    await db.commit()
    return ChannelResponse.from_row(row)


@router.get("", response_model=list[ChannelResponse])
async def list_channels(
    db: DbDep,
    limit: int = 20,
    offset: int = 0,
) -> list[ChannelResponse]:
    """List channels with pagination."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(LIST_CHANNELS, {"limit": limit, "offset": offset})
        rows = await cur.fetchall()
    return [ChannelResponse.from_row(row) for row in rows]


@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: uuid.UUID, db: DbDep) -> ChannelResponse:
    """Get a single channel by ID."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(GET_CHANNEL, {"channel_id": channel_id})
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ChannelResponse.from_row(row)
