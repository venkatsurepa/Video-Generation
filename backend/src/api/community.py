"""Community API — topic submissions, Patreon sync trigger, metrics."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from psycopg.rows import dict_row

from src.db.queries import (
    COUNT_TOPIC_SUBMISSIONS,
    GET_TOPIC_SUBMISSION,
    LIST_TOPIC_SUBMISSIONS,
    UPDATE_TOPIC_SUBMISSION_STATUS,
)
from src.dependencies import DbDep
from src.models.community import TopicSubmission, TopicSubmissionCreate
from src.models.pagination import PaginatedResponse

router = APIRouter()


@router.get("/submissions", response_model=PaginatedResponse[TopicSubmission])
async def list_submissions(
    db: DbDep,
    status: str = Query(default="new", description="Filter by status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedResponse[TopicSubmission]:
    """List community topic submissions."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(COUNT_TOPIC_SUBMISSIONS, {"status": status})
        total = (await cur.fetchone() or {}).get("total", 0)
        await cur.execute(
            LIST_TOPIC_SUBMISSIONS,
            {"status": status, "limit": limit, "offset": offset},
        )
        rows = await cur.fetchall()

    return PaginatedResponse(
        items=[TopicSubmission.from_row(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/submissions/count")
async def count_submissions(
    db: DbDep,
    status: str = Query(default="new"),
) -> dict[str, int]:
    """Count submissions by status."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(COUNT_TOPIC_SUBMISSIONS, {"status": status})
        row = await cur.fetchone()
    return {"count": row["total"] if row else 0}


@router.get("/submissions/{submission_id}", response_model=TopicSubmission)
async def get_submission(
    submission_id: uuid.UUID,
    db: DbDep,
) -> TopicSubmission:
    """Get a single submission by ID."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(GET_TOPIC_SUBMISSION, {"id": submission_id})
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    return TopicSubmission.from_row(row)


@router.post("/submissions", response_model=TopicSubmission, status_code=201)
async def create_submission(
    body: TopicSubmissionCreate,
    db: DbDep,
) -> TopicSubmission:
    """Create a new topic submission (manual source)."""
    from src.db.queries import INSERT_TOPIC_SUBMISSION

    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            INSERT_TOPIC_SUBMISSION,
            {
                "source": body.source,
                "submitter_name": body.submitter_name,
                "submitter_contact": body.submitter_contact,
                "case_name": body.case_name,
                "description": body.description,
                "why_interesting": body.why_interesting,
                "source_links": body.source_links,
                "score": None,
            },
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=500, detail="Failed to create submission")
    await db.commit()
    return TopicSubmission.from_row(row)


@router.patch("/submissions/{submission_id}", response_model=TopicSubmission)
async def review_submission(
    submission_id: uuid.UUID,
    status: str = Query(description="New status: accepted, rejected, reviewed"),
    db: DbDep = ...,  # type: ignore[assignment]
) -> TopicSubmission:
    """Accept or reject a topic submission."""
    if status not in ("reviewed", "accepted", "rejected", "produced"):
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            UPDATE_TOPIC_SUBMISSION_STATUS,
            {
                "id": submission_id,
                "status": status,
                "assigned_topic_id": None,
                "assigned_video_id": None,
            },
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    await db.commit()
    return TopicSubmission.from_row(row)
