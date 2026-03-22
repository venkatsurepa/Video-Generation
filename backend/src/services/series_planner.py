"""Series planner — multi-episode narrative arcs and cross-video hooks.

Organises videos into series (multi-part investigations, thematic seasons,
ongoing arcs) with AI-planned narrative arcs, cross-video hooks (recaps,
teasers, end screens), and YouTube playlist integration.

Series-based content drives 4-7x algorithmic promotion when YouTube detects
3+ videos watched in a single session (Bible §7B.3).
"""

from __future__ import annotations

import asyncio
import json
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, cast

import anthropic
import structlog

from src.db.queries import (
    GET_SERIES,
    GET_SERIES_ANALYTICS,
    GET_SERIES_EPISODES,
    INSERT_SERIES,
    INSERT_SERIES_EPISODE,
    LINK_EPISODE_VIDEO,
    LIST_SERIES,
    UPDATE_EPISODE_HOOKS,
    UPDATE_SERIES_ARC,
    UPDATE_SERIES_PLAYLIST,
)
from src.models.script import APICallCost
from src.models.series import (
    CrossLink,
    CrossVideoHooks,
    EpisodeArcPlan,
    EpisodeMetric,
    SeriesAnalytics,
    SeriesArc,
    SeriesEpisodeResponse,
    SeriesInput,
    SeriesResponse,
    SeriesSuggestion,
    SeriesSuggestionResult,
)
from src.services.script_generator import (
    MODEL_HAIKU,
    MODEL_SONNET,
    _calculate_cost,
    _strip_json_fences,
)
from src.utils.cost_tracker import track_cost

if TYPE_CHECKING:
    import uuid

    import httpx
    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()

_ONE_MILLION = Decimal("1_000_000")

# Maximum retry attempts for transient API errors
MAX_RETRIES: int = 3
BASE_RETRY_DELAY: float = 1.0


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

SERIES_ARC_SYSTEM_PROMPT: str = """\
You are a series architect for a premium true-crime YouTube documentary channel.
You plan multi-episode narrative arcs that maximise viewer retention across
episodes.  When YouTube detects 3+ videos watched in a single session, the
algorithm promotes the channel 4-7x more aggressively.

# ═══════════════════════════════════════════════════════════════
# SERIES TYPES
# ═══════════════════════════════════════════════════════════════

1. **multi_part** — Multi-part investigation of a single complex case.
   Each episode peels back a layer.  The final episode delivers the
   definitive conclusion.
   Example: "The Wirecard Files: Part 1 — The Golden Boy"

2. **thematic_season** — Conceptually linked episodes around a category.
   Each episode is self-contained but contributes to a larger thesis.
   Example: "Ponzi Season" — one famous Ponzi per episode.

3. **ongoing_arc** — Real-time coverage of an evolving story.
   Each episode covers new developments.  Build speculation between episodes.
   Example: "The FTX Trial" — one video per major trial development.

# ═══════════════════════════════════════════════════════════════
# ARC DESIGN PRINCIPLES
# ═══════════════════════════════════════════════════════════════

1. Each episode MUST have a clear **core question** it answers.
2. Each episode MUST end with an **open loop** that drives viewers to the next.
3. The overarching thesis should only be fully answerable after all episodes.
4. Episode 1 must be the most compelling — it hooks the entire series.
5. Place the biggest revelation at the ~75 % mark of the series (not finale).
6. The finale must provide catharsis and close ALL open loops.

## Open Loop Strategy
- Episode 1: open 3+ loops, close 1.
- Middle episodes: open 1-2 new loops while closing 1 from prior episodes.
- Penultimate episode: close all but the central question.
- Finale: close the central question.

## Title Conventions
For multi_part: "Series Title: Part N — Episode Subtitle"
For thematic_season: standalone titles that share a thematic template
For ongoing_arc: "Case Name — Development Title"

# ═══════════════════════════════════════════════════════════════
# RESPONSE FORMAT
# ═══════════════════════════════════════════════════════════════

Return a single JSON object (no markdown fences):

{
  "overarching_thesis": "The single big question the series answers",
  "narrative_structure": "e.g. linear chronological, investigation spiral",
  "episodes": [
    {
      "episode_number": 1,
      "title": "Series Title: Part 1 — Episode Subtitle",
      "core_question": "What question does this episode answer?",
      "key_revelation": "The main reveal or twist in this episode",
      "open_loop_forward": "Unanswered question carrying to the next episode",
      "suggested_hook_type": "cold_open",
      "estimated_length_minutes": 15
    }
  ],
  "recurring_motifs": ["motif1", "motif2"],
  "cliffhanger_strategy": "How episodes end to drive next-episode consumption"
}
"""


