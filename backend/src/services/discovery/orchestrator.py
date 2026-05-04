"""Discovery orchestrator — runs all sources, scores, deduplicates, saves.

This is the main entry point for the topic discovery pipeline.
Can be run via CLI, cron, or as a background task in the Railway worker.

Usage:
    # Run all sources
    python -m src.services.discovery

    # Run specific source
    python -m src.services.discovery --source reddit

    # Run with scoring
    python -m src.services.discovery --score
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .advisory_poller import AdvisoryPoller
from .competitor_scanner import CompetitorScanner
from .court_listener import CourtListenerScanner
from .gdelt_scanner import GdeltScanner
from .google_trends import GoogleTrendsScanner
from .reddit_scanner import RedditScanner
from .topic_scorer import TopicScorer
from .wikipedia_monitor import WikipediaMonitor

if TYPE_CHECKING:
    from .base import DiscoverySource, TopicCandidate

logger = logging.getLogger("discovery")

# All available discovery sources
SOURCE_REGISTRY: dict[str, type[DiscoverySource]] = {
    "reddit": RedditScanner,
    "advisory": AdvisoryPoller,
    "competitor": CompetitorScanner,
    "court_listener": CourtListenerScanner,
    "gdelt": GdeltScanner,
    "google_trends": GoogleTrendsScanner,
    "wikipedia": WikipediaMonitor,
}


class DiscoveryOrchestrator:
    """Orchestrates all topic discovery sources and scoring."""

    def __init__(self, supabase_client: Any, config: Any | None = None):
        self.supabase = supabase_client
        self.config = config
        self.sources: dict[str, DiscoverySource] = {}

        # Initialize all sources
        for name, source_cls in SOURCE_REGISTRY.items():
            try:
                self.sources[name] = source_cls(supabase_client, config)
            except Exception as e:
                logger.warning(f"Failed to initialize source '{name}': {e}")

    async def run_all(self, score: bool = True) -> dict[str, Any]:
        """Run all discovery sources, optionally score results, and save."""
        start = datetime.now(UTC)
        results = {
            "started_at": start.isoformat(),
            "sources": {},
            "total_candidates": 0,
            "total_saved": 0,
            "errors": [],
        }

        all_candidates: list[TopicCandidate] = []

        # Run each source
        for name, source in self.sources.items():
            try:
                logger.info(f"Running discovery source: {name}")
                candidates = await source.scan()
                results["sources"][name] = {
                    "candidates": len(candidates),
                    "status": "ok",
                }
                all_candidates.extend(candidates)
            except Exception as e:
                logger.error(f"Source '{name}' failed: {e}")
                results["sources"][name] = {
                    "candidates": 0,
                    "status": "error",
                    "error": str(e),
                }
                results["errors"].append(f"{name}: {e}")

        results["total_candidates"] = len(all_candidates)

        # Score candidates using Claude Haiku
        if score and all_candidates:
            anthropic_cfg = getattr(self.config, "anthropic", None) if self.config else None
            api_key = getattr(anthropic_cfg, "api_key", None) or None
            if api_key:
                logger.info(f"Scoring {len(all_candidates)} candidates with Claude Haiku...")
                scorer = TopicScorer(api_key)
                all_candidates = await scorer.score_candidates(all_candidates)
                results["scoring"] = "completed"
            else:
                logger.warning("No ANTHROPIC_API_KEY — skipping scoring")
                results["scoring"] = "skipped (no API key)"

        # Deduplicate against existing topics
        all_candidates = await self._deduplicate(all_candidates)

        # Save to discovered_topics
        saved = 0
        for source in self.sources.values():
            saved += await source.save_candidates(
                [c for c in all_candidates if c.source == source.name]
            )
        # Handle candidates from sources that aren't in the sources dict
        remaining = [c for c in all_candidates if c.source not in self.sources]
        if remaining and self.sources:
            first_source = next(iter(self.sources.values()))
            saved += await first_source.save_candidates(remaining)

        results["total_saved"] = saved
        results["completed_at"] = datetime.now(UTC).isoformat()
        results["duration_seconds"] = (datetime.now(UTC) - start).total_seconds()

        logger.info(
            f"Discovery complete: {results['total_candidates']} found, "
            f"{saved} saved, {len(results['errors'])} errors"
        )
        return results

    async def run_source(self, source_name: str, score: bool = False) -> dict[str, Any]:
        """Run a single discovery source."""
        if source_name not in self.sources:
            available = ", ".join(self.sources.keys())
            raise ValueError(f"Unknown source '{source_name}'. Available: {available}")

        source = self.sources[source_name]
        logger.info(f"Running single source: {source_name}")
        candidates = await source.scan()

        if score and candidates:
            anthropic_cfg = getattr(self.config, "anthropic", None) if self.config else None
            api_key = getattr(anthropic_cfg, "api_key", None) or None
            if api_key:
                scorer = TopicScorer(api_key)
                candidates = await scorer.score_candidates(candidates)

        candidates = await self._deduplicate(candidates)
        saved = await source.save_candidates(candidates)

        return {
            "source": source_name,
            "candidates_found": len(candidates),
            "candidates_saved": saved,
        }

    async def _deduplicate(self, candidates: list[TopicCandidate]) -> list[TopicCandidate]:
        """Remove candidates that are too similar to existing topics."""
        if not candidates:
            return candidates

        # Fetch existing topic titles for fuzzy matching
        try:
            existing = self.supabase.table("discovered_topics").select(
                "title"
            ).is_("used_in_video_id", "null").execute()
            existing_titles = {row["title"].lower() for row in (existing.data or [])}
        except Exception as e:
            logger.warning(f"Failed to fetch existing topics for dedup: {e}")
            return candidates

        deduped = []
        seen_titles: set[str] = set()

        for c in candidates:
            title_lower = c.title.lower()

            # Skip if exact match to existing
            if title_lower in existing_titles:
                continue

            # Skip if too similar to another candidate in this batch
            if any(self._is_similar(title_lower, seen) for seen in seen_titles):
                continue

            # Skip if too similar to existing (simple substring check)
            if any(self._is_similar(title_lower, ex) for ex in existing_titles):
                continue

            seen_titles.add(title_lower)
            deduped.append(c)

        logger.info(f"Dedup: {len(candidates)} → {len(deduped)} candidates")
        return deduped

    @staticmethod
    def _is_similar(a: str, b: str, threshold: float = 0.6) -> bool:
        """Simple similarity check using word overlap (Jaccard)."""
        words_a = set(a.split())
        words_b = set(b.split())
        if not words_a or not words_b:
            return False
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union) > threshold


async def main():
    """CLI entry point for running discovery."""
    import argparse
    import os
    import sys

    # Add project root to path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

    parser = argparse.ArgumentParser(description="Run topic discovery pipeline")
    parser.add_argument("--source", type=str, help="Run specific source only")
    parser.add_argument("--score", action="store_true", help="Score with Claude Haiku")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)-20s %(levelname)-5s %(message)s",
    )

    # Import config and supabase client. CrimeMill Settings is nested:
    #   settings.database.url / settings.database.service_role_key
    try:
        from src.config import get_settings
        settings = get_settings()

        from supabase import create_client
        supabase = create_client(
            settings.database.url, settings.database.service_role_key
        )
    except ImportError:
        logger.error("Could not import settings. Run from backend/ directory.")
        sys.exit(1)

    orchestrator = DiscoveryOrchestrator(supabase, settings)

    if args.source:
        result = await orchestrator.run_source(args.source, score=args.score)
    else:
        result = await orchestrator.run_all(score=args.score)

    # Pretty-print results
    import json
    print(json.dumps(result, indent=2, default=str))


# Package-level __init__.py content follows in __init__.py
