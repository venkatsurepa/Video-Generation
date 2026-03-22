from __future__ import annotations

import asyncio
import math
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import structlog
from PIL import Image, ImageEnhance, ImageFilter

from src.models.image import ColorGrade, ProcessingParams, ProcessingStyle

if TYPE_CHECKING:
    from src.config import Settings

logger = structlog.get_logger()

# Documentary preset: grain → desaturate → vignette → chromatic aberration → bleach bypass
_DOCUMENTARY_PARAMS = ProcessingParams(
    style=ProcessingStyle.DOCUMENTARY,
    grain_intensity=0.20,
    desaturation_amount=0.15,
    vignette_intensity=0.20,
    chromatic_aberration_px=2,
    color_grade=ColorGrade.BLEACH_BYPASS,
    jpeg_quality=92,
)


class ImageProcessor:
    """Post-processes AI-generated images for a documentary film aesthetic.

    Pipeline (anti-AI detection):
      1. Film grain — Gaussian noise blended at 15-25%
      2. Desaturation — reduce saturation 10-20% from AI defaults
      3. Vignette — 10-25% edge darkening
      4. Chromatic aberration — 1-3px RGB channel offset at edges
      5. Color grading — kodak_portra (warm) or bleach_bypass (gritty)

    All operations use Pillow (PIL). Output is JPEG quality 92.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_scene_image(
        self,
        input_path: str,
        output_path: str,
        style: ProcessingStyle = ProcessingStyle.DOCUMENTARY,
    ) -> str:
        """Apply the full post-processing pipeline to a single image.

        Runs CPU-bound Pillow work in a thread pool to avoid blocking the
        event loop.  Returns the output path.
        """
        params = (
            _DOCUMENTARY_PARAMS
            if style == ProcessingStyle.DOCUMENTARY
            else ProcessingParams(style=style)
        )
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, partial(self._process_sync, input_path, output_path, params)
        )
        await logger.ainfo("image_processed", input=input_path, output=result, style=style.value)
        return result

    async def process_batch(
        self,
        image_paths: list[str],
        style: ProcessingStyle = ProcessingStyle.DOCUMENTARY,
        output_dir: str | None = None,
    ) -> list[str]:
        """Process a batch of images concurrently."""
        tasks = []
        for path in image_paths:
            out = _derive_output_path(path, output_dir)
            tasks.append(self.process_scene_image(path, out, style))
        results = await asyncio.gather(*tasks)
        await logger.ainfo("batch_processed", count=len(results), style=style.value)
        return list(results)

    # ------------------------------------------------------------------
    # Individual effects (static, usable standalone)
    # ------------------------------------------------------------------

    @staticmethod
    def apply_film_grain(image: Image.Image, intensity: float = 0.20) -> Image.Image:
        """Add realistic film grain via Gaussian noise.

        Generates a noise layer, applies a slight Gaussian blur (radius 0.5)
        for natural grain structure, then blends with the original at the
        given intensity.
        """
        arr = np.array(image, dtype=np.float32)
        rng = np.random.default_rng()
        noise = rng.normal(0, 255 * intensity, arr.shape).astype(np.float32)

        # Blur the noise slightly for realistic grain structure
        noise_img = Image.fromarray(np.clip(noise + 128, 0, 255).astype(np.uint8))
        noise_img = noise_img.filter(ImageFilter.GaussianBlur(radius=0.5))
        noise_blurred = np.array(noise_img, dtype=np.float32) - 128

        result = arr + noise_blurred
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

    @staticmethod
    def apply_desaturation(image: Image.Image, amount: float = 0.15) -> Image.Image:
        """Reduce saturation to counter AI-generated over-saturation.

        amount=0.15 means reduce saturation by 15% (factor = 0.85).
        """
        enhancer = ImageEnhance.Color(image)
        return enhancer.enhance(1.0 - amount)

    @staticmethod
    def apply_vignette(image: Image.Image, intensity: float = 0.20) -> Image.Image:
        """Apply edge darkening vignette effect.

        Creates a radial gradient mask and blends a darkened version of
        the image at edges.
        """
        w, h = image.size
        cx, cy = w / 2, h / 2
        max_dist = math.sqrt(cx**2 + cy**2)

        # Build vignette mask: 1.0 at center, drops toward edges
        y_coords, x_coords = np.mgrid[0:h, 0:w]
        dist = np.sqrt((x_coords - cx) ** 2 + (y_coords - cy) ** 2)
        # Normalize to [0, 1] and apply power curve for softer falloff
        normalized = dist / max_dist
        mask = 1.0 - intensity * (normalized**1.5)
        mask = np.clip(mask, 0, 1)

        # Apply to each channel
        arr = np.array(image, dtype=np.float32)
        if arr.ndim == 3:
            mask = mask[:, :, np.newaxis]
        result = arr * mask
        return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8))

    @staticmethod
    def apply_chromatic_aberration(image: Image.Image, offset_pixels: int = 2) -> Image.Image:
        """Simulate lens chromatic aberration with RGB channel offset at edges.

        Shifts the red channel outward and the blue channel inward by
        offset_pixels, scaled by distance from center. Green stays put.
        """
        if offset_pixels == 0:
            return image

        arr = np.array(image, dtype=np.uint8)
        h, w = arr.shape[:2]
        cx, cy = w / 2, h / 2
        max_dist = math.sqrt(cx**2 + cy**2)

        y_coords, x_coords = np.mgrid[0:h, 0:w]
        dx = (x_coords - cx) / max_dist
        dy = (y_coords - cy) / max_dist

        # Per-pixel shift proportional to distance from center
        shift_x = (dx * offset_pixels).astype(np.float32)
        shift_y = (dy * offset_pixels).astype(np.float32)

        result = arr.copy()

        # Red channel: shift outward (+offset)
        r_x = np.clip(x_coords + shift_x, 0, w - 1).astype(np.intp)
        r_y = np.clip(y_coords + shift_y, 0, h - 1).astype(np.intp)
        result[:, :, 0] = arr[r_y, r_x, 0]

        # Blue channel: shift inward (-offset)
        b_x = np.clip(x_coords - shift_x, 0, w - 1).astype(np.intp)
        b_y = np.clip(y_coords - shift_y, 0, h - 1).astype(np.intp)
        result[:, :, 2] = arr[b_y, b_x, 2]

        return Image.fromarray(result)

    @staticmethod
    def apply_color_grade(image: Image.Image, grade: str = "kodak_portra") -> Image.Image:
        """Apply a color grading preset.

        Presets:
          - kodak_portra: warm skin tones, lifted shadows, slight magenta in mids
          - bleach_bypass: desaturated, high contrast, gritty documentary look
        """
        arr = np.array(image, dtype=np.float32)

        if grade == ColorGrade.KODAK_PORTRA or grade == "kodak_portra":
            # Warm shift: boost reds/yellows, lift shadows, gentle magenta mids
            # Shadows lift
            arr = arr + 8
            # Warm: slight red/green push, blue pull
            arr[:, :, 0] = arr[:, :, 0] * 1.04  # red +4%
            arr[:, :, 1] = arr[:, :, 1] * 1.01  # green +1%
            arr[:, :, 2] = arr[:, :, 2] * 0.94  # blue -6%
            # Slight contrast bump via midtone S-curve approximation
            arr = 128 + (arr - 128) * 1.05

        elif grade == ColorGrade.BLEACH_BYPASS or grade == "bleach_bypass":
            # High contrast, desaturated, crushed blacks
            # Convert to grayscale weights for luminance blend
            luma = arr[:, :, 0] * 0.2126 + arr[:, :, 1] * 0.7152 + arr[:, :, 2] * 0.0722
            luma = luma[:, :, np.newaxis]
            # Blend 30% luminance into color for washed look
            arr = arr * 0.70 + luma * 0.30
            # Contrast boost
            arr = 128 + (arr - 128) * 1.25
            # Crush blacks slightly
            arr = np.where(arr < 20, arr * 0.6, arr)

        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _process_sync(self, input_path: str, output_path: str, params: ProcessingParams) -> str:
        """Synchronous processing pipeline — called from thread pool."""
        img = Image.open(input_path).convert("RGB")

        if params.style == ProcessingStyle.RAW:
            img.save(output_path, "JPEG", quality=params.jpeg_quality)
            return output_path

        # Documentary pipeline: grain → desaturate → vignette → chromatic → color grade
        img = self.apply_film_grain(img, params.grain_intensity)
        img = self.apply_desaturation(img, params.desaturation_amount)
        img = self.apply_vignette(img, params.vignette_intensity)
        img = self.apply_chromatic_aberration(img, params.chromatic_aberration_px)
        img = self.apply_color_grade(img, params.color_grade)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        img.save(output_path, "JPEG", quality=params.jpeg_quality)
        return output_path


def _derive_output_path(input_path: str, output_dir: str | None) -> str:
    """Create an output path by adding '_processed' suffix."""
    p = Path(input_path)
    base = output_dir or str(p.parent)
    return str(Path(base) / f"{p.stem}_processed.jpg")
