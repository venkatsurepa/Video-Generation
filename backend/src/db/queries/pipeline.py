from __future__ import annotations

__all__ = [
    "CLAIM_NEXT_JOB",
    "COMPLETE_JOB",
    "FAIL_JOB",
    "CREATE_JOB",
    "GET_PIPELINE_JOBS",
    "RETRY_FAILED_JOBS",
    "GET_COMPLETED_STAGES",
    "GET_ENQUEUED_STAGES",
    "CANCEL_PIPELINE_JOBS",
]

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
SET status = 'in_progress',
    visible_at = now() + interval '5 minutes',
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

GET_COMPLETED_STAGES: str = """
SELECT stage, result
FROM pipeline_jobs
WHERE video_id = %(video_id)s
  AND status = 'completed'
ORDER BY completed_at ASC;
"""

GET_ENQUEUED_STAGES: str = """
SELECT DISTINCT stage
FROM pipeline_jobs
WHERE video_id = %(video_id)s
  AND status NOT IN ('dead_letter');
"""

CANCEL_PIPELINE_JOBS: str = """
UPDATE pipeline_jobs
SET status = 'failed',
    error_message = 'Pipeline cancelled',
    updated_at = now()
WHERE video_id = %(video_id)s
  AND status IN ('pending', 'in_progress')
RETURNING id;
"""
