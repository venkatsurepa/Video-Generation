from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import httpx
from fastapi import APIRouter, HTTPException, Query

if TYPE_CHECKING:
    from src.services.publish_scheduler import PublishScheduler

from src.dependencies import DbPoolDep, SettingsDep
from src.models.schedule import (
    ApproveRequest,
    PublishingCalendar,
    RejectRequest,
    RescheduleRequest,
    ScheduleSlot,
    VideoForReview,
)

router = APIRouter()


def _build_scheduler(settings: SettingsDep, pool: DbPoolDep) -> PublishScheduler:
    """Construct PublishScheduler with dependencies."""
    from src.services.publish_scheduler import PublishScheduler
    from src.services.youtube_uploader import YouTubeUploader

    http_client = httpx.AsyncClient(timeout=120.0)
    yt = YouTubeUploader(settings, http_client)
    return PublishScheduler(settings, pool, yt)


@router.get("/calendar", response_model=PublishingCalendar)
async def get_calendar(
    settings: SettingsDep,
    pool: DbPoolDep,
    days: int = Query(default=14, ge=1, le=90),
) -> PublishingCalendar:
    """Full publishing calendar across all channels."""
    scheduler = _build_scheduler(settings, pool)
    return await scheduler.get_publishing_calendar(days_ahead=days)


@router.get("/review-queue", response_model=list[VideoForReview])
async def get_review_queue(
    settings: SettingsDep,
    pool: DbPoolDep,
) -> list[VideoForReview]:
    """Videos in 'assembled' status awaiting human review."""
    scheduler = _build_scheduler(settings, pool)
    return await scheduler.get_review_queue()


@router.post("/approve/{video_id}", response_model=ScheduleSlot)
async def approve_video(
    video_id: uuid.UUID,
    body: ApproveRequest,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> ScheduleSlot:
    """Approve a video for publishing — schedules it and triggers upload."""
    scheduler = _build_scheduler(settings, pool)
    try:
        return await scheduler.approve_for_publish(video_id, body.reviewer_notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reject/{video_id}", status_code=204)
async def reject_video(
    video_id: uuid.UUID,
    body: RejectRequest,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> None:
    """Reject a video — cancels it and frees the slot."""
    scheduler = _build_scheduler(settings, pool)
    try:
        await scheduler.reject_video(video_id, body.reason)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reschedule/{video_id}", response_model=ScheduleSlot)
async def reschedule_video(
    video_id: uuid.UUID,
    body: RescheduleRequest,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> ScheduleSlot:
    """Move a scheduled video to a different publish slot."""
    scheduler = _build_scheduler(settings, pool)
    try:
        return await scheduler.reschedule(video_id, body.new_datetime)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/next-slot/{channel_id}", response_model=ScheduleSlot)
async def get_next_slot(
    channel_id: uuid.UUID,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> ScheduleSlot:
    """Next available publish time for a channel."""
    scheduler = _build_scheduler(settings, pool)
    try:
        return await scheduler.get_next_slot(channel_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
