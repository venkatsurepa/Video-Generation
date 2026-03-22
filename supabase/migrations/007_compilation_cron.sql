-- ============================================================
-- 006: Monthly compilation video scheduling via pg_cron
-- ============================================================
-- Runs on the 28th of each month at 06:00 UTC.
-- Inserts a compilation job into pipeline_jobs for each active channel.
-- The worker picks up the job and delegates to CompilationGenerator.
-- ============================================================

-- 1. Helper function to enqueue monthly compilations
CREATE OR REPLACE FUNCTION enqueue_monthly_compilations()
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    _channel RECORD;
    _month DATE := date_trunc('month', now())::date;
    _video_id UUID;
    _topic JSONB;
    _title TEXT;
BEGIN
    FOR _channel IN
        SELECT id, name FROM channels WHERE status = 'active'
    LOOP
        -- Skip if compilation already exists for this channel + month
        IF EXISTS (
            SELECT 1 FROM videos
            WHERE channel_id = _channel.id
              AND topic->>'type' = 'compilation'
              AND (topic->>'month')::date = _month
        ) THEN
            CONTINUE;
        END IF;

        _title := 'Best of ' || to_char(_month, 'FMMonth YYYY') || ' | ' || _channel.name;
        _topic := jsonb_build_object(
            'type', 'compilation',
            'theme', 'best_of',
            'month', _month::text
        );

        -- Create the video record
        INSERT INTO videos (channel_id, title, topic, status)
        VALUES (_channel.id, _title, _topic, 'pending')
        RETURNING id INTO _video_id;

        -- Enqueue a compilation pipeline job
        INSERT INTO pipeline_jobs (video_id, stage, payload, priority)
        VALUES (
            _video_id,
            'compilation_generation',
            jsonb_build_object(
                'channel_id', _channel.id::text,
                'month', _month::text,
                'theme', 'best_of'
            ),
            5  -- lower priority than regular videos
        );

        RAISE NOTICE 'Enqueued compilation for channel % (%) month %',
            _channel.name, _channel.id, _month;
    END LOOP;
END;
$$;


-- 2. Schedule: 28th of every month at 06:00 UTC
-- (pg_cron must be enabled on the Supabase instance)
SELECT cron.schedule(
    'monthly-compilation',
    '0 6 28 * *',
    $$ SELECT enqueue_monthly_compilations(); $$
);
