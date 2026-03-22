from __future__ import annotations

__all__ = [
    "GET_VIDEO_STATUS",
    "UPDATE_VIDEO_STATUS",
    "INSERT_VIDEO",
    "LIST_VIDEOS",
    "UPDATE_VIDEO",
    "LIST_VIDEOS_FILTERED",
    "GET_VIDEO_COST_SUMMARY",
    "GET_VIDEO_WITH_CHANNEL",
    "UPDATE_VIDEO_FIELDS",
    "LIST_REVIEW_QUEUE",
    "UPDATE_VIDEO_REVIEW",
    "COUNT_VIDEOS_FILTERED",
]

GET_VIDEO_STATUS: str = """
SELECT id, channel_id, title, description, tags, topic, status, error_message,
       youtube_video_id, youtube_privacy_status, published_at,
       script_word_count, video_length_seconds,
       created_at, updated_at
FROM videos
WHERE id = %(video_id)s;
"""

UPDATE_VIDEO_STATUS: str = """
UPDATE videos
SET status = %(status)s
WHERE id = %(video_id)s
RETURNING *;
"""

INSERT_VIDEO: str = """
INSERT INTO videos (channel_id, title, description, tags, topic, status)
VALUES (%(channel_id)s, %(title)s, %(description)s, %(tags)s, %(topic)s, 'pending')
RETURNING *;
"""

LIST_VIDEOS: str = """
SELECT id, channel_id, title, description, tags, topic, status, error_message,
       youtube_video_id, youtube_privacy_status, published_at,
       script_word_count, video_length_seconds,
       created_at, updated_at
FROM videos
ORDER BY created_at DESC
LIMIT %(limit)s OFFSET %(offset)s;
"""

UPDATE_VIDEO: str = """
UPDATE videos
SET status = %(status)s
WHERE id = %(video_id)s
RETURNING *;
"""

LIST_VIDEOS_FILTERED: str = """
SELECT id, channel_id, title, description, tags, topic, status, error_message,
       youtube_video_id, youtube_privacy_status, published_at,
       script_word_count, video_length_seconds,
       created_at, updated_at
FROM videos
WHERE (%(status_filter)s IS NULL OR status = %(status_filter)s)
  AND (%(channel_filter)s IS NULL OR channel_id = %(channel_filter)s)
  AND (%(date_from)s IS NULL OR created_at >= %(date_from)s)
  AND (%(date_to)s IS NULL OR created_at <= %(date_to)s)
ORDER BY created_at DESC
LIMIT %(limit)s OFFSET %(offset)s;
"""

GET_VIDEO_COST_SUMMARY: str = """
SELECT
    video_id,
    stage,
    provider,
    model,
    input_units,
    output_units,
    cost_usd,
    latency_ms,
    created_at
FROM generation_costs
WHERE video_id = %(video_id)s
ORDER BY created_at ASC;
"""

GET_VIDEO_WITH_CHANNEL: str = """
SELECT v.id, v.channel_id, v.title, v.description, v.tags, v.topic,
       v.status, v.error_message, v.script_word_count, v.video_length_seconds,
       c.name AS channel_name, c.youtube_channel_id
FROM videos v
JOIN channels c ON c.id = v.channel_id
WHERE v.id = %(video_id)s;
"""

UPDATE_VIDEO_FIELDS: str = """
UPDATE videos
SET status = %(status)s,
    title = COALESCE(%(title)s, title),
    description = COALESCE(%(description)s, description),
    script_word_count = COALESCE(%(script_word_count)s, script_word_count),
    video_length_seconds = COALESCE(%(video_length_seconds)s, video_length_seconds),
    error_message = %(error_message)s,
    updated_at = now()
WHERE id = %(video_id)s;
"""

LIST_REVIEW_QUEUE: str = """
SELECT v.id, v.channel_id, v.title, v.status, v.created_at, v.updated_at,
       c.name AS channel_name
FROM videos v
JOIN channels c ON c.id = v.channel_id
WHERE v.status = 'assembled'
ORDER BY v.created_at ASC;
"""

UPDATE_VIDEO_REVIEW: str = """
UPDATE videos
SET status = %(status)s,
    error_message = %(notes)s,
    updated_at = now()
WHERE id = %(video_id)s
RETURNING *;
"""

COUNT_VIDEOS_FILTERED: str = """
SELECT COUNT(*) AS total
FROM videos
WHERE (%(status_filter)s IS NULL OR status = %(status_filter)s)
  AND (%(channel_filter)s IS NULL OR channel_id = %(channel_filter)s)
  AND (%(date_from)s IS NULL OR created_at >= %(date_from)s)
  AND (%(date_to)s IS NULL OR created_at <= %(date_to)s);
"""
