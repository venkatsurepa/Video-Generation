from __future__ import annotations

__all__ = [
    "LIST_SCHEDULED_VIDEOS",
]

LIST_SCHEDULED_VIDEOS: str = """
SELECT v.id, v.title, v.status, v.published_at, v.created_at,
       c.name AS channel_name, c.handle
FROM videos v
JOIN channels c ON c.id = v.channel_id
WHERE v.status IN ('assembled', 'uploading')
  AND (v.published_at IS NULL OR v.published_at <= now() + make_interval(days := %(days)s))
ORDER BY COALESCE(v.published_at, v.created_at) ASC;
"""
