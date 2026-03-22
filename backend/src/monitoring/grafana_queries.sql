-- =============================================================================
-- CrimeMill — Grafana Cloud Dashboard Queries
-- =============================================================================
-- Data source: Supabase PostgreSQL (direct connection)
-- Import these as individual panels in a Grafana dashboard.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Dashboard: Pipeline Overview
-- ---------------------------------------------------------------------------

-- Panel: Videos produced per day (last 30 days)
SELECT
    DATE(published_at) AS day,
    COUNT(*)           AS videos
FROM videos
WHERE status = 'published'
GROUP BY day
ORDER BY day DESC
LIMIT 30;


-- Panel: Pipeline success rate by stage (last 7 days)
SELECT
    stage,
    COUNT(*) FILTER (WHERE status = 'completed')   AS succeeded,
    COUNT(*) FILTER (WHERE status = 'dead_letter')  AS failed,
    ROUND(
        COUNT(*) FILTER (WHERE status = 'completed')::numeric
        / NULLIF(COUNT(*), 0) * 100,
        1
    ) AS success_rate
FROM pipeline_jobs
WHERE created_at > now() - interval '7 days'
GROUP BY stage
ORDER BY stage;


-- Panel: Average cost per video (last 30 days)
SELECT
    DATE(v.created_at) AS day,
    ROUND(AVG(cs.total)::numeric, 4)  AS avg_cost,
    COUNT(*)                           AS video_count
FROM videos v
JOIN (
    SELECT video_id, SUM(cost_usd) AS total
    FROM generation_costs
    GROUP BY video_id
) cs ON cs.video_id = v.id
WHERE v.created_at > now() - interval '30 days'
GROUP BY day
ORDER BY day DESC;


-- Panel: Cost breakdown by stage (last 7 days)
SELECT
    stage,
    ROUND(SUM(cost_usd)::numeric, 2)  AS total_cost,
    ROUND(AVG(cost_usd)::numeric, 4)  AS avg_cost,
    COUNT(*)                            AS calls
FROM generation_costs
WHERE created_at > now() - interval '7 days'
GROUP BY stage
ORDER BY total_cost DESC;


-- Panel: Queue depth (current snapshot)
SELECT
    stage,
    COUNT(*) FILTER (WHERE status = 'pending')     AS pending,
    COUNT(*) FILTER (WHERE status = 'in_progress')  AS in_progress,
    COUNT(*) FILTER (WHERE status = 'dead_letter')  AS dead_letter
FROM pipeline_jobs
GROUP BY stage;


-- Panel: Per-video cost summary (last 50 published)
SELECT
    v.id,
    v.title,
    v.status,
    v.published_at,
    ROUND(cs.total::numeric, 4) AS total_cost_usd
FROM videos v
JOIN (
    SELECT video_id, SUM(cost_usd) AS total
    FROM generation_costs
    GROUP BY video_id
) cs ON cs.video_id = v.id
ORDER BY v.published_at DESC NULLS LAST
LIMIT 50;


-- Panel: Average stage duration (from structlog metric ingestion)
-- Note: requires Loki/Grafana Cloud Logs with label filter:
--   {app="crimemill"} |= "metric" | json | metric_name =~ "job_duration_seconds.*"


-- ---------------------------------------------------------------------------
-- Dashboard: Channel Performance
-- ---------------------------------------------------------------------------

-- Panel: Videos per channel
SELECT
    c.name                    AS channel_name,
    COUNT(v.id)               AS total_videos,
    COUNT(*) FILTER (WHERE v.status = 'published') AS published,
    COUNT(*) FILTER (WHERE v.status = 'failed')    AS failed
FROM channels c
LEFT JOIN videos v ON v.channel_id = c.id
GROUP BY c.id, c.name
ORDER BY published DESC;


-- ---------------------------------------------------------------------------
-- Alerts
-- ---------------------------------------------------------------------------

-- Alert: Dead letter jobs in the last 24 hours
SELECT
    video_id,
    stage,
    error_message,
    created_at
FROM pipeline_jobs
WHERE status = 'dead_letter'
  AND created_at > now() - interval '24 hours'
ORDER BY created_at DESC;


-- Alert: No videos produced in 24 hours
SELECT
    CASE
        WHEN COUNT(*) = 0 THEN 'ALERT: No videos published in 24h'
        ELSE 'OK: ' || COUNT(*) || ' videos published'
    END AS status
FROM videos
WHERE status = 'published'
  AND published_at > now() - interval '24 hours';


-- Alert: Cost spike — video exceeding 2× average cost
SELECT
    cs.video_id,
    v.title,
    ROUND(cs.total::numeric, 4)       AS cost_usd,
    ROUND(avg_cost.avg_cost::numeric, 4) AS avg_cost_usd
FROM (
    SELECT video_id, SUM(cost_usd) AS total
    FROM generation_costs
    GROUP BY video_id
) cs
JOIN videos v ON v.id = cs.video_id
CROSS JOIN (
    SELECT AVG(total) AS avg_cost
    FROM (
        SELECT SUM(cost_usd) AS total
        FROM generation_costs
        GROUP BY video_id
    ) sub
) avg_cost
WHERE cs.total > avg_cost.avg_cost * 2
ORDER BY cs.total DESC;
