-- ============================================================
-- CrimeMill — Podcast Episodes Schema
-- ============================================================
-- Tracks podcast episodes published to Buzzsprout from finished
-- YouTube videos.  One video → zero or one podcast episode.
-- ============================================================

CREATE TABLE IF NOT EXISTS podcast_episodes (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id                UUID NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    buzzsprout_episode_id   INT,
    title                   TEXT NOT NULL DEFAULT '',
    description             TEXT NOT NULL DEFAULT '',
    audio_storage_path      TEXT,
    duration_seconds        DOUBLE PRECISION,
    file_size_bytes         BIGINT,
    rss_feed_url            TEXT,
    total_downloads         INT NOT NULL DEFAULT 0,
    status                  TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'published', 'failed', 'archived')),
    error_message           TEXT,
    published_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_podcast_video UNIQUE (video_id)
);

CREATE TRIGGER trg_podcast_episodes_updated_at
    BEFORE UPDATE ON podcast_episodes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Index for Buzzsprout episode lookups
CREATE INDEX IF NOT EXISTS idx_podcast_buzzsprout_id
    ON podcast_episodes (buzzsprout_episode_id)
    WHERE buzzsprout_episode_id IS NOT NULL;

-- Index for status-based queries (feed sync, retry logic)
CREATE INDEX IF NOT EXISTS idx_podcast_status
    ON podcast_episodes (status)
    WHERE status NOT IN ('published', 'archived');

-- RLS: service role only (no anon access to podcast data)
ALTER TABLE podcast_episodes ENABLE ROW LEVEL SECURITY;

CREATE POLICY podcast_service_all ON podcast_episodes
    FOR ALL
    USING (auth.role() = 'service_role')
    WITH CHECK (auth.role() = 'service_role');


-- ============================================================
-- SQL queries used by the podcast publisher service
-- ============================================================

-- Insert a new podcast episode record (called before Buzzsprout upload)
-- INSERT INTO podcast_episodes (video_id, title, status)
-- VALUES ($1, $2, 'processing')
-- RETURNING *;

-- Update after successful Buzzsprout upload
-- UPDATE podcast_episodes
-- SET buzzsprout_episode_id = $1,
--     audio_storage_path = $2,
--     duration_seconds = $3,
--     file_size_bytes = $4,
--     rss_feed_url = $5,
--     status = 'published',
--     published_at = now(),
--     updated_at = now()
-- WHERE video_id = $6;

-- Sync download stats (pg_cron weekly)
-- UPDATE podcast_episodes
-- SET total_downloads = $1,
--     updated_at = now()
-- WHERE buzzsprout_episode_id = $2;
