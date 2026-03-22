-- 007_community.sql — Community ecosystem tables
-- Topic submissions from Discord / Google Forms / manual entry
-- Patreon member sync for early access, credits, and metrics

-- ---------------------------------------------------------------------------
-- Topic submissions
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS topic_submissions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT CHECK (source IN ('google_forms', 'discord', 'youtube_comment', 'manual')),
    submitter_name  TEXT,
    submitter_contact TEXT,  -- discord handle, email, etc.
    case_name       TEXT NOT NULL,
    description     TEXT,
    why_interesting TEXT,
    source_links    TEXT[],
    score           NUMERIC(5,2),  -- from topic selector
    status          TEXT CHECK (status IN ('new', 'reviewed', 'accepted', 'rejected', 'produced'))
                         DEFAULT 'new',
    assigned_topic_id UUID,
    assigned_video_id UUID REFERENCES videos(id),
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Fast lookup for unreviewed submissions
CREATE INDEX IF NOT EXISTS idx_submissions_status
    ON topic_submissions (status) WHERE status = 'new';

-- Deduplication: find existing submissions by case name
CREATE INDEX IF NOT EXISTS idx_submissions_case_name
    ON topic_submissions USING gin (to_tsvector('english', case_name));

-- ---------------------------------------------------------------------------
-- Patreon members
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS patreon_members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patreon_id      TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    email           TEXT,
    tier_name       TEXT,
    tier_amount_cents INT,
    is_active       BOOLEAN DEFAULT true,
    show_in_credits BOOLEAN DEFAULT true,
    last_synced_at  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Active patrons for credit generation and early access
CREATE INDEX IF NOT EXISTS idx_patreon_active
    ON patreon_members (is_active) WHERE is_active = true;

-- Lookup by tier for tiered perks
CREATE INDEX IF NOT EXISTS idx_patreon_tier
    ON patreon_members (tier_name) WHERE is_active = true;
