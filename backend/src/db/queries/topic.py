from __future__ import annotations

__all__ = [
    "LIST_TOPICS_BY_PRIORITY",
    "COUNT_TOPICS",
]

LIST_TOPICS_BY_PRIORITY: str = """
SELECT id, title, description, category, composite_score, priority,
       competitor_saturation, discovered_at, expires_at, created_at
FROM discovered_topics
WHERE (%(priority_filter)s IS NULL OR priority = %(priority_filter)s)
  AND used_in_video_id IS NULL
ORDER BY composite_score DESC
LIMIT %(limit)s;
"""

COUNT_TOPICS: str = """
SELECT COUNT(*) AS total
FROM discovered_topics
WHERE (%(priority_filter)s IS NULL OR priority = %(priority_filter)s)
  AND used_in_video_id IS NULL;
"""
