-- ============================================================
-- 007: Localization support — multi-language video pipeline
-- ============================================================
-- Adds parent_video_id and language to videos, plus a config
-- table mapping source channels to target language channels.
-- ============================================================

-- 1. Add localization columns to videos
ALTER TABLE videos
    ADD COLUMN IF NOT EXISTS parent_video_id UUID REFERENCES videos(id),
    ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT 'en';

-- Index for finding all localizations of a source video
CREATE INDEX IF NOT EXISTS idx_videos_parent_video_id
    ON videos (parent_video_id)
    WHERE parent_video_id IS NOT NULL;

-- Index for filtering by language
CREATE INDEX IF NOT EXISTS idx_videos_language
    ON videos (language);


-- 2. Localization config table
CREATE TABLE IF NOT EXISTS localization_config (
    source_channel_id   UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    target_channel_id   UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    target_language      TEXT NOT NULL,
    voice_id            TEXT NOT NULL,
    font_family         TEXT,
    auto_localize       BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_channel_id, target_language)
);

-- Prevent a channel from targeting itself
ALTER TABLE localization_config
    ADD CONSTRAINT localization_config_no_self_ref
    CHECK (source_channel_id != target_channel_id);

-- Index for reverse lookups (find all sources for a target channel)
CREATE INDEX IF NOT EXISTS idx_localization_config_target
    ON localization_config (target_channel_id);


-- 3. Trigger: auto-enqueue localization jobs after English publish
CREATE OR REPLACE FUNCTION on_video_published_localize()
RETURNS TRIGGER AS $$
DECLARE
    _config RECORD;
    _new_video_id UUID;
    _topic JSONB;
BEGIN
    -- Only fire when status transitions TO 'published'
    IF NEW.status = 'published'
       AND (OLD.status IS NULL OR OLD.status != 'published')
       AND NEW.language = 'en'
       AND NEW.parent_video_id IS NULL  -- skip localizations of localizations
    THEN
        FOR _config IN
            SELECT target_channel_id, target_language, voice_id
            FROM localization_config
            WHERE source_channel_id = NEW.channel_id
              AND auto_localize = true
        LOOP
            _topic := COALESCE(NEW.topic, '{}'::jsonb)
                || jsonb_build_object(
                    'localized_from', NEW.id::text,
                    'language', _config.target_language
                );

            -- Create the localized video record
            INSERT INTO videos (
                channel_id, title, description, tags, topic,
                status, parent_video_id, language
            )
            VALUES (
                _config.target_channel_id,
                NEW.title,  -- placeholder; localizer will translate
                NEW.description,
                NEW.tags,
                _topic,
                'pending',
                NEW.id,
                _config.target_language
            )
            RETURNING id INTO _new_video_id;

            -- Enqueue localization pipeline job
            INSERT INTO pipeline_jobs (video_id, stage, payload, priority)
            VALUES (
                _new_video_id,
                'localization',
                jsonb_build_object(
                    'source_video_id', NEW.id::text,
                    'target_language', _config.target_language,
                    'target_channel_id', _config.target_channel_id::text,
                    'voice_id', _config.voice_id
                ),
                5  -- lower priority than main pipeline
            );
        END LOOP;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach trigger (fires on UPDATE only — publish is an update to status)
DROP TRIGGER IF EXISTS trg_video_published_localize ON videos;
CREATE TRIGGER trg_video_published_localize
    AFTER UPDATE ON videos
    FOR EACH ROW
    EXECUTE FUNCTION on_video_published_localize();
