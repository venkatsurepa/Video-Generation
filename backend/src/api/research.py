"""Research database API — search sources, manage case files, track FOIA requests."""

from __future__ import annotations

import uuid
from datetime import date

import httpx
from fastapi import APIRouter, HTTPException
from psycopg.rows import dict_row

from src.db import queries
from src.dependencies import DbDep, DbPoolDep, SettingsDep
from src.models.pagination import PaginatedResponse
from src.models.research import (
    CaseFileCreate,
    CaseFileResponse,
    CollectionRequest,
    CollectionResult,
    FOIARequestInput,
    FOIAResponse,
    FOIAUpdateInput,
    ResearchSourceResponse,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Source search
# ---------------------------------------------------------------------------


@router.get("/search", response_model=PaginatedResponse[ResearchSourceResponse])
async def search_sources(
    db: DbDep,
    q: str,
    source_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 20,
    offset: int = 0,
) -> PaginatedResponse[ResearchSourceResponse]:
    """Full-text search across all research sources."""
    params = {
        "query": q,
        "source_type": source_type,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "limit": limit,
        "offset": offset,
    }
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(queries.COUNT_RESEARCH_SOURCES, params)
        total = (await cur.fetchone() or {}).get("total", 0)
        await cur.execute(queries.SEARCH_RESEARCH_SOURCES, params)
        rows = await cur.fetchall()

    return PaginatedResponse(
        items=[ResearchSourceResponse.from_row(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# Case files
# ---------------------------------------------------------------------------


@router.get("/cases", response_model=PaginatedResponse[CaseFileResponse])
async def list_cases(
    db: DbDep,
    category: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> PaginatedResponse[CaseFileResponse]:
    """List case files with optional category/status filters."""
    params = {"category": category, "status": status, "limit": limit, "offset": offset}
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(queries.COUNT_CASE_FILES, params)
        total = (await cur.fetchone() or {}).get("total", 0)
        await cur.execute(queries.LIST_CASE_FILES, params)
        rows = await cur.fetchall()

    return PaginatedResponse(
        items=[CaseFileResponse.from_row(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/cases/{case_id}", response_model=CaseFileResponse)
async def get_case(case_id: uuid.UUID, db: DbDep) -> CaseFileResponse:
    """Get a single case file with linked source count."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(queries.GET_CASE_FILE, {"case_file_id": str(case_id)})
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Case file not found")
    return CaseFileResponse.from_row(row)


@router.post("/cases", response_model=CaseFileResponse, status_code=201)
async def create_case(body: CaseFileCreate, db: DbDep) -> CaseFileResponse:
    """Create a new case file."""
    async with db.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            queries.INSERT_CASE_FILE,
            {
                "case_name": body.case_name,
                "category": body.category,
                "summary": body.summary,
            },
        )
        row = await cur.fetchone()
    await db.commit()
    return CaseFileResponse.from_row(row)


# ---------------------------------------------------------------------------
# Automated collection
# ---------------------------------------------------------------------------


@router.post("/collect", response_model=CollectionResult, status_code=202)
async def trigger_collection(
    body: CollectionRequest,
    db_pool: DbPoolDep,
    settings: SettingsDep,
) -> CollectionResult:
    """Trigger automated source collection across public records APIs."""
    from src.services.research_collector import ResearchCollector

    async with httpx.AsyncClient() as http:
        collector = ResearchCollector(settings, http, db_pool)
        return await collector.collect(body)


# ---------------------------------------------------------------------------
# FOIA requests
# ---------------------------------------------------------------------------


@router.get("/foia", response_model=list[FOIAResponse])
async def list_foia(
    db_pool: DbPoolDep,
    settings: SettingsDep,
    status: str | None = None,
    agency: str | None = None,
    overdue: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> list[FOIAResponse]:
    """List FOIA requests with optional filters."""
    from src.services.foia_tracker import FOIATracker

    async with httpx.AsyncClient() as http:
        tracker = FOIATracker(settings, db_pool, http)
        if overdue:
            return await tracker.get_overdue_requests()
        return await tracker.get_pending_requests(
            status=status,
            agency=agency,
            limit=limit,
            offset=offset,
        )


@router.post("/foia", response_model=FOIAResponse, status_code=201)
async def file_foia(
    body: FOIARequestInput,
    db_pool: DbPoolDep,
    settings: SettingsDep,
) -> FOIAResponse:
    """File a new FOIA request tracking record."""
    from src.services.foia_tracker import FOIATracker

    async with httpx.AsyncClient() as http:
        tracker = FOIATracker(settings, db_pool, http)
        return await tracker.file_request(body)


@router.patch("/foia/{foia_id}", response_model=FOIAResponse)
async def update_foia(
    foia_id: uuid.UUID,
    body: FOIAUpdateInput,
    db_pool: DbPoolDep,
    settings: SettingsDep,
) -> FOIAResponse:
    """Update FOIA request status, tracking number, or notes."""
    from src.services.foia_tracker import FOIATracker

    async with httpx.AsyncClient() as http:
        tracker = FOIATracker(settings, db_pool, http)
        try:
            return await tracker.update_status(foia_id, body)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
