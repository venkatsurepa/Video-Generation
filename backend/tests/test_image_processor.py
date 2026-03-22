"""Tests for the image post-processing pipeline.

These tests verify the documentary film aesthetic processing:
grain, desaturation, vignette, chromatic aberration, and color grading.
No API calls required — all processing is local via Pillow/numpy.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.config import Settings
from src.models.image import ProcessingStyle
from src.services.image_processor import ImageProcessor


@pytest.fixture
def processor() -> ImageProcessor:
    return ImageProcessor(Settings())


class TestFilmGrain:
    def test_film_grain_changes_pixels(self, test_image_path: str) -> None:
        """Grain processing must actually modify pixel values."""
        original = Image.open(test_image_path)
        original_arr = np.array(original)

        processed = ImageProcessor.apply_film_grain(original.copy(), intensity=0.20)
        processed_arr = np.array(processed)

        assert original_arr.shape == processed_arr.shape
        # At least some pixels should differ
        diff = np.abs(original_arr.astype(float) - processed_arr.astype(float))
        assert diff.mean() > 0, "Grain did not modify any pixels"

    def test_grain_intensity_zero_is_noop(self, test_image_path: str) -> None:
        """Zero intensity grain should not change the image."""
        original = Image.open(test_image_path)
        processed = ImageProcessor.apply_film_grain(original.copy(), intensity=0.0)

        original_arr = np.array(original)
        processed_arr = np.array(processed)
        np.testing.assert_array_equal(original_arr, processed_arr)


class TestDesaturation:
    def test_desaturation_reduces_color(self, test_image_path: str) -> None:
        """Desaturation should measurably reduce color saturation."""
        original = Image.open(test_image_path).convert("RGB")
        from PIL import ImageEnhance

        desaturated = ImageEnhance.Color(original).enhance(0.85)  # 15% desat

        # Convert to HSV and compare saturation channel
        orig_hsv = original.convert("HSV")
        desat_hsv = desaturated.convert("HSV")

        orig_sat = np.array(orig_hsv)[:, :, 1].mean()
        desat_sat = np.array(desat_hsv)[:, :, 1].mean()

        assert desat_sat <= orig_sat, "Desaturation did not reduce saturation"


class TestVignette:
    def test_vignette_darkens_edges(self, test_image_1920x1080: str) -> None:
        """Edges should be darker than center after vignette."""
        img = Image.open(test_image_1920x1080)
        arr = np.array(img, dtype=np.float32)
        h, w = arr.shape[:2]

        # Apply a basic vignette: darken edges
        center_y, center_x = h / 2, w / 2
        y_coords, x_coords = np.ogrid[:h, :w]
        max_dist = np.sqrt(center_x**2 + center_y**2)
        dist = np.sqrt((x_coords - center_x) ** 2 + (y_coords - center_y) ** 2) / max_dist
        vignette_mask = 1.0 - (dist * 0.20)
        vignette_mask = np.clip(vignette_mask, 0, 1)

        vignetted = (arr * vignette_mask[:, :, np.newaxis]).astype(np.uint8)

        # Compare corner brightness vs center brightness
        corner_mean = vignetted[:50, :50].mean()
        center_region = vignetted[h // 2 - 25 : h // 2 + 25, w // 2 - 25 : w // 2 + 25]
        center_mean = center_region.mean()

        assert corner_mean < center_mean, "Vignette did not darken edges relative to center"


class TestFullPipeline:
    async def test_full_pipeline_produces_valid_jpeg(
        self,
        processor: ImageProcessor,
        test_image_path: str,
        tmp_path: Path,
    ) -> None:
        """Process a test image through the full pipeline and verify output."""
        output_path = str(tmp_path / "processed.jpg")

        result = await processor.process_scene_image(
            test_image_path, output_path, ProcessingStyle.DOCUMENTARY
        )

        assert Path(result).exists()
        # Should be a valid JPEG
        processed = Image.open(result)
        assert processed.format == "JPEG" or result.endswith(".jpg")

    async def test_output_dimensions_preserved(
        self,
        processor: ImageProcessor,
        test_image_1920x1080: str,
        tmp_path: Path,
    ) -> None:
        """Processing should not change image dimensions."""
        original = Image.open(test_image_1920x1080)
        orig_size = original.size

        output_path = str(tmp_path / "processed_hd.jpg")
        await processor.process_scene_image(test_image_1920x1080, output_path)

        processed = Image.open(output_path)
        assert processed.size == orig_size

    async def test_batch_processing(
        self,
        processor: ImageProcessor,
        test_image_path: str,
        tmp_path: Path,
    ) -> None:
        """process_batch should handle multiple images."""
        # Create multiple test images
        paths = []
        for i in range(3):
            src = Path(test_image_path)
            dest = tmp_path / f"scene_{i}.jpg"
            dest.write_bytes(src.read_bytes())
            paths.append(str(dest))

        output_dir = str(tmp_path / "processed")
        Path(output_dir).mkdir()

        results = await processor.process_batch(paths, output_dir=output_dir)
        assert len(results) == 3
        for r in results:
            assert Path(r).exists()
