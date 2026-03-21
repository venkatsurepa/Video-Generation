-- ============================================================
-- CrimeMill — Complete Database Schema
-- ============================================================
-- Run via Supabase SQL Editor. Single file, idempotent-safe.
--
-- Design principles:
--   • One table per pipeline stage (not polymorphic)
--   • TEXT + CHECK constraints (not Postgres enums)
--   • UUID PKs via gen_random_uuid()
--   • All timestamps TIMESTAMPTZ
--   • Hybrid JSONB: normalized columns for queries, JSONB for API metadata
--   • Trigger-maintained summaries for instant dashboard reads
--   • Store bucket_id + path (never full URLs)
--
-- Storage buckets (configure in Supabase Dashboard → Storage):
--   • thumbnails  — public,  1-year cache (cacheControl: '31536000')
--   • images      — private, scene images served via signed URLs
--   • audio       — private, voiceovers and music tracks
--   • videos      — private, assembled final videos (largest files)
--   Path pattern: {channel_id}/{video_id}/{filename}
-- ============================================================


-- ============================================================
-- 0. EXTENSIONS
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";     -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_cron";      -- scheduled jobs
CREATE EXTENSION IF NOT EXISTS "pg_net";       -- async HTTP from triggers


-- ============================================================
-- 1. UTILITY: auto-update updated_at trigger
-- ============================================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- 2. CHANNELS & CONFIGURATION
-- ============================================================

CREATE TABLE channels (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    youtube_channel_id  TEXT NOT NULL DEFAULT '',
    handle              TEXT NOT NULL DEFAULT '',
    description         TEXT NOT NULL DEFAULT '',
    status              TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'suspended', 'archived')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_channels_updated_at
    BEFORE UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE channel_voice_settings (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id                  UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE UNIQUE,
    fish_audio_voice_id         TEXT NOT NULL DEFAULT '',
    voice_name                  TEXT NOT NULL DEFAULT '',
    emotion_preset              JSONB NOT NULL DEFAULT '{}',
    narration_speed_wpm_default INT NOT NULL DEFAULT 150,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_channel_voice_updated_at
    BEFORE UPDATE ON channel_voice_settings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE channel_brand_settings (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id              UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE UNIQUE,
    color_palette           JSONB NOT NULL DEFAULT '{}',
    thumbnail_archetype     TEXT NOT NULL DEFAULT 'mugshot_drama'
        CHECK (thumbnail_archetype IN (
            'mugshot_drama', 'mystery_reveal', 'crime_scene',
            'victim_memorial', 'evidence_collage', 'location_map'
        )),
    font_family             TEXT NOT NULL DEFAULT 'Inter',
    cinematic_prompt_suffix TEXT NOT NULL DEFAULT '',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_channel_brand_updated_at
    BEFORE UPDATE ON channel_brand_settings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE channel_credentials (
    id                                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id                          UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE UNIQUE,
    youtube_oauth_refresh_token_encrypted TEXT,
    adsense_account_id                  TEXT,
    fish_audio_api_key_encrypted        TEXT,
    created_at                          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_channel_creds_updated_at
    BEFORE UPDATE ON channel_credentials
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE channel_generation_settings (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id                  UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE UNIQUE,
    target_video_length_minutes INT NOT NULL DEFAULT 10,
    target_word_count           INT NOT NULL DEFAULT 1500,
    script_model                TEXT NOT NULL DEFAULT 'claude-sonnet-4',
    structured_model            TEXT NOT NULL DEFAULT 'claude-haiku-4-5',
    image_provider              TEXT NOT NULL DEFAULT 'fal',
    image_model                 TEXT NOT NULL DEFAULT 'flux-pro',
    images_per_video            INT NOT NULL DEFAULT 20,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_channel_gen_updated_at
    BEFORE UPDATE ON channel_generation_settings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- 3. VIDEOS (central entity)
-- ============================================================

CREATE TABLE videos (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id              UUID NOT NULL REFERENCES channels(id),
    title                   TEXT,
    description             TEXT,
    tags                    TEXT[] DEFAULT '{}',
    status                  TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'topic_selected', 'script_generated',
            'media_generating', 'media_complete', 'assembling',
            'assembled', 'uploading', 'published', 'failed', 'cancelled'
        )),
    error_message           TEXT,

    -- YouTube metadata (populated after upload)
    youtube_video_id        TEXT UNIQUE,
    youtube_privacy_status  TEXT CHECK (youtube_privacy_status IS NULL OR youtube_privacy_status IN (
        'private', 'unlisted', 'public'
    )),
    published_at            TIMESTAMPTZ,

    -- Content metadata
    topic                   JSONB NOT NULL DEFAULT '{}',
    script_word_count       INT,
    video_length_seconds    INT,
    "containsSyntheticMedia" BOOLEAN NOT NULL DEFAULT true,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_videos_updated_at
    BEFORE UPDATE ON videos
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- 4. PIPELINE STAGE TABLES
-- ============================================================

-- 4a. Script Generation
CREATE TABLE script_generations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE UNIQUE,
    model               TEXT,
    prompt_version      TEXT,
    raw_output          TEXT,
    edited_output       TEXT,
    scene_breakdown     JSONB,
    image_prompts       JSONB,
    sfx_annotations     JSONB,
    ad_break_timestamps JSONB,
    word_count          INT,
    status              TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'retrying')),
    attempts            INT NOT NULL DEFAULT 0,
    max_attempts        INT NOT NULL DEFAULT 3,
    error_message       TEXT,
    input_tokens        INT,
    output_tokens       INT,
    cost_usd            NUMERIC(10, 6),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ
);


