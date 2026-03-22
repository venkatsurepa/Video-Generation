from __future__ import annotations

__all__ = [
    "INSERT_TOPIC_SUBMISSION",
    "LIST_TOPIC_SUBMISSIONS",
    "COUNT_TOPIC_SUBMISSIONS",
    "GET_TOPIC_SUBMISSION",
    "UPDATE_TOPIC_SUBMISSION_STATUS",
    "UPDATE_TOPIC_SUBMISSION_SCORE",
    "DEDUPLICATE_SUBMISSION",
    "COUNT_SUBMISSIONS_THIS_MONTH",
    "COUNT_COMMUNITY_SOURCED_VIDEOS",
    "UPSERT_PATREON_MEMBER",
    "LIST_ACTIVE_PATRONS",
    "LIST_PATRON_CREDITS",
    "MARK_CHURNED_PATRONS",
    "COUNT_ACTIVE_PATRONS",
    "PATRON_RETENTION_RATE",
]

INSERT_TOPIC_SUBMISSION: str = """
INSERT INTO topic_submissions
    (source, submitter_name, submitter_contact, case_name,
     description, why_interesting, source_links, score)
VALUES
    (%(source)s, %(submitter_name)s, %(submitter_contact)s, %(case_name)s,
     %(description)s, %(why_interesting)s, %(source_links)s, %(score)s)
RETURNING *;
"""

LIST_TOPIC_SUBMISSIONS: str = """
SELECT *
FROM topic_submissions
WHERE status = %(status)s
ORDER BY created_at DESC
LIMIT %(limit)s OFFSET %(offset)s;
"""

COUNT_TOPIC_SUBMISSIONS: str = """
SELECT count(*) AS total
FROM topic_submissions
WHERE status = %(status)s;
"""

GET_TOPIC_SUBMISSION: str = """
SELECT * FROM topic_submissions WHERE id = %(id)s;
"""

UPDATE_TOPIC_SUBMISSION_STATUS: str = """
UPDATE topic_submissions
SET status = %(status)s,
    assigned_topic_id = COALESCE(%(assigned_topic_id)s, assigned_topic_id),
    assigned_video_id = COALESCE(%(assigned_video_id)s, assigned_video_id)
WHERE id = %(id)s
RETURNING *;
"""

UPDATE_TOPIC_SUBMISSION_SCORE: str = """
UPDATE topic_submissions
SET score = %(score)s
WHERE id = %(id)s;
"""

DEDUPLICATE_SUBMISSION: str = """
SELECT id, case_name, status, score
FROM topic_submissions
WHERE to_tsvector('english', case_name) @@ plainto_tsquery('english', %(case_name)s)
  AND status NOT IN ('rejected')
LIMIT 5;
"""

COUNT_SUBMISSIONS_THIS_MONTH: str = """
SELECT count(*) AS total
FROM topic_submissions
WHERE created_at >= date_trunc('month', now());
"""

COUNT_COMMUNITY_SOURCED_VIDEOS: str = """
SELECT count(*) AS total
FROM topic_submissions
WHERE status = 'produced'
  AND assigned_video_id IS NOT NULL;
"""

UPSERT_PATREON_MEMBER: str = """
INSERT INTO patreon_members
    (patreon_id, name, email, tier_name, tier_amount_cents, is_active, last_synced_at)
VALUES
    (%(patreon_id)s, %(name)s, %(email)s, %(tier_name)s,
     %(tier_amount_cents)s, %(is_active)s, now())
ON CONFLICT (patreon_id) DO UPDATE SET
    name = EXCLUDED.name,
    email = EXCLUDED.email,
    tier_name = EXCLUDED.tier_name,
    tier_amount_cents = EXCLUDED.tier_amount_cents,
    is_active = EXCLUDED.is_active,
    last_synced_at = now()
RETURNING *;
"""

LIST_ACTIVE_PATRONS: str = """
SELECT *
FROM patreon_members
WHERE is_active = true
ORDER BY tier_amount_cents DESC, name ASC;
"""

LIST_PATRON_CREDITS: str = """
SELECT name, tier_name, tier_amount_cents
FROM patreon_members
WHERE is_active = true
  AND show_in_credits = true
ORDER BY tier_amount_cents DESC, name ASC;
"""

MARK_CHURNED_PATRONS: str = """
UPDATE patreon_members
SET is_active = false
WHERE is_active = true
  AND last_synced_at < %(cutoff)s
RETURNING id, patreon_id, name;
"""

COUNT_ACTIVE_PATRONS: str = """
SELECT
    count(*) AS patron_count,
    COALESCE(SUM(tier_amount_cents), 0) AS total_mrr_cents
FROM patreon_members
WHERE is_active = true;
"""

PATRON_RETENTION_RATE: str = """
SELECT
    CASE WHEN count(*) = 0 THEN 0
         ELSE count(*) FILTER (WHERE is_active) * 1.0 / count(*)
    END AS retention_rate
FROM patreon_members;
"""
