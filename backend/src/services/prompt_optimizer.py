"""Prompt optimizer — automatic generation weight tuning via performance feedback.

Generates weekly optimization reports, applies low-risk weight changes
automatically, and uses Thompson Sampling for title/thumbnail experimentation.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import TYPE_CHECKING, Any

import structlog
from psycopg.rows import dict_row
from scipy import stats as scipy_stats

from src.models.performance import (
    FeatureRankings,
    OptimizationReport,
    ThompsonResult,
    ThompsonVariant,
    WeightChange,
)

if TYPE_CHECKING:
    import uuid

    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings
    from src.services.performance_analyzer import PerformanceAnalyzer

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_GET_GENERATION_SETTINGS: str = """
SELECT id, channel_id, target_video_length_minutes, target_word_count,
       generation_params
FROM channel_generation_settings
WHERE channel_id = %(channel_id)s;
"""

_UPDATE_GENERATION_PARAMS: str = """
UPDATE channel_generation_settings
SET generation_params = %(generation_params)s,
    updated_at = now()
WHERE channel_id = %(channel_id)s;
"""

_GET_PUBLISHED_VIDEO_COUNT: str = """
SELECT COUNT(*) AS cnt
FROM videos
WHERE channel_id = %(channel_id)s
  AND status = 'published';
"""

_GET_VIDEO_SCORES_FOR_THOMPSON: str = """
SELECT
    v.id AS video_id,
    v.published_at
FROM videos v
WHERE v.channel_id = %(channel_id)s
  AND v.status = 'published'
  AND v.published_at IS NOT NULL
ORDER BY v.published_at DESC;
"""

_GET_SCRIPT_FEATURES_BULK: str = """
SELECT pj.video_id, pj.result
FROM pipeline_jobs pj
WHERE pj.video_id = ANY(%(video_ids)s)
  AND pj.stage = 'script_generation'
  AND pj.status = 'completed';
"""

_GET_THUMBNAIL_ARCHETYPES_BULK: str = """
SELECT video_id, archetype
FROM thumbnail_generations
WHERE video_id = ANY(%(video_ids)s)
  AND is_active = true;
