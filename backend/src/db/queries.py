"""SQL query constants for the pipeline job queue and core operations."""

from __future__ import annotations

CLAIM_NEXT_JOB: str = """
WITH next AS (
    SELECT id
    FROM pipeline_jobs
    WHERE status = 'pending'
      AND visible_at <= now()
    ORDER BY priority DESC, created_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE pipeline_jobs
SET status = 'running',
    started_at = now(),
    updated_at = now()
FROM next
WHERE pipeline_jobs.id = next.id
RETURNING pipeline_jobs.*;
"""

COMPLETE_JOB: str = """
UPDATE pipeline_jobs
SET status = 'completed',
    result = %(result)s,
    completed_at = now(),
    updated_at = now()
WHERE id = %(job_id)s;
"""

FAIL_JOB: str = """
UPDATE pipeline_jobs
SET status = CASE
        WHEN retry_count >= max_retries THEN 'dead_letter'
        ELSE 'pending'
    END,
    visible_at = now() + (power(2, retry_count) * interval '1 minute'),
    retry_count = retry_count + 1,
    error_message = %(error_message)s,
    updated_at = now()
WHERE id = %(job_id)s;
"""

CREATE_JOB: str = """
INSERT INTO pipeline_jobs (video_id, stage, payload, priority)
VALUES (%(video_id)s, %(stage)s, %(payload)s, %(priority)s)
RETURNING *;
"""

GET_VIDEO_STATUS: str = """
SELECT id, channel_id, title, topic, status, error_message,
       created_at, updated_at
FROM videos
WHERE id = %(video_id)s;
"""

UPDATE_VIDEO_STATUS: str = """
UPDATE videos
SET status = %(status)s,
    updated_at = now()
WHERE id = %(video_id)s
RETURNING *;
"""

INSERT_COST: str = """
INSERT INTO generation_costs
    (video_id, stage, provider, model, input_units, output_units, cost_usd, latency_ms)
VALUES
    (%(video_id)s, %(stage)s, %(provider)s, %(model)s,
     %(input_units)s, %(output_units)s, %(cost_usd)s, %(latency_ms)s);
"""

# --- Video CRUD ---

INSERT_VIDEO: str = """
INSERT INTO videos (channel_id, title, topic, status)
VALUES (%(channel_id)s, %(title)s, %(topic)s, 'pending')
RETURNING *;
"""

LIST_VIDEOS: str = """
SELECT id, channel_id, title, topic, status, error_message,
       created_at, updated_at
FROM videos
ORDER BY created_at DESC
LIMIT %(limit)s OFFSET %(offset)s;
"""

UPDATE_VIDEO: str = """
UPDATE videos
SET status = %(status)s,
    updated_at = now()
WHERE id = %(video_id)s
RETURNING *;
"""

# --- Channel CRUD ---

INSERT_CHANNEL: str = """
INSERT INTO channels (name, youtube_channel_id, description)
VALUES (%(name)s, %(youtube_channel_id)s, %(description)s)
RETURNING *;
"""

LIST_CHANNELS: str = """
SELECT id, name, youtube_channel_id, description, created_at, updated_at
FROM channels
ORDER BY created_at DESC
LIMIT %(limit)s OFFSET %(offset)s;
"""

GET_CHANNEL: str = """
SELECT id, name, youtube_channel_id, description, created_at, updated_at
FROM channels
WHERE id = %(channel_id)s;
"""

# --- Pipeline queries ---

GET_PIPELINE_JOBS: str = """
SELECT id, video_id, stage, status, priority, retry_count, max_retries,
       error_message, created_at, started_at, completed_at
FROM pipeline_jobs
WHERE video_id = %(video_id)s
ORDER BY created_at ASC;
"""

RETRY_FAILED_JOBS: str = """
UPDATE pipeline_jobs
SET status = 'pending',
    error_message = NULL,
    visible_at = now(),
    updated_at = now()
WHERE video_id = %(video_id)s
  AND status IN ('dead_letter', 'failed')
RETURNING *;
"""
