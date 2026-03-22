"""Performance analyzer — retention patterns, composite scoring, and Goodhart detection.

Correlates content decisions with YouTube performance outcomes by analysing
retention curves, computing multi-objective composite scores, detecting
Goodhart's Law violations, and ranking content features.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

import structlog
from psycopg.rows import dict_row

from src.models.performance import (
    FeatureRank,
    FeatureRankings,
    GoodhartAlert,
    RetentionAnalysis,
    RetentionPattern,
    ScoreBreakdown,
    VideoPerformanceScore,
)

if TYPE_CHECKING:
    import uuid

    from psycopg_pool import AsyncConnectionPool

    from src.config import Settings

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------

_GET_VIDEOS_WITH_RETENTION: str = """
SELECT
    v.id AS video_id,
    v.title,
    v.published_at,
    v.video_length_seconds,
    v.topic,
    vdm.audience_retention_curve,
    vdm.metric_date
FROM videos v
JOIN video_daily_metrics vdm ON vdm.video_id = v.id
WHERE v.channel_id = %(channel_id)s
  AND v.status = 'published'
  AND vdm.audience_retention_curve IS NOT NULL
ORDER BY v.published_at DESC;
"""

_GET_SCRIPT_FEATURES: str = """
SELECT
    pj.video_id,
    pj.result
FROM pipeline_jobs pj
WHERE pj.video_id = ANY(%(video_ids)s)
  AND pj.stage = 'script_generation'
  AND pj.status = 'completed';
"""

_GET_THUMBNAIL_ARCHETYPES: str = """
SELECT video_id, archetype
FROM thumbnail_generations
WHERE video_id = ANY(%(video_ids)s)
  AND is_active = true;
"""

_GET_VIDEO_METRICS_WINDOW: str = """
SELECT
    video_id,
    metric_date,
    views,
    estimated_minutes_watched,
    average_view_duration_seconds,
    average_view_percentage,
    impressions,
    ctr,
    likes,
    dislikes,
    comments,
    shares,
    subscribers_gained,
    subscribers_lost,
    estimated_revenue,
    traffic_source_breakdown
FROM video_daily_metrics
WHERE video_id = %(video_id)s
ORDER BY metric_date ASC;
"""

_GET_VIDEO_PUBLISHED_AT: str = """
SELECT id, published_at, video_length_seconds
FROM videos
WHERE id = %(video_id)s;
"""

_GET_CHANNEL_PUBLISHED_VIDEOS: str = """
SELECT
    v.id AS video_id,
    v.title,
    v.published_at,
    v.video_length_seconds,
    v.topic
FROM videos v
WHERE v.channel_id = %(channel_id)s
  AND v.status = 'published'
  AND v.published_at IS NOT NULL
ORDER BY v.published_at DESC;
"""

_GET_CHANNEL_VIDEO_SCORES: str = """
SELECT
    v.id AS video_id,
    v.published_at,
    COALESCE(SUM(vdm.views), 0) AS total_views,
    COALESCE(AVG(vdm.ctr), 0) AS avg_ctr,
    COALESCE(AVG(vdm.average_view_percentage), 0) AS avg_view_pct,
    COALESCE(SUM(vdm.subscribers_gained), 0) AS total_subs_gained,
    COALESCE(SUM(vdm.likes), 0) AS total_likes,
    COALESCE(SUM(vdm.dislikes), 0) AS total_dislikes
FROM videos v
LEFT JOIN video_daily_metrics vdm ON vdm.video_id = v.id
WHERE v.channel_id = %(channel_id)s
  AND v.status = 'published'
  AND v.published_at IS NOT NULL
