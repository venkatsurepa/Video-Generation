"""Per-video budget enforcement with graceful degradation.

Checks cumulative spend before each pipeline stage and returns a
``BudgetDecision`` that tells the worker whether to proceed, degrade, or
abort.  When the spend crosses the *hard alert* threshold, the enforcer
builds a ``DegradationPlan`` that instructs downstream handlers to use
cheaper models, fewer images, or lower-quality settings.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any, cast

import structlog
from pydantic import BaseModel, Field

from src.db.queries import GET_VIDEO_COST_SUMMARY

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Stage budget allocation (fraction of total budget per stage)
# ---------------------------------------------------------------------------

STAGE_ALLOCATIONS: dict[str, Decimal] = {
    "script_generation": Decimal("0.25"),
    "voiceover_generation": Decimal("0.20"),
    "image_generation": Decimal("0.20"),
    "music_selection": Decimal("0.02"),
    "audio_processing": Decimal("0.03"),
    "image_processing": Decimal("0.02"),
    "caption_generation": Decimal("0.03"),
    "video_assembly": Decimal("0.10"),
    "thumbnail_generation": Decimal("0.10"),
    "youtube_upload": Decimal("0.05"),
}


# ---------------------------------------------------------------------------
# Degradation hierarchy — ordered from least to most impact
# ---------------------------------------------------------------------------


class DegradationLevel(StrEnum):
    """Ordered severity of cost-reduction measures."""

    NONE = "none"
    DOWNGRADE_MODELS = "downgrade_models"
    REDUCE_IMAGES = "reduce_images"
    SKIP_MUSIC = "skip_music"
    MINIMUM_VIABLE = "minimum_viable"


DEGRADATION_HIERARCHY: list[DegradationLevel] = [
    DegradationLevel.NONE,
    DegradationLevel.DOWNGRADE_MODELS,
    DegradationLevel.REDUCE_IMAGES,
    DegradationLevel.SKIP_MUSIC,
    DegradationLevel.MINIMUM_VIABLE,
]


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class VideoSpend(BaseModel):
    """Cumulative spend for a single video across all stages."""

    video_id: uuid.UUID
    total_usd: Decimal = Field(default=Decimal("0"))
    by_stage: dict[str, Decimal] = Field(default_factory=dict)
    cost_entries: list[dict[str, Any]] = Field(default_factory=list)


class DegradationPlan(BaseModel):
    """Instructions for downstream handlers on how to reduce cost."""

    level: DegradationLevel = DegradationLevel.NONE
    use_haiku_for_creative: bool = Field(
        default=False,
        description="Downgrade Sonnet calls to Haiku",
    )
    max_images: int | None = Field(
        default=None,
        description="Cap the number of generated images (None = no cap)",
    )
    skip_music: bool = Field(
        default=False,
        description="Skip music selection/processing entirely",
    )
    use_batch_api: bool = Field(
        default=False,
        description="Force batch API for remaining LLM calls (50 % discount)",
    )
    notes: list[str] = Field(default_factory=list)


class BudgetDecision(BaseModel):
    """The enforcer's verdict on whether to proceed with a stage."""

    allow: bool = True
    stage: str = ""
    video_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    spend: VideoSpend = Field(default_factory=lambda: VideoSpend(video_id=uuid.uuid4()))
    budget_usd: Decimal = Decimal("15")
    budget_remaining_usd: Decimal = Decimal("15")
    budget_used_pct: float = 0.0
    alert_level: str = "normal"  # normal | soft | hard | exceeded
    degradation: DegradationPlan = Field(default_factory=DegradationPlan)
    reason: str = ""


# ---------------------------------------------------------------------------
# BudgetEnforcer
# ---------------------------------------------------------------------------


