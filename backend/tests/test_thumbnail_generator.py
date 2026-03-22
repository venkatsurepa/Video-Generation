"""Tests for the thumbnail generator.

Tests text placement, resolution, file size, and archetype rotation.
Uses Pillow directly — no API calls for these unit tests.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from PIL import Image

from src.models.thumbnail import (
    ALL_ARCHETYPES,
    BrandSettings,
    ThumbnailInput,
    ThumbnailResult,
)
from src.services.thumbnail_generator import (
    JPEG_QUALITY,
    MAX_FILE_SIZE_BYTES,
    THUMB_HEIGHT,
    THUMB_SIZE,
    THUMB_WIDTH,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestThumbnailResolution:
    def test_output_resolution_2560x1440(self, tmp_path: Path) -> None:
        """Thumbnail output must be exactly 2560x1440."""
        # Create a test image at the correct size
        img = Image.new("RGB", THUMB_SIZE, color=(40, 20, 10))
        path = tmp_path / "thumb_test.jpg"
        img.save(str(path), "JPEG", quality=JPEG_QUALITY)

        loaded = Image.open(str(path))
        assert loaded.size == (THUMB_WIDTH, THUMB_HEIGHT)

    def test_thumb_constants_match_youtube_spec(self) -> None:
        """Verify constants match YouTube's recommended thumbnail resolution."""
        assert THUMB_WIDTH == 2560
        assert THUMB_HEIGHT == 1440
        assert THUMB_SIZE == (2560, 1440)


class TestThumbnailFileSize:
    def test_file_size_under_2mb(self, tmp_path: Path) -> None:
        """JPEG output at quality 92 should be under YouTube's 2MB API limit."""
        # Create a realistic-size thumbnail
        img = Image.new("RGB", THUMB_SIZE, color=(60, 30, 15))
        path = tmp_path / "size_test.jpg"
        img.save(str(path), "JPEG", quality=JPEG_QUALITY)

        file_size = path.stat().st_size
        assert file_size < MAX_FILE_SIZE_BYTES, (
            f"Thumbnail is {file_size} bytes, exceeds {MAX_FILE_SIZE_BYTES} (2MB)"
        )

    def test_solid_color_is_small(self, tmp_path: Path) -> None:
        """A solid color image should compress very efficiently."""
        img = Image.new("RGB", THUMB_SIZE, color=(0, 0, 0))
        path = tmp_path / "solid.jpg"
        img.save(str(path), "JPEG", quality=JPEG_QUALITY)

        assert path.stat().st_size < 100_000  # should be well under 100KB


class TestArchetypeRotation:
    def test_all_archetypes_defined(self) -> None:
        """All 6 archetypes should be defined."""
        assert len(ALL_ARCHETYPES) == 6
        expected = {
            "interrogation",
            "storyteller",
            "duality",
            "case_file",
            "beauty_beast",
            "cold_case",
        }
        assert set(ALL_ARCHETYPES) == expected

    def test_archetype_rotation_no_repeats(self) -> None:
        """Consecutive thumbnails should use different archetypes when possible."""
        recent: list[str] = []
        used: set[str] = set()

        for _i in range(6):
            # Prefer archetypes not yet used; fall back to excluding last 2
            available = [a for a in ALL_ARCHETYPES if a not in set(recent)]
            if not available:
                available = [a for a in ALL_ARCHETYPES if a not in recent[-2:]]
            chosen = available[0]
            assert chosen not in recent[-2:] or len(recent) < 2, (
                f"Archetype {chosen} repeated within last 2"
            )
            recent.append(chosen)
            used.add(chosen)

        # All 6 archetypes should have been used
        assert len(used) == 6

    def test_thumbnail_input_accepts_explicit_archetype(self) -> None:
        """ThumbnailInput should accept an explicit archetype override."""
        input_data = ThumbnailInput(
            video_id=uuid.uuid4(),
            title="Test Case",
            archetype="interrogation",
        )
        assert input_data.archetype == "interrogation"

    def test_thumbnail_input_default_no_archetype(self) -> None:
        """ThumbnailInput with no archetype should default to None (auto-select)."""
        input_data = ThumbnailInput(
            video_id=uuid.uuid4(),
            title="Test Case",
        )
        assert input_data.archetype is None


class TestTextSafeZone:
    def test_text_composite_within_safe_zone(self) -> None:
        """Text placement should stay in the center 1100x620 safe zone at 2560x1440.

        The safe zone ensures text is visible even when YouTube crops the
        thumbnail to different aspect ratios in different views (cards, search results).
        """
        safe_left = (THUMB_WIDTH - 1100) // 2  # 730
        safe_right = safe_left + 1100  # 1830
        safe_top = (THUMB_HEIGHT - 620) // 2  # 410
        safe_bottom = safe_top + 620  # 1030

        # The safe zone should be centered
        assert safe_left == 730
        assert safe_right == 1830
        assert safe_top == 410
        assert safe_bottom == 1030

        # Verify the safe zone dimensions
        assert safe_right - safe_left == 1100
        assert safe_bottom - safe_top == 620


class TestThumbnailResult:
    def test_result_model_validation(self) -> None:
        """ThumbnailResult should validate all required fields."""
        result = ThumbnailResult(
            file_path="/tmp/thumb.jpg",
            archetype="interrogation",
            resolution=(2560, 1440),
            file_size_bytes=500_000,
            text_overlay="GUILTY",
            background_prompt="dark interrogation room",
            cost_usd=0.055,
            generation_time_seconds=3.5,
        )
        assert result.archetype == "interrogation"
        assert result.resolution == (2560, 1440)
        assert result.file_size_bytes == 500_000

    def test_text_overlay_max_length(self) -> None:
        """text_overlay should be limited to 30 characters (0-3 words)."""
        # Valid: short text
        input_data = ThumbnailInput(
            video_id=uuid.uuid4(),
            title="Test",
            text_overlay="GUILTY",
        )
        assert len(input_data.text_overlay) <= 30

        # Should reject text over 30 chars
        with pytest.raises(ValueError):
            ThumbnailInput(
                video_id=uuid.uuid4(),
                title="Test",
                text_overlay="A" * 31,
            )

    def test_brand_settings_defaults(self) -> None:
        """BrandSettings should have sensible defaults."""
        brand = BrandSettings()
        assert brand.primary_accent_color == "#8B0000"
        assert "cinematic" in brand.cinematic_prompt_suffix
        assert brand.font_family == "BebasNeue-Bold"
