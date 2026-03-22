"""Seed development database with test channel and sample data.

Run: cd backend && python scripts/seed_dev_data.py

Requires SUPABASE_DB_URL in environment or .env file.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHANNEL_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CHANNEL_NAME = "CrimeMill Dev"

# Deterministic UUIDs for reproducible seeds
VIDEO_IDS = {
    "pending": uuid.UUID("22222222-2222-2222-2222-222222222201"),
    "script_generated": uuid.UUID("22222222-2222-2222-2222-222222222202"),
    "media_generating": uuid.UUID("22222222-2222-2222-2222-222222222203"),
    "assembled": uuid.UUID("22222222-2222-2222-2222-222222222204"),
    "published": uuid.UUID("22222222-2222-2222-2222-222222222205"),
}

TOPIC_IDS = [
    uuid.UUID("33333333-3333-3333-3333-333333333301"),
    uuid.UUID("33333333-3333-3333-3333-333333333302"),
    uuid.UUID("33333333-3333-3333-3333-333333333303"),
]


def _get_db_url() -> str:
    """Resolve DB URL from env or .env file."""
    import os

    url = os.environ.get("SUPABASE_DB_URL", "")
    if url:
        return url

    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("SUPABASE_DB_URL=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip().strip("'\"")
    return ""


async def seed(db_url: str) -> None:
    """Insert all seed data inside a single transaction."""
    now = datetime.now(timezone.utc)
    counts: dict[str, int] = {}

    async with await psycopg.AsyncConnection.connect(
        db_url, row_factory=dict_row
    ) as conn:
        async with conn.transaction():
            # ---------------------------------------------------------------
            # 1. Channel
            # ---------------------------------------------------------------
            await conn.execute(
                """INSERT INTO channels (id, name, youtube_channel_id, handle, description)
                   VALUES (%(id)s, %(name)s, %(yt)s, %(handle)s, %(desc)s)
                   ON CONFLICT (id) DO NOTHING""",
                {
                    "id": CHANNEL_ID,
                    "name": CHANNEL_NAME,
                    "yt": "UC_dev_channel_000",
                    "handle": "@crimemilldev",
                    "desc": "Development/test channel for the CrimeMill pipeline",
                },
            )
            counts["channels"] = 1

            # ---------------------------------------------------------------
            # 2. Channel settings (4 tables)
            # ---------------------------------------------------------------
            await conn.execute(
                """INSERT INTO channel_voice_settings
                       (channel_id, fish_audio_voice_id, voice_name,
                        narration_speed_wpm_default)
                   VALUES (%(ch)s, 'dev-voice-id', 'Dev Narrator', 155)
                   ON CONFLICT (channel_id) DO NOTHING""",
                {"ch": CHANNEL_ID},
            )
            await conn.execute(
                """INSERT INTO channel_brand_settings
                       (channel_id, color_palette, thumbnail_archetype,
                        font_family, cinematic_prompt_suffix)
                   VALUES (%(ch)s, %(palette)s, 'mugshot_drama',
                           'BebasNeue-Bold', 'cinematic color grading, anamorphic lens')
                   ON CONFLICT (channel_id) DO NOTHING""",
                {
                    "ch": CHANNEL_ID,
                    "palette": json.dumps(
                        {"primary": "#8B0000", "secondary": "#1a1a2e", "accent": "#e94560"}
                    ),
                },
            )
            await conn.execute(
                """INSERT INTO channel_generation_settings
                       (channel_id, target_video_length_minutes, target_word_count,
                        script_model, structured_model, images_per_video)
                   VALUES (%(ch)s, 15, 2200, 'claude-sonnet-4', 'claude-haiku-4-5', 20)
                   ON CONFLICT (channel_id) DO NOTHING""",
                {"ch": CHANNEL_ID},
            )
            await conn.execute(
                """INSERT INTO channel_credentials (channel_id)
                   VALUES (%(ch)s)
                   ON CONFLICT (channel_id) DO NOTHING""",
                {"ch": CHANNEL_ID},
            )
            counts["channel_settings"] = 4

            # ---------------------------------------------------------------
            # 3. Discovered topics (3)
            # ---------------------------------------------------------------
            topics = [
                {
                    "id": TOPIC_IDS[0],
                    "title": "The Vanishing of Flight MH370: New Evidence Surfaces",
                    "desc": "Malaysian authorities release previously classified radar data.",
                    "cat": "aviation",
                    "score": 87.5,
                    "priority": "immediate",
                },
                {
                    "id": TOPIC_IDS[1],
                    "title": "The Idaho Student Murders: Timeline Reconstruction",
                    "desc": "A detailed breakdown of the night four students were killed.",
                    "cat": "homicide",
                    "score": 82.1,
                    "priority": "this_week",
                },
                {
                    "id": TOPIC_IDS[2],
                    "title": "Inside the Sinaloa Cartel's Tunnel Network",
                    "desc": "DEA documents reveal 47 cross-border tunnels discovered since 2020.",
                    "cat": "organized_crime",
                    "score": 74.3,
                    "priority": "low",
                },
            ]
            for t in topics:
                await conn.execute(
                    """INSERT INTO discovered_topics
                           (id, title, description, category, composite_score,
                            priority, discovered_at)
                       VALUES (%(id)s, %(title)s, %(desc)s, %(cat)s, %(score)s,
                               %(priority)s, now())
                       ON CONFLICT (id) DO NOTHING""",
                    t,
                )
            counts["topics"] = len(topics)

            # ---------------------------------------------------------------
            # 4. Competitor channels (5)
            # ---------------------------------------------------------------
            competitors = [
                ("UCYwVxWpjeKFWwu8TML-Te9A", "JCS - Criminal Psychology", 6_200_000),
                ("UCaiJqh_MbFnf55B7tPKmuJw", "That Chapter", 5_100_000),
                ("UCsIg9WMfxjZZvwROleiVsQg", "Coffeehouse Crime", 3_800_000),
                ("UCLhgnMAdG2t0bDBxMjpUbAg", "Matt Orchard", 3_400_000),
                ("UCobkd3O_kILgrTz43Ip-sPg", "Explore With Us", 7_900_000),
            ]
            for yt_id, name, subs in competitors:
                await conn.execute(
                    """INSERT INTO competitor_channels
                           (youtube_channel_id, name, subscriber_count, category)
                       VALUES (%(yt)s, %(name)s, %(subs)s, 'true_crime')
                       ON CONFLICT (youtube_channel_id) DO NOTHING""",
                    {"yt": yt_id, "name": name, "subs": subs},
                )
            counts["competitors"] = len(competitors)

            # ---------------------------------------------------------------
            # 5. Sample videos (5 — one per pipeline status)
            # ---------------------------------------------------------------
            video_defs = [
                {
                    "id": VIDEO_IDS["pending"],
                    "status": "pending",
                    "title": None,
                    "topic": {"topic": "The Delphi Murders: New Trial Evidence", "video_length_minutes": 15},
                    "word_count": None,
                    "length_sec": None,
                    "yt_id": None,
                    "published_at": None,
                },
                {
                    "id": VIDEO_IDS["script_generated"],
                    "status": "script_generated",
                    "title": "The Hiker Who Vanished Without a Trace",
                    "topic": {"topic": "Olympic National Park disappearance", "video_length_minutes": 12},
                    "word_count": 1800,
                    "length_sec": None,
                    "yt_id": None,
                    "published_at": None,
                },
                {
                    "id": VIDEO_IDS["media_generating"],
                    "status": "media_generating",
                    "title": "Caught on Camera: The Night Stalker's Final Hours",
                    "topic": {"topic": "Night Stalker investigation", "video_length_minutes": 18},
                    "word_count": 2600,
                    "length_sec": None,
                    "yt_id": None,
                    "published_at": None,
                },
                {
                    "id": VIDEO_IDS["assembled"],
                    "status": "assembled",
                    "title": "The Cold Case That Shocked a Small Town",
                    "topic": {"topic": "Small-town cold case reopened", "video_length_minutes": 14},
                    "word_count": 2100,
                    "length_sec": 840,
                    "yt_id": None,
                    "published_at": None,
                },
                {
                    "id": VIDEO_IDS["published"],
                    "status": "published",
                    "title": "Inside the FBI's Most Wanted: The Fugitive Next Door",
                    "topic": {"topic": "FBI fugitive captured after 20 years", "video_length_minutes": 16},
                    "word_count": 2400,
                    "length_sec": 960,
                    "yt_id": "dQw4w9WgXcQ",
                    "published_at": now - timedelta(days=3),
                },
            ]
            for v in video_defs:
                await conn.execute(
                    """INSERT INTO videos
                           (id, channel_id, title, status, topic,
                            script_word_count, video_length_seconds,
                            youtube_video_id, published_at)
                       VALUES (%(id)s, %(ch)s, %(title)s, %(status)s, %(topic)s,
                               %(wc)s, %(len)s, %(yt)s, %(pub)s)
                       ON CONFLICT (id) DO NOTHING""",
                    {
                        "id": v["id"],
                        "ch": CHANNEL_ID,
                        "title": v["title"],
                        "status": v["status"],
                        "topic": json.dumps(v["topic"]),
                        "wc": v["word_count"],
                        "len": v["length_sec"],
                        "yt": v["yt_id"],
                        "pub": v["published_at"],
                    },
                )
            counts["videos"] = len(video_defs)

            # ---------------------------------------------------------------
            # 6. Music library entries (3 — schema test only, no real files)
            # ---------------------------------------------------------------
            music_entries = [
                {
                    "video_id": VIDEO_IDS["assembled"],
                    "source": "epidemic_sound",
                    "track_name": "Dark Horizon",
                    "mood_category": "tension",
                    "bpm": 90,
                    "duration_seconds": 180.0,
                    "status": "completed",
                },
                {
                    "video_id": VIDEO_IDS["published"],
                    "source": "epidemic_sound",
                    "track_name": "Shadows in the Rain",
                    "mood_category": "somber",
                    "bpm": 72,
                    "duration_seconds": 240.0,
                    "status": "completed",
                },
            ]
            for m in music_entries:
                await conn.execute(
                    """INSERT INTO music_selections
                           (video_id, source, track_name, mood_category,
                            bpm, duration_seconds, status)
                       VALUES (%(video_id)s, %(source)s, %(track_name)s,
                               %(mood_category)s, %(bpm)s, %(duration_seconds)s,
                               %(status)s)
                       ON CONFLICT (video_id) DO NOTHING""",
                    m,
                )
            counts["music_selections"] = len(music_entries)

            # ---------------------------------------------------------------
            # 7. Generation costs for the published video (realistic breakdown)
            # ---------------------------------------------------------------
            cost_entries = [
                ("script_generation", "anthropic", "claude-sonnet-4", 0.0312),
                ("voiceover_generation", "fish_audio", "fish-s2", 0.1840),
                ("image_generation", "fal_ai", "flux-pro", 0.8000),
                ("music_selection", "epidemic_sound", "library", 0.0000),
                ("audio_processing", "local", "ffmpeg", 0.0000),
                ("image_processing", "local", "pillow", 0.0000),
                ("caption_generation", "groq", "whisper-large-v3", 0.0107),
                ("video_assembly", "remotion", "lambda", 0.1100),
                ("thumbnail_generation", "fal_ai", "flux-pro", 0.0550),
            ]
            for stage, provider, model, cost in cost_entries:
                await conn.execute(
                    """INSERT INTO generation_costs
                           (video_id, stage, provider, model, cost_usd)
                       VALUES (%(vid)s, %(stage)s, %(prov)s, %(model)s, %(cost)s)""",
                    {
                        "vid": VIDEO_IDS["published"],
                        "stage": stage,
                        "prov": provider,
                        "model": model,
                        "cost": cost,
                    },
                )
            counts["generation_costs"] = len(cost_entries)

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n  Seed data inserted successfully!\n")
    for table, count in counts.items():
        print(f"    {table:<25} {count} rows")
    total = sum(counts.values())
    print(f"\n    {'TOTAL':<25} {total} rows")
    print(f"\n  Channel ID: {CHANNEL_ID}")
    print(f"  Video IDs:  {', '.join(str(v)[:8] + '...' for v in VIDEO_IDS.values())}")
    print()


def main() -> None:
    db_url = _get_db_url()
    if not db_url:
        print("Error: SUPABASE_DB_URL not set. Set it in environment or .env file.")
        sys.exit(1)

    print(f"\n  Seeding database: {db_url[:40]}...")
    asyncio.run(seed(db_url))


if __name__ == "__main__":
    main()
