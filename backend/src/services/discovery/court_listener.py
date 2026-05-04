"""CourtListener API integration for legal case discovery.

Searches CourtListener for new filings, opinions, and developments
in crime-related cases. Useful for CrimeMill content about ongoing cases.
Requires COURTLISTENER_API_TOKEN env var.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from .base import DiscoveryChannel, DiscoverySource, TopicCandidate

COURTLISTENER_BASE = "https://www.courtlistener.com/api/rest/v3"

# Search queries for different crime categories
CASE_SEARCH_QUERIES = [
    {"query": "fraud conviction sentence", "category": "corporate_fraud"},
    {"query": "ponzi scheme SEC", "category": "ponzi_scheme"},
    {"query": "money laundering indictment", "category": "white_collar"},
    {"query": "embezzlement federal", "category": "corporate_fraud"},
    {"query": "insider trading conviction", "category": "corporate_fraud"},
    {"query": "RICO racketeering", "category": "organized_crime"},
    {"query": "corruption bribery public official", "category": "government_corruption"},
    {"query": "cybercrime hacking federal", "category": "cybercrime"},
    {"query": "drug trafficking cartel", "category": "drug_trafficking"},
    {"query": "wrongful conviction exoneration", "category": "wrongful_conviction"},
    {"query": "murder conviction appeal", "category": "murder"},
    {"query": "serial killer trial", "category": "serial_killer"},
    {"query": "kidnapping federal", "category": "kidnapping"},
]


class CourtListenerScanner(DiscoverySource):
    """Searches CourtListener for new legal developments in crime cases."""

    name = "court_listener"

    def __init__(self, supabase_client: Any, config: Any | None = None):
        super().__init__(supabase_client, config)
        # CrimeMill Settings is nested: config.court_listener.api_token
        court = getattr(config, "court_listener", None) if config else None
        self.api_token = getattr(court, "api_token", None) or None

    async def scan(self) -> list[TopicCandidate]:
        """Search CourtListener for recent opinions in crime-related cases."""
        if not self.api_token:
            self.logger.warning("No COURTLISTENER_API_TOKEN — skipping court scan")
            return []

        candidates: list[TopicCandidate] = []
        cutoff = (datetime.now(UTC) - timedelta(days=14)).strftime("%Y-%m-%d")

        async with httpx.AsyncClient(
            timeout=30.0,
            headers={"Authorization": f"Token {self.api_token}"},
        ) as client:
            for search in CASE_SEARCH_QUERIES:
                try:
                    results = await self._search_opinions(client, search["query"], cutoff)
                    for opinion in results:
                        candidate = self._opinion_to_candidate(opinion, search["category"])
                        if candidate:
                            candidates.append(candidate)
                except Exception as e:
                    self.logger.warning(f"CourtListener search failed for '{search['query']}': {e}")

        self.logger.info(f"CourtListener scan found {len(candidates)} candidates")
        return candidates

    async def _search_opinions(
        self, client: httpx.AsyncClient, query: str, date_after: str, max_results: int = 5
    ) -> list[dict]:
        """Search CourtListener opinions API."""
        url = f"{COURTLISTENER_BASE}/search/"
        params = {
            "q": query,
            "type": "o",  # opinions
            "order_by": "dateFiled desc",
            "filed_after": date_after,
            "page_size": max_results,
        }
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])

    def _opinion_to_candidate(self, opinion: dict, category: str) -> TopicCandidate | None:
        """Convert a CourtListener opinion into a topic candidate."""
        case_name = opinion.get("caseName", "") or opinion.get("case_name", "")
        if not case_name or len(case_name) < 5:
            return None

        court = opinion.get("court", "") or opinion.get("court_id", "")
        date_filed = opinion.get("dateFiled", "") or opinion.get("date_filed", "")
        snippet = opinion.get("snippet", "") or opinion.get("text", "")[:500]
        absolute_url = opinion.get("absolute_url", "")

        # Score based on court level and recency
        score = 40  # Base
        court_lower = str(court).lower()
        if "supreme" in court_lower:
            score += 30
        elif "circuit" in court_lower or "appeals" in court_lower:
            score += 20
        elif "district" in court_lower:
            score += 10

        # Recency bonus
        if date_filed:
            try:
                filed_date = datetime.strptime(date_filed[:10], "%Y-%m-%d")
                days_old = (datetime.now() - filed_date).days
                if days_old <= 3:
                    score += 20
                elif days_old <= 7:
                    score += 10
            except ValueError:
                pass

        url = f"https://www.courtlistener.com{absolute_url}" if absolute_url else None

        return TopicCandidate(
            title=f"Legal update: {case_name[:150]}",
            description=f"Court: {court}. Filed: {date_filed}. {snippet[:400]}",
            category=category,
            channel=DiscoveryChannel.CRIMEMILL,
            source="court_listener",
            source_url=url,
            raw_signals={
                "case_name": case_name,
                "court": str(court),
                "date_filed": date_filed,
            },
            score=min(100, score),
        )
