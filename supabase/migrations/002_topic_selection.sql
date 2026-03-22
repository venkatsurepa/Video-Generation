-- ============================================================
-- CrimeMill — Topic Discovery & Competitor Tracking
-- ============================================================
-- Migration 002: tables for the five-layer topic selection pipeline.
--
-- discovered_topics:    scored topics from Google Trends, Reddit, GDELT
-- competitor_channels:  tracked YouTube channels for saturation checks
-- competitor_videos:    cached competitor video titles for fuzzy matching
-- ============================================================


-- ============================================================
-- 1. DISCOVERED TOPICS
-- ============================================================

CREATE TABLE IF NOT EXISTS discovered_topics (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title                   TEXT NOT NULL,
    description             TEXT,
    category                TEXT NOT NULL DEFAULT 'other',
    composite_score         NUMERIC(5, 2),
    score_breakdown         JSONB,
    source_signals          JSONB,
    competitor_saturation   NUMERIC(3, 2),
    priority                TEXT DEFAULT 'low'
        CHECK (priority IN ('immediate', 'this_week', 'low', 'archived')),
    used_in_video_id        UUID REFERENCES videos(id),
    discovered_at           TIMESTAMPTZ DEFAULT now(),
    expires_at              TIMESTAMPTZ DEFAULT now() + INTERVAL '30 days',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Primary query: unused topics ranked by score
CREATE INDEX IF NOT EXISTS idx_topics_priority
    ON discovered_topics (priority, composite_score DESC)
    WHERE used_in_video_id IS NULL;

-- Filter by category
CREATE INDEX IF NOT EXISTS idx_topics_category
    ON discovered_topics (category);

-- Expiry cleanup
CREATE INDEX IF NOT EXISTS idx_topics_expires
    ON discovered_topics (expires_at)
    WHERE used_in_video_id IS NULL AND priority != 'archived';


-- ============================================================
-- 2. COMPETITOR CHANNELS
-- ============================================================

CREATE TABLE IF NOT EXISTS competitor_channels (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    youtube_channel_id      TEXT UNIQUE NOT NULL,
    name                    TEXT NOT NULL,
    subscriber_count        INT,
    category                TEXT,
    last_scanned_at         TIMESTAMPTZ,
    is_active               BOOLEAN DEFAULT true,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- 3. COMPETITOR VIDEOS
-- ============================================================

CREATE TABLE IF NOT EXISTS competitor_videos (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competitor_channel_id   UUID REFERENCES competitor_channels(id),
    youtube_video_id        TEXT UNIQUE NOT NULL,
    title                   TEXT NOT NULL,
    published_at            TIMESTAMPTZ,
    view_count              INT DEFAULT 0,
    scanned_at              TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_competitor_videos_channel
    ON competitor_videos (competitor_channel_id, published_at DESC);


-- ============================================================
-- 4. SEED COMPETITOR CHANNELS
-- ============================================================
-- Top 15 crime/finance documentary channels from the bible.

INSERT INTO competitor_channels (youtube_channel_id, name, category) VALUES
    ('UCFNTq9XKHDNy_1-2lL9SVdQ', 'Coffeezilla',        'financial_crime'),
    ('UCAL3JXZSzUm6E-6GIq0Ntpw', 'ColdFusion',         'business_documentary'),
    ('UChmE0AZkeOYA3NxoF1wMStg', 'MagnatesMedia',       'business_documentary'),
    ('UC_zEzzq1-3wPTMTbBwVnFJg', 'James Jani',          'financial_crime'),
    ('UCnYrsaByosDrhFiMqLR0Y5g', 'Patrick Boyle',       'finance_education'),
    ('UCL_f53ZEJxp8TtlOkHwMV9Q', 'JCS - Criminal Psychology', 'criminal_psychology'),
    ('UC3sznuotAs2ohg_U2sOhbOw', 'Matt Orchard',         'criminal_psychology'),
    ('UCYwVxWpjeKFWwu8TML-Te9A', 'Disturban',            'true_crime'),
    ('UCPH0GaTbMuht8rIUgRC-xLQ', 'That Chapter',         'true_crime'),
    ('UC1xS-MNzUOv8dMasCgzJbQA', 'SomeOrdinaryGamers',   'internet_crime'),
    ('UCVYamHliCI9rw1tHR1xbkfw', 'Dave Lee',              'finance_education'),
    ('UCnQC_G5Xsjhp9fEJKuIcrSw', 'Ben Mallah',            'business_documentary'),
    ('UCFg3rN7_bHLuY7SZ0Dq-ePQ', 'Upper Echelon',         'internet_crime'),
    ('UCWFKCr40YwOZQx8FHU_ZqqQ', 'Bright Sun Films',      'business_documentary'),
    ('UC4V3oCikXeSqYQr0zBMkemg', 'Company Man',            'business_documentary')
ON CONFLICT (youtube_channel_id) DO NOTHING;


-- ============================================================
-- 5. RLS
-- ============================================================

ALTER TABLE discovered_topics    ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitor_channels  ENABLE ROW LEVEL SECURITY;
ALTER TABLE competitor_videos    ENABLE ROW LEVEL SECURITY;


-- ============================================================
-- 6. PG_CRON: Daily topic discovery
-- ============================================================
-- Triggers the topic discovery pipeline every day at 06:00 UTC.
-- The Edge Function / FastAPI endpoint handles the actual work.
--
-- To enable (run manually after deploying the endpoint):
--
-- SELECT cron.schedule('daily-topic-discovery', '0 6 * * *', $$
--     SELECT net.http_post(
--         url     := current_setting('app.settings.supabase_url', true)
--                    || '/functions/v1/discover-topics',
--         headers := jsonb_build_object(
--             'Content-Type', 'application/json',
--             'Authorization', 'Bearer ' || current_setting('app.settings.service_role_key', true)
--         )
--     )
-- $$);
--
-- Cleanup expired topics weekly:
--
-- SELECT cron.schedule('cleanup-expired-topics', '0 4 * * 1', $$
--     UPDATE discovered_topics
--     SET priority = 'archived'
--     WHERE expires_at < now()
--       AND used_in_video_id IS NULL
--       AND priority != 'archived'
-- $$);
