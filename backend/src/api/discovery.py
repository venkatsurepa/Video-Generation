"""Discovery API — manual triggers for the topic discovery pipeline."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from src.dependencies import SettingsDep

router = APIRouter()


def _build_supabase(settings: Any) -> Any:
    """Construct a fresh Supabase client. Lazy so the dep stays optional."""
    from supabase import create_client

    return create_client(settings.database.url, settings.database.service_role_key)


@router.post("/run")
async def run_all(
    settings: SettingsDep,
    score: bool = Query(False, description="Run Claude Haiku scorer on results"),
) -> dict[str, Any]:
    """Run every discovery source, deduplicate, and persist. Returns the run summary."""
    from src.services.discovery import DiscoveryOrchestrator

    orch = DiscoveryOrchestrator(_build_supabase(settings), settings)
    return await orch.run_all(score=score)


@router.post("/run/{source_name}")
async def run_source(
    source_name: str,
    settings: SettingsDep,
    score: bool = Query(False, description="Run Claude Haiku scorer on results"),
) -> dict[str, Any]:
    """Run a single discovery source by name (e.g. ``reddit``, ``gdelt``)."""
    from src.services.discovery import DiscoveryOrchestrator

    orch = DiscoveryOrchestrator(_build_supabase(settings), settings)
    try:
        return await orch.run_source(source_name, score=score)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/backlog")
async def get_backlog(
    settings: SettingsDep,
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    """Top unassigned discovered topics ordered by composite score (descending)."""
    sb = _build_supabase(settings)
    res = (
        sb.table("discovered_topics")
        .select("id, title, category, composite_score, priority, source_signals, created_at")
        .is_("used_in_video_id", "null")
        .order("composite_score", desc=True)
        .limit(limit)
        .execute()
    )
    rows = res.data or []
    return {"count": len(rows), "topics": rows}