CROSS_VIDEO_HOOKS_SYSTEM_PROMPT: str = """\
You are a retention specialist for a true-crime YouTube series.  You generate
cross-episode hooks that glue individual videos into a binge-worthy sequence.

# ═══════════════════════════════════════════════════════════════
# YOUR OUTPUTS
# ═══════════════════════════════════════════════════════════════

## 1. Recap Narration (15-30 seconds)
- For viewers who click directly into this episode without watching prior ones.
- Summarise ONLY what is essential to understand THIS episode.
- End with a smooth transition into the current episode's hook.
- Write in the voice of a documentary narrator: measured, cinematic, gripping.

## 2. Teaser Narration (10-20 seconds)
- Placed BEFORE the end screen (last 20 s of video).
- Create an irresistible urge to click the next episode.
- Reveal JUST enough about the next episode's core question to intrigue.
- NEVER spoil the next episode's key revelation.

## 3. End Screen CTA (1-2 sentences)
- Text for the end screen card.
- Direct, action-oriented: "Watch Part 3 now to find out..."

## 4. Description Cross-Links
- Formatted markdown block for the video description showing all episodes:
  "📺 Watch the full series:
  Part 1: [title] — [link placeholder]
  ▶ Part 3: THIS VIDEO
  Part 4: Coming soon"

## 5. Cross-Links (info cards)
- 1-3 moments in this episode where an info card to another episode is relevant.

# ═══════════════════════════════════════════════════════════════
# RESPONSE FORMAT
# ═══════════════════════════════════════════════════════════════

Return a single JSON object (no markdown fences):

{
  "recap_narration": "In our last episode, we discovered...",
  "teaser_narration": "Next time: ...",
  "end_screen_cta": "Watch Part N now to find out...",
  "description_cross_links": "📺 Watch the full series:\\n...",
  "cross_links": [
    {
      "target_episode_number": 2,
      "reason": "When we reference the timeline established in episode 2",
      "suggested_timestamp_description": "When discussing the alibi"
    }
  ]
}
"""


SERIES_SUGGESTION_SYSTEM_PROMPT: str = """\
You are a content strategist for a true-crime YouTube channel network.  Based
on topic performance data and channel analytics, suggest new multi-episode
series that would maximise views and subscriber growth.

# ═══════════════════════════════════════════════════════════════
# INPUTS
# ═══════════════════════════════════════════════════════════════

You will receive:
- Top unused topics from the discovery pipeline (with scores and categories)
- Existing series for this channel (to avoid duplication)
- Recent video performance data (views, CTR, watch time)

# ═══════════════════════════════════════════════════════════════
# CRITERIA
# ═══════════════════════════════════════════════════════════════

1. Group related topics that form a coherent multi-episode narrative.
2. Prioritise topics with high composite scores + low competitor saturation.
3. Match series type to the topic cluster's natural structure:
   - Single complex case → multi_part (3-5 episodes)
   - Category of related cases → thematic_season (8-12 episodes)
   - Active developing story → ongoing_arc (open-ended)
4. Consider seasonal timing and current events.
5. Estimate total views based on component topics' indicators.

# ═══════════════════════════════════════════════════════════════
# RESPONSE FORMAT
# ═══════════════════════════════════════════════════════════════

Return a JSON array of 3-5 suggestions (no fences):
[
  {
    "title": "Series title",
    "description": "2-3 sentence pitch",
    "series_type": "multi_part",
    "suggested_episodes": 4,
    "rationale": "Why this series would perform well",
    "estimated_total_views": 500000,
    "source_topic_ids": ["uuid1", "uuid2"],
    "confidence_score": 0.8
  }
]
"""


