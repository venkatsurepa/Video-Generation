-- ============================================================
-- 009 — Optimization: generation_params JSONB + weekly cron
-- ============================================================
-- Adds a JSONB column to channel_generation_settings for storing
-- tunable weights (hook type, title formula, thumbnail archetype)
-- and Thompson Sampling parameters.
--
-- Also schedules a weekly optimization report via pg_cron.
-- ============================================================

-- 1. Add generation_params JSONB column
ALTER TABLE channel_generation_settings
    ADD COLUMN IF NOT EXISTS generation_params JSONB NOT NULL DEFAULT '{
        "hook_type_weights": {
            "cold_open": 0.20,
            "provocative_question": 0.20,
            "shocking_statistic": 0.20,
            "contradiction": 0.20,
            "sensory_scene": 0.20
        },
        "title_formula_weights": {
            "adjective_case": 0.167,
            "how_person": 0.167,
            "nobody_talks": 0.167,
            "why_question": 0.167,
            "truth_behind": 0.167,
            "what_happened": 0.167
        },
        "thumbnail_archetype_weights": {
            "mugshot_drama": 0.167,
            "mystery_reveal": 0.167,
            "crime_scene": 0.167,
            "victim_memorial": 0.167,
            "evidence_collage": 0.167,
            "location_map": 0.167
        },
        "thompson_params": {}
    }'::jsonb;


-- 2. Index for fast JSONB lookups on generation_params
CREATE INDEX IF NOT EXISTS idx_channel_gen_params
    ON channel_generation_settings USING gin (generation_params);


-- 3. Weekly optimization report — Sundays at 00:00 UTC
SELECT cron.schedule('optimization-weekly-report', '0 0 * * 0', $$
    SELECT net.http_post(
        url     := current_setting('app.settings.supabase_url', true)
                   || '/functions/v1/optimization-report',
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'Authorization', 'Bearer ' || current_setting('app.settings.service_role_key', true)
        ),
        body    := '{}'::jsonb
    );
$$);
