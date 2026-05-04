"""Discovery-run audit row — one row per orchestrator pass.

Mirrors the introspected ``discovery_runs`` Supabase table. Every call to
``DiscoveryOrchestrator.run_all()`` or ``run_source()`` writes one row so we
have an audit trail of when discovery executed, how long it took, what each
source produced, and what (if anything) it cost.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

DiscoveryTrigger = Literal["manual", "cron", "api"]


class DiscoveryRunBase(BaseModel):
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: Decimal | None = None
    sources_run: list[str] = Field(default_factory=list)
    total_candidates: int = Field(default=0, ge=0)
    total_saved: int = Field(default=0, ge=0)
    total_deduplicated: int = Field(default=0, ge=0)
    scoring_enabled: bool = False
    scoring_cost_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    source_results: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    triggered_by: DiscoveryTrigger = "manual"


class DiscoveryRunCreate(DiscoveryRunBase):
    pass


class DiscoveryRunResponse(DiscoveryRunBase):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "11111111-2222-3333-4444-555555555555",
                "started_at": "2026-05-04T16:36:00Z",
                "completed_at": "2026-05-04T16:36:42Z",
                "duration_seconds": "42.3",
                "sources_run": ["reddit", "advisory", "wikipedia", "gdelt"],
                "total_candidates": 240,
                "total_saved": 194,
                "total_deduplicated": 46,
                "scoring_enabled": False,
                "scoring_cost_usd": "0",
                "source_results": {
                    "reddit": {"candidates": 91, "status": "ok"},
                    "advisory": {"candidates": 51, "status": "ok"},
                    "wikipedia": {"candidates": 77, "status": "ok"},
                    "gdelt": {"candidates": 21, "status": "ok"},
                },
                "errors": [],
                "triggered_by": "manual",
                "created_at": "2026-05-04T16:36:00Z",
            }
        }
    )

    id: uuid.UUID
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> DiscoveryRunResponse:
        return cls.model_validate(row)


# Bare-name alias, matching the convention on the other newer model files.
DiscoveryRun = DiscoveryRunBase

__all__ = [
    "DiscoveryRun",
    "DiscoveryRunBase",
    "DiscoveryRunCreate",
    "DiscoveryRunResponse",
    "DiscoveryTrigger",
]
