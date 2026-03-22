-- 005_scheduling.sql
-- Content scheduling system: publish calendar, network grid, human review queue.

CREATE TABLE IF NOT EXISTS publish_schedule (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id        UUID UNIQUE REFERENCES videos(id),
    channel_id      UUID NOT NULL REFERENCES channels(id),
    scheduled_publish_at TIMESTAMPTZ NOT NULL,
    actual_published_at  TIMESTAMPTZ,
    reviewer_id     UUID,
    reviewer_notes  TEXT,
    approved_at     TIMESTAMPTZ,
    status          TEXT CHECK (status IN (
                        'scheduled', 'publishing', 'published', 'cancelled'
                    )) DEFAULT 'scheduled',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS channel_schedule_config (
    channel_id          UUID PRIMARY KEY REFERENCES channels(id),
    grid_slots          JSONB NOT NULL DEFAULT '[]'::jsonb,
    max_videos_per_week INT DEFAULT 5,
    auto_publish        BOOLEAN DEFAULT false,
    timezone            TEXT DEFAULT 'America/Chicago',
    q4_boost_enabled    BOOLEAN DEFAULT true,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_schedule_channel_date
    ON publish_schedule (channel_id, scheduled_publish_at);

CREATE INDEX IF NOT EXISTS idx_schedule_status
    ON publish_schedule (status) WHERE status = 'scheduled';