class BudgetEnforcer:
    """Per-video budget gate that runs before each pipeline stage.

    Parameters
    ----------
    settings:
        Application settings (reads ``budget.per_video_usd``,
        ``budget.soft_alert_pct``, ``budget.hard_alert_pct``).
    db_pool:
        Async connection pool for querying ``generation_costs``.
    """

    def __init__(self, settings: Settings, db_pool: AsyncConnectionPool) -> None:
        self._budget = Decimal(str(settings.budget.per_video_usd))
        self._soft_pct = Decimal(str(settings.budget.soft_alert_pct))
        self._hard_pct = Decimal(str(settings.budget.hard_alert_pct))
        self._pool = db_pool

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_budget(
        self,
        video_id: uuid.UUID,
        stage: str,
    ) -> BudgetDecision:
        """Check whether a stage should proceed given current spend.

        Returns a ``BudgetDecision`` with:
        - ``allow=True`` and an optional ``DegradationPlan`` if the stage
          can proceed (possibly with cost-saving measures).
        - ``allow=False`` if the hard cap is exceeded.
        """
        spend = await self.get_video_spend(video_id)
        remaining = self._budget - spend.total_usd
        used_pct = float(spend.total_usd / self._budget) if self._budget > 0 else 0.0

        # Determine alert level
        if spend.total_usd >= self._budget:
            alert_level = "exceeded"
        elif used_pct >= float(self._hard_pct):
            alert_level = "hard"
        elif used_pct >= float(self._soft_pct):
            alert_level = "soft"
        else:
            alert_level = "normal"

        # Build degradation plan based on alert level
        degradation = self._build_degradation(alert_level, remaining, stage)

        # Check stage allocation — refuse if remaining budget is negative
        allow = spend.total_usd < self._budget
        reason = ""
        if not allow:
            reason = (
                f"Budget exceeded: ${spend.total_usd:.4f} / ${self._budget:.2f} "
                f"({used_pct:.1%}). Stage {stage} refused."
            )

        decision = BudgetDecision(
            allow=allow,
            stage=stage,
            video_id=video_id,
            spend=spend,
            budget_usd=self._budget,
            budget_remaining_usd=max(remaining, Decimal("0")),
            budget_used_pct=used_pct,
            alert_level=alert_level,
            degradation=degradation,
            reason=reason,
        )

        await logger.ainfo(
            "budget_check",
            video_id=str(video_id),
            stage=stage,
            total_spend=str(spend.total_usd),
            budget=str(self._budget),
            remaining=str(remaining),
            used_pct=f"{used_pct:.1%}",
            alert_level=alert_level,
            allow=allow,
            degradation_level=degradation.level.value,
        )

        # Record alert if threshold crossed
        if alert_level in ("soft", "hard", "exceeded"):
            await self.record_budget_alert(video_id, stage, decision)

        return decision

    async def get_video_spend(self, video_id: uuid.UUID) -> VideoSpend:
        """Query cumulative spend for a video from generation_costs."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(GET_VIDEO_COST_SUMMARY, {"video_id": video_id})
            rows = cast("list[dict[str, Any]]", await cur.fetchall())

        by_stage: dict[str, Decimal] = {}
        total = Decimal("0")
        entries: list[dict[str, Any]] = []

        for row in rows:
            cost = Decimal(str(row["cost_usd"]))
            stage = row["stage"]
            by_stage[stage] = by_stage.get(stage, Decimal("0")) + cost
            total += cost
            entries.append(
                {
                    "stage": stage,
                    "provider": row["provider"],
                    "model": row["model"],
                    "cost_usd": str(cost),
                    "created_at": str(row["created_at"]),
                }
            )

        return VideoSpend(
            video_id=video_id,
            total_usd=total,
            by_stage=by_stage,
            cost_entries=entries,
        )

    async def record_budget_alert(
        self,
        video_id: uuid.UUID,
        stage: str,
        decision: BudgetDecision,
    ) -> None:
        """Log a budget alert event for monitoring and auditing."""
        await logger.awarning(
            "budget_alert",
            video_id=str(video_id),
            stage=stage,
            alert_level=decision.alert_level,
            total_spend=str(decision.spend.total_usd),
            budget=str(decision.budget_usd),
            used_pct=f"{decision.budget_used_pct:.1%}",
            degradation_level=decision.degradation.level.value,
            reason=decision.reason,
        )

    # ------------------------------------------------------------------
    # Degradation plan builder
    # ------------------------------------------------------------------

    def _build_degradation(
        self,
        alert_level: str,
        remaining: Decimal,
        stage: str,
    ) -> DegradationPlan:
        """Build a DegradationPlan based on alert level and remaining budget."""
        if alert_level == "normal":
            return DegradationPlan(level=DegradationLevel.NONE)

        notes: list[str] = []

        if alert_level == "soft":
            # Soft alert: use batch API where possible, but no quality impact
            notes.append("Soft budget alert — enabling batch API for remaining LLM calls")
            return DegradationPlan(
                level=DegradationLevel.DOWNGRADE_MODELS,
                use_batch_api=True,
                notes=notes,
            )

        if alert_level == "hard":
            # Hard alert: downgrade models + reduce images
            notes.append("Hard budget alert — downgrading models and reducing image count")
            max_images = self._calculate_max_images(remaining, stage)
            return DegradationPlan(
                level=DegradationLevel.REDUCE_IMAGES,
                use_haiku_for_creative=True,
                max_images=max_images,
                use_batch_api=True,
                notes=notes,
            )

        # exceeded: minimum viable — skip optional stages
        notes.append("Budget exceeded — minimum viable mode")
        return DegradationPlan(
            level=DegradationLevel.MINIMUM_VIABLE,
            use_haiku_for_creative=True,
            max_images=5,
            skip_music=True,
            use_batch_api=True,
            notes=notes,
        )

    def _calculate_max_images(self, remaining: Decimal, stage: str) -> int:
        """Estimate how many images the remaining budget can afford.

        Assumes ~$0.04 per image (fal.ai Flux pricing).  Returns at least 5.
        """
        cost_per_image = Decimal("0.04")
        # Reserve 40% of remaining for non-image stages
        image_budget = remaining * Decimal("0.4")
        affordable = int(image_budget / cost_per_image) if cost_per_image > 0 else 20
        return max(affordable, 5)

    # ------------------------------------------------------------------
    # Convenience: enforce_degradation applies plan to payload
    # ------------------------------------------------------------------

    @staticmethod
    def enforce_degradation(
        degradation: DegradationPlan,
        stage: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply a degradation plan to a stage's payload dict.

        Mutates ``payload`` in-place and returns it for chaining.  Handlers
        should check ``payload.get("_degradation")`` to adjust their behavior.
        """
        payload["_degradation"] = degradation.model_dump()

        if degradation.level == DegradationLevel.NONE:
            return payload

        # Inject hints that handlers can read
        if degradation.use_haiku_for_creative:
            payload["_force_model"] = "claude-haiku-4-5-20251001"

        if degradation.max_images is not None:
            payload["_max_images"] = degradation.max_images

        if degradation.skip_music:
            payload["_skip_music"] = True

        if degradation.use_batch_api:
            payload["_use_batch_api"] = True

        return payload