"""


# ---------------------------------------------------------------------------
# Default generation weights
# ---------------------------------------------------------------------------

DEFAULT_GENERATION_PARAMS: dict[str, object] = {
    "hook_type_weights": {
        "cold_open": 0.20,
        "provocative_question": 0.20,
        "shocking_statistic": 0.20,
        "contradiction": 0.20,
        "sensory_scene": 0.20,
    },
    "title_formula_weights": {
        "adjective_case": 0.167,
        "how_person": 0.167,
        "nobody_talks": 0.167,
        "why_question": 0.167,
        "truth_behind": 0.167,
        "what_happened": 0.167,
    },
    "thumbnail_archetype_weights": {
        "mugshot_drama": 0.167,
        "mystery_reveal": 0.167,
        "crime_scene": 0.167,
        "victim_memorial": 0.167,
        "evidence_collage": 0.167,
        "location_map": 0.167,
    },
    "thompson_params": {},
}

# Maximum single-step weight change (prevents wild swings)
MAX_WEIGHT_DELTA: float = 0.15
# Minimum sample count before optimizing
MIN_SAMPLES_FOR_OPTIMIZATION: int = 5


# ---------------------------------------------------------------------------
# PromptOptimizer
# ---------------------------------------------------------------------------


class PromptOptimizer:
    """Optimises generation weights based on performance feedback.

    Parameters
    ----------
    settings:
        Application settings.
    db_pool:
        Shared ``AsyncConnectionPool``.
    analyzer:
        ``PerformanceAnalyzer`` instance for running analyses.
    """

    def __init__(
        self,
        settings: Settings,
        db_pool: AsyncConnectionPool,
        analyzer: PerformanceAnalyzer,
    ) -> None:
        self._settings = settings
        self._pool = db_pool
        self._analyzer = analyzer

    # ==================================================================
    # Generation settings helpers
    # ==================================================================

    async def _get_params(self, channel_id: uuid.UUID) -> dict[str, Any]:
        """Load generation_params JSONB for a channel, initialising defaults if empty."""
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_GET_GENERATION_SETTINGS, {"channel_id": channel_id})
            row = await cur.fetchone()

        if not row:
            return dict(DEFAULT_GENERATION_PARAMS)

        params = row.get("generation_params") or {}
        if not params:
            params = dict(DEFAULT_GENERATION_PARAMS)
        return params

    async def _save_params(self, channel_id: uuid.UUID, params: dict[str, Any]) -> None:
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    _UPDATE_GENERATION_PARAMS,
                    {"channel_id": channel_id, "generation_params": json.dumps(params)},
                )
            await conn.commit()

    # ==================================================================
    # 1. Weekly optimization report
    # ==================================================================

    async def generate_optimization_report(
        self,
        channel_id: uuid.UUID,
    ) -> OptimizationReport:
        """Generate a weekly optimisation report.

        1. Analyse retention patterns.
        2. Rank content features.
        3. Detect Goodhart violations.
        4. Generate specific weight-change recommendations.
        5. Auto-apply low-risk changes (if no Goodhart violations).
        6. Flag high-risk changes for human approval.
        """
        retention = await self._analyzer.analyze_retention_patterns(channel_id)
        rankings = await self._analyzer.rank_content_features(channel_id)
        goodhart = await self._analyzer.detect_goodhart_violations(channel_id)

        params = await self._get_params(channel_id)
        changes = self._generate_changes(rankings, params)

        auto_applied: list[WeightChange] = []
        requires_approval: list[WeightChange] = []

        has_goodhart = bool(goodhart)

        for change in changes:
            if has_goodhart:
                # Freeze all automatic changes when Goodhart detected
                change = WeightChange(
                    feature=change.feature,
                    old_value=change.old_value,
                    new_value=change.new_value,
                    reason=change.reason + " [BLOCKED: Goodhart violation detected]",
                    risk_level="high",
                )
                requires_approval.append(change)
            elif change.risk_level == "low":
                auto_applied.append(change)
            else:
                requires_approval.append(change)

        # Auto-apply low-risk changes
        if auto_applied:
            await self.update_generation_weights(channel_id, auto_applied)

        await logger.ainfo(
            "optimization_report_generated",
            channel_id=str(channel_id),
            goodhart_alerts=len(goodhart),
            auto_applied=len(auto_applied),
            requires_approval=len(requires_approval),
        )

        return OptimizationReport(
            channel_id=channel_id,
            retention_analysis=retention,
            feature_rankings=rankings,
            goodhart_alerts=goodhart,
            recommended_changes=changes,
            auto_applied=auto_applied,
            requires_approval=requires_approval,
        )

    def _generate_changes(
        self,
        rankings: FeatureRankings,
        current_params: dict[str, Any],
    ) -> list[WeightChange]:
        """Derive concrete weight changes from feature rankings."""
        changes: list[WeightChange] = []

        weight_keys = {
            "hook_type": "hook_type_weights",
            "title_formula": "title_formula_weights",
            "thumbnail_archetype": "thumbnail_archetype_weights",
        }

        for feature_cat, param_key in weight_keys.items():
            ranked = rankings.rankings.get(feature_cat, [])
            current_weights: dict[str, float] = current_params.get(param_key, {})
            if not ranked or not current_weights:
                continue

            # Only consider variants with enough samples
            sig = [r for r in ranked if r.sample_count >= MIN_SAMPLES_FOR_OPTIMIZATION]
            if len(sig) < 2:
                continue

            best = sig[0]
            worst = sig[-1]
            gap = best.mean_score - worst.mean_score

            if gap < 3.0:
                continue  # Not significant enough

            # Compute new weights: boost best, reduce worst
            old_best_w = current_weights.get(best.feature_value, 0.0)
            old_worst_w = current_weights.get(worst.feature_value, 0.0)

            # Scale delta by performance gap (max MAX_WEIGHT_DELTA)
            delta = min(MAX_WEIGHT_DELTA, gap / 100.0 * 0.5)

            new_best_w = min(0.60, old_best_w + delta)
            new_worst_w = max(0.05, old_worst_w - delta)

            risk = "low" if delta <= 0.05 else "medium" if delta <= 0.10 else "high"

            if new_best_w != old_best_w:
                changes.append(
                    WeightChange(
                        feature=f"{param_key}.{best.feature_value}",
                        old_value=round(old_best_w, 3),
                        new_value=round(new_best_w, 3),
                        reason=(
                            f'"{best.feature_value}" scores {best.mean_score:.1f} '
                            f"(N={best.sample_count}) — increase weight."
                        ),
                        risk_level=risk,  # type: ignore[arg-type]
                    )
                )

            if new_worst_w != old_worst_w:
                changes.append(
                    WeightChange(
                        feature=f"{param_key}.{worst.feature_value}",
                        old_value=round(old_worst_w, 3),
                        new_value=round(new_worst_w, 3),
                        reason=(
                            f'"{worst.feature_value}" scores {worst.mean_score:.1f} '
                            f"(N={worst.sample_count}) — reduce weight."
                        ),
                        risk_level=risk,  # type: ignore[arg-type]
                    )
                )

        return changes

    # ==================================================================
    # 2. Apply weight changes
    # ==================================================================

    async def update_generation_weights(
        self,
        channel_id: uuid.UUID,
        changes: list[WeightChange],
    ) -> None:
        """Apply approved weight changes to channel_generation_settings.generation_params.

        Each change targets a dotted path like ``hook_type_weights.cold_open``.
        After applying, weights within each category are renormalised to sum to 1.
        """
        params = await self._get_params(channel_id)

        for change in changes:
            parts = change.feature.split(".", 1)
            if len(parts) != 2:
                await logger.awarning("invalid_weight_path", path=change.feature)
                continue

            category, variant = parts
            if category not in params:
                params[category] = {}

            weights = params[category]
            if not isinstance(weights, dict):
                continue

            weights[variant] = change.new_value

        # Renormalise each weight category to sum to 1.0
        for key in ("hook_type_weights", "title_formula_weights", "thumbnail_archetype_weights"):
            weights = params.get(key)
            if isinstance(weights, dict) and weights:
                total = sum(weights.values())
                if total > 0:
                    params[key] = {k: round(v / total, 4) for k, v in weights.items()}

        await self._save_params(channel_id, params)

        await logger.ainfo(
            "generation_weights_updated",
            channel_id=str(channel_id),
            changes_applied=len(changes),
        )

    # ==================================================================
    # 3. Thompson Sampling
    # ==================================================================

    async def run_thompson_sampling(
        self,
        channel_id: uuid.UUID,
        feature: str,
    ) -> ThompsonResult:
        """Run Thompson Sampling for a feature dimension.

        Operates at strategy-pattern level (e.g., "hook_type", "title_formula",
        "thumbnail_archetype").  Uses batch weekly rewards, not per-video.

        For each variant, maintains Beta(alpha, beta) where:
        - alpha = videos scoring above channel median + 1 (prior)
        - beta = videos scoring at or below median + 1 (prior)

        Samples from each Beta distribution, selects the highest sample.
        Convergence is fast with small sample sizes (perfect for <200 video
        channels).
        """
        params = await self._get_params(channel_id)
        thompson_params: dict[str, Any] = params.get("thompson_params", {})
        feature_params: dict[str, dict[str, float]] = thompson_params.get(feature, {})

        # Get all published videos and their scores
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_GET_VIDEO_SCORES_FOR_THOMPSON, {"channel_id": channel_id})
            video_rows = await cur.fetchall()

        if not video_rows:
            return ThompsonResult(
                feature=feature,
                variants={},
                selected="",
                exploration_ratio=1.0,
            )

        video_ids = [r["video_id"] for r in video_rows]

        # Compute scores
        scores: dict[str, float] = {}
        for vid in video_ids:
            video_score = await self._analyzer.compute_video_score(vid)
            scores[str(vid)] = video_score.composite_score

        if not scores:
            return ThompsonResult(
                feature=feature,
                variants={},
                selected="",
                exploration_ratio=1.0,
            )

        median_score = sorted(scores.values())[len(scores) // 2]

        # Map feature values to videos
        feature_map: dict[str, str] = {}  # video_id → feature_value

        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            if feature in ("hook_type", "title_formula"):
                await cur.execute(_GET_SCRIPT_FEATURES_BULK, {"video_ids": video_ids})
                for row in await cur.fetchall():
                    result = row.get("result") or {}
                    val = result.get(feature)
                    if val:
                        feature_map[str(row["video_id"])] = val
            elif feature == "thumbnail_archetype":
                await cur.execute(_GET_THUMBNAIL_ARCHETYPES_BULK, {"video_ids": video_ids})
                for row in await cur.fetchall():
                    if row.get("archetype"):
                        feature_map[str(row["video_id"])] = row["archetype"]

        # Count successes and failures per variant
        variant_counts: dict[str, dict[str, int]] = defaultdict(
            lambda: {"successes": 0, "failures": 0},
        )

        for vid_str, feat_val in feature_map.items():
            score = scores.get(vid_str)
            if score is None:
                continue
            if score > median_score:
                variant_counts[feat_val]["successes"] += 1
            else:
                variant_counts[feat_val]["failures"] += 1

        # Build Beta distributions and sample
        variants: dict[str, ThompsonVariant] = {}
        max_sampled = -1.0
        selected = ""

        for variant_name, counts in variant_counts.items():
            # Use stored params as prior, or uniform Beta(1,1)
            prior = feature_params.get(variant_name, {"alpha": 1.0, "beta": 1.0})
            alpha = prior.get("alpha", 1.0) + counts["successes"]
            beta_val = prior.get("beta", 1.0) + counts["failures"]
            n = counts["successes"] + counts["failures"]

            sampled = float(scipy_stats.beta.rvs(alpha, beta_val))
            mean = alpha / (alpha + beta_val)

            variants[variant_name] = ThompsonVariant(
                name=variant_name,
                alpha=round(alpha, 2),
                beta_param=round(beta_val, 2),
                mean=round(mean, 4),
                sampled_value=round(sampled, 4),
                sample_count=n,
            )

            if sampled > max_sampled:
                max_sampled = sampled
                selected = variant_name

        # Exploration ratio: samples from least-tried / total
        if variants:
            min_n = min(v.sample_count for v in variants.values())
            total_n = sum(v.sample_count for v in variants.values())
            exploration_ratio = min_n / max(total_n, 1)
        else:
            exploration_ratio = 1.0

        # Persist updated Thompson params
        updated_tp: dict[str, dict[str, float]] = {}
        for vname, variant in variants.items():
            updated_tp[vname] = {"alpha": variant.alpha, "beta": variant.beta_param}
        thompson_params[feature] = updated_tp
        params["thompson_params"] = thompson_params
        await self._save_params(channel_id, params)

        await logger.ainfo(
            "thompson_sampling_complete",
            channel_id=str(channel_id),
            feature=feature,
            selected=selected,
            variants={k: v.sampled_value for k, v in variants.items()},
        )

        return ThompsonResult(
            feature=feature,
            variants=variants,
            selected=selected,
            exploration_ratio=round(exploration_ratio, 4),
        )
