"""Google Trends spike detection for crime and travel topics.

Uses pytrends to detect rising search interest in crime cases
and travel safety topics. Spikes indicate timely content opportunities.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .base import DiscoveryChannel, DiscoverySource, TopicCandidate

# Crime-related search terms to monitor
CRIME_TREND_TERMS = [
    "ponzi scheme news",
    "fraud conviction",
    "corporate scandal",
    "true crime case",
    "serial killer caught",
    "cold case solved",
    "wrongful conviction",
    "heist robbery",
    "money laundering",
    "cybercrime attack",
    "corruption scandal",
    "organized crime bust",
]

# Travel safety terms to monitor
TRAVEL_TREND_TERMS = [
    "{destination} safe to travel",
    "{destination} tourist scam",
    "{destination} travel warning",
    "{destination} dangerous",
]

# Top tourist destinations to check trends for
TRAVEL_DESTINATIONS = [
    ("Thailand", "TH"), ("Mexico", "MX"), ("Indonesia", "ID"), ("Turkey", "TR"),
    ("Colombia", "CO"), ("Brazil", "BR"), ("India", "IN"), ("Egypt", "EG"),
    ("Morocco", "MA"), ("South Africa", "ZA"), ("Peru", "PE"), ("Vietnam", "VN"),
    ("Philippines", "PH"), ("Cambodia", "KH"), ("Kenya", "KE"), ("Ecuador", "EC"),
    ("Costa Rica", "CR"), ("Guatemala", "GT"), ("Honduras", "HN"), ("Jamaica", "JM"),
]

SPIKE_THRESHOLD = 75  # Interest score above which we consider it a spike


class GoogleTrendsScanner(DiscoverySource):
    """Detects search interest spikes for crime and travel topics using Google Trends."""

    name = "google_trends"

    async def scan(self) -> list[TopicCandidate]:
        """Check Google Trends for spikes in crime and travel topics."""
        try:
            from pytrends.request import TrendReq
        except ImportError:
            self.logger.warning("pytrends not installed — pip install pytrends")
            return []

        candidates: list[TopicCandidate] = []

        try:
            pytrends = TrendReq(hl="en-US", tz=360)

            # Check crime trends
            crime_candidates = await asyncio.to_thread(
                self._check_crime_trends, pytrends
            )
            candidates.extend(crime_candidates)

            # Check travel destination trends
            travel_candidates = await asyncio.to_thread(
                self._check_travel_trends, pytrends
            )
            candidates.extend(travel_candidates)

        except Exception as e:
            self.logger.error(f"Google Trends scan failed: {e}")

        self.logger.info(f"Google Trends scan found {len(candidates)} candidates")
        return candidates

    def _check_crime_trends(self, pytrends: Any) -> list[TopicCandidate]:
        """Check crime-related search terms for spikes."""
        candidates = []

        # Process in batches of 5 (pytrends limit)
        for i in range(0, len(CRIME_TREND_TERMS), 5):
            batch = CRIME_TREND_TERMS[i:i + 5]
            try:
                pytrends.build_payload(batch, cat=0, timeframe="now 7-d")
                interest = pytrends.interest_over_time()

                if interest.empty:
                    continue

                for term in batch:
                    if term not in interest.columns:
                        continue
                    max_interest = int(interest[term].max())
                    recent_interest = int(interest[term].iloc[-1]) if len(interest) > 0 else 0

                    if max_interest >= SPIKE_THRESHOLD:
                        # Also check related queries for specific case names
                        related = self._get_related_queries(pytrends, term)

                        candidates.append(TopicCandidate(
                            title=f"Trending: {term.title()} (Interest: {max_interest})",
                            description=f"Google search interest spiked to {max_interest}/100 in the past 7 days. Related queries: {', '.join(related[:5])}",
                            category="other",
                            channel=DiscoveryChannel.CRIMEMILL,
                            source="google_trends",
                            raw_signals={
                                "search_term": term,
                                "max_interest": max_interest,
                                "recent_interest": recent_interest,
                                "related_queries": related[:10],
                            },
                            score=min(100, max_interest),
                        ))

            except Exception as e:
                self.logger.debug(f"Trends batch failed for {batch}: {e}")

        return candidates

    def _check_travel_trends(self, pytrends: Any) -> list[TopicCandidate]:
        """Check travel destination safety searches for spikes."""
        candidates = []

        for destination, country_code in TRAVEL_DESTINATIONS:
            terms = [
                f"{destination} safe",
                f"{destination} travel warning",
                f"{destination} dangerous",
            ]
            try:
                pytrends.build_payload(terms, cat=0, timeframe="now 7-d")
                interest = pytrends.interest_over_time()

                if interest.empty:
                    continue

                # Sum interest across all terms for this destination
                total_interest = 0
                peak_term = ""
                for term in terms:
                    if term in interest.columns:
                        max_val = int(interest[term].max())
                        if max_val > total_interest:
                            total_interest = max_val
                            peak_term = term

                if total_interest >= SPIKE_THRESHOLD:
                    candidates.append(TopicCandidate(
                        title=f"Is {destination} Safe? (Search interest spiking: {total_interest})",
                        description=f"Google searches for '{peak_term}' spiked to {total_interest}/100. Something is happening that's making people question safety.",
                        category="destination_safety",
                        channel=DiscoveryChannel.STREET_LEVEL,
                        source="google_trends",
                        source_url=f"https://trends.google.com/trends/explore?q={peak_term.replace(' ', '+')}",
                        raw_signals={
                            "destination": destination,
                            "peak_term": peak_term,
                            "max_interest": total_interest,
                        },
                        score=min(100, total_interest),
                        country_code=country_code,
                    ))

            except Exception as e:
                self.logger.debug(f"Trends check failed for {destination}: {e}")

        return candidates

    @staticmethod
    def _get_related_queries(pytrends: Any, term: str) -> list[str]:
        """Get rising related queries for a search term."""
        try:
            pytrends.build_payload([term], cat=0, timeframe="now 7-d")
            related = pytrends.related_queries()
            rising = related.get(term, {}).get("rising")
            if rising is not None and not rising.empty:
                return rising["query"].tolist()[:10]
        except Exception:
            pass
        return []
