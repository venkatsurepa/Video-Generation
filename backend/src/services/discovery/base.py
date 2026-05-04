"""Base class and shared types for topic discovery sources."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class DiscoveryChannel(StrEnum):
    CRIMEMILL = "crimemill"
    STREET_LEVEL = "street_level"
    BOTH = "both"


@dataclass
class TopicCandidate:
    """A potential video topic discovered by a source."""

    title: str
    description: str
    category: str  # Must match case_files category CHECK
    channel: DiscoveryChannel
    source: str  # e.g., "reddit", "gdelt", "state_dept", "competitor", "court_listener"
    source_url: str | None = None
    raw_signals: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0  # 0-100, set by scorer
    country_code: str | None = None  # ISO 3166-1 alpha-2 for travel topics
    discovered_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_discovered_topic_row(self) -> dict[str, Any]:
        """Convert to a row for the discovered_topics table."""
        return {
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "composite_score": self.score,
            "source_signals": {
                "source": self.source,
                "channel": self.channel.value,
                "source_url": self.source_url,
                "country_code": self.country_code,
                **self.raw_signals,
            },
            "priority": self._score_to_priority(),
        }

    def _score_to_priority(self) -> str:
        if self.score >= 75:
            return "immediate"
        elif self.score >= 50:
            return "this_week"
        else:
            return "low"


class DiscoverySource(ABC):
    """Abstract base class for all topic discovery sources."""

    name: str = "base"

    def __init__(self, supabase_client: Any, config: Any | None = None):
        self.supabase = supabase_client
        self.config = config
        self.logger = logging.getLogger(f"discovery.{self.name}")

    @abstractmethod
    async def scan(self) -> list[TopicCandidate]:
        """Scan the source and return topic candidates."""
        ...

    async def save_candidates(self, candidates: list[TopicCandidate]) -> int:
        """Save candidates to discovered_topics, skipping duplicates. Returns count saved."""
        saved = 0
        for c in candidates:
            row = c.to_discovered_topic_row()
            try:
                # Check for fuzzy title match using pg_trgm
                existing = self.supabase.table("discovered_topics").select("id").ilike(
                    "title", f"%{c.title[:60]}%"
                ).execute()
                if existing.data:
                    self.logger.debug(f"Skipping duplicate: {c.title[:60]}...")
                    continue

                self.supabase.table("discovered_topics").insert(row).execute()
                saved += 1
                self.logger.info(f"Saved topic: {c.title[:80]}")
            except Exception as e:
                self.logger.warning(f"Failed to save '{c.title[:60]}': {e}")
        return saved
