from __future__ import annotations

__all__ = [
    "INSERT_SERIES",
    "GET_SERIES",
    "LIST_SERIES",
    "UPDATE_SERIES_ARC",
    "UPDATE_SERIES_PLAYLIST",
    "UPDATE_SERIES_STATUS",
    "INSERT_SERIES_EPISODE",
    "GET_SERIES_EPISODES",
    "UPDATE_EPISODE_HOOKS",
    "LINK_EPISODE_VIDEO",
    "GET_SERIES_ANALYTICS",
    "COUNT_SERIES",
]

INSERT_SERIES: str = """
INSERT INTO series (title, description, channel_id, series_type, planned_episodes)
VALUES (%(title)s, %(description)s, %(channel_id)s, %(series_type)s, %(planned_episodes)s)
RETURNING *;
"""

GET_SERIES: str = """
SELECT id, title, description, channel_id, series_type, planned_episodes,
       youtube_playlist_id, arc_plan, status, created_at, updated_at
FROM series
WHERE id = %(series_id)s;
"""

LIST_SERIES: str = """
SELECT id, title, description, channel_id, series_type, planned_episodes,
       youtube_playlist_id, arc_plan, status, created_at, updated_at
FROM series
WHERE channel_id = %(channel_id)s
  AND (%(status_filter)s IS NULL OR status = %(status_filter)s)
ORDER BY created_at DESC
LIMIT %(limit)s OFFSET %(offset)s;
"""

UPDATE_SERIES_ARC: str = """
UPDATE series
SET arc_plan = %(arc_plan)s,
    status = 'in_production'
WHERE id = %(series_id)s
RETURNING *;
"""

UPDATE_SERIES_PLAYLIST: str = """
UPDATE series
SET youtube_playlist_id = %(playlist_id)s
WHERE id = %(series_id)s
RETURNING *;
"""

UPDATE_SERIES_STATUS: str = """
UPDATE series
SET status = %(status)s
WHERE id = %(series_id)s
RETURNING *;
"""

INSERT_SERIES_EPISODE: str = """
INSERT INTO series_episodes
    (series_id, episode_number, title, core_question, key_revelation, open_loop_forward)
VALUES
    (%(series_id)s, %(episode_number)s, %(title)s, %(core_question)s,
     %(key_revelation)s, %(open_loop_forward)s)
ON CONFLICT (series_id, episode_number) DO UPDATE SET
    title = EXCLUDED.title,
    core_question = EXCLUDED.core_question,
    key_revelation = EXCLUDED.key_revelation,
    open_loop_forward = EXCLUDED.open_loop_forward
RETURNING *;
"""

GET_SERIES_EPISODES: str = """
SELECT id, series_id, episode_number, video_id, title, core_question,
       key_revelation, open_loop_forward, recap_narration, teaser_narration,
       end_screen_cta, cross_links, status, created_at, updated_at
FROM series_episodes
WHERE series_id = %(series_id)s
ORDER BY episode_number ASC;
"""

UPDATE_EPISODE_HOOKS: str = """
UPDATE series_episodes
SET recap_narration = %(recap_narration)s,
    teaser_narration = %(teaser_narration)s,
    end_screen_cta = %(end_screen_cta)s,
    cross_links = %(cross_links)s
WHERE series_id = %(series_id)s
  AND episode_number = %(episode_number)s
RETURNING *;
"""

LINK_EPISODE_VIDEO: str = """
UPDATE series_episodes
SET video_id = %(video_id)s,
    status = %(status)s
WHERE series_id = %(series_id)s
  AND episode_number = %(episode_number)s
RETURNING *;
"""

GET_SERIES_ANALYTICS: str = """
SELECT
    se.episode_number,
    se.video_id,
    se.title,
    COALESCE(SUM(vdm.views), 0)                     AS views,
    COALESCE(SUM(vdm.estimated_minutes_watched), 0)  AS watch_minutes,
    CASE WHEN COUNT(vdm.metric_date) > 0
         THEN AVG(vdm.average_view_duration_seconds)
         ELSE 0 END                                   AS avg_view_duration_seconds,
    CASE WHEN SUM(vdm.impressions) > 0
         THEN ROUND(SUM(vdm.views)::NUMERIC / SUM(vdm.impressions), 4)
         ELSE 0 END                                   AS ctr,
    COALESCE(SUM(vdm.estimated_revenue), 0)           AS revenue
FROM series_episodes se
LEFT JOIN video_daily_metrics vdm ON vdm.video_id = se.video_id
WHERE se.series_id = %(series_id)s
GROUP BY se.episode_number, se.video_id, se.title
ORDER BY se.episode_number ASC;
"""

COUNT_SERIES: str = """
SELECT COUNT(*) AS total
FROM series
WHERE channel_id = %(channel_id)s
  AND (%(status_filter)s IS NULL OR status = %(status_filter)s);
"""