# ---------------------------------------------------------------------------
# SeriesPlanner
# ---------------------------------------------------------------------------


class SeriesPlanner:
    """Plans and manages multi-episode series with AI-generated narrative arcs.

    Parameters
    ----------
    settings:
        Application settings (must contain ``anthropic.api_key``).
    http_client:
        Shared ``httpx.AsyncClient`` for interface consistency.
    db_pool:
        Async connection pool for database operations.
    """

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
        db_pool: AsyncConnectionPool,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._pool = db_pool
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic.api_key)

    # ------------------------------------------------------------------
    # Internal: Claude caller with retry + cost tracking
    # ------------------------------------------------------------------

    async def _call_claude(
        self,
        *,
        model: str,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 4_096,
        temperature: float = 1.0,
    ) -> tuple[str, APICallCost]:
        """Send a message to Claude and return (text, cost).

        Retries up to ``MAX_RETRIES`` on transient errors with exponential
        back-off.
        """
        last_exc: BaseException | None = None

        for attempt in range(MAX_RETRIES):
            t0 = time.monotonic()
            try:
                response = await self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": user_message}],
                )
                latency_ms = int((time.monotonic() - t0) * 1_000)

                text = response.content[0].text  # type: ignore[union-attr]
                usage = response.usage
                input_tokens = usage.input_tokens
                output_tokens = usage.output_tokens
                cached_input = getattr(usage, "cache_creation_input_tokens", 0) + getattr(
                    usage, "cache_read_input_tokens", 0
                )
                cost_usd = _calculate_cost(model, input_tokens, output_tokens, cached_input)

                cost = APICallCost(
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    cached_input_tokens=cached_input,
                )

                await logger.ainfo(
                    "series_claude_call",
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=str(cost_usd),
                    latency_ms=latency_ms,
                    attempt=attempt + 1,
                )
                return text, cost

            except anthropic.RateLimitError as exc:
                last_exc = exc
                await logger.awarning("series_rate_limit", attempt=attempt + 1)
            except anthropic.APIStatusError as exc:
                if exc.status_code >= 500:
                    last_exc = exc
                    await logger.awarning("series_server_error", status=exc.status_code)
                else:
                    raise
            except anthropic.APIConnectionError as exc:
                last_exc = exc
                await logger.awarning("series_connection_error", error=str(exc))

            if attempt < MAX_RETRIES - 1:
                delay = min(BASE_RETRY_DELAY * (2**attempt), 60.0)
                await asyncio.sleep(delay)

        raise RuntimeError(
            f"Series planner Claude call failed after {MAX_RETRIES} attempts: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------------
    # 1. Create series
    # ------------------------------------------------------------------

    async def create_series(self, inp: SeriesInput) -> SeriesResponse:
        """Insert a new series record into the database."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                INSERT_SERIES,
                {
                    "title": inp.title,
                    "description": inp.description,
                    "channel_id": inp.channel_id,
                    "series_type": inp.series_type,
                    "planned_episodes": inp.planned_episodes,
                },
            )
            row = cast("dict[str, Any] | None", await cur.fetchone())
            await conn.commit()

        if row is None:
            raise RuntimeError("Failed to insert series")

        await logger.ainfo(
            "series_created",
            series_id=str(row["id"]),
            title=inp.title,
            episodes=inp.planned_episodes,
        )
        return SeriesResponse.from_row(dict(row))

    # ------------------------------------------------------------------
    # 2. Plan series arc (Claude Sonnet — creative)
    # ------------------------------------------------------------------

    async def plan_series_arc(self, series_id: uuid.UUID) -> SeriesArc:
        """Use Claude to plan the narrative arc across all episodes.

        Stores the arc in ``series.arc_plan`` JSONB and creates
        ``series_episodes`` rows for each planned episode.
        """
        # Fetch series metadata
        async with self._pool.connection() as conn:
            cur = await conn.execute(GET_SERIES, {"series_id": series_id})
            series_row = await cur.fetchone()
        if series_row is None:
            raise ValueError(f"Series {series_id} not found")

        series = dict(series_row)

        # Build user message
        parts = [
            "## Series to Plan",
            f"**Title:** {series['title']}",
            f"**Type:** {series['series_type']}",
            f"**Planned Episodes:** {series['planned_episodes']}",
        ]
        if series["description"]:
            parts.append(f"**Description:** {series['description']}")
        parts += [
            "",
            "## Instructions",
            f"Plan a {series['planned_episodes']}-episode documentary series.",
            "For each episode, define the title, core question, key revelation,",
            "open loop, suggested hook type, and estimated length.",
            "The series must build tension across episodes.",
            "Episode 1 hooks with mystery. Middle episodes deepen the investigation.",
            "Final episode delivers the payoff.",
            "Every episode must work standalone while rewarding series watchers.",
        ]

        user_message = "\n".join(parts)

        text, cost = await self._call_claude(
            model=MODEL_SONNET,
            system_prompt=SERIES_ARC_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=4_096,
            temperature=0.9,
        )

        data = json.loads(_strip_json_fences(text))

        episodes = [EpisodeArcPlan.model_validate(ep) for ep in data["episodes"]]

        arc = SeriesArc(
            series_id=series_id,
            overarching_thesis=data.get("overarching_thesis", ""),
            narrative_structure=data.get("narrative_structure", ""),
            episodes=episodes,
            recurring_motifs=data.get("recurring_motifs", []),
            cliffhanger_strategy=data.get("cliffhanger_strategy", ""),
            cost=cost,
        )

        # Persist arc and create episode rows
        arc_json = json.dumps(
            {
                "overarching_thesis": arc.overarching_thesis,
                "narrative_structure": arc.narrative_structure,
                "episodes": [ep.model_dump() for ep in episodes],
                "recurring_motifs": arc.recurring_motifs,
                "cliffhanger_strategy": arc.cliffhanger_strategy,
            }
        )

        async with self._pool.connection() as conn:
            await conn.execute(
                UPDATE_SERIES_ARC,
                {"series_id": series_id, "arc_plan": arc_json},
            )

            for ep in episodes:
                await conn.execute(
                    INSERT_SERIES_EPISODE,
                    {
                        "series_id": series_id,
                        "episode_number": ep.episode_number,
                        "title": ep.title,
                        "core_question": ep.core_question,
                        "key_revelation": ep.key_revelation,
                        "open_loop_forward": ep.open_loop_forward,
                    },
                )

            # Track cost
            await track_cost(
                cast("AsyncConnection[dict[str, object]]", conn),
                video_id=series_id,  # Use series_id as the tracking entity
                stage="series_arc_planning",
                provider="anthropic",
                model=MODEL_SONNET,
                input_units=cost.input_tokens,
                output_units=cost.output_tokens,
                cost_usd=cost.cost_usd,
                latency_ms=0,
            )
            await conn.commit()

        await logger.ainfo(
            "series_arc_planned",
            series_id=str(series_id),
            episodes=len(episodes),
            cost_usd=str(cost.cost_usd),
        )
        return arc

    # ------------------------------------------------------------------
    # 3. Generate cross-video hooks (Claude Haiku — structured)
    # ------------------------------------------------------------------

    async def generate_cross_video_hooks(
        self,
        series_id: uuid.UUID,
        episode_number: int,
    ) -> CrossVideoHooks:
        """Generate recap, teaser, end screen, and cross-links for an episode."""
        # Fetch series + all episodes
        async with self._pool.connection() as conn:
            cur = await conn.execute(GET_SERIES, {"series_id": series_id})
            series_row = await cur.fetchone()
            cur2 = await conn.execute(GET_SERIES_EPISODES, {"series_id": series_id})
            episode_rows = await cur2.fetchall()

        if series_row is None:
            raise ValueError(f"Series {series_id} not found")

        series = dict(series_row)
        episodes = [dict(r) for r in episode_rows]

        current_ep = next((e for e in episodes if e["episode_number"] == episode_number), None)
        if current_ep is None:
            raise ValueError(f"Episode {episode_number} not found in series {series_id}")

        prev_ep = next((e for e in episodes if e["episode_number"] == episode_number - 1), None)
        next_ep = next((e for e in episodes if e["episode_number"] == episode_number + 1), None)

        # Build user message with full series context
        ep_summaries = "\n".join(
            f"  Part {e['episode_number']}: {e['title']} — "
            f"Q: {e['core_question']} | Reveal: {e['key_revelation']}"
            for e in episodes
        )

        parts = [
            f"## Series: {series['title']}",
            f"**Type:** {series['series_type']}",
            f"**Total episodes:** {series['planned_episodes']}",
            "",
            "## All Episodes",
            ep_summaries,
            "",
            f"## Current Episode: Part {episode_number}",
            f"**Title:** {current_ep['title']}",
            f"**Core question:** {current_ep['core_question']}",
            f"**Key revelation:** {current_ep['key_revelation']}",
        ]

        if prev_ep:
            parts += [
                "",
                f"## Previous Episode: Part {prev_ep['episode_number']}",
                f"**Title:** {prev_ep['title']}",
                f"**Key revelation:** {prev_ep['key_revelation']}",
                f"**Open loop forward:** {prev_ep['open_loop_forward']}",
            ]
        else:
            parts.append(
                "\n## This is Episode 1 — no recap needed, write a brief series intro instead."
            )

        if next_ep:
            parts += [
                "",
                f"## Next Episode: Part {next_ep['episode_number']}",
                f"**Title:** {next_ep['title']}",
                f"**Core question:** {next_ep['core_question']}",
            ]
        else:
            parts.append(
                "\n## This is the FINAL episode — no teaser needed, write a series wrap-up."
            )

        parts += [
            "",
            "## Instructions",
            "Generate the recap, teaser, end screen CTA, description cross-links,",
            "and info card cross-links for this episode.",
        ]

        user_message = "\n".join(parts)

        text, cost = await self._call_claude(
            model=MODEL_HAIKU,
            system_prompt=CROSS_VIDEO_HOOKS_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=2_048,
            temperature=0.7,
        )

        data = json.loads(_strip_json_fences(text))

        cross_links = [CrossLink.model_validate(cl) for cl in data.get("cross_links", [])]

        hooks = CrossVideoHooks(
            series_id=series_id,
            episode_number=episode_number,
            recap_narration=data.get("recap_narration", ""),
            teaser_narration=data.get("teaser_narration", ""),
            end_screen_cta=data.get("end_screen_cta", ""),
            description_cross_links=data.get("description_cross_links", ""),
            cross_links=cross_links,
            cost=cost,
        )

        # Persist hooks to episode row
        async with self._pool.connection() as conn:
            await conn.execute(
                UPDATE_EPISODE_HOOKS,
                {
                    "series_id": series_id,
                    "episode_number": episode_number,
                    "recap_narration": hooks.recap_narration,
                    "teaser_narration": hooks.teaser_narration,
                    "end_screen_cta": hooks.end_screen_cta,
                    "cross_links": json.dumps([cl.model_dump() for cl in cross_links]),
                },
            )
            await track_cost(
                cast("AsyncConnection[dict[str, object]]", conn),
                video_id=series_id,
                stage="series_hooks_generation",
                provider="anthropic",
                model=MODEL_HAIKU,
                input_units=cost.input_tokens,
                output_units=cost.output_tokens,
                cost_usd=cost.cost_usd,
                latency_ms=0,
            )
            await conn.commit()

        await logger.ainfo(
            "series_hooks_generated",
            series_id=str(series_id),
            episode=episode_number,
            cost_usd=str(cost.cost_usd),
        )
        return hooks

    # ------------------------------------------------------------------
    # 4. Series analytics
    # ------------------------------------------------------------------

    async def get_series_analytics(self, series_id: uuid.UUID) -> SeriesAnalytics:
        """Aggregate analytics across all episodes of a series."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(GET_SERIES, {"series_id": series_id})
            series_row = await cur.fetchone()

            cur2 = await conn.execute(GET_SERIES_ANALYTICS, {"series_id": series_id})
            metric_rows = await cur2.fetchall()

        if series_row is None:
            raise ValueError(f"Series {series_id} not found")

        series = dict(series_row)
        episode_metrics: list[EpisodeMetric] = []
        total_views = 0
        total_watch_minutes = Decimal("0")
        total_revenue = Decimal("0")
        published = 0

        for row in metric_rows:
            r = dict(row)
            views = int(r.get("views") or 0)
            watch_mins = Decimal(str(r.get("watch_minutes") or 0))
            revenue = Decimal(str(r.get("revenue") or 0))

            if r.get("video_id"):
                published += 1

            episode_metrics.append(
                EpisodeMetric(
                    episode_number=r["episode_number"],
                    video_id=r.get("video_id"),
                    title=r.get("title", ""),
                    views=views,
                    watch_minutes=watch_mins,
                    avg_view_duration_seconds=Decimal(str(r.get("avg_view_duration_seconds") or 0)),
                    ctr=Decimal(str(r.get("ctr") or 0)),
                    revenue=revenue,
                )
            )
            total_views += views
            total_watch_minutes += watch_mins
            total_revenue += revenue

        # Compute completion rates (approximate: views of ep N+1 / views of ep N)
        completion_rates: dict[int, float] = {}
        for i in range(len(episode_metrics) - 1):
            current = episode_metrics[i]
            nxt = episode_metrics[i + 1]
            if current.views > 0:
                completion_rates[current.episode_number] = round(nxt.views / current.views, 4)

        # Find best / drop-off episode
        best_ep = (
            max(episode_metrics, key=lambda e: e.views).episode_number if episode_metrics else None
        )
        drop_off_ep = None
        if completion_rates:
            drop_off_ep = min(completion_rates, key=completion_rates.get)

        # Average session depth approximation
        avg_session_depth = 0.0
        if episode_metrics and episode_metrics[0].views > 0:
            avg_session_depth = round(total_views / episode_metrics[0].views, 2)

        return SeriesAnalytics(
            series_id=series_id,
            series_title=series["title"],
            total_episodes=series["planned_episodes"],
            published_episodes=published,
            total_views=total_views,
            total_watch_minutes=total_watch_minutes,
            total_revenue=total_revenue,
            episode_metrics=episode_metrics,
            episode_completion_rates=completion_rates,
            avg_session_depth=avg_session_depth,
            best_performing_episode=best_ep,
            drop_off_episode=drop_off_ep,
        )

    # ------------------------------------------------------------------
    # 5. Auto-create YouTube playlist
    # ------------------------------------------------------------------

    async def auto_create_playlist(
        self,
        series_id: uuid.UUID,
        channel_id: uuid.UUID,
    ) -> str:
        """Create a YouTube playlist for the series.

        Uses ``YouTubeUploader.create_playlist()`` and updates the series
        record with the playlist ID.
        """
        from src.services.youtube_uploader import YouTubeUploader

        # Fetch series metadata
        async with self._pool.connection() as conn:
            cur = await conn.execute(GET_SERIES, {"series_id": series_id})
            series_row = await cur.fetchone()

        if series_row is None:
            raise ValueError(f"Series {series_id} not found")

        series = dict(series_row)

        uploader = YouTubeUploader(self._settings, self._http)
        playlist_id = await uploader.create_playlist(
            title=series["title"],
            description=series["description"] or f"Full series: {series['title']}",
            channel_id=channel_id,
        )

        if playlist_id is None:
            raise RuntimeError("Failed to create YouTube playlist")

        # Update series with playlist ID
        async with self._pool.connection() as conn:
            await conn.execute(
                UPDATE_SERIES_PLAYLIST,
                {"series_id": series_id, "playlist_id": playlist_id},
            )
            await conn.commit()

        await logger.ainfo(
            "series_playlist_created",
            series_id=str(series_id),
            playlist_id=playlist_id,
        )
        return playlist_id

    # ------------------------------------------------------------------
    # 6. Suggest next series (Claude Sonnet — creative)
    # ------------------------------------------------------------------

    async def suggest_next_series(
        self,
        channel_id: uuid.UUID,
        limit: int = 5,
    ) -> SeriesSuggestionResult:
        """Use Claude + topic data to suggest new series ideas."""
        from src.db.queries import LIST_TOPICS_BY_PRIORITY

        # Fetch available topics
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                LIST_TOPICS_BY_PRIORITY,
                {"priority_filter": None, "limit": 30},
            )
            topic_rows = cast("list[dict[str, Any]]", await cur.fetchall())

            # Fetch existing series for dedup
            cur2 = await conn.execute(
                LIST_SERIES,
                {
                    "channel_id": channel_id,
                    "status_filter": None,
                    "limit": 20,
                    "offset": 0,
                },
            )
            series_rows = cast("list[dict[str, Any]]", await cur2.fetchall())

        topics_data = [
            {
                "id": str(r["id"]),
                "title": r["title"],
                "category": r.get("category", ""),
                "composite_score": float(r.get("composite_score") or 0),
                "competitor_saturation": float(r.get("competitor_saturation") or 0),
            }
            for r in topic_rows
        ]

        existing_series = [
            {"title": r["title"], "type": r["series_type"], "status": r["status"]}
            for r in series_rows
        ]

        user_message = (
            f"## Available Topics (top {len(topics_data)} unused)\n"
            f"{json.dumps(topics_data, indent=2)}\n\n"
            f"## Existing Series on This Channel\n"
            f"{json.dumps(existing_series, indent=2)}\n\n"
            f"## Instructions\n"
            f"Suggest {limit} new series ideas based on the available topics.\n"
            f"Avoid duplicating existing series.\n"
            f"Group related topics into coherent multi-episode narratives.\n"
            f"Include source_topic_ids from the available topics list."
        )

        text, cost = await self._call_claude(
            model=MODEL_SONNET,
            system_prompt=SERIES_SUGGESTION_SYSTEM_PROMPT,
            user_message=user_message,
            max_tokens=4_096,
            temperature=0.9,
        )

        raw = json.loads(_strip_json_fences(text))
        if not isinstance(raw, list):
            raw = [raw]

        suggestions = [SeriesSuggestion.model_validate(s) for s in raw[:limit]]

        # Track cost
        async with self._pool.connection() as conn:
            await track_cost(
                cast("AsyncConnection[dict[str, object]]", conn),
                video_id=channel_id,  # Use channel_id as tracking entity
                stage="series_suggestion",
                provider="anthropic",
                model=MODEL_SONNET,
                input_units=cost.input_tokens,
                output_units=cost.output_tokens,
                cost_usd=cost.cost_usd,
                latency_ms=0,
            )
            await conn.commit()

        await logger.ainfo(
            "series_suggestions_generated",
            channel_id=str(channel_id),
            count=len(suggestions),
            cost_usd=str(cost.cost_usd),
        )
        return SeriesSuggestionResult(suggestions=suggestions, cost=cost)

    # ------------------------------------------------------------------
    # 7. Link episode to video
    # ------------------------------------------------------------------

    async def link_episode_to_video(
        self,
        series_id: uuid.UUID,
        episode_number: int,
        video_id: uuid.UUID,
        status: str = "scripted",
    ) -> SeriesEpisodeResponse:
        """Link a video to a series episode and update its status."""
        async with self._pool.connection() as conn:
            cur = await conn.execute(
                LINK_EPISODE_VIDEO,
                {
                    "series_id": series_id,
                    "episode_number": episode_number,
                    "video_id": video_id,
                    "status": status,
                },
            )
            row = await cur.fetchone()
            await conn.commit()

        if row is None:
            raise ValueError(f"Episode {episode_number} not found in series {series_id}")

        await logger.ainfo(
            "episode_linked",
            series_id=str(series_id),
            episode=episode_number,
            video_id=str(video_id),
        )
        return SeriesEpisodeResponse.from_row(dict(row))
