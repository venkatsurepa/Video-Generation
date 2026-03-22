"""Shared test fixtures for the CrimeMill backend test suite."""

from __future__ import annotations

import json
import os
import struct
import uuid
import wave
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Settings
from src.db.connection import create_pool
from src.main import create_app
from src.models.script import SceneBreakdown

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool

# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

_HAS_DB_URL = bool(os.environ.get("SUPABASE_DB_URL", ""))
_HAS_ANTHROPIC = bool(os.environ.get("ANTHROPIC_API_KEY", ""))
_HAS_FAL = bool(os.environ.get("FAL_AI_API_KEY", ""))
_HAS_FISH = bool(os.environ.get("FISH_AUDIO_API_KEY", ""))
_HAS_GROQ = bool(os.environ.get("GROQ_API_KEY", ""))

requires_db = pytest.mark.skipif(not _HAS_DB_URL, reason="SUPABASE_DB_URL not set")
requires_anthropic = pytest.mark.skipif(not _HAS_ANTHROPIC, reason="ANTHROPIC_API_KEY not set")
requires_fal = pytest.mark.skipif(not _HAS_FAL, reason="FAL_AI_API_KEY not set")
requires_fish = pytest.mark.skipif(not _HAS_FISH, reason="FISH_AUDIO_API_KEY not set")
requires_groq = pytest.mark.skipif(not _HAS_GROQ, reason="GROQ_API_KEY not set")

# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
async def db_pool(settings: Settings) -> AsyncIterator[AsyncConnectionPool]:
    if not settings.database.db_url:
        pytest.skip("SUPABASE_DB_URL not set")
    pool = await create_pool(settings.database.db_url, min_size=1, max_size=2)
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def db_conn(
    db_pool: AsyncConnectionPool,
) -> AsyncIterator[AsyncConnection[dict[str, object]]]:
    async with db_pool.connection() as conn:
        yield conn


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------

TEST_CHANNEL_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_VIDEO_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")


@pytest.fixture
async def test_channel(
    db_pool: AsyncConnectionPool,
) -> AsyncIterator[dict[str, Any]]:
    """Create a test channel in the DB and clean up afterwards."""
    channel_id = uuid.uuid4()
    async with db_pool.connection() as conn:
        cur = await conn.execute(
            """INSERT INTO channels (id, name, youtube_channel_id, handle, description)
               VALUES (%(id)s, %(name)s, %(yt_id)s, %(handle)s, %(desc)s)
               RETURNING *""",
            {
                "id": channel_id,
                "name": "Test Crime Channel",
                "yt_id": "UC_test_channel_123",
                "handle": "@testcrimechannel",
                "desc": "Test channel for automated pipeline testing",
            },
        )
        row = await cur.fetchone()
        assert row is not None
        await conn.commit()

    yield dict(row)

    async with db_pool.connection() as conn:
        await conn.execute("DELETE FROM channels WHERE id = %(id)s", {"id": channel_id})
        await conn.commit()


