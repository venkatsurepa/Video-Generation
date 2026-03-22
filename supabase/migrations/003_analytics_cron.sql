-- ============================================================
-- 003 — Analytics Collection Cron Jobs
-- ============================================================
-- Schedules two pg_cron jobs that POST to the backend API to
-- trigger YouTube Analytics data collection.
--
-- Tier 2 (daily):  Full Analytics API + retention + traffic
-- Tier 1 (6-hourly): Lightweight real-time stats via Data API
-- ============================================================

-- Daily analytics collection at 06:00 UTC
-- Calls POST /api/v1/analytics/collect
SELECT cron.schedule('analytics-collect-daily', '0 6 * * *', $$
    SELECT net.http_post(
        url     := current_setting('app.settings.supabase_url', true)
                   || '/functions/v1/analytics-collect',
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'Authorization', 'Bearer ' || current_setting('app.settings.service_role_key', true)
        ),
        body    := '{}'::jsonb
    );
$$);

-- Real-time stats collection every 6 hours
-- Calls POST /api/v1/analytics/collect/realtime
SELECT cron.schedule('analytics-realtime', '0 */6 * * *', $$
    SELECT net.http_post(
        url     := current_setting('app.settings.supabase_url', true)
                   || '/functions/v1/analytics-realtime',
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'Authorization', 'Bearer ' || current_setting('app.settings.service_role_key', true)
        ),
        body    := '{}'::jsonb
    );
$$);
