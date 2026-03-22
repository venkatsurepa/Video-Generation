-- 008_cross_platform.sql
-- Cross-platform distribution tracking: TikTok, IG Reels, FB Reels, Twitter.

CREATE TABLE IF NOT EXISTS cross_platform_distributions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    short_id        UUID REFERENCES shorts(id),
    video_id        UUID NOT NULL REFERENCES videos(id),
    platform        TEXT NOT NULL CHECK (platform IN (
                        'tiktok', 'instagram_reels', 'facebook_reels',
                        'youtube_community', 'twitter'
                    )),
    method          TEXT CHECK (method IN (
                        'repurpose_io', 'ayrshare', 'direct_api', 'scheduled'
                    )),
    post_id         TEXT DEFAULT '',
    post_url        TEXT DEFAULT '',
    status          TEXT CHECK (status IN (
                        'scheduled', 'queued', 'posted', 'failed', 'cancelled'
                    )) DEFAULT 'scheduled',
    scheduled_at    TIMESTAMPTZ,
    posted_at       TIMESTAMPTZ,
    views           INT DEFAULT 0,
    likes           INT DEFAULT 0,
    comments        INT DEFAULT 0,
    shares          INT DEFAULT 0,
    reach           INT DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),

    UNIQUE (short_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_dist_video
    ON cross_platform_distributions (video_id);

CREATE INDEX IF NOT EXISTS idx_dist_status
    ON cross_platform_distributions (status)
    WHERE status IN ('scheduled', 'queued');

CREATE INDEX IF NOT EXISTS idx_dist_platform
    ON cross_platform_distributions (platform, posted_at DESC);