-- 4b. Voiceover Generation
CREATE TABLE voiceover_generations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE UNIQUE,
    provider            TEXT NOT NULL DEFAULT 'fish_audio',
    voice_id            TEXT,
    emotion_tags_used   JSONB,
    duration_seconds    NUMERIC(8, 2),
    sample_rate         INT NOT NULL DEFAULT 48000,
    storage_bucket      TEXT,
    storage_path        TEXT,
    status              TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'retrying')),
    attempts            INT NOT NULL DEFAULT 0,
    max_attempts        INT NOT NULL DEFAULT 3,
    error_message       TEXT,
    cost_usd            NUMERIC(10, 6),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ
);


-- 4c. Scene Images
CREATE TABLE scene_images (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    scene_number        INT NOT NULL,
    prompt              TEXT,
    negative_prompt     TEXT,
    provider            TEXT,
    model               TEXT,
    width               INT,
    height              INT,
    storage_bucket      TEXT,
    storage_path        TEXT,
    post_processed      BOOLEAN NOT NULL DEFAULT false,
    generation_params   JSONB,
    status              TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'retrying')),
    attempts            INT NOT NULL DEFAULT 0,
    max_attempts        INT NOT NULL DEFAULT 3,
    error_message       TEXT,
    cost_usd            NUMERIC(10, 6),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at        TIMESTAMPTZ,
    UNIQUE (video_id, scene_number)
);


-- 4d. Music Selections
CREATE TABLE music_selections (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id            UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE UNIQUE,
    source              TEXT NOT NULL DEFAULT 'royalty_free'
        CHECK (source IN ('epidemic_sound', 'suno', 'ace_step', 'custom')),
    track_id            TEXT,
    track_name          TEXT,
    mood_category       TEXT,
    bpm                 INT,
    duration_seconds    NUMERIC(8, 2),
    storage_bucket      TEXT,
    storage_path        TEXT,
    license_info        JSONB,
    status              TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'retrying')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- 4e. Video Assemblies
CREATE TABLE video_assemblies (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id                UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE UNIQUE,
    remotion_composition_id TEXT,
    render_id               TEXT,
    render_duration_seconds NUMERIC(8, 2),
    output_resolution       TEXT NOT NULL DEFAULT '2560x1440',
    output_codec            TEXT NOT NULL DEFAULT 'h264',
    output_container        TEXT NOT NULL DEFAULT 'mp4',
    file_size_bytes         BIGINT,
    storage_bucket          TEXT,
    storage_path            TEXT,
    caption_srt_path        TEXT,
    status                  TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'retrying')),
    attempts                INT NOT NULL DEFAULT 0,
    max_attempts            INT NOT NULL DEFAULT 3,
    error_message           TEXT,
    cost_usd                NUMERIC(10, 6),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at            TIMESTAMPTZ
);


