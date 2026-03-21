from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row

from src.db.queries import GET_PIPELINE_JOBS, GET_VIDEO_STATUS, RETRY_FAILED_JOBS
from src.dependencies import DbDep
from src.models.pipeline import PipelineJobResponse, PipelineStatusResponse

router = APIRouter()


@router.post("/trigger/{video_id}", response_model=PipelineStatusResponse, status_code=202)
async def trigger_pipeline(video_id: uuid.UUID, db: DbDep) -> PipelineStatusResponse:
    """Start the pipeline for a video.

    Creates the initial pipeline job(s) and returns the current pipeline status.
    """
    from src.pipeline.orchestrator import Orchestrator

    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(GET_VIDEO_STATUS, {"video_id": video_id})
        video_row = await cur.fetchone()
    if video_row is None:
        raise HTTPException(status_code=404, detail="Video not found")

    orchestrator = Orchestrator(db)
    await orchestrator.start_pipeline(video_id)
    await db.commit()

    return await _get_pipeline_status(video_id, db, str(video_row["status"]))


@router.get("/status/{video_id}", response_model=PipelineStatusResponse)
async def get_pipeline_status(video_id: uuid.UUID, db: DbDep) -> PipelineStatusResponse:
    """Get the current pipeline status for a video."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(GET_VIDEO_STATUS, {"video_id": video_id})
        video_row = await cur.fetchone()
    if video_row is None:
        raise HTTPException(status_code=404, detail="Video not found")

    return await _get_pipeline_status(video_id, db, str(video_row["status"]))


@router.post("/retry/{video_id}", response_model=PipelineStatusResponse)
async def retry_failed(video_id: uuid.UUID, db: DbDep) -> PipelineStatusResponse:
    """Retry all failed/dead-letter jobs for a video."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(GET_VIDEO_STATUS, {"video_id": video_id})
        video_row = await cur.fetchone()
    if video_row is None:
        raise HTTPException(status_code=404, detail="Video not found")

    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(RETRY_FAILED_JOBS, {"video_id": video_id})
    await db.commit()

    return await _get_pipeline_status(video_id, db, str(video_row["status"]))


async def _get_pipeline_status(
    video_id: uuid.UUID,
    db: DbDep,
    video_status: str,
) -> PipelineStatusResponse:
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(GET_PIPELINE_JOBS, {"video_id": video_id})
        job_rows = await cur.fetchall()

    jobs = [PipelineJobResponse.from_row(row) for row in job_rows]

    return PipelineStatusResponse(
        video_id=video_id,
        video_status=video_status,
        jobs=jobs,
    )
