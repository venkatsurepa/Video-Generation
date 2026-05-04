"""Reddit monitoring for true crime and travel safety topics.

Scans subreddits for trending posts about crime cases and travel dangers.
Uses Reddit's public JSON API (no auth required for reading).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from .base import DiscoveryChannel, DiscoverySource, TopicCandidate

# Subreddits to scan, grouped by channel
CRIME_SUBREDDITS = [
    "TrueCrime",
    "UnresolvedMysteries",
    "TrueCrimeDiscussion",
    "serialkillers",
    "Scams",
]
TRAVEL_SUBREDDITS = [
    "travel",
    "solotravel",
    "TravelHacks",
    "TravelNoPics",
]

# Keywords that signal video-worthy content
CRIME_KEYWORDS = frozenset({
    "murder", "killed", "convicted", "sentenced", "arrested", "fraud",
    "ponzi", "scam", "heist", "robbery", "kidnap", "missing", "cold case",
    "serial killer", "organized crime", "drug trafficking", "corruption",
    "embezzle", "launder", "cartel", "mafia", "con artist", "identity theft",
    "cybercrime", "ransomware", "wrongful conviction", "exonerated",
    "unsolved", "investigation", "FBI", "DOJ", "indicted",
})
TRAVEL_KEYWORDS = frozenset({
    "scam", "scammed", "robbed", "pickpocket", "dangerous", "unsafe",
    "warning", "be careful", "got mugged", "avoid", "tourist trap",
    "overcharged", "taxi scam", "drugged", "spiked", "kidnap",
    "passport stolen", "embassy", "travel advisory", "don't go",
    "worst experience", "nightmare", "safety", "crime", "arrested",
})

# Category mapping from subreddit + keyword context
CRIME_CATEGORY_MAP = {
    "murder": "murder", "killed": "murder", "serial killer": "serial_killer",
    "ponzi": "ponzi_scheme", "fraud": "corporate_fraud", "scam": "romance_scam",
    "heist": "heist", "robbery": "robbery", "kidnap": "kidnapping",
    "cold case": "cold_case", "missing": "cold_case", "unsolved": "cold_case",
    "wrongful conviction": "wrongful_conviction", "exonerated": "wrongful_conviction",
    "cybercrime": "cybercrime", "ransomware": "cybercrime", "hacker": "cybercrime",
    "drug trafficking": "drug_trafficking", "cartel": "drug_trafficking",
    "corruption": "government_corruption", "embezzle": "corporate_fraud",
    "organized crime": "organized_crime", "mafia": "organized_crime",
}
TRAVEL_CATEGORY_MAP = {
    "scam": "tourist_scam", "scammed": "tourist_scam", "taxi scam": "taxi_scam",
    "pickpocket": "pickpocketing_ring", "robbed": "robbery",
    "dangerous": "destination_safety", "unsafe": "destination_safety",
    "drugged": "destination_safety", "spiked": "destination_safety",
    "kidnap": "kidnapping_risk", "passport stolen": "destination_safety",
    "embassy": "destination_safety", "travel advisory": "destination_safety",
}

# Minimum upvotes to consider a post
MIN_UPVOTES_CRIME = 200
MIN_UPVOTES_TRAVEL = 150


class RedditScanner(DiscoverySource):
    """Scans Reddit for trending true crime and travel safety posts."""

    name = "reddit"

    def __init__(self, supabase_client: Any, config: Any | None = None):
        super().__init__(supabase_client, config)
        self.user_agent = "CrimeMill-Discovery/1.0 (content research bot)"

    async def scan(self) -> list[TopicCandidate]:
        """Scan all configured subreddits for video-worthy topics."""
        candidates: list[TopicCandidate] = []

        async with httpx.AsyncClient(
            headers={"User-Agent": self.user_agent},
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            # Scan crime subreddits
            for sub in CRIME_SUBREDDITS:
                try:
                    posts = await self._fetch_subreddit(client, sub, "hot", limit=50)
                    posts += await self._fetch_subreddit(client, sub, "top", limit=25, time_filter="week")
                    for post in posts:
                        candidate = self._evaluate_crime_post(post, sub)
                        if candidate:
                            candidates.append(candidate)
                    await asyncio.sleep(2)  # Rate limit: 1 req/2s
                except Exception as e:
                    self.logger.warning(f"Failed to scan r/{sub}: {e}")

            # Scan travel subreddits
            for sub in TRAVEL_SUBREDDITS:
                try:
                    posts = await self._fetch_subreddit(client, sub, "hot", limit=50)
                    posts += await self._fetch_subreddit(client, sub, "top", limit=25, time_filter="week")
                    for post in posts:
                        candidate = self._evaluate_travel_post(post, sub)
                        if candidate:
                            candidates.append(candidate)
                    await asyncio.sleep(2)
                except Exception as e:
                    self.logger.warning(f"Failed to scan r/{sub}: {e}")

        self.logger.info(f"Reddit scan found {len(candidates)} candidates")
        return candidates

    async def _fetch_subreddit(
        self,
        client: httpx.AsyncClient,
        subreddit: str,
        sort: str = "hot",
        limit: int = 50,
        time_filter: str = "week",
    ) -> list[dict]:
        """Fetch posts from a subreddit via the public JSON API."""
        url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
        params = {"limit": min(limit, 100), "raw_json": 1}
        if sort == "top":
            params["t"] = time_filter

        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        posts = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            if post.get("stickied") or post.get("over_18"):
                continue
            posts.append({
                "title": post.get("title", ""),
                "selftext": post.get("selftext", "")[:2000],
                "url": f"https://reddit.com{post.get('permalink', '')}",
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "created_utc": post.get("created_utc", 0),
                "subreddit": subreddit,
            })
        return posts

    def _evaluate_crime_post(self, post: dict, subreddit: str) -> TopicCandidate | None:
        """Evaluate if a crime subreddit post is video-worthy."""
        if post["score"] < MIN_UPVOTES_CRIME:
            return None

        text = f"{post['title']} {post['selftext']}".lower()
        matched_keywords = [kw for kw in CRIME_KEYWORDS if kw in text]
        if not matched_keywords:
            return None

        # Determine category from keywords
        category = "other"
        for kw in matched_keywords:
            if kw in CRIME_CATEGORY_MAP:
                category = CRIME_CATEGORY_MAP[kw]
                break

        # Score: upvotes + comment engagement + keyword density
        score = min(100, (
            min(post["score"] / 50, 40) +  # Upvote component (max 40)
            min(post["num_comments"] / 20, 30) +  # Comment engagement (max 30)
            min(len(matched_keywords) * 5, 30)  # Keyword density (max 30)
        ))

        return TopicCandidate(
            title=self._clean_title(post["title"]),
            description=post["selftext"][:500] if post["selftext"] else f"Trending crime discussion on r/{subreddit}",
            category=category,
            channel=DiscoveryChannel.CRIMEMILL,
            source="reddit",
            source_url=post["url"],
            raw_signals={
                "subreddit": subreddit,
                "upvotes": post["score"],
                "comments": post["num_comments"],
                "matched_keywords": matched_keywords[:10],
            },
            score=score,
        )

    def _evaluate_travel_post(self, post: dict, subreddit: str) -> TopicCandidate | None:
        """Evaluate if a travel subreddit post is video-worthy."""
        if post["score"] < MIN_UPVOTES_TRAVEL:
            return None

        text = f"{post['title']} {post['selftext']}".lower()
        matched_keywords = [kw for kw in TRAVEL_KEYWORDS if kw in text]
        if not matched_keywords:
            return None

        category = "destination_safety"
        for kw in matched_keywords:
            if kw in TRAVEL_CATEGORY_MAP:
                category = TRAVEL_CATEGORY_MAP[kw]
                break

        # Try to extract a country/city from the title
        country_code = self._extract_country_hint(post["title"])

        score = min(100, (
            min(post["score"] / 40, 40) +
            min(post["num_comments"] / 15, 30) +
            min(len(matched_keywords) * 5, 30)
        ))

        return TopicCandidate(
            title=self._clean_title(post["title"]),
            description=post["selftext"][:500] if post["selftext"] else f"Travel safety discussion on r/{subreddit}",
            category=category,
            channel=DiscoveryChannel.STREET_LEVEL,
            source="reddit",
            source_url=post["url"],
            raw_signals={
                "subreddit": subreddit,
                "upvotes": post["score"],
                "comments": post["num_comments"],
                "matched_keywords": matched_keywords[:10],
            },
            score=score,
            country_code=country_code,
        )

    @staticmethod
    def _clean_title(title: str) -> str:
        """Clean Reddit title into a presentable format."""
        # Remove common Reddit prefixes
        title = re.sub(r"^\[.*?\]\s*", "", title)
        title = re.sub(r"^(TIL|PSA|LPT|ELI5|CMV|TIFU)\s*:?\s*", "", title, flags=re.IGNORECASE)
        return title.strip()[:200]

    @staticmethod
    def _extract_country_hint(title: str) -> str | None:
        """Try to extract a country code from the post title. Returns None if ambiguous."""
        # Common country/city names → ISO codes (non-exhaustive, covers top travel destinations)
        hints = {
            "thailand": "TH", "bangkok": "TH", "phuket": "TH", "chiang mai": "TH",
            "mexico": "MX", "mexico city": "MX", "cancun": "MX", "tulum": "MX",
            "bali": "ID", "indonesia": "ID", "jakarta": "ID",
            "turkey": "TR", "istanbul": "TR",
            "portugal": "PT", "lisbon": "PT",
            "spain": "ES", "barcelona": "ES", "madrid": "ES",
            "france": "FR", "paris": "FR",
            "italy": "IT", "rome": "IT", "naples": "IT",
            "colombia": "CO", "medellin": "CO", "bogota": "CO",
            "brazil": "BR", "rio": "BR", "sao paulo": "BR",
            "india": "IN", "delhi": "IN", "mumbai": "IN", "goa": "IN",
            "egypt": "EG", "cairo": "EG",
            "morocco": "MA", "marrakech": "MA",
            "south africa": "ZA", "cape town": "ZA", "johannesburg": "ZA",
            "japan": "JP", "tokyo": "JP",
            "vietnam": "VN", "hanoi": "VN", "ho chi minh": "VN",
            "cambodia": "KH", "phnom penh": "KH", "siem reap": "KH",
            "peru": "PE", "lima": "PE", "cusco": "PE",
            "argentina": "AR", "buenos aires": "AR",
            "costa rica": "CR",
            "philippines": "PH", "manila": "PH",
            "greece": "GR", "athens": "GR",
            "kenya": "KE", "nairobi": "KE",
            "tanzania": "TZ",
            "ecuador": "EC", "quito": "EC",
        }
        title_lower = title.lower()
        for name, code in hints.items():
            if name in title_lower:
                return code
        return None
