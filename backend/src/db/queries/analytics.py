from __future__ import annotations

__all__ = [
    "GET_CHANNEL_DAILY_ANALYTICS",
    "GET_TOP_VIDEOS",
    "GET_QUEUE_DEPTH",
    "GET_CHANNEL_LAST_PUBLISHED",
    "GET_CHANNEL_QUEUE_DEPTH",
    "GET_CHANNEL_MONTHLY_REVENUE",
    "GET_DEAD_LETTER_COUNT",
    "EXPORT_VIDEO_METRICS",
]

GET_CHANNEL_DAILY_ANALYTICS: str = """
SELECT
    SUM(vdm.views) AS total_views,
    SUM(vdm.estimated_revenue) AS total_revenue,
    CASE WHEN SUM(vdm.impressions) > 0
         THEN ROUND(SUM(vdm.views)::NUMERIC / SUM(vdm.impressions), 4)
         ELSE 0 END AS avg_ctr,
    SUM(vdm.subscribers_gained - vdm.subscribers_lost) AS net_subscribers,
    SUM(vdm.likes) AS total_likes,
    SUM(vdm.comments) AS total_comments
FROM video_daily_metrics vdm
JOIN videos v ON v.id = vdm.video_id
WHERE v.channel_id = %(channel_id)s
  AND vdm.metric_date = %(metric_date)s;
"""

GET_TOP_VIDEOS: str = """
SELECT
    v.id, v.title, v.published_at,
    SUM(vdm.views) AS total_views,
    SUM(vdm.estimated_revenue) AS total_revenue,
    CASE WHEN SUM(vdm.impressions) > 0
         THEN ROUND(SUM(vdm.views)::NUMERIC / SUM(vdm.impressions), 4)
         ELSE 0 END AS avg_ctr,
    SUM(vdm.estimated_minutes_watched) AS total_watch_minutes
FROM videos v
JOIN video_daily_metrics vdm ON vdm.video_id = v.id
WHERE v.channel_id = %(channel_id)s
  AND vdm.metric_date >= current_date - make_interval(days := %(days)s)
GROUP BY v.id, v.title, v.published_at
ORDER BY {sort_column} DESC
LIMIT %(limit)s;
"""

GET_QUEUE_DEPTH: str = """
SELECT
    stage,
    COUNT(*) FILTER (WHERE status = 'pending')     AS pending,
    COUNT(*) FILTER (WHERE status = 'in_progress')  AS in_progress,
    COUNT(*) FILTER (WHERE status = 'dead_letter')  AS dead_letter
FROM pipeline_jobs
GROUP BY stage
ORDER BY stage;
"""

GET_CHANNEL_LAST_PUBLISHED: str = """
SELECT published_at
FROM videos
WHERE channel_id = %(channel_id)s
  AND status = 'published'
ORDER BY published_at DESC
LIMIT 1;
"""

GET_CHANNEL_QUEUE_DEPTH: str = """
SELECT
    COUNT(*) FILTER (WHERE pj.status IN ('pending', 'in_progress')) AS videos_in_queue,
    COUNT(*) FILTER (WHERE pj.status = 'dead_letter') AS dead_letter_jobs
FROM pipeline_jobs pj
JOIN videos v ON v.id = pj.video_id
WHERE v.channel_id = %(channel_id)s;
"""

GET_CHANNEL_MONTHLY_REVENUE: str = """
SELECT SUM(vdm.estimated_revenue) AS monthly_revenue
FROM video_daily_metrics vdm
JOIN videos v ON v.id = vdm.video_id
WHERE v.channel_id = %(channel_id)s
  AND vdm.metric_date >= current_date - interval '30 days';
"""

GET_DEAD_LETTER_COUNT: str = """
SELECT COUNT(*) AS count
FROM pipeline_jobs
WHERE status = 'dead_letter';
"""

EXPORT_VIDEO_METRICS: str = """
SELECT
    v.title,
    vdm.metric_date,
    vdm.views,
    vdm.estimated_minutes_watched,
    vdm.average_view_duration_seconds,
    vdm.impressions,
    vdm.ctr,
    vdm.likes,
    vdm.comments,
    vdm.subscribers_gained,
    vdm.subscribers_lost,
    vdm.estimated_revenue
FROM video_daily_metrics vdm
JOIN videos v ON v.id = vdm.video_id
WHERE v.channel_id = %(channel_id)s
  AND vdm.metric_date >= current_date - make_interval(days := %(days)s)
ORDER BY vdm.metric_date DESC, v.title;
"""
