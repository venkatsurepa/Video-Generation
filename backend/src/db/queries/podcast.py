from __future__ import annotations

__all__ = [
    "INSERT_PODCAST_EPISODE",
    "UPDATE_PODCAST_EPISODE_PUBLISHED",
    "FAIL_PODCAST_EPISODE",
    "GET_PODCAST_EPISODE",
    "LIST_PODCAST_EPISODES",
    "UPDATE_PODCAST_DOWNLOADS",
]

INSERT_PODCAST_EPISODE: str = """
INSERT INTO podcast_episodes (video_id, title, status)
VALUES (%(video_id)s, %(title)s, 'processing')
RETURNING *;
"""

UPDATE_PODCAST_EPISODE_PUBLISHED: str = """
UPDATE podcast_episodes
SET buzzsprout_episode_id = %(buzzsprout_episode_id)s,
    description = %(description)s,
    audio_storage_path = %(audio_storage_path)s,
    duration_seconds = %(duration_seconds)s,
    file_size_bytes = %(file_size_bytes)s,
    rss_feed_url = %(rss_feed_url)s,
    status = 'published',
    published_at = now(),
    updated_at = now()
WHERE video_id = %(video_id)s
RETURNING *;
"""

FAIL_PODCAST_EPISODE: str = """
UPDATE podcast_episodes
SET status = 'failed',
    error_message = %(error_message)s,
    updated_at = now()
WHERE video_id = %(video_id)s;
"""

GET_PODCAST_EPISODE: str = """
SELECT id, video_id, buzzsprout_episode_id, title, description,
       audio_storage_path, duration_seconds, file_size_bytes,
       rss_feed_url, total_downloads, status, error_message,
       published_at, created_at, updated_at
FROM podcast_episodes
WHERE video_id = %(video_id)s;
"""

LIST_PODCAST_EPISODES: str = """
SELECT id, video_id, buzzsprout_episode_id, title, description,
       audio_storage_path, duration_seconds, file_size_bytes,
       rss_feed_url, total_downloads, status, error_message,
       published_at, created_at, updated_at
FROM podcast_episodes
WHERE status = 'published'
ORDER BY published_at DESC
LIMIT %(limit)s OFFSET %(offset)s;
"""

UPDATE_PODCAST_DOWNLOADS: str = """
UPDATE podcast_episodes
SET total_downloads = %(total_downloads)s,
    updated_at = now()
WHERE buzzsprout_episode_id = %(buzzsprout_episode_id)s;
"""
