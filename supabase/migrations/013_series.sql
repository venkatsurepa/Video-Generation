-- ============================================================
-- 010_series.sql — Series and season planning system
-- ============================================================
-- Multi-episode narrative arcs, cross-video hooks, YouTube playlists.
-- Supports: multi-part investigations, thematic seasons, ongoing arcs.
-- ============================================================


-- ---------------------------------------------------------------------------
-- series — top-level series record
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS series (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title               TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    channel_id          UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    series_type         TEXT NOT NULL CHECK (series_type IN (
                            'multi_part', 'thematic_season', 'ongoing_arc'
                        )) DEFAULT 'multi_part',
    planned_episodes    INT NOT NULL DEFAULT 3
                        CHECK (planned_episodes >= 1 AND planned_episodes <= 52),
    youtube_playlist_id TEXT,
    arc_plan            JSONB,
    status              TEXT NOT NULL CHECK (status IN (
                            'planning', 'in_production', 'active', 'completed'
                        )) DEFAULT 'planning',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_series_updated_at
    BEFORE UPDATE ON series
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_series_channel
    ON series (channel_id);

CREATE INDEX IF NOT EXISTS idx_series_status
    ON series (status) WHERE status IN ('planning', 'in_production', 'active');


-- ---------------------------------------------------------------------------
-- series_episodes — per-episode metadata and cross-video hooks
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS series_episodes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    series_id           UUID NOT NULL REFERENCES series(id) ON DELETE CASCADE,
    episode_number      INT NOT NULL CHECK (episode_number >= 1),
    video_id            UUID REFERENCES videos(id) ON DELETE SET NULL,
    title               TEXT NOT NULL DEFAULT '',
    core_question       TEXT NOT NULL DEFAULT '',
    key_revelation      TEXT NOT NULL DEFAULT '',
    open_loop_forward   TEXT NOT NULL DEFAULT '',
    recap_narration     TEXT NOT NULL DEFAULT '',
    teaser_narration    TEXT NOT NULL DEFAULT '',
    end_screen_cta      TEXT NOT NULL DEFAULT '',
    cross_links         JSONB NOT NULL DEFAULT '[]'::jsonb,
    status              TEXT NOT NULL CHECK (status IN (
                            'planned', 'scripted', 'produced', 'published'
                        )) DEFAULT 'planned',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (series_id, episode_number)
);

CREATE TRIGGER trg_series_episodes_updated_at
    BEFORE UPDATE ON series_episodes
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_series_episodes_series
    ON series_episodes (series_id);

CREATE INDEX IF NOT EXISTS idx_series_episodes_video
    ON series_episodes (video_id) WHERE video_id IS NOT NULL;