GROUP BY v.id, v.published_at
ORDER BY v.published_at DESC;
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _retention_at(curve: list[dict[str, float]], target_ratio: float) -> float:
    """Interpolate absolute retention at a given elapsed_ratio from a curve."""
    if not curve:
        return 0.0
    # Find the two bounding points
    prev = curve[0]
    for pt in curve:
        ratio = pt.get("elapsed_ratio", pt.get("elapsedVideoTimeRatio", 0.0))
        if ratio >= target_ratio:
            prev_ratio = prev.get("elapsed_ratio", prev.get("elapsedVideoTimeRatio", 0.0))
            prev_ret = prev.get("absolute_retention", prev.get("audienceWatchRatio", 0.0))
            cur_ret = pt.get("absolute_retention", pt.get("audienceWatchRatio", 0.0))
            if ratio == prev_ratio:
                return cur_ret
            # Linear interpolation
            t = (target_ratio - prev_ratio) / (ratio - prev_ratio) if ratio != prev_ratio else 0
            return prev_ret + t * (cur_ret - prev_ret)
        prev = pt
    # Beyond the last point — return last value
    return prev.get("absolute_retention", prev.get("audienceWatchRatio", 0.0))


def _classify_curve(
    first_30s: float,
    mid: float,
    end: float,
) -> str:
    """Classify a retention curve shape.

    - cliff_drop: first 30s retention < 0.50
    - mid_lull: mid drops >20% relative to first_30s and end recovers
    - spike: end > mid (unusual — rewind moments)
    - healthy: gradual decline
    """
    if first_30s < 0.50:
        return "cliff_drop"
    if mid < first_30s * 0.80 and end > mid * 1.05:
        return "spike"
    if mid < first_30s * 0.75:
        return "mid_lull"
    return "healthy"


def _normalize_score(value: float, channel_min: float, channel_max: float) -> float:
    """Normalize a metric value to 0-100 relative to channel range."""
    if channel_max <= channel_min:
        return 50.0
    return max(0.0, min(100.0, (value - channel_min) / (channel_max - channel_min) * 100))


def _compute_trend(values: list[float]) -> tuple[str, float]:
    """Determine trend from an ordered list of values (oldest to newest)."""
    if len(values) < 3:
        return "stable", 0.0
    recent = statistics.mean(values[-3:])
    older = statistics.mean(values[:3])
    if older == 0:
        return "stable", 0.0
    delta = (recent - older) / abs(older)
    if delta > 0.10:
        return "improving", delta
    if delta < -0.10:
        return "declining", delta
    return "stable", delta


# ---------------------------------------------------------------------------
# PerformanceAnalyzer
# ---------------------------------------------------------------------------


