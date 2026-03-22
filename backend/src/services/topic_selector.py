from __future__ import annotations

import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import orjson
import structlog
from psycopg.rows import dict_row
from rapidfuzz import fuzz

from src.models.topic import (
    CompetitorVideo,
    CoverageSaturation,
    GDELTSignal,
    RedditSignal,
    ScoredTopic,
    TopicCandidate,
    TopicPriority,
    TrendSignal,
)
from src.utils.retry import async_retry

if TYPE_CHECKING:
    import uuid

    import httpx
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()

# ---------- Constants ----------

# Google Trends RSS (free, no key)
GOOGLE_TRENDS_RSS_URL = "https://trends.google.com/trending/rss"
YOUTUBE_SUGGEST_URL = "http://suggestqueries.google.com/complete/search"

# Reddit JSON API (no PRAW, no key)
REDDIT_BASE_URL = "https://www.reddit.com"
REDDIT_SUBREDDITS = [
    "TrueCrime",
    "Scams",
    "UnresolvedMysteries",
    "news",
    "WhiteCollarCrime",
    "Fraud",
]
REDDIT_USER_AGENT = "CrimeMill/1.0 (topic-discovery; async-httpx)"

# GDELT direct API (free, updates every 15 min)
GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# YouTube Data API v3
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Crime-related keyword filters for Google Trends
CRIME_KEYWORDS = frozenset(
    {
        "fraud",
        "scam",
        "arrest",
        "murder",
        "crime",
        "indictment",
        "trial",
        "convicted",
        "sentenced",
        "guilty",
        "theft",
        "robbery",
        "kidnapping",
        "embezzlement",
        "laundering",
        "trafficking",
        "corruption",
        "ponzi",
        "forgery",
        "extortion",
        "bribery",
        "conspiracy",
        "homicide",
        "manslaughter",
        "cartel",
        "gang",
        "shooting",
        "stabbing",
        "missing",
        "suspect",
        "fugitive",
        "warrant",
        "investigation",
        "fbi",
        "doj",
        "sec",
        "prosecution",
        "heist",
    }
)

# Alphabet soup seed keywords for YouTube autocomplete
SEED_KEYWORDS = ["fraud", "scam", "crime documentary", "true crime", "criminal"]

# Scoring weights (Layer 5) — from bible §3.4
SCORE_WEIGHTS: dict[str, float] = {
    "recency": 0.15,
    "emotional_resonance": 0.15,
    "severity": 0.12,
    "search_volume": 0.10,
    "celebrity_involvement": 0.10,
    "ongoing_developments": 0.10,
    "media_coverage": 0.08,
    "social_media_buzz": 0.08,
    "competitor_saturation_inv": 0.07,
    "geographic_relevance": 0.05,
}

# ---------- SQL ----------

INSERT_DISCOVERED_TOPIC = """
INSERT INTO discovered_topics
    (id, title, description, category, composite_score, score_breakdown,
     source_signals, competitor_saturation, priority)
VALUES
    (%(id)s, %(title)s, %(description)s, %(category)s, %(composite_score)s,
     %(score_breakdown)s, %(source_signals)s, %(competitor_saturation)s, %(priority)s)
ON CONFLICT (id) DO UPDATE SET
    composite_score = EXCLUDED.composite_score,
    score_breakdown = EXCLUDED.score_breakdown,
    source_signals = EXCLUDED.source_signals,
    competitor_saturation = EXCLUDED.competitor_saturation,
    priority = EXCLUDED.priority
RETURNING *;
"""

LIST_TOP_TOPICS = """
SELECT *
FROM discovered_topics
WHERE used_in_video_id IS NULL
  AND priority != 'archived'
  AND (%(priority)s IS NULL OR priority = %(priority)s)
  AND (%(category)s IS NULL OR category = %(category)s)
ORDER BY composite_score DESC NULLS LAST
LIMIT %(limit)s OFFSET %(offset)s;
"""

