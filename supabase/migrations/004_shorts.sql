-- ============================================================
-- CrimeMill — Shorts Pipeline Tables
-- ============================================================
-- Stores YouTube Shorts derived from parent long-form videos.
-- Each parent video can produce 2-3 Shorts as discovery funnels.
--
-- Design:
--   • Links to parent video via parent_video_id FK
--   • Tracks render, upload, and performance independently
--   • Optional pipeline stage — failures don't block parent
-- ============================================================


-- ============================================================
-- 1. SHORTS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS shorts (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_video_id         UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    channel_id              UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,

    -- Segment metadata (from Claude Haiku identification)
    segment_index           INT NOT NULL DEFAULT 0,
    hook_text               TEXT NOT NULL DEFAULT '',
    cliffhanger_text        TEXT NOT NULL DEFAULT '',
    narration_text          TEXT NOT NULL DEFAULT '',
    scene_numbers           JSONB NOT NULL DEFAULT '[]',
    duration_type           TEXT NOT NULL DEFAULT '60s'
        CHECK (duration_type IN ('13s', '60s')),
    reasoning               TEXT NOT NULL DEFAULT '',

    -- Render output
    status                  TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'rendering', 'rendered',
            'uploading', 'published', 'failed'
        )),
    file_path               TEXT NOT NULL DEFAULT '',
    file_url                TEXT NOT NULL DEFAULT '',
    duration_seconds        DOUBLE PRECISION NOT NULL DEFAULT 0,
    file_size_bytes         BIGINT NOT NULL DEFAULT 0,
    resolution              TEXT NOT NULL DEFAULT '1080x1920',
    render_time_seconds     DOUBLE PRECISION NOT NULL DEFAULT 0,

    -- YouTube upload
    youtube_short_id        TEXT DEFAULT NULL,
    youtube_url             TEXT DEFAULT NULL,
    privacy_status          TEXT DEFAULT NULL,

    -- Cost tracking
    cost_usd                NUMERIC(10, 6) NOT NULL DEFAULT 0,

    -- Error handling
    error_message           TEXT DEFAULT NULL,
    retry_count             INT NOT NULL DEFAULT 0,

    -- Timestamps
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_shorts_updated_at
    BEFORE UPDATE ON shorts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Index for finding all Shorts for a parent video
CREATE INDEX IF NOT EXISTS idx_shorts_parent_video_id
    ON shorts (parent_video_id);

-- Index for finding pending/failed Shorts for retry
CREATE INDEX IF NOT EXISTS idx_shorts_status
    ON shorts (status) WHERE status IN ('pending', 'failed');

-- Index for channel-level Short analytics
CREATE INDEX IF NOT EXISTS idx_shorts_channel_id
    ON shorts (channel_id);


-- ============================================================
-- 2. SHORTS PERFORMANCE (populated by analytics cron)
-- ============================================================

CREATE TABLE IF NOT EXISTS short_performance (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    short_id                UUID NOT NULL REFERENCES shorts(id) ON DELETE CASCADE UNIQUE,
    youtube_short_id        TEXT NOT NULL DEFAULT '',

    -- Metrics (updated periodically)
    view_count              BIGINT NOT NULL DEFAULT 0,
    like_count              BIGINT NOT NULL DEFAULT 0,
    comment_count           BIGINT NOT NULL DEFAULT 0,
    share_count             BIGINT NOT NULL DEFAULT 0,

    -- Funnel metrics — did the Short drive traffic to the parent?
    parent_video_click_through  BIGINT NOT NULL DEFAULT 0,

    -- Retention
    average_view_duration_seconds   DOUBLE PRECISION NOT NULL DEFAULT 0,
    average_view_percentage         DOUBLE PRECISION NOT NULL DEFAULT 0,

    last_fetched_at         TIMESTAMPTZ DEFAULT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_short_performance_updated_at
    BEFORE UPDATE ON short_performance
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- ============================================================
-- 3. CHANNEL-LEVEL SHORTS SETTINGS
-- ============================================================

CREATE TABLE IF NOT EXISTS channel_shorts_settings (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id              UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE UNIQUE,

    -- Enable/disable Shorts generation for this channel
    enabled                 BOOLEAN NOT NULL DEFAULT true,

    -- Max Shorts per parent video (2-3)
    max_shorts_per_video    INT NOT NULL DEFAULT 3
        CHECK (max_shorts_per_video BETWEEN 1 AND 5),

    -- Preferred duration type
    preferred_duration      TEXT NOT NULL DEFAULT '60s'
        CHECK (preferred_duration IN ('13s', '60s', 'auto')),

    -- Auto-upload Shorts to YouTube (or just render and hold)
    auto_upload             BOOLEAN NOT NULL DEFAULT false,

    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_channel_shorts_settings_updated_at
    BEFORE UPDATE ON channel_shorts_settings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
