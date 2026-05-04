"""Claude Haiku-powered virality scorer for topic candidates.

Takes raw TopicCandidate objects from discovery sources and uses
Claude Haiku to assess virality potential, narrative strength,
data availability, and competition gap.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from .base import TopicCandidate

logger = logging.getLogger("discovery.scorer")

SCORING_PROMPT = """You are a YouTube content strategist for two channels:
1. CrimeMill — true crime documentaries (murder, fraud, heists, cold cases, organized crime)
2. Street Level — travel danger narratives (what went wrong for travelers, what could have been done differently)

Score this topic candidate for its video potential. Return ONLY valid JSON, no markdown.

Topic: {title}
Description: {description}
Category: {category}
Channel: {channel}
Source: {source}
Source URL: {source_url}
Raw signals: {raw_signals}

Score each dimension 0-100:
- virality: Would this title get clicked? Is there emotional hook, surprise, or stakes?
- narrative_strength: Is there a clear story arc? Beginning, middle, end? Characters?
- data_availability: Can we find enough public information to script a 14-minute video?
- competition_gap: Are there few existing YouTube videos on this exact angle?
- timeliness: Is this relevant NOW? Breaking/trending, or evergreen?

Also provide:
- suggested_title: A better YouTube title if the current one is weak
- suggested_category: The best case_files category (from: corporate_fraud, ponzi_scheme, murder, serial_killer, organized_crime, heist, robbery, kidnapping, cold_case, wrongful_conviction, cybercrime, drug_trafficking, government_corruption, destination_safety, tourist_scam, other)
- reasoning: 1-2 sentences on why this would or wouldn't make a good video

JSON format:
{{
  "virality": 0,
  "narrative_strength": 0,
  "data_availability": 0,
  "competition_gap": 0,
  "timeliness": 0,
  "composite_score": 0,
  "suggested_title": "",
  "suggested_category": "",
  "reasoning": ""
}}

The composite_score should be a weighted average:
- virality: 30%
- narrative_strength: 25%
- data_availability: 20%
- competition_gap: 15%
- timeliness: 10%
"""


class TopicScorer:
    """Uses Claude Haiku to score topic candidates for video potential."""

    def __init__(self, anthropic_api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = anthropic_api_key
        self.model = model
        self.api_url = "https://api.anthropic.com/v1/messages"

    async def score_candidates(
        self, candidates: list[TopicCandidate], batch_size: int = 5
    ) -> list[TopicCandidate]:
        """Score a list of topic candidates using Claude Haiku. Returns sorted by score."""
        scored = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(0, len(candidates), batch_size):
                batch = candidates[i:i + batch_size]
                for candidate in batch:
                    try:
                        result = await self._score_single(client, candidate)
                        if result:
                            candidate.score = result.get("composite_score", candidate.score)
                            candidate.raw_signals["scorer"] = result
                            # Use suggested category if better
                            suggested_cat = result.get("suggested_category", "")
                            if suggested_cat and suggested_cat != "other":
                                candidate.category = suggested_cat
                            # Use suggested title if provided
                            suggested_title = result.get("suggested_title", "")
                            if suggested_title and len(suggested_title) > 10:
                                candidate.raw_signals["original_title"] = candidate.title
                                candidate.title = suggested_title
                        scored.append(candidate)
                    except Exception as e:
                        logger.warning(f"Failed to score '{candidate.title[:60]}': {e}")
                        scored.append(candidate)  # Keep unscored with original score

        # Sort by composite score descending
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored

    async def _score_single(self, client: httpx.AsyncClient, candidate: TopicCandidate) -> dict | None:
        """Score a single topic candidate via Claude Haiku."""
        prompt = SCORING_PROMPT.format(
            title=candidate.title[:200],
            description=candidate.description[:500],
            category=candidate.category,
            channel=candidate.channel.value,
            source=candidate.source,
            source_url=candidate.source_url or "N/A",
            raw_signals=json.dumps(candidate.raw_signals, default=str)[:500],
        )

        resp = await client.post(
            self.api_url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.model,
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()

        # Extract text from response
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")

        # Parse JSON from response
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.debug(f"Failed to parse scorer response: {text[:200]}")
            return None