GET_TOPIC = """
SELECT * FROM discovered_topics WHERE id = %(topic_id)s;
"""

ASSIGN_TOPIC = """
UPDATE discovered_topics
SET used_in_video_id = %(video_id)s,
    priority = 'archived'
WHERE id = %(topic_id)s
  AND used_in_video_id IS NULL
RETURNING *;
"""

ARCHIVE_TOPIC = """
UPDATE discovered_topics
SET priority = 'archived'
WHERE id = %(topic_id)s
RETURNING *;
"""

LIST_COMPETITOR_CHANNELS = """
SELECT youtube_channel_id, name, category
FROM competitor_channels
WHERE is_active = true;
"""

UPSERT_COMPETITOR_VIDEO = """
INSERT INTO competitor_videos
    (competitor_channel_id, youtube_video_id, title, published_at, view_count)
VALUES
    (%(competitor_channel_id)s, %(youtube_video_id)s, %(title)s,
     %(published_at)s, %(view_count)s)
ON CONFLICT (youtube_video_id) DO UPDATE SET
    view_count = EXCLUDED.view_count,
    scanned_at = now();
"""

GET_COMPETITOR_CHANNEL_ID = """
SELECT id FROM competitor_channels WHERE youtube_channel_id = %(yt_channel_id)s;
"""

UPDATE_CHANNEL_SCAN_TIME = """
UPDATE competitor_channels SET last_scanned_at = now()
WHERE youtube_channel_id = %(yt_channel_id)s;
"""


