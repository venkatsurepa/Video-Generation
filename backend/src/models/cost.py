from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class CostEntry(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    stage: str
    provider: str
    model: str
    input_units: int
    output_units: int
    cost_usd: Decimal
    latency_ms: int
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> CostEntry:
        return cls.model_validate(row)
