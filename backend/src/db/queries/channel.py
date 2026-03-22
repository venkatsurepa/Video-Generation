from __future__ import annotations

__all__ = [
    "INSERT_CHANNEL",
    "LIST_CHANNELS",
    "GET_CHANNEL",
    "GET_CHANNEL_WITH_STATS",
    "UPDATE_CHANNEL_SETTINGS",
    "INSERT_CHANNEL_VOICE_SETTINGS",
    "INSERT_CHANNEL_BRAND_SETTINGS",
    "INSERT_CHANNEL_CREDENTIALS",
    "INSERT_CHANNEL_GENERATION_SETTINGS",
    "UPDATE_CHANNEL_CREDENTIALS_OAUTH",
    "UPDATE_CHANNEL_VOICE",
    "GET_CHANNEL_CREDENTIALS",
    "GET_CHANNEL_VOICE_SETTINGS",
    "LIST_CHANNELS_WITH_STATS",
    "GET_CHANNEL_BY_HANDLE",
    "COUNT_CHANNELS",
]

INSERT_CHANNEL: str = """
INSERT INTO channels (name, youtube_channel_id, handle, description)
VALUES (%(name)s, %(youtube_channel_id)s, %(handle)s, %(description)s)
RETURNING *;
"""

LIST_CHANNELS: str = """
SELECT id, name, youtube_channel_id, handle, description, status, created_at, updated_at
FROM channels
ORDER BY created_at DESC
LIMIT %(limit)s OFFSET %(offset)s;
"""

GET_CHANNEL: str = """
SELECT id, name, youtube_channel_id, handle, description, status, created_at, updated_at
FROM channels
WHERE id = %(channel_id)s;
"""

GET_CHANNEL_WITH_STATS: str = """
SELECT
    c.id, c.name, c.youtube_channel_id, c.handle, c.description,
    c.status, c.created_at, c.updated_at,
    COUNT(v.id)                                             AS total_videos,
    COUNT(*) FILTER (WHERE v.status = 'published')          AS published_videos,
    COALESCE(SUM(gc.cost_usd), 0)                           AS total_cost_usd
FROM channels c
LEFT JOIN videos v ON v.channel_id = c.id
LEFT JOIN generation_costs gc ON gc.video_id = v.id
WHERE c.id = %(channel_id)s
GROUP BY c.id;
"""

UPDATE_CHANNEL_SETTINGS: str = """
UPDATE channels
SET name = COALESCE(%(name)s, name),
    description = COALESCE(%(description)s, description),
    handle = COALESCE(%(handle)s, handle),
    updated_at = now()
WHERE id = %(channel_id)s
RETURNING *;
"""

INSERT_CHANNEL_VOICE_SETTINGS: str = """
INSERT INTO channel_voice_settings (channel_id, fish_audio_voice_id, voice_name)
VALUES (%(channel_id)s, %(voice_id)s, %(voice_name)s)
ON CONFLICT (channel_id) DO UPDATE SET
    fish_audio_voice_id = EXCLUDED.fish_audio_voice_id,
    voice_name = EXCLUDED.voice_name,
    updated_at = now()
RETURNING *;
"""

INSERT_CHANNEL_BRAND_SETTINGS: str = """
INSERT INTO channel_brand_settings
    (channel_id, color_palette, thumbnail_archetype, font_family, cinematic_prompt_suffix)
VALUES
    (%(channel_id)s, %(color_palette)s, %(thumbnail_archetype)s,
     %(font_family)s, %(cinematic_prompt_suffix)s)
ON CONFLICT (channel_id) DO UPDATE SET
    color_palette = EXCLUDED.color_palette,
    thumbnail_archetype = EXCLUDED.thumbnail_archetype,
    font_family = EXCLUDED.font_family,
    cinematic_prompt_suffix = EXCLUDED.cinematic_prompt_suffix,
    updated_at = now()
RETURNING *;
"""

INSERT_CHANNEL_CREDENTIALS: str = """
INSERT INTO channel_credentials (channel_id)
VALUES (%(channel_id)s)
ON CONFLICT (channel_id) DO NOTHING
RETURNING *;
"""

INSERT_CHANNEL_GENERATION_SETTINGS: str = """
INSERT INTO channel_generation_settings (channel_id)
VALUES (%(channel_id)s)
ON CONFLICT (channel_id) DO NOTHING
RETURNING *;
"""

UPDATE_CHANNEL_CREDENTIALS_OAUTH: str = """
UPDATE channel_credentials
SET youtube_oauth_refresh_token_encrypted = %(refresh_token)s,
    updated_at = now()
WHERE channel_id = %(channel_id)s
RETURNING *;
"""

UPDATE_CHANNEL_VOICE: str = """
UPDATE channel_voice_settings
SET fish_audio_voice_id = %(voice_id)s,
    voice_name = %(voice_name)s,
    updated_at = now()
WHERE channel_id = %(channel_id)s
RETURNING *;
"""

GET_CHANNEL_CREDENTIALS: str = """
SELECT youtube_oauth_refresh_token_encrypted
FROM channel_credentials
WHERE channel_id = %(channel_id)s;
"""

GET_CHANNEL_VOICE_SETTINGS: str = """
SELECT fish_audio_voice_id, voice_name, emotion_preset, narration_speed_wpm_default
FROM channel_voice_settings
WHERE channel_id = %(channel_id)s;
"""

LIST_CHANNELS_WITH_STATS: str = """
SELECT
    c.id, c.name, c.youtube_channel_id, c.handle, c.description,
    c.status, c.created_at, c.updated_at,
    COUNT(v.id)                                             AS total_videos,
    COUNT(*) FILTER (WHERE v.status = 'published')          AS published_videos,
    COALESCE(SUM(gc.cost_usd), 0)                           AS total_cost_usd
FROM channels c
LEFT JOIN videos v ON v.channel_id = c.id
LEFT JOIN generation_costs gc ON gc.video_id = v.id
GROUP BY c.id
ORDER BY c.created_at DESC;
"""

GET_CHANNEL_BY_HANDLE: str = """
SELECT id, name, youtube_channel_id, handle, description, status, created_at, updated_at
FROM channels
WHERE handle = %(handle)s;
"""

COUNT_CHANNELS: str = """
SELECT COUNT(*) AS total FROM channels;
"""