class TopicSelector:
    """Five-layer topic discovery, scoring, and ranking pipeline.

    Layers:
      1. Google Trends — detect breakout crime topics
      2. Reddit — stream trending crime stories
      3. GDELT — monitor breaking crime news
      4. YouTube — check competitor coverage saturation
      5. Score and rank all discovered topics

    Scoring: 10 weighted features × multipliers → 0-100+ composite score.
    """

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
        db_pool: AsyncConnectionPool,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._db = db_pool

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def discover_topics(self) -> list[ScoredTopic]:
        """Run the full five-layer discovery pipeline. Return top 20 scored topics."""
        # Layers 1-3 run concurrently
        trends_task = asyncio.create_task(self._safe(self.check_google_trends()))
        reddit_task = asyncio.create_task(self._safe(self.check_reddit()))
        gdelt_task = asyncio.create_task(self._safe(self.check_gdelt()))

        trends, reddit_signals, gdelt_signals = await asyncio.gather(
            trends_task,
            reddit_task,
            gdelt_task,
        )

        # Aggregate signals into candidate topics
        candidates = self._aggregate_signals(trends, reddit_signals, gdelt_signals)

        await logger.ainfo(
            "signals_collected",
            trends=len(trends),
            reddit=len(reddit_signals),
            gdelt=len(gdelt_signals),
            candidates=len(candidates),
        )

        # Layer 4: check competitor coverage for each candidate (concurrently, limited)
        semaphore = asyncio.Semaphore(3)

        async def _check(c: TopicCandidate) -> TopicCandidate:
            async with semaphore:
                c.coverage = await self._safe_coverage(c.title)
            return c

        candidates = await asyncio.gather(*[_check(c) for c in candidates])

        # Layer 5: score and rank
        scored = [self.score_topic(c) for c in candidates]
        scored.sort(key=lambda t: t.composite_score, reverse=True)
        top = scored[:20]

        # Persist to DB
        await self._persist_topics(top)

        await logger.ainfo(
            "discovery_complete",
            total_scored=len(scored),
            top_score=top[0].composite_score if top else 0,
        )

        return top

    async def get_top_topics(
        self,
        limit: int = 20,
        offset: int = 0,
        priority: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, object]]:
        """Fetch ranked topics from DB, excluding already-used topics."""
        async with self._db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                LIST_TOP_TOPICS,
                {"limit": limit, "offset": offset, "priority": priority, "category": category},
            )
            return await cur.fetchall()

    async def mark_topic_used(
        self, topic_id: uuid.UUID, video_id: uuid.UUID
    ) -> dict[str, object] | None:
        """Mark a topic as assigned to a video."""
        async with self._db.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(ASSIGN_TOPIC, {"topic_id": topic_id, "video_id": video_id})
                row = await cur.fetchone()
            await conn.commit()
        return row

    # ------------------------------------------------------------------
    # Layer 1: Google Trends
    # ------------------------------------------------------------------

    async def check_google_trends(self) -> list[TrendSignal]:
        """Detect breakout crime topics via Google Trends RSS + YouTube autocomplete."""
        signals: list[TrendSignal] = []

        # 1a. Google Trends RSS feed (US, crime-filtered)
        rss_signals = await self._fetch_trends_rss()
        signals.extend(rss_signals)

        # 1b. YouTube autocomplete "alphabet soup" for seed keywords
        autocomplete_signals = await self._fetch_youtube_autocomplete()
        signals.extend(autocomplete_signals)

        await logger.ainfo("google_trends_complete", signals=len(signals))
        return signals

    @async_retry(max_attempts=2, base_delay=1.0)
    async def _fetch_trends_rss(self) -> list[TrendSignal]:
        """Parse Google Trends RSS for crime-related trending topics."""
        signals: list[TrendSignal] = []
        try:
            resp = await self._http.get(
                GOOGLE_TRENDS_RSS_URL,
                params={"geo": "US"},
                timeout=15.0,
            )
            resp.raise_for_status()

            root = ET.fromstring(resp.text)
            ns = {"ht": "https://trends.google.com/trending/rss"}

            for item in root.iter("item"):
                title_el = item.find("title")
                if title_el is None or title_el.text is None:
                    continue
                title = title_el.text.strip()
                if not _matches_crime_keywords(title):
                    continue

                traffic_el = item.find("ht:approx_traffic", ns)
                interest = _parse_traffic_to_score(
                    traffic_el.text if traffic_el is not None and traffic_el.text else "0"
                )

                signals.append(
                    TrendSignal(
                        source="google_trends",
                        query=title,
                        interest_score=interest,
                        growth_label="Trending",
                    )
                )
        except Exception:
            await logger.awarning("trends_rss_failed", exc_info=True)

        return signals

    async def _fetch_youtube_autocomplete(self) -> list[TrendSignal]:
        """YouTube autocomplete 'alphabet soup' — append a-z to seed keywords."""
        signals: list[TrendSignal] = []
        seen: set[str] = set()

        for seed in SEED_KEYWORDS[:3]:  # limit to avoid rate limits
            for letter in "abcdefghij":  # first 10 letters per seed
                query = f"{seed} {letter}"
                try:
                    resp = await self._http.get(
                        YOUTUBE_SUGGEST_URL,
                        params={"client": "firefox", "ds": "yt", "q": query},
                        timeout=10.0,
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    suggestions = data[1] if len(data) > 1 else []

                    for suggestion in suggestions:
                        s = suggestion.strip().lower()
                        if s in seen or not _matches_crime_keywords(s):
                            continue
                        seen.add(s)
                        signals.append(
                            TrendSignal(
                                source="youtube_autocomplete",
                                query=suggestion.strip(),
                                interest_score=60,  # autocomplete = moderate interest
                                growth_label="Rising",
                            )
                        )
                except Exception:
                    continue

                # Rate limit: 3-5 second delay between requests
                await asyncio.sleep(3.5)

        return signals

    # ------------------------------------------------------------------
    # Layer 2: Reddit
    # ------------------------------------------------------------------

    async def check_reddit(self) -> list[RedditSignal]:
        """Detect trending crime stories from Reddit JSON API."""
        signals: list[RedditSignal] = []

        tasks = [self._fetch_subreddit(sub) for sub in REDDIT_SUBREDDITS]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, BaseException):
                await logger.awarning("reddit_subreddit_failed", error=str(result))
                continue
            signals.extend(result)

        # Sort by engagement velocity (upvotes as proxy)
        signals.sort(key=lambda s: s.upvotes, reverse=True)
        await logger.ainfo("reddit_complete", signals=len(signals))
        return signals

    @async_retry(max_attempts=2, base_delay=2.0)
    async def _fetch_subreddit(self, subreddit: str) -> list[RedditSignal]:
        """Fetch hot posts from a single subreddit via JSON API."""
        signals: list[RedditSignal] = []

        resp = await self._http.get(
            f"{REDDIT_BASE_URL}/r/{subreddit}/hot.json",
            params={"limit": 25},
            headers={"User-Agent": REDDIT_USER_AGENT},
            timeout=15.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()

        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            if post.get("stickied"):
                continue

            title = post.get("title", "")
            upvotes = post.get("ups", 0)
            ratio = post.get("upvote_ratio", 0.0)

            # Crime filter for general subs like r/news
            if subreddit in ("news",) and not _matches_crime_keywords(title):
                continue

            # Velocity filter: >100 upvotes with high ratio
            if upvotes < 50:
                continue

            created_utc = datetime.fromtimestamp(post.get("created_utc", 0), tz=UTC)
            entities = _extract_entities(title)

            signals.append(
                RedditSignal(
                    subreddit=subreddit,
                    title=title,
                    url=f"https://reddit.com{post.get('permalink', '')}",
                    upvotes=upvotes,
                    upvote_ratio=ratio,
                    num_comments=post.get("num_comments", 0),
                    num_crossposts=post.get("num_crossposts", 0),
                    created_utc=created_utc,
                    extracted_entities=entities,
                )
            )

        return signals

    # ------------------------------------------------------------------
    # Layer 3: GDELT
    # ------------------------------------------------------------------

    async def check_gdelt(self) -> list[GDELTSignal]:
        """Monitor breaking crime news via GDELT API (free, 15-min updates)."""
        signals: list[GDELTSignal] = []

        queries = [
            "fraud OR arrest OR indictment",
            "murder OR homicide OR kidnapping",
            "scam OR ponzi OR embezzlement",
        ]

        tasks = [self._fetch_gdelt_query(q) for q in queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        seen_urls: set[str] = set()
        for result in results:
            if isinstance(result, BaseException):
                await logger.awarning("gdelt_query_failed", error=str(result))
                continue
            for signal in result:
                if signal.url not in seen_urls:
                    seen_urls.add(signal.url)
                    signals.append(signal)

        await logger.ainfo("gdelt_complete", signals=len(signals))
        return signals

    @async_retry(max_attempts=2, base_delay=2.0)
    async def _fetch_gdelt_query(self, query: str) -> list[GDELTSignal]:
        """Execute a single GDELT API article search."""
        resp = await self._http.get(
            GDELT_API_URL,
            params={
                "query": query,
                "mode": "ArtList",
                "maxrecords": "50",
                "format": "json",
                "timespan": "24h",
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()

        signals: list[GDELTSignal] = []
        for article in data.get("articles", []):
            pub_date = article.get("seendate", "")
            try:
                published_at = datetime.strptime(pub_date[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
            except (ValueError, IndexError):
                published_at = datetime.now(UTC)

            signals.append(
                GDELTSignal(
                    title=article.get("title", ""),
                    url=article.get("url", ""),
                    source_name=article.get("domain", ""),
                    language=article.get("language", "English"),
                    theme=article.get("theme", ""),
                    tone=float(article.get("tone", 0)),
                    published_at=published_at,
                )
            )

        return signals

    # ------------------------------------------------------------------
    # Layer 4: Competitor Coverage
    # ------------------------------------------------------------------

    async def check_competitor_coverage(self, topic: str) -> CoverageSaturation:
        """Check how many tracked competitor channels have covered this topic."""
        async with self._db.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(LIST_COMPETITOR_CHANNELS)
            channels = await cur.fetchall()

        if not channels:
            return CoverageSaturation(topic=topic)

        competitor_videos: list[CompetitorVideo] = []
        channels_covered = 0

        for channel in channels:
            yt_id = channel["youtube_channel_id"]
            name = channel["name"]
            # Convert UC channel ID to UU uploads playlist
            uploads_playlist = "UU" + yt_id[2:] if yt_id.startswith("UC") else None
            if not uploads_playlist:
                continue

            videos = await self._search_channel_uploads(uploads_playlist, topic, name)
            if videos:
                channels_covered += 1
                competitor_videos.extend(videos)

        total = len(channels)
        saturation = _compute_saturation_score(channels_covered)

        return CoverageSaturation(
            topic=topic,
            channels_covered=channels_covered,
            total_channels_tracked=total,
            saturation_score=saturation,
            competitor_videos=competitor_videos,
        )

    async def _search_channel_uploads(
        self,
        playlist_id: str,
        topic: str,
        channel_name: str,
    ) -> list[CompetitorVideo]:
        """Search a channel's uploads playlist for topic matches via fuzzy matching."""
        api_key = self._settings.youtube.client_id  # reuse client_id as API key
        if not api_key:
            return []

        try:
            resp = await self._http.get(
                f"{YOUTUBE_API_BASE}/playlistItems",
                params={
                    "part": "snippet",
                    "playlistId": playlist_id,
                    "maxResults": 50,
                    "key": api_key,
                },
                timeout=15.0,
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            matches: list[CompetitorVideo] = []

            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                title = snippet.get("title", "")

                # Fuzzy match topic against video title
                ratio = fuzz.token_set_ratio(topic.lower(), title.lower())
                if ratio >= 65:
                    pub = snippet.get("publishedAt", "")
                    try:
                        pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pub_dt = datetime.now(UTC)

                    vid_id = snippet.get("resourceId", {}).get("videoId", "")

                    matches.append(
                        CompetitorVideo(
                            channel_name=channel_name,
                            video_title=title,
                            youtube_video_id=vid_id,
                            published_at=pub_dt,
                        )
                    )

            return matches
        except Exception:
            await logger.awarning(
                "competitor_search_failed",
                playlist=playlist_id,
                exc_info=True,
            )
            return []

    # ------------------------------------------------------------------
    # Layer 5: Scoring
    # ------------------------------------------------------------------

    @staticmethod
    def score_topic(topic: TopicCandidate) -> ScoredTopic:
        """Compute weighted composite score with bonus multipliers.

        10 features × weights → base score (0-10 each).
        Multiplied by 10 → 0-100 scale.
        Bonus multipliers applied on top.
        """
        # Compute feature scores (0-10 scale each)
        recency = _score_recency(topic.recency_days)
        emotional = min(topic.emotional_resonance, 10)
        severity = min(topic.severity_estimate, 10)
        search_vol = min(topic.search_volume_trend, 10)
        celebrity = min(topic.celebrity_involvement, 10)
        ongoing = 10 if topic.has_ongoing_developments else 3
        media = min(topic.media_coverage_level, 10)
        social = min(topic.social_media_buzz, 10)
        geo = min(topic.geographic_relevance, 10)

        # Competitor saturation (inverse): 0 covered = 10, 15+ = 2
        coverage = topic.coverage
        comp_inv = _score_competitor_saturation_inv(coverage.channels_covered) if coverage else 8

        features = {
            "recency": recency,
            "emotional_resonance": emotional,
            "severity": severity,
            "search_volume": search_vol,
            "celebrity_involvement": celebrity,
            "ongoing_developments": ongoing,
            "media_coverage": media,
            "social_media_buzz": social,
            "competitor_saturation_inv": comp_inv,
            "geographic_relevance": geo,
        }

        # Weighted sum × 10 → 0-100
        breakdown: dict[str, float] = {}
        raw_score = 0.0
        for feature, value in features.items():
            weight = SCORE_WEIGHTS[feature]
            weighted = value * weight
            breakdown[feature] = round(weighted * 10, 2)
            raw_score += weighted

        composite = round(raw_score * 10, 2)

        # Bonus multipliers
        multipliers: list[str] = []
        if coverage and coverage.channels_covered <= 3:
            composite *= 1.3
            multipliers.append("first_mover_x1.3")
        if topic.has_ongoing_developments:
            composite *= 1.2
            multipliers.append("sequel_potential_x1.2")

        composite = round(composite, 2)

        # Priority assignment
        priority: TopicPriority
        if composite >= 80:
            priority = "immediate"
        elif composite >= 60:
            priority = "this_week"
        else:
            priority = "low"

        return ScoredTopic(
            title=topic.title,
            description=topic.description,
            category=topic.category,
            composite_score=composite,
            score_breakdown=breakdown,
            multipliers_applied=multipliers,
            priority=priority,
            source_signals_count=len(topic.source_signals),
            competitor_saturation=coverage.saturation_score if coverage else 0.0,
        )

    # ------------------------------------------------------------------
    # Signal aggregation
    # ------------------------------------------------------------------

    @staticmethod
    def _aggregate_signals(
        trends: list[TrendSignal],
        reddit: list[RedditSignal],
        gdelt: list[GDELTSignal],
    ) -> list[TopicCandidate]:
        """Deduplicate and merge signals into TopicCandidate objects.

        Groups by fuzzy title matching — signals about the same story
        get merged into a single candidate.
        """
        candidates: list[TopicCandidate] = []
        used_indices: dict[str, set[int]] = {"trends": set(), "reddit": set(), "gdelt": set()}

        # Build candidates from Reddit first (highest signal quality)
        for i, r in enumerate(reddit):
            if i in used_indices["reddit"]:
                continue
            used_indices["reddit"].add(i)

            c = TopicCandidate(
                title=r.title[:200],
                description=f"From r/{r.subreddit}: {r.title}",
                source_signals=[r],
                social_media_buzz=_reddit_buzz_score(r),
            )

            # Find matching trends
            for j, t in enumerate(trends):
                if j not in used_indices["trends"] and fuzz.token_set_ratio(r.title, t.query) >= 60:
                    c.source_signals.append(t)
                    c.search_volume_trend = max(c.search_volume_trend, t.interest_score // 10)
                    used_indices["trends"].add(j)

            # Find matching GDELT
            for j, g in enumerate(gdelt):
                if j not in used_indices["gdelt"] and fuzz.token_set_ratio(r.title, g.title) >= 55:
                    c.source_signals.append(g)
                    c.media_coverage_level = 7  # appeared in GDELT = notable coverage
                    used_indices["gdelt"].add(j)

            candidates.append(c)

        # Remaining GDELT signals become their own candidates
        for i, g in enumerate(gdelt):
            if i in used_indices["gdelt"]:
                continue
            used_indices["gdelt"].add(i)
            candidates.append(
                TopicCandidate(
                    title=g.title[:200],
                    description=f"From {g.source_name}: {g.title}",
                    source_signals=[g],
                    media_coverage_level=6,
                )
            )

        # Remaining trends
        for i, t in enumerate(trends):
            if i in used_indices["trends"]:
                continue
            candidates.append(
                TopicCandidate(
                    title=t.query[:200],
                    description=f"Trending: {t.query} ({t.growth_label})",
                    source_signals=[t],
                    search_volume_trend=t.interest_score // 10,
                )
            )

        return candidates

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_topics(self, topics: list[ScoredTopic]) -> None:
        """Upsert scored topics into the database."""
        if not topics:
            return
        async with self._db.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                for t in topics:
                    await cur.execute(
                        INSERT_DISCOVERED_TOPIC,
                        {
                            "id": t.id,
                            "title": t.title,
                            "description": t.description,
                            "category": t.category,
                            "composite_score": t.composite_score,
                            "score_breakdown": orjson.dumps(t.score_breakdown).decode(),
                            "source_signals": orjson.dumps(
                                {"count": t.source_signals_count}
                            ).decode(),
                            "competitor_saturation": t.competitor_saturation,
                            "priority": t.priority,
                        },
                    )
            await conn.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _safe(coro: Any) -> list[Any]:
        """Run a coroutine, return empty list on failure."""
        try:
            result: list[Any] = await coro
            return result
        except Exception:
            await logger.awarning("discovery_layer_failed", exc_info=True)
            return []

    async def _safe_coverage(self, topic: str) -> CoverageSaturation:
        """Run competitor check, return empty on failure."""
        try:
            return await self.check_competitor_coverage(topic)
        except Exception:
            await logger.awarning("coverage_check_failed", topic=topic, exc_info=True)
            return CoverageSaturation(topic=topic)


# ---------- Module-level helpers ----------


def _matches_crime_keywords(text: str) -> bool:
    """Check if text contains any crime-related keywords."""
    words = set(re.findall(r"[a-z]+", text.lower()))
    return bool(words & CRIME_KEYWORDS)


def _parse_traffic_to_score(traffic_str: str) -> int:
    """Convert Google Trends traffic string (e.g. '500,000+') to 0-100 score."""
    cleaned = re.sub(r"[^0-9]", "", traffic_str)
    if not cleaned:
        return 50  # trending but no volume data
    volume = int(cleaned)
    if volume >= 1_000_000:
        return 100
    if volume >= 500_000:
        return 85
    if volume >= 100_000:
        return 70
    if volume >= 50_000:
        return 55
    if volume >= 10_000:
        return 40
    return 25


def _extract_entities(text: str) -> list[str]:
    """Extract likely proper nouns / case names from a title.

    Simple heuristic: consecutive capitalized words (2+).
    """
    entities: list[str] = []
    words = text.split()
    current: list[str] = []
    for w in words:
        # Strip punctuation for the check, keep original
        clean = re.sub(r"[^\w]", "", w)
        if clean and clean[0].isupper() and len(clean) > 1:
            current.append(w)
        else:
            if len(current) >= 2:
                entities.append(" ".join(current))
            current = []
    if len(current) >= 2:
        entities.append(" ".join(current))
    return entities


def _score_recency(days: int) -> int:
    """Score recency: today=10, past week=8, past month=6, older=3."""
    if days <= 1:
        return 10
    if days <= 7:
        return 8
    if days <= 30:
        return 6
    return 3


def _score_competitor_saturation_inv(channels_covered: int) -> int:
    """Inverse saturation score: 0 covered=10, 15+=2."""
    if channels_covered == 0:
        return 10
    if channels_covered <= 3:
        return 8
    if channels_covered <= 10:
        return 5
    return 2


def _compute_saturation_score(channels_covered: int) -> float:
    """Saturation as 0.0-1.0 ratio (for storage/display)."""
    # Normalize against a baseline of 15 channels = fully saturated
    return min(channels_covered / 15.0, 1.0)


def _reddit_buzz_score(signal: RedditSignal) -> int:
    """Convert Reddit signal strength to 0-10 social buzz score."""
    score = 0
    if signal.upvotes >= 10000:
        score = 10
    elif signal.upvotes >= 5000:
        score = 8
    elif signal.upvotes >= 1000:
        score = 6
    elif signal.upvotes >= 500:
        score = 5
    elif signal.upvotes >= 100:
        score = 3
    else:
        score = 1

    # Bonus for cross-posting (mainstream breakout)
    if signal.num_crossposts > 0:
        score = min(score + 2, 10)

    return score
