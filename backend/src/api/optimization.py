"""Optimization API — performance analysis, feature rankings, and prompt tuning."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from src.dependencies import DbPoolDep, SettingsDep
from src.models.performance import (
    FeatureRankings,
    GoodhartAlert,
    OptimizationReport,
    VideoPerformanceScore,
    WeightChange,
)
from src.services.performance_analyzer import PerformanceAnalyzer
from src.services.prompt_optimizer import PromptOptimizer

router = APIRouter()

# ---------------------------------------------------------------------------
# Helpers — build service instances per request
# ---------------------------------------------------------------------------


def _build_analyzer(settings: SettingsDep, pool: DbPoolDep) -> PerformanceAnalyzer:
    return PerformanceAnalyzer(settings, pool)


def _build_optimizer(
    settings: SettingsDep,
    pool: DbPoolDep,
) -> PromptOptimizer:
    analyzer = PerformanceAnalyzer(settings, pool)
    return PromptOptimizer(settings, pool, analyzer)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/report/{channel_id}",
    response_model=OptimizationReport,
)
async def get_optimization_report(
    channel_id: uuid.UUID,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> OptimizationReport:
    """Generate a weekly optimization report for a channel.

    Analyses retention patterns, ranks content features, checks for Goodhart
    violations, and recommends (or auto-applies) weight changes.
    """
    optimizer = _build_optimizer(settings, pool)
    return await optimizer.generate_optimization_report(channel_id)


@router.get(
    "/features/{channel_id}",
    response_model=FeatureRankings,
)
async def get_feature_rankings(
    channel_id: uuid.UUID,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> FeatureRankings:
    """Return ranked content features correlated with performance."""
    analyzer = _build_analyzer(settings, pool)
    return await analyzer.rank_content_features(channel_id)


@router.get(
    "/goodhart/{channel_id}",
    response_model=list[GoodhartAlert],
)
async def get_goodhart_violations(
    channel_id: uuid.UUID,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> list[GoodhartAlert]:
    """Check for Goodhart's Law violations across a channel's recent videos."""
    analyzer = _build_analyzer(settings, pool)
    return await analyzer.detect_goodhart_violations(channel_id)


@router.post(
    "/apply/{channel_id}",
    status_code=204,
)
async def apply_weight_changes(
    channel_id: uuid.UUID,
    changes: list[WeightChange],
    settings: SettingsDep,
    pool: DbPoolDep,
) -> None:
    """Apply approved weight changes to a channel's generation settings."""
    if not changes:
        raise HTTPException(status_code=400, detail="No changes provided")
    optimizer = _build_optimizer(settings, pool)
    await optimizer.update_generation_weights(channel_id, changes)


@router.get(
    "/score/{video_id}",
    response_model=VideoPerformanceScore,
)
async def get_video_score(
    video_id: uuid.UUID,
    settings: SettingsDep,
    pool: DbPoolDep,
) -> VideoPerformanceScore:
    """Compute a composite performance score for a single video."""
    analyzer = _build_analyzer(settings, pool)
    return await analyzer.compute_video_score(video_id)