class PerformanceAnalyzer:
    """Analyses YouTube performance data and correlates with content decisions.

    Parameters
    ----------
    settings:
        Application settings.
    db_pool:
        Shared ``AsyncConnectionPool`` for database access.
    """

    def __init__(self, settings: Settings, db_pool: AsyncConnectionPool) -> None:
        self._settings = settings
        self._pool = db_pool

    # ==================================================================
    # 1. Retention pattern analysis
    # ==================================================================

    async def analyze_retention_patterns(
        self,
        channel_id: uuid.UUID,
        min_videos: int = 10,
    ) -> RetentionAnalysis:
        """Analyse retention curves across a channel's video library.

        Classifies each curve shape (cliff_drop, mid_lull, spike, healthy),
        correlates with script features (hook type, open loops, pattern
        interrupts), and ranks which hook types have lowest first-30s dropout.
        """
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            # Fetch retention curves
            await cur.execute(_GET_VIDEOS_WITH_RETENTION, {"channel_id": channel_id})
            retention_rows = await cur.fetchall()

        if not retention_rows:
            return RetentionAnalysis(
                channel_id=channel_id,
                videos_analyzed=0,
                recommendations=["Not enough published videos with retention data."],
            )

        # Deduplicate: keep latest metric_date per video
        latest_by_video: dict[str, dict[str, Any]] = {}
        for row in retention_rows:
            vid = str(row["video_id"])
            if (
                vid not in latest_by_video
                or row["metric_date"] > latest_by_video[vid]["metric_date"]
            ):
                latest_by_video[vid] = row

        video_ids = [row["video_id"] for row in latest_by_video.values()]

        if len(video_ids) < min_videos:
            return RetentionAnalysis(
                channel_id=channel_id,
                videos_analyzed=len(video_ids),
                recommendations=[
                    f"Only {len(video_ids)} videos with retention data; need {min_videos} for meaningful analysis.",
                ],
            )

        # Fetch script features (hook type, open loops, etc.)
        script_features: dict[str, dict[str, Any]] = {}
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_GET_SCRIPT_FEATURES, {"video_ids": video_ids})
            for row in await cur.fetchall():
                result = row.get("result") or {}
                script_features[str(row["video_id"])] = result

        # Analyse each video
        patterns: list[RetentionPattern] = []
        hook_retention: dict[str, list[float]] = defaultdict(list)
        shape_counts: dict[str, int] = defaultdict(int)

        for vid_str, row in latest_by_video.items():
            curve = row.get("audience_retention_curve") or []
            if not curve or len(curve) < 5:
                continue

            first_30s = _retention_at(curve, 0.20)
            mid = _retention_at(curve, 0.60)
            end = _retention_at(curve, 0.90)
            shape = _classify_curve(first_30s, mid, end)
            shape_counts[shape] += 1

            sf = script_features.get(vid_str, {})
            hook_type = sf.get("hook_type")
            open_loops = sf.get("open_loops", [])
            # Check scene breakdown for pattern interrupts
            scene_breakdown = sf.get("scene_breakdown")
            has_pi = False
            ad_break_count = 0
            if isinstance(scene_breakdown, list):
                for scene in scene_breakdown:
                    if isinstance(scene, dict):
                        if scene.get("is_pattern_interrupt"):
                            has_pi = True
                        if scene.get("is_ad_break"):
                            ad_break_count += 1

            if hook_type:
                hook_retention[hook_type].append(first_30s)

            patterns.append(
                RetentionPattern(
                    video_id=row["video_id"],
                    title=row.get("title"),
                    curve_shape=shape,  # type: ignore[arg-type]
                    first_30s_retention=round(first_30s, 4),
                    mid_retention=round(mid, 4),
                    end_retention=round(end, 4),
                    hook_type=hook_type,
                    open_loop_count=len(open_loops) if isinstance(open_loops, list) else 0,
                    has_pattern_interrupts=has_pi,
                    ad_break_count=ad_break_count,
                )
            )

        # Rank hook types by average first-30s retention
        hook_ranking = {
            ht: round(statistics.mean(vals), 4)
            for ht, vals in hook_retention.items()
            if len(vals) >= 3
        }

        # Generate recommendations
        recommendations: list[str] = []
        if hook_ranking:
            best = max(hook_ranking, key=lambda k: hook_ranking[k])
            worst = min(hook_ranking, key=lambda k: hook_ranking[k])
            if hook_ranking[best] - hook_ranking[worst] > 0.05:
                recommendations.append(
                    f'Hook "{best}" retains {hook_ranking[best]:.0%} at 30s vs '
                    f'"{worst}" at {hook_ranking[worst]:.0%} — increase "{best}" weight.'
                )

        cliff_pct = shape_counts.get("cliff_drop", 0) / max(len(patterns), 1)
        if cliff_pct > 0.30:
            recommendations.append(
                f"{cliff_pct:.0%} of videos have cliff-drop retention — "
                "review opening hooks and first-30s narration."
            )

        lull_pct = shape_counts.get("mid_lull", 0) / max(len(patterns), 1)
        if lull_pct > 0.25:
            recommendations.append(
                f"{lull_pct:.0%} of videos have mid-video lulls — "
                "add more pattern interrupts or open loops at the 55-65% mark."
            )

        await logger.ainfo(
            "retention_analysis_complete",
            channel_id=str(channel_id),
            videos_analyzed=len(patterns),
            shapes=dict(shape_counts),
        )

        return RetentionAnalysis(
            channel_id=channel_id,
            videos_analyzed=len(patterns),
            patterns=patterns,
            hook_retention_ranking=hook_ranking,
            curve_shape_distribution=dict(shape_counts),
            recommendations=recommendations,
        )

    # ==================================================================
    # 2. Composite video score
    # ==================================================================

    async def compute_video_score(
        self,
        video_id: uuid.UUID,
    ) -> VideoPerformanceScore:
        """Compute a multi-objective composite score (0-100) for a video.

        Short-term (40%): CTR 15%, first-48h views 10%, avg view duration 15%.
        Medium-term (35%): subscriber conversion 15%, 30-day views 10%,
        returning viewer % 10%.
        Long-term (25%): comment sentiment 10%, like ratio 5%, search traffic 5%,
        evergreen score 5%.
        """
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_GET_VIDEO_PUBLISHED_AT, {"video_id": video_id})
            video_row = await cur.fetchone()

            if not video_row or not video_row.get("published_at"):
                return self._empty_score(video_id)

            published_at: datetime = video_row["published_at"]

            await cur.execute(_GET_VIDEO_METRICS_WINDOW, {"video_id": video_id})
            metrics = await cur.fetchall()

        if not metrics:
            return self._empty_score(video_id)

        # Aggregate metrics by time window
        total_views = 0
        first_48h_views = 0
        thirty_day_views = 0
        day_7_views = 0
        day_90_views = 0
        total_likes = 0
        total_dislikes = 0
        total_subs_gained = 0
        ctr_values: list[float] = []
        view_pct_values: list[float] = []
        search_views = 0
        total_traffic_views = 0

        cutoff_48h = published_at.date() + timedelta(days=2)
        cutoff_7d = published_at.date() + timedelta(days=7)
        cutoff_30d = published_at.date() + timedelta(days=30)
        cutoff_90d = published_at.date() + timedelta(days=90)

        for m in metrics:
            md = m["metric_date"]
            views = m["views"] or 0
            total_views += views
            total_likes += m["likes"] or 0
            total_dislikes += m["dislikes"] or 0
            total_subs_gained += m["subscribers_gained"] or 0

            if m["ctr"] and m["impressions"]:
                ctr_values.append(float(m["ctr"]))
            if m["average_view_percentage"]:
                view_pct_values.append(float(m["average_view_percentage"]))

            if md <= cutoff_48h:
                first_48h_views += views
            if md <= cutoff_7d:
                day_7_views += views
            if md <= cutoff_30d:
                thirty_day_views += views
            if md <= cutoff_90d:
                day_90_views += views

            # Traffic source breakdown
            tsb = m.get("traffic_source_breakdown")
            if isinstance(tsb, dict):
                for source, count in tsb.items():
                    cnt = int(count) if count else 0
                    total_traffic_views += cnt
                    if "SEARCH" in source.upper():
                        search_views += cnt

        # --- Short-term (40%) ---
        avg_ctr = statistics.mean(ctr_values) if ctr_values else 0.0
        avg_view_pct = statistics.mean(view_pct_values) if view_pct_values else 0.0

        # Normalize: CTR typically 2-15%, view pct 30-70%
        ctr_score = min(100.0, max(0.0, (avg_ctr - 2.0) / 13.0 * 100))
        first_48h_score = min(100.0, first_48h_views / max(1, 500) * 100)
        view_dur_score = min(100.0, max(0.0, (avg_view_pct - 30.0) / 40.0 * 100))

        short_term = ctr_score * 0.15 + first_48h_score * 0.10 + view_dur_score * 0.15

        # --- Medium-term (35%) ---
        sub_conversion = total_subs_gained / max(total_views, 1) * 100  # as percentage
        sub_score = min(100.0, sub_conversion / 2.0 * 100)  # 2% = excellent
        thirty_day_score = min(100.0, thirty_day_views / max(1, 5_000) * 100)
        # Returning viewer % — not available from daily metrics; use 50 as neutral
        returning_score = 50.0

        medium_term = sub_score * 0.15 + thirty_day_score * 0.10 + returning_score * 0.10

        # --- Long-term (25%) ---
        # Comment sentiment — would need comment text + LLM; use neutral placeholder
        sentiment_score = 50.0

        like_total = total_likes + total_dislikes
        like_ratio = total_likes / max(like_total, 1)
        like_score = like_ratio * 100

        search_pct = search_views / max(total_traffic_views, 1) * 100
        search_score = min(100.0, search_pct / 30.0 * 100)  # 30% search = excellent

        evergreen_ratio = day_90_views / max(day_7_views, 1) if day_7_views > 0 else 0
        # Evergreen: day-90 total ideally 5-10x day-7
        evergreen_score = min(100.0, evergreen_ratio / 10.0 * 100)

        long_term = (
            sentiment_score * 0.10
            + like_score * 0.05
            + search_score * 0.05
            + evergreen_score * 0.05
        )

        composite = round(short_term + medium_term + long_term, 2)

        breakdown = ScoreBreakdown(
            ctr_score=round(ctr_score, 2),
            first_48h_views_score=round(first_48h_score, 2),
            avg_view_duration_score=round(view_dur_score, 2),
            short_term_total=round(short_term, 2),
            subscriber_conversion_score=round(sub_score, 2),
            thirty_day_views_score=round(thirty_day_score, 2),
            returning_viewer_score=round(returning_score, 2),
            medium_term_total=round(medium_term, 2),
            comment_sentiment_score=round(sentiment_score, 2),
            like_ratio_score=round(like_score, 2),
            search_traffic_score=round(search_score, 2),
            evergreen_score=round(evergreen_score, 2),
            long_term_total=round(long_term, 2),
        )

        await logger.ainfo(
            "video_score_computed",
            video_id=str(video_id),
            composite=composite,
        )

        return VideoPerformanceScore(
            video_id=video_id,
            composite_score=composite,
            breakdown=breakdown,
        )

    @staticmethod
    def _empty_score(video_id: uuid.UUID) -> VideoPerformanceScore:
        return VideoPerformanceScore(
            video_id=video_id,
            composite_score=0.0,
            breakdown=ScoreBreakdown(
                ctr_score=0,
                first_48h_views_score=0,
                avg_view_duration_score=0,
                short_term_total=0,
                subscriber_conversion_score=0,
                thirty_day_views_score=0,
                returning_viewer_score=0,
                medium_term_total=0,
                comment_sentiment_score=0,
                like_ratio_score=0,
                search_traffic_score=0,
                evergreen_score=0,
                long_term_total=0,
            ),
        )

    # ==================================================================
    # 3. Goodhart's Law detection
    # ==================================================================

    async def detect_goodhart_violations(
        self,
        channel_id: uuid.UUID,
    ) -> list[GoodhartAlert]:
        """Detect Goodhart's Law violations across channel videos.

        Compares rolling 5-video average against prior 20-video baseline for:
        - CTR rising + retention falling → clickbait drift
        - Views rising + subscriber conversion falling → audience mismatch
        - Engagement rising + sentiment proxies falling → controversy farming
        """
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_GET_CHANNEL_VIDEO_SCORES, {"channel_id": channel_id})
            rows = await cur.fetchall()

        if len(rows) < 25:
            return []

        # Most recent first → reverse for chronological order
        rows = list(reversed(rows))

        alerts: list[GoodhartAlert] = []

        # Extract per-video metrics
        ctrs = [float(r["avg_ctr"] or 0) for r in rows]
        view_pcts = [float(r["avg_view_pct"] or 0) for r in rows]
        views = [int(r["total_views"] or 0) for r in rows]
        subs = [int(r["total_subs_gained"] or 0) for r in rows]
        likes = [int(r["total_likes"] or 0) for r in rows]
        dislikes = [int(r["total_dislikes"] or 0) for r in rows]

        sub_conversions = [s / max(v, 1) for s, v in zip(subs, views, strict=False)]
        like_ratios = [lk / max(lk + d, 1) for lk, d in zip(likes, dislikes, strict=False)]

        def _check(
            name: str,
            alert_type: Literal["clickbait_drift", "audience_mismatch", "controversy_farming"],
            rising: Sequence[float],
            rising_label: str,
            falling: Sequence[float],
            falling_label: str,
            recommendation: str,
        ) -> None:
            baseline_rising = statistics.mean(rising[-25:-5])
            recent_rising = statistics.mean(rising[-5:])
            baseline_falling = statistics.mean(falling[-25:-5])
            recent_falling = statistics.mean(falling[-5:])

            if baseline_rising == 0 or baseline_falling == 0:
                return

            rising_delta = (recent_rising - baseline_rising) / abs(baseline_rising)
            falling_delta = (recent_falling - baseline_falling) / abs(baseline_falling)

            # Rising must be up >10%, falling must be down >10%
            if rising_delta > 0.10 and falling_delta < -0.10:
                severity: Literal["warning", "critical"] = (
                    "critical" if falling_delta < -0.25 else "warning"
                )
                alerts.append(
                    GoodhartAlert(
                        alert_type=alert_type,
                        severity=severity,
                        metric_rising=rising_label,
                        metric_falling=falling_label,
                        recent_avg=round(recent_rising, 4),
                        baseline_avg=round(baseline_rising, 4),
                        delta_pct=round(falling_delta * 100, 1),
                        message=(
                            f"{rising_label} up {rising_delta:+.0%} but "
                            f"{falling_label} down {falling_delta:+.0%} vs baseline."
                        ),
                        recommendation=recommendation,
                    )
                )

        _check(
            "clickbait_drift",
            "clickbait_drift",
            ctrs,
            "CTR",
            view_pcts,
            "avg_view_percentage",
            "Titles/thumbnails may be over-promising. Review recent thumbnails for clickbait drift.",
        )
        _check(
            "audience_mismatch",
            "audience_mismatch",
            views,
            "views",
            sub_conversions,
            "subscriber_conversion",
            "Views are attracting non-target audience. Review topic selection and targeting.",
        )
        _check(
            "controversy_farming",
            "controversy_farming",
            like_ratios,
            "engagement",
            like_ratios,
            "like_ratio",
            "Engagement patterns suggest controversy farming. Review content tone.",
        )

        if alerts:
            await logger.awarning(
                "goodhart_violations_detected",
                channel_id=str(channel_id),
                alert_count=len(alerts),
                types=[a.alert_type for a in alerts],
            )

        return alerts

    # ==================================================================
    # 4. Feature rankings
    # ==================================================================

    async def rank_content_features(
        self,
        channel_id: uuid.UUID,
    ) -> FeatureRankings:
        """Rank content decisions by correlation with composite performance score.

        Analyses: hook type, title formula, thumbnail archetype, video length,
        topic category, day of week, and time of day published.
        """
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_GET_CHANNEL_PUBLISHED_VIDEOS, {"channel_id": channel_id})
            videos = await cur.fetchall()

        if not videos:
            return FeatureRankings(
                channel_id=channel_id,
                total_videos_analyzed=0,
                top_recommendations=["No published videos to analyse."],
            )

        video_ids = [v["video_id"] for v in videos]

        # Compute composite scores for all videos
        scores: dict[str, float] = {}
        for vid in video_ids:
            vid_score = await self.compute_video_score(vid)
            scores[str(vid)] = vid_score.composite_score

        # Fetch script features and thumbnail archetypes
        script_features: dict[str, dict[str, Any]] = {}
        archetype_map: dict[str, str] = {}

        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_GET_SCRIPT_FEATURES, {"video_ids": video_ids})
            for row in await cur.fetchall():
                script_features[str(row["video_id"])] = row.get("result") or {}

            await cur.execute(_GET_THUMBNAIL_ARCHETYPES, {"video_ids": video_ids})
            for row in await cur.fetchall():
                if row.get("archetype"):
                    archetype_map[str(row["video_id"])] = row["archetype"]

        # Build feature buckets
        buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

        for v in videos:
            vid_str = str(v["video_id"])
            score = scores.get(vid_str, 0.0)
            sf = script_features.get(vid_str, {})

            # Hook type
            ht = sf.get("hook_type")
            if ht:
                buckets["hook_type"][ht].append(score)

            # Title formula — from titles result if available
            # The pipeline may store selected title formula in result
            title_formula = sf.get("title_formula")
            if title_formula:
                buckets["title_formula"][title_formula].append(score)

            # Thumbnail archetype
            arch = archetype_map.get(vid_str)
            if arch:
                buckets["thumbnail_archetype"][arch].append(score)

            # Video length buckets
            length_s = v.get("video_length_seconds")
            if length_s:
                minutes = length_s / 60
                if minutes <= 12:
                    bucket = "10-12min"
                elif minutes <= 15:
                    bucket = "12-15min"
                elif minutes <= 20:
                    bucket = "15-20min"
                else:
                    bucket = "20-25min"
                buckets["video_length"][bucket].append(score)

            # Topic category — from video.topic JSONB
            topic = v.get("topic") or {}
            if isinstance(topic, dict):
                topic_str = topic.get("topic", topic.get("category", ""))
                if topic_str:
                    # Simplify to first few words
                    cat = " ".join(str(topic_str).split()[:3]).lower()
                    buckets["topic_category"][cat].append(score)

            # Day of week
            pub = v.get("published_at")
            if pub:
                day_name = pub.strftime("%A")
                buckets["day_of_week"][day_name].append(score)

                hour = pub.hour
                if hour < 6:
                    tod = "night"
                elif hour < 12:
                    tod = "morning"
                elif hour < 18:
                    tod = "afternoon"
                else:
                    tod = "evening"
                buckets["time_of_day"][tod].append(score)

        # Convert buckets into ranked FeatureRank objects
        rankings: dict[str, list[FeatureRank]] = {}
        all_recommendations: list[str] = []

        for feature_cat, value_map in buckets.items():
            ranks: list[FeatureRank] = []
            for val, score_list in value_map.items():
                if len(score_list) < 2:
                    continue
                mean_s = statistics.mean(score_list)
                stdev = statistics.stdev(score_list) if len(score_list) >= 3 else 0.0
                n = len(score_list)
                margin = 1.96 * stdev / (n**0.5) if n > 1 else 0.0
                trend, delta = _compute_trend(score_list)

                ranks.append(
                    FeatureRank(
                        feature_name=feature_cat,
                        feature_value=val,
                        sample_count=n,
                        mean_score=round(mean_s, 2),
                        ci_lower=round(mean_s - margin, 2),
                        ci_upper=round(mean_s + margin, 2),
                        trend=trend,  # type: ignore[arg-type]
                        trend_delta=round(delta, 4),
                    )
                )

            ranks.sort(key=lambda r: r.mean_score, reverse=True)
            rankings[feature_cat] = ranks

            # Top recommendation for this category
            sig_ranks = [r for r in ranks if r.sample_count >= 5]
            if len(sig_ranks) >= 2:
                best = sig_ranks[0]
                worst = sig_ranks[-1]
                gap = best.mean_score - worst.mean_score
                if gap > 5:
                    all_recommendations.append(
                        f'{feature_cat}: "{best.feature_value}" scores '
                        f'{best.mean_score:.1f} vs "{worst.feature_value}" '
                        f"at {worst.mean_score:.1f} (N≥5 each) — increase "
                        f'"{best.feature_value}" weight.'
                    )

        await logger.ainfo(
            "feature_rankings_complete",
            channel_id=str(channel_id),
            videos=len(videos),
            feature_categories=list(rankings.keys()),
        )

        return FeatureRankings(
            channel_id=channel_id,
            total_videos_analyzed=len(videos),
            rankings=rankings,
            top_recommendations=all_recommendations,
        )
