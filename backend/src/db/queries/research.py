from __future__ import annotations

__all__ = [
    "INSERT_RESEARCH_SOURCE",
    "SEARCH_RESEARCH_SOURCES",
    "GET_RESEARCH_SOURCE",
    "GET_CASE_SOURCES",
    "LINK_SOURCE_TO_CASE",
    "INSERT_CASE_FILE",
    "GET_CASE_FILE",
    "LIST_CASE_FILES",
    "UPDATE_CASE_FILE",
    "INSERT_FOIA_REQUEST",
    "UPDATE_FOIA_REQUEST",
    "GET_FOIA_REQUEST",
    "LIST_FOIA_REQUESTS",
    "GET_OVERDUE_FOIA",
    "COUNT_CASE_FILES",
    "COUNT_FOIA_REQUESTS",
    "COUNT_RESEARCH_SOURCES",
]

INSERT_RESEARCH_SOURCE: str = """
INSERT INTO research_sources
    (case_file_id, source_type, title, url, source_name,
     publication_date, raw_text, entities, metadata, relevance_score)
VALUES
    (%(case_file_id)s, %(source_type)s, %(title)s, %(url)s, %(source_name)s,
     %(publication_date)s, %(raw_text)s, %(entities)s, %(metadata)s, %(relevance_score)s)
RETURNING *;
"""

SEARCH_RESEARCH_SOURCES: str = """
SELECT rs.*,
       ts_rank(to_tsvector('english', rs.raw_text),
               plainto_tsquery('english', %(query)s)) AS rank
FROM research_sources rs
WHERE to_tsvector('english', rs.raw_text) @@ plainto_tsquery('english', %(query)s)
  AND (%(source_type)s IS NULL OR rs.source_type = %(source_type)s)
  AND (%(date_from)s IS NULL OR rs.publication_date >= %(date_from)s)
  AND (%(date_to)s IS NULL OR rs.publication_date <= %(date_to)s)
ORDER BY rank DESC, rs.created_at DESC
LIMIT %(limit)s OFFSET %(offset)s;
"""

GET_RESEARCH_SOURCE: str = """
SELECT * FROM research_sources WHERE id = %(source_id)s;
"""

GET_CASE_SOURCES: str = """
SELECT *
FROM research_sources
WHERE case_file_id = %(case_file_id)s
ORDER BY publication_date DESC NULLS LAST;
"""

LINK_SOURCE_TO_CASE: str = """
UPDATE research_sources
SET case_file_id = %(case_file_id)s
WHERE id = %(source_id)s
RETURNING *;
"""

INSERT_CASE_FILE: str = """
INSERT INTO case_files (case_name, category, summary)
VALUES (%(case_name)s, %(category)s, %(summary)s)
RETURNING *;
"""

GET_CASE_FILE: str = """
SELECT cf.*,
       (SELECT COUNT(*) FROM research_sources rs
        WHERE rs.case_file_id = cf.id) AS source_count
FROM case_files cf
WHERE cf.id = %(case_file_id)s;
"""

LIST_CASE_FILES: str = """
SELECT cf.*,
       (SELECT COUNT(*) FROM research_sources rs
        WHERE rs.case_file_id = cf.id) AS source_count
FROM case_files cf
WHERE (%(category)s IS NULL OR cf.category = %(category)s)
  AND (%(status)s IS NULL OR cf.status = %(status)s)
ORDER BY cf.updated_at DESC
LIMIT %(limit)s OFFSET %(offset)s;
"""

UPDATE_CASE_FILE: str = """
UPDATE case_files
SET case_name = COALESCE(%(case_name)s, case_name),
    category = COALESCE(%(category)s, category),
    summary = COALESCE(%(summary)s, summary),
    key_entities = COALESCE(%(key_entities)s, key_entities),
    timeline = COALESCE(%(timeline)s, timeline),
    financial_impact_usd = COALESCE(%(financial_impact_usd)s, financial_impact_usd),
    status = COALESCE(%(status)s, status),
    assigned_video_id = COALESCE(%(assigned_video_id)s, assigned_video_id),
    assigned_topic_id = COALESCE(%(assigned_topic_id)s, assigned_topic_id),
    notes = COALESCE(%(notes)s, notes),
    updated_at = now()
WHERE id = %(case_file_id)s
RETURNING *;
"""

INSERT_FOIA_REQUEST: str = """
INSERT INTO foia_requests
    (agency, description, case_reference, case_file_id, method,
     date_filed, expected_response_date)
VALUES
    (%(agency)s, %(description)s, %(case_reference)s, %(case_file_id)s,
     %(method)s, %(date_filed)s, %(expected_response_date)s)
RETURNING *;
"""

UPDATE_FOIA_REQUEST: str = """
UPDATE foia_requests
SET status = COALESCE(%(status)s, status),
    tracking_number = COALESCE(%(tracking_number)s, tracking_number),
    notes = COALESCE(%(notes)s, notes),
    documents_received = COALESCE(%(documents_received)s, documents_received),
    actual_response_date = COALESCE(%(actual_response_date)s, actual_response_date),
    updated_at = now()
WHERE id = %(foia_id)s
RETURNING *;
"""

GET_FOIA_REQUEST: str = """
SELECT * FROM foia_requests WHERE id = %(foia_id)s;
"""

LIST_FOIA_REQUESTS: str = """
SELECT *
FROM foia_requests
WHERE (%(status)s IS NULL OR status = %(status)s)
  AND (%(agency)s IS NULL OR agency = %(agency)s)
ORDER BY created_at DESC
LIMIT %(limit)s OFFSET %(offset)s;
"""

GET_OVERDUE_FOIA: str = """
SELECT *
FROM foia_requests
WHERE status IN ('filed', 'acknowledged', 'processing')
  AND expected_response_date IS NOT NULL
  AND expected_response_date < CURRENT_DATE
ORDER BY expected_response_date ASC;
"""

COUNT_CASE_FILES: str = """
SELECT COUNT(*) AS total
FROM case_files
WHERE (%(category)s IS NULL OR category = %(category)s)
  AND (%(status)s IS NULL OR status = %(status)s);
"""

COUNT_FOIA_REQUESTS: str = """
SELECT COUNT(*) AS total
FROM foia_requests
WHERE (%(status)s IS NULL OR status = %(status)s)
  AND (%(agency)s IS NULL OR agency = %(agency)s);
"""

COUNT_RESEARCH_SOURCES: str = """
SELECT COUNT(*) AS total
FROM research_sources rs
WHERE to_tsvector('english', rs.raw_text) @@ plainto_tsquery('english', %(query)s)
  AND (%(source_type)s IS NULL OR rs.source_type = %(source_type)s)
  AND (%(date_from)s IS NULL OR rs.publication_date >= %(date_from)s)
  AND (%(date_to)s IS NULL OR rs.publication_date <= %(date_to)s);
"""
