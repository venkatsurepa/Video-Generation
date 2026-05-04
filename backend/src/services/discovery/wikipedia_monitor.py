"""Wikipedia monitoring for newly notable crime cases and events.

Monitors Wikipedia's "In the news" and "Deaths" portals plus
recent edits to crime-related articles for emerging stories.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from .base import DiscoveryChannel, DiscoverySource, TopicCandidate

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

# Wikipedia categories to monitor for new/updated articles
CRIME_CATEGORIES = [
    "Category:2025_crimes",
    "Category:2026_crimes",
    "Category:Unsolved_murders",
    "Category:Ponzi_schemes",
    "Category:Corporate_scandals",
    "Category:American_fraudsters",
    "Category:People_convicted_of_fraud",
    "Category:FBI_Most_Wanted_Fugitives",
    "Category:Cold_cases",
    "Category:Wrongful_convictions",
]

# Keywords in article titles that suggest video-worthy crime content
TITLE_SIGNALS = frozenset({
    "murder", "scandal", "fraud", "theft", "robbery", "kidnapping",
    "massacre", "assassination", "heist", "disappearance", "conviction",
    "trial", "arrest", "indictment", "scheme", "laundering", "embezzlement",
    "corruption", "trafficking", "cartel", "mafia",
})


class WikipediaMonitor(DiscoverySource):
    """Monitors Wikipedia for newly notable crime cases and events."""

    name = "wikipedia"

    async def scan(self) -> list[TopicCandidate]:
        """Check Wikipedia for recently updated crime articles."""
        candidates: list[TopicCandidate] = []

        # Wikimedia's User-Agent policy returns 403 without a contact-bearing UA.
        # See https://meta.wikimedia.org/wiki/User-Agent_policy
        ua = "CrimeMillDiscovery/1.0 (https://github.com/venkatsurepa/Video-Generation; topic discovery)"
        async with httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": ua}
        ) as client:
            # 1. Check recent changes in crime categories
            for category in CRIME_CATEGORIES:
                try:
                    articles = await self._get_category_recent_changes(client, category)
                    for article in articles:
                        candidate = self._evaluate_article(article)
                        if candidate:
                            candidates.append(candidate)
                except Exception as e:
                    self.logger.debug(f"Failed to check {category}: {e}")

            # 2. Check "In the news" portal for crime stories
            try:
                itn_candidates = await self._check_in_the_news(client)
                candidates.extend(itn_candidates)
            except Exception as e:
                self.logger.debug(f"Failed to check ITN: {e}")

            # 3. Check recent deaths for notable criminals
            try:
                death_candidates = await self._check_recent_deaths(client)
                candidates.extend(death_candidates)
            except Exception as e:
                self.logger.debug(f"Failed to check deaths: {e}")

        self.logger.info(f"Wikipedia scan found {len(candidates)} candidates")
        return candidates

    def _evaluate_article(self, article: dict[str, Any]) -> TopicCandidate | None:
        """Convert a Wikipedia ``categorymembers`` entry into a candidate.

        Filters out non-article namespaces and disambiguation pages; routes
        the rest into a baseline-scored TopicCandidate that the scorer can
        promote later.
        """
        title = article.get("title", "")
        if not title or article.get("ns") != 0:
            return None
        if "(disambiguation)" in title.lower():
            return None
        return TopicCandidate(
            title=title[:200],
            description=f"Recently updated Wikipedia article: {title}",
            category=self._categorize_from_title(title),
            channel=DiscoveryChannel.CRIMEMILL,
            source="wikipedia",
            source_url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
            raw_signals={"pageid": article.get("pageid")},
            score=40.0,
        )

    async def _get_category_recent_changes(
        self, client: httpx.AsyncClient, category: str, limit: int = 20
    ) -> list[dict]:
        """Get recently modified articles in a Wikipedia category."""
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmsort": "timestamp",
            "cmdir": "desc",
            "cmlimit": limit,
            "cmtype": "page",
            "format": "json",
        }
        resp = await client.get(WIKIPEDIA_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("query", {}).get("categorymembers", [])

    async def _check_in_the_news(self, client: httpx.AsyncClient) -> list[TopicCandidate]:
        """Parse Wikipedia's 'In the news' section for crime-related items."""
        params = {
            "action": "parse",
            "page": "Template:In_the_news",
            "prop": "text|links",
            "format": "json",
        }
        resp = await client.get(WIKIPEDIA_API, params=params)
        resp.raise_for_status()
        data = resp.json()

        candidates = []
        links = data.get("parse", {}).get("links", [])
        text = data.get("parse", {}).get("text", {}).get("*", "")

        for link in links:
            title = link.get("*", "")
            if not title:
                continue
            title_lower = title.lower()
            if any(signal in title_lower for signal in TITLE_SIGNALS):
                # Extract a snippet from the HTML text near this link
                snippet = self._extract_snippet(text, title)
                candidates.append(TopicCandidate(
                    title=f"In the news: {title}",
                    description=snippet[:500] if snippet else f"Wikipedia 'In the news' article about {title}",
                    category=self._categorize_from_title(title),
                    channel=DiscoveryChannel.CRIMEMILL,
                    source="wikipedia",
                    source_url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                    raw_signals={"wikipedia_section": "in_the_news"},
                    score=70,  # ITN items are already notable
                ))
        return candidates

    async def _check_recent_deaths(self, client: httpx.AsyncClient) -> list[TopicCandidate]:
        """Check recent deaths portal for notable criminals whose stories could be revisited."""
        params = {
            "action": "parse",
            "page": "Deaths_in_2026",
            "prop": "links",
            "section": 0,
            "format": "json",
        }
        resp = await client.get(WIKIPEDIA_API, params=params)
        resp.raise_for_status()
        data = resp.json()

        candidates = []
        links = data.get("parse", {}).get("links", [])

        for link in links:
            title = link.get("*", "")
            if not title:
                continue
            # Check if this person is crime-related by fetching their article categories
            try:
                is_crime = await self._is_crime_related_person(client, title)
                if is_crime:
                    candidates.append(TopicCandidate(
                        title=f"Death of {title}: Their Crime Story",
                        description=f"Notable figure {title} recently died. Their involvement in criminal activity makes this a timely retrospective opportunity.",
                        category="other",
                        channel=DiscoveryChannel.CRIMEMILL,
                        source="wikipedia",
                        source_url=f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                        raw_signals={"wikipedia_section": "recent_deaths"},
                        score=65,
                    ))
            except Exception:
                pass

        return candidates

    async def _is_crime_related_person(self, client: httpx.AsyncClient, title: str) -> bool:
        """Check if a Wikipedia article about a person is crime-related."""
        params = {
            "action": "query",
            "titles": title,
            "prop": "categories",
            "cllimit": 50,
            "format": "json",
        }
        resp = await client.get(WIKIPEDIA_API, params=params)
        resp.raise_for_status()
        data = resp.json()

        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            categories = page.get("categories", [])
            for cat in categories:
                cat_title = cat.get("title", "").lower()
                if any(kw in cat_title for kw in (
                    "convicted", "criminal", "fraudster", "murderer", "killer",
                    "mob boss", "drug lord", "corrupt", "embezzler",
                    "fugitive", "prisoner", "inmate",
                )):
                    return True
        return False

    @staticmethod
    def _categorize_from_title(title: str) -> str:
        """Infer a case_files category from article title."""
        t = title.lower()
        if any(w in t for w in ("murder", "killing", "assassination", "massacre")):
            return "murder"
        if any(w in t for w in ("fraud", "scandal", "scheme", "embezzlement")):
            return "corporate_fraud"
        if any(w in t for w in ("robbery", "heist", "theft")):
            return "heist"
        if any(w in t for w in ("kidnapping", "abduction", "disappearance")):
            return "kidnapping"
        if any(w in t for w in ("trafficking", "cartel")):
            return "drug_trafficking"
        if any(w in t for w in ("corruption")):
            return "government_corruption"
        return "other"

    @staticmethod
    def _extract_snippet(html_text: str, link_title: str) -> str:
        """Extract text near a link in the ITN HTML."""
        # Simple approach: find the link text and grab surrounding text
        clean = re.sub(r"<[^>]+>", " ", html_text)
        clean = re.sub(r"\s+", " ", clean).strip()
        idx = clean.lower().find(link_title.lower())
        if idx >= 0:
            start = max(0, idx - 100)
            end = min(len(clean), idx + 300)
            return clean[start:end].strip()
        return ""