-- 4f. Thumbnail Generations
CREATE TABLE thumbnail_generations (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id                UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    variant_number          INT NOT NULL DEFAULT 1,
    background_provider     TEXT,
    background_prompt       TEXT,
    text_overlay            TEXT,
    archetype               TEXT
        CHECK (archetype IS NULL OR archetype IN (
            'mugshot_drama', 'mystery_reveal', 'crime_scene',
            'victim_memorial', 'evidence_collage', 'location_map'
        )),
    storage_bucket          TEXT,
    storage_path            TEXT,
    is_active               BOOLEAN NOT NULL DEFAULT false,
    youtube_test_compare_id TEXT,
    ctr                     NUMERIC(5, 4),
    status                  TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'retrying')),
    cost_usd                NUMERIC(10, 6),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (video_id, variant_number)
);


-- ============================================================
-- 5. PIPELINE TRANSITIONS (event-sourced audit trail)
-- ============================================================
-- Append-only. Never UPDATE rows in this table.

CREATE TABLE pipeline_transitions (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    video_id        UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    from_status     TEXT,
    to_status       TEXT NOT NULL,
    triggered_by    TEXT,           -- 'system', 'retry', 'manual', 'worker'
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- 6. PIPELINE JOB QUEUE (SKIP LOCKED pattern)
-- ============================================================

CREATE TABLE pipeline_jobs (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    video_id        UUID NOT NULL REFERENCES videos(id),
    stage           TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed', 'failed', 'dead_letter')),
    payload         JSONB NOT NULL DEFAULT '{}',
    result          JSONB,
    error_message   TEXT,
    retry_count     INT NOT NULL DEFAULT 0,
    max_retries     INT NOT NULL DEFAULT 3,
    priority        INT NOT NULL DEFAULT 0,
    visible_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

CREATE TRIGGER trg_pipeline_jobs_updated_at
    BEFORE UPDATE ON pipeline_jobs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- 7. COST TRACKING
-- ============================================================

CREATE TABLE api_providers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT UNIQUE NOT NULL,
    provider_type   TEXT NOT NULL
        CHECK (provider_type IN ('llm', 'tts', 'image_gen', 'music_gen', 'transcription', 'video_render')),
    base_url        TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE api_pricing (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id         UUID NOT NULL REFERENCES api_providers(id),
    model               TEXT NOT NULL,
    input_cost_per_unit NUMERIC(12, 8),
    output_cost_per_unit NUMERIC(12, 8),
    unit_type           TEXT NOT NULL,  -- 'per_1k_tokens', 'per_character', 'per_image', 'per_second'
    effective_from      DATE NOT NULL,
    effective_to        DATE,           -- NULL = current pricing
    notes               TEXT,
    UNIQUE (provider_id, model, effective_from)
);


CREATE TABLE generation_costs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id        UUID NOT NULL REFERENCES videos(id),
    stage           TEXT NOT NULL,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    input_units     NUMERIC NOT NULL DEFAULT 0,
    output_units    NUMERIC NOT NULL DEFAULT 0,
    cost_usd        NUMERIC(10, 6) NOT NULL DEFAULT 0,
    latency_ms      INT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE TABLE video_cost_summary (
    video_id        UUID PRIMARY KEY REFERENCES videos(id),
    script_cost     NUMERIC(10, 4) NOT NULL DEFAULT 0,
    voiceover_cost  NUMERIC(10, 4) NOT NULL DEFAULT 0,
    image_cost      NUMERIC(10, 4) NOT NULL DEFAULT 0,
    music_cost      NUMERIC(10, 4) NOT NULL DEFAULT 0,
    assembly_cost   NUMERIC(10, 4) NOT NULL DEFAULT 0,
    thumbnail_cost  NUMERIC(10, 4) NOT NULL DEFAULT 0,
    caption_cost    NUMERIC(10, 4) NOT NULL DEFAULT 0,
    total_cost_usd  NUMERIC(10, 4) NOT NULL DEFAULT 0,
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- 8. YOUTUBE ANALYTICS
-- ============================================================

CREATE TABLE video_daily_metrics (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id                        UUID NOT NULL REFERENCES videos(id),
    metric_date                     DATE NOT NULL,
    -- Reach
    views                           INT DEFAULT 0,
    estimated_minutes_watched       NUMERIC(12, 2) DEFAULT 0,
    average_view_duration_seconds   NUMERIC(10, 2) DEFAULT 0,
    average_view_percentage         NUMERIC(6, 2) DEFAULT 0,
    impressions                     INT DEFAULT 0,
    ctr                             NUMERIC(5, 4) DEFAULT 0,
    -- Engagement
    likes                           INT DEFAULT 0,
    dislikes                        INT DEFAULT 0,
    comments                        INT DEFAULT 0,
    shares                          INT DEFAULT 0,
    subscribers_gained              INT DEFAULT 0,
    subscribers_lost                INT DEFAULT 0,
    -- Revenue
    estimated_revenue               NUMERIC(10, 4) DEFAULT 0,
    -- Breakdowns (JSONB for variable-shape data)
    traffic_source_breakdown        JSONB,
    audience_retention_curve        JSONB,
    fetched_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (video_id, metric_date)
);


-- ============================================================
-- 9. CHANNEL MEMBERS (future dashboard RLS)
-- ============================================================

CREATE TABLE channel_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id  UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL,
    role        TEXT NOT NULL DEFAULT 'viewer'
        CHECK (role IN ('owner', 'editor', 'viewer')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (channel_id, user_id)
);


-- ============================================================
-- 10. TRIGGERS
-- ============================================================

-- 10a. Auto-update video_cost_summary when generation_costs rows are inserted
CREATE OR REPLACE FUNCTION on_generation_cost_insert()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO video_cost_summary (
        video_id, script_cost, voiceover_cost, image_cost, music_cost,
        assembly_cost, thumbnail_cost, caption_cost, total_cost_usd
    )
    SELECT
        NEW.video_id,
        SUM(CASE WHEN stage = 'script_generation'    THEN cost_usd ELSE 0 END),
        SUM(CASE WHEN stage = 'voiceover_generation'  THEN cost_usd ELSE 0 END),
        SUM(CASE WHEN stage = 'image_generation'      THEN cost_usd ELSE 0 END),
        SUM(CASE WHEN stage = 'music_selection'        THEN cost_usd ELSE 0 END),
        SUM(CASE WHEN stage = 'video_assembly'         THEN cost_usd ELSE 0 END),
        SUM(CASE WHEN stage = 'thumbnail_generation'   THEN cost_usd ELSE 0 END),
        SUM(CASE WHEN stage = 'caption_generation'     THEN cost_usd ELSE 0 END),
        SUM(cost_usd)
    FROM generation_costs
    WHERE video_id = NEW.video_id
    ON CONFLICT (video_id) DO UPDATE SET
        script_cost     = EXCLUDED.script_cost,
        voiceover_cost  = EXCLUDED.voiceover_cost,
        image_cost      = EXCLUDED.image_cost,
        music_cost      = EXCLUDED.music_cost,
        assembly_cost   = EXCLUDED.assembly_cost,
        thumbnail_cost  = EXCLUDED.thumbnail_cost,
        caption_cost    = EXCLUDED.caption_cost,
        total_cost_usd  = EXCLUDED.total_cost_usd,
        last_updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_generation_cost_insert
    AFTER INSERT ON generation_costs
    FOR EACH ROW EXECUTE FUNCTION on_generation_cost_insert();


-- 10b. Record pipeline transitions when videos.status changes
CREATE OR REPLACE FUNCTION on_video_status_change()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO pipeline_transitions (video_id, from_status, to_status, triggered_by)
        VALUES (NEW.id, OLD.status, NEW.status, 'system');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_video_status_change
    AFTER UPDATE OF status ON videos
    FOR EACH ROW EXECUTE FUNCTION on_video_status_change();


-- 10c. Advance pipeline when a job stage completes
--      Calls an Edge Function via pg_net to enqueue dependent stages.
CREATE OR REPLACE FUNCTION on_stage_completion()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.status = 'completed' AND OLD.status IS DISTINCT FROM 'completed' THEN
        -- Record the stage completion in the audit trail
        INSERT INTO pipeline_transitions (video_id, from_status, to_status, triggered_by, metadata)
        VALUES (
            NEW.video_id,
            OLD.status,
            'completed',
            'worker',
            jsonb_build_object('stage', NEW.stage, 'job_id', NEW.id)
        );

        -- Async HTTP call to advance-pipeline Edge Function
        PERFORM net.http_post(
            url     := current_setting('app.settings.supabase_url', true)
                       || '/functions/v1/advance-pipeline',
            body    := jsonb_build_object(
                'video_id', NEW.video_id,
                'completed_stage', NEW.stage
            ),
            headers := jsonb_build_object(
                'Content-Type', 'application/json',
                'Authorization', 'Bearer ' || current_setting('app.settings.service_role_key', true)
            )
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER trg_stage_completion
    AFTER UPDATE OF status ON pipeline_jobs
    FOR EACH ROW EXECUTE FUNCTION on_stage_completion();


-- ============================================================
-- 11. INDEXES
-- ============================================================

-- Videos: core query patterns
CREATE INDEX idx_videos_channel_status
    ON videos (channel_id, status);
CREATE INDEX idx_videos_channel_created
    ON videos (channel_id, created_at DESC);
CREATE INDEX idx_videos_active_status
    ON videos (status) WHERE status NOT IN ('published', 'cancelled');

-- Pipeline jobs: queue polling (the critical hot path)
CREATE INDEX idx_pipeline_jobs_queue
    ON pipeline_jobs (visible_at, created_at)
    WHERE status = 'pending';
CREATE INDEX idx_pipeline_jobs_video
    ON pipeline_jobs (video_id);

-- Scene images: fetch all scenes for a video in order
CREATE INDEX idx_scene_images_video
    ON scene_images (video_id, scene_number);
CREATE INDEX idx_scene_images_pending
    ON scene_images (status)
    WHERE status IN ('pending', 'in_progress', 'retrying');

-- Stage tables: find incomplete work (partial indexes)
CREATE INDEX idx_script_gen_status
    ON script_generations (status)
    WHERE status != 'completed';
CREATE INDEX idx_voiceover_gen_status
    ON voiceover_generations (status)
    WHERE status != 'completed';

-- Analytics: time-range queries
CREATE INDEX idx_vdm_video_date
    ON video_daily_metrics (video_id, metric_date DESC);
CREATE INDEX idx_vdm_date
    ON video_daily_metrics (metric_date DESC);
-- BRIN for low-overhead date filtering as table grows
CREATE INDEX idx_vdm_date_brin
    ON video_daily_metrics USING brin (metric_date)
    WITH (pages_per_range = 32);

-- Cost tracking
CREATE INDEX idx_gen_costs_video
    ON generation_costs (video_id);
CREATE INDEX idx_gen_costs_video_stage
    ON generation_costs (video_id, stage);
CREATE INDEX idx_gen_costs_created_brin
    ON generation_costs USING brin (created_at)
    WITH (pages_per_range = 32);

-- Pipeline transitions: audit trail queries
CREATE INDEX idx_transitions_video
    ON pipeline_transitions (video_id, created_at DESC);

-- Channel members: support RLS policy joins
CREATE INDEX idx_channel_members_user
    ON channel_members (user_id);


-- ============================================================
-- 12. MATERIALIZED VIEWS
-- ============================================================

-- Channel-level daily summary
CREATE MATERIALIZED VIEW mv_channel_daily_summary AS
SELECT
    c.id                    AS channel_id,
    vdm.metric_date,
    SUM(vdm.views)          AS total_views,
    SUM(vdm.estimated_minutes_watched) AS total_watch_minutes,
    CASE
        WHEN SUM(vdm.impressions) > 0
        THEN SUM(vdm.views)::NUMERIC / SUM(vdm.impressions)
        ELSE 0
    END                     AS avg_ctr,
    SUM(vdm.likes)          AS total_likes,
    SUM(vdm.subscribers_gained - vdm.subscribers_lost) AS net_subscribers,
    SUM(vdm.estimated_revenue) AS total_revenue
FROM video_daily_metrics vdm
JOIN videos v  ON v.id  = vdm.video_id
JOIN channels c ON c.id = v.channel_id
GROUP BY c.id, vdm.metric_date;

CREATE UNIQUE INDEX ON mv_channel_daily_summary (channel_id, metric_date);


-- Video profitability (the key dashboard query)
CREATE MATERIALIZED VIEW mv_video_profitability AS
SELECT
    v.id            AS video_id,
    v.title,
    v.published_at,
    c.id            AS channel_id,
    c.name          AS channel_name,
    SUM(vdm.views)  AS lifetime_views,
    SUM(vdm.estimated_minutes_watched) AS lifetime_watch_minutes,
    SUM(vdm.estimated_revenue)         AS lifetime_revenue,
    COALESCE(vcs.total_cost_usd, 0)    AS generation_cost,
    SUM(COALESCE(vdm.estimated_revenue, 0)) - COALESCE(vcs.total_cost_usd, 0) AS net_profit,
    CASE
        WHEN COALESCE(vcs.total_cost_usd, 0) > 0
        THEN ROUND((SUM(COALESCE(vdm.estimated_revenue, 0)) / vcs.total_cost_usd)::NUMERIC, 2)
        ELSE NULL
    END AS roi_ratio,
    CASE
        WHEN COALESCE(vcs.total_cost_usd, 0) = 0 THEN 'no_cost_data'
        WHEN SUM(COALESCE(vdm.estimated_revenue, 0)) >= vcs.total_cost_usd THEN 'profitable'
        ELSE 'not_yet_profitable'
    END AS profitability_status
FROM videos v
JOIN channels c ON c.id = v.channel_id
LEFT JOIN video_daily_metrics vdm ON vdm.video_id = v.id
LEFT JOIN video_cost_summary  vcs ON vcs.video_id = v.id
GROUP BY v.id, v.title, v.published_at, c.id, c.name, vcs.total_cost_usd;

CREATE UNIQUE INDEX ON mv_video_profitability (video_id);
CREATE INDEX        ON mv_video_profitability (channel_id);
CREATE INDEX        ON mv_video_profitability (profitability_status);


-- ============================================================
-- 13. PG_CRON SCHEDULES
-- ============================================================

-- Process pipeline queue: every minute, POST to Edge Function
SELECT cron.schedule('process-pipeline-queue', '* * * * *', $$
    SELECT net.http_post(
        url     := current_setting('app.settings.supabase_url', true)
                   || '/functions/v1/process-queue',
        headers := jsonb_build_object(
            'Content-Type', 'application/json',
            'Authorization', 'Bearer ' || current_setting('app.settings.service_role_key', true)
        )
    )
$$);

-- Recover stalled jobs: every 5 minutes, reset in_progress past visible_at
SELECT cron.schedule('recover-stalled-jobs', '*/5 * * * *', $$
    UPDATE pipeline_jobs
    SET status     = 'pending',
        updated_at = now()
    WHERE status      = 'in_progress'
      AND visible_at  < now()
      AND retry_count < max_retries
$$);

-- Refresh materialized views daily
SELECT cron.schedule('refresh-channel-summary', '30 3 * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_channel_daily_summary');

SELECT cron.schedule('refresh-profitability', '35 3 * * *',
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_video_profitability');


-- ============================================================
-- 14. ROW LEVEL SECURITY
-- ============================================================
-- Enable on all tables now. Service role bypasses RLS, so the
-- pipeline runs unimpeded. SELECT policies will be added when
-- the dashboard is built.

ALTER TABLE channels                    ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_voice_settings      ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_brand_settings      ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_credentials         ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_generation_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE videos                      ENABLE ROW LEVEL SECURITY;
ALTER TABLE script_generations          ENABLE ROW LEVEL SECURITY;
ALTER TABLE voiceover_generations       ENABLE ROW LEVEL SECURITY;
ALTER TABLE scene_images                ENABLE ROW LEVEL SECURITY;
ALTER TABLE music_selections            ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_assemblies            ENABLE ROW LEVEL SECURITY;
ALTER TABLE thumbnail_generations       ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_transitions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_jobs               ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_providers               ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_pricing                 ENABLE ROW LEVEL SECURITY;
ALTER TABLE generation_costs            ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_cost_summary          ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_daily_metrics         ENABLE ROW LEVEL SECURITY;
ALTER TABLE channel_members             ENABLE ROW LEVEL SECURITY;

-- SECURITY DEFINER helper: returns channel IDs the current user can access.
-- Used in future dashboard RLS policies. Avoids nested RLS on channel_members.
CREATE OR REPLACE FUNCTION user_channel_ids()
RETURNS SETOF UUID
LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
    SELECT channel_id FROM channel_members
    WHERE user_id = (SELECT auth.uid())
$$;


-- ============================================================
-- Done. 20 tables, 2 materialized views, 3 triggers, 4 cron jobs.
-- ============================================================