@pytest.fixture
async def test_video(
    db_pool: AsyncConnectionPool,
    test_channel: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Create a test video in the DB and clean up afterwards."""
    video_id = uuid.uuid4()
    topic = {
        "topic": "The disappearance of a hiker in Olympic National Park",
        "video_length_minutes": 15,
    }
    async with db_pool.connection() as conn:
        cur = await conn.execute(
            """INSERT INTO videos (id, channel_id, title, topic, status)
               VALUES (%(id)s, %(channel_id)s, %(title)s, %(topic)s, 'pending')
               RETURNING *""",
            {
                "id": video_id,
                "channel_id": test_channel["id"],
                "title": "Test Video",
                "topic": json.dumps(topic),
            },
        )
        row = await cur.fetchone()
        assert row is not None
        await conn.commit()

    yield dict(row)

    async with db_pool.connection() as conn:
        await conn.execute("DELETE FROM pipeline_jobs WHERE video_id = %(id)s", {"id": video_id})
        await conn.execute("DELETE FROM generation_costs WHERE video_id = %(id)s", {"id": video_id})
        await conn.execute("DELETE FROM videos WHERE id = %(id)s", {"id": video_id})
        await conn.commit()


@pytest.fixture
async def test_pipeline_job(
    db_pool: AsyncConnectionPool,
    test_video: dict[str, Any],
) -> AsyncIterator[dict[str, Any]]:
    """Create a pending pipeline job for testing."""
    async with db_pool.connection() as conn:
        cur = await conn.execute(
            """INSERT INTO pipeline_jobs (video_id, stage, payload, priority)
               VALUES (%(video_id)s, %(stage)s, %(payload)s, %(priority)s)
               RETURNING *""",
            {
                "video_id": test_video["id"],
                "stage": "script_generation",
                "payload": json.dumps({}),
                "priority": 0,
            },
        )
        row = await cur.fetchone()
        assert row is not None
        await conn.commit()

    yield dict(row)


# ---------------------------------------------------------------------------
# Test data: images, audio, scenes
# ---------------------------------------------------------------------------


@pytest.fixture
def test_image_path(tmp_path: Path) -> str:
    """Create a 100x100 RGB test image and return its path."""
    from PIL import Image

    img = Image.new("RGB", (100, 100), color=(128, 64, 32))
    path = tmp_path / "test_scene.jpg"
    img.save(str(path), "JPEG")
    return str(path)


@pytest.fixture
def test_image_1920x1080(tmp_path: Path) -> str:
    """Create a 1920x1080 test image for thumbnail/image processor tests."""
    from PIL import Image

    img = Image.new("RGB", (1920, 1080), color=(80, 40, 20))
    path = tmp_path / "test_scene_hd.jpg"
    img.save(str(path), "JPEG")
    return str(path)


@pytest.fixture
def test_audio_path(tmp_path: Path) -> str:
    """Create a 1-second silent WAV file for audio processor tests."""
    path = tmp_path / "test_silence.wav"
    sample_rate = 48000
    duration_seconds = 1
    n_samples = sample_rate * duration_seconds

    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_samples)

    return str(path)


@pytest.fixture
def test_audio_with_tone(tmp_path: Path) -> str:
    """Create a 2-second WAV with a 440Hz tone for loudness tests."""
    import math

    path = tmp_path / "test_tone.wav"
    sample_rate = 48000
    duration = 2
    n_samples = sample_rate * duration
    amplitude = 16000

    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = b""
        for i in range(n_samples):
            sample = int(amplitude * math.sin(2.0 * math.pi * 440.0 * i / sample_rate))
            frames += struct.pack("<h", sample)
        wf.writeframes(frames)

    return str(path)


@pytest.fixture
def sample_scenes() -> list[SceneBreakdown]:
    """Minimal SceneBreakdown list for testing downstream consumers."""
    return [
        SceneBreakdown(
            scene_number=1,
            start_time_seconds=0.0,
            end_time_seconds=60.0,
            narration_text="In the summer of 2019, a hiker vanished.",
            scene_description="Dark forest trail at dusk with fog",
            emotion_tag="tense",
            narration_speed="NORMAL",
        ),
        SceneBreakdown(
            scene_number=2,
            start_time_seconds=60.0,
            end_time_seconds=180.0,
            narration_text="Search teams combed the area for weeks.",
            scene_description="Search and rescue helicopter over mountains",
            emotion_tag="urgent",
            narration_speed="FAST",
        ),
        SceneBreakdown(
            scene_number=3,
            start_time_seconds=180.0,
            end_time_seconds=300.0,
            narration_text="But what they found changed everything.",
            scene_description="Close-up of evidence markers in clearing",
            emotion_tag="reveal",
            narration_speed="REVEAL",
            is_pattern_interrupt=True,
        ),
        SceneBreakdown(
            scene_number=4,
            start_time_seconds=300.0,
            end_time_seconds=450.0,
            narration_text="The investigation took a dark turn.",
            scene_description="Interrogation room with single overhead light",
            emotion_tag="dark",
            narration_speed="SLOW",
            is_ad_break=True,
        ),
        SceneBreakdown(
            scene_number=5,
            start_time_seconds=450.0,
            end_time_seconds=600.0,
            narration_text="And the truth was more disturbing than anyone imagined.",
            scene_description="Empty courtroom with gavel close-up",
            emotion_tag="somber",
            narration_speed="NORMAL",
        ),
    ]


@pytest.fixture
def mock_http_client() -> AsyncMock:
    """Create a mock httpx.AsyncClient for service tests."""
    return AsyncMock()


@pytest.fixture
def mock_r2_client() -> MagicMock:
    """Create a mock R2Client."""
    mock = MagicMock()
    mock.upload_file.return_value = "test-key"
    mock.download_file.return_value = "/tmp/test-file"
    mock.file_exists.return_value = True
    return mock
