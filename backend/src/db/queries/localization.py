from __future__ import annotations

__all__ = [
    "GET_LOCALIZATION_CONFIG",
    "GET_AUTO_LOCALIZE_CONFIGS",
    "UPSERT_LOCALIZATION_CONFIG",
    "INSERT_LOCALIZED_VIDEO",
    "GET_VIDEO_LOCALIZATIONS",
    "GET_SOURCE_SCRIPT_TEXT",
    "GET_TOP_VIDEOS_WITH_RETENTION",
    "INSERT_COMPILATION_VIDEO",
    "GET_COMPILATION_CANDIDATES",
]

GET_LOCALIZATION_CONFIG: str = """
SELECT source_channel_id, target_channel_id, target_language,
       voice_id, font_family, auto_localize
FROM localization_config
WHERE source_channel_id = %(source_channel_id)s
  AND target_language = %(target_language)s;
"""

GET_AUTO_LOCALIZE_CONFIGS: str = """
SELECT source_channel_id, target_channel_id, target_language,
       voice_id, font_family, auto_localize
FROM localization_config
WHERE source_channel_id = %(source_channel_id)s
  AND auto_localize = true;
"""

UPSERT_LOCALIZATION_CONFIG: str = """
INSERT INTO localization_config
    (source_channel_id, target_channel_id, target_language, voice_id, font_family, auto_localize)
VALUES
    (%(source_channel_id)s, %(target_channel_id)s, %(target_language)s,
     %(voice_id)s, %(font_family)s, %(auto_localize)s)
ON CONFLICT (source_channel_id, target_language) DO UPDATE SET
    target_channel_id = EXCLUDED.target_channel_id,
    voice_id = EXCLUDED.voice_id,
    font_family = EXCLUDED.font_family,
    auto_localize = EXCLUDED.auto_localize,
    updated_at = now()
RETURNING *;
"""

INSERT_LOCALIZED_VIDEO: str = """
INSERT INTO videos
    (channel_id, title, description, tags, topic, status, parent_video_id, language)
VALUES
    (%(channel_id)s, %(title)s, %(description)s, %(tags)s, %(topic)s,
     'pending', %(parent_video_id)s, %(language)s)
RETURNING id;
"""

GET_VIDEO_LOCALIZATIONS: str = """
SELECT id, channel_id, title, language, status, created_at
FROM videos
WHERE parent_video_id = %(video_id)s
ORDER BY language;
"""

GET_SOURCE_SCRIPT_TEXT: str = """
SELECT result->>'script_text' AS script_text,
       result->>'word_count' AS word_count
FROM pipeline_jobs
WHERE video_id = %(video_id)s
  AND stage = 'script_generation'
  AND status = 'completed'
ORDER BY completed_at DESC
LIMIT 1;
"""

GET_TOP_VIDEOS_WITH_RETENTION: str = """
SELECT
    v.id              AS video_id,
    v.title           AS video_title,
    v.youtube_video_id,
    v.video_length_seconds,
    SUM(m.views)      AS total_views,
    (
        SELECT audience_retention_curve
        FROM video_daily_metrics m2
        WHERE m2.video_id = v.id
          AND m2.audience_retention_curve IS NOT NULL
        ORDER BY m2.metric_date DESC
        LIMIT 1
    ) AS retention_curve
FROM videos v
JOIN video_daily_metrics m ON m.video_id = v.id
WHERE v.channel_id = %(channel_id)s
  AND v.status = 'published'
  AND v.published_at >= %(published_after)s
  AND v.youtube_video_id IS NOT NULL
GROUP BY v.id
HAVING SUM(m.views) >= %(min_views)s
ORDER BY SUM(m.views) DESC
LIMIT 50;
"""

INSERT_COMPILATION_VIDEO: str = """
INSERT INTO videos (channel_id, title, description, tags, topic, status)
VALUES (
    %(channel_id)s,
    %(title)s,
    %(description)s,
    %(tags)s,
    %(topic)s,
    'pending'
)
RETURNING id;
"""

GET_COMPILATION_CANDIDATES: str = """
SELECT
    v.id,
    v.title,
    v.youtube_video_id,
    v.video_length_seconds,
    v.published_at,
    COALESCE(SUM(m.views), 0) AS total_views,
    COALESCE(AVG(m.average_view_percentage), 0) AS avg_retention_pct
FROM videos v
LEFT JOIN video_daily_metrics m ON m.video_id = v.id
WHERE v.channel_id = %(channel_id)s
  AND v.status = 'published'
  AND v.published_at >= %(published_after)s
  AND v.youtube_video_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM videos comp
      WHERE comp.topic->>'type' = 'compilation'
        AND comp.topic->'source_video_ids' ? v.id::text
  )
GROUP BY v.id
HAVING COALESCE(SUM(m.views), 0) >= %(min_views)s
ORDER BY COALESCE(SUM(m.views), 0) DESC;
"""
