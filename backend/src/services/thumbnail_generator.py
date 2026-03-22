from __future__ import annotations

import asyncio
import math
import tempfile
import time
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
import structlog
from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from src.models.image import FalModel
from src.models.thumbnail import (
    ALL_ARCHETYPES,
    ThumbnailArchetype,
    ThumbnailInput,
    ThumbnailResult,
)

if TYPE_CHECKING:
    import httpx

    from src.config import Settings
    from src.models.script import BrandSettings
    from src.services.image_generator import ImageGenerator

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# YouTube recommended thumbnail resolution
THUMB_WIDTH = 2560
THUMB_HEIGHT = 1440
THUMB_SIZE = (THUMB_WIDTH, THUMB_HEIGHT)

# Output quality
JPEG_QUALITY = 92
MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB YouTube API limit

# Cost: Flux Pro New at $0.055 per image
BACKGROUND_COST = FalModel.FLUX_PRO_NEW.cost_per_image

# Font resolution — resolved at runtime from backend/assets/fonts/
_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"
_FONT_CANDIDATES = [
    "BebasNeue-Bold.ttf",
    "Montserrat-ExtraBold.ttf",
    "Impact",  # system fallback
]

# Text overlay defaults
_DROP_SHADOW_OFFSET = (6, 6)
_STROKE_WIDTH = 5

# Safe zone: critical elements within center 1100×620 (at 2560×1440)
_SAFE_LEFT = (THUMB_WIDTH - 1100) // 2  # 730
_SAFE_TOP = (THUMB_HEIGHT - 620) // 2  # 410
_SAFE_RIGHT = _SAFE_LEFT + 1100  # 1830
_SAFE_BOTTOM = _SAFE_TOP + 620  # 1030

# YouTube Test & Compare maximum
MAX_VARIANTS = 3

# ---------------------------------------------------------------------------
# Archetype prompt templates
# ---------------------------------------------------------------------------

_ARCHETYPE_PROMPTS: dict[ThumbnailArchetype, str] = {
    "interrogation": (
        "Dark interrogation room, single overhead light, dramatic shadows, "
        "{topic_context}, noir atmosphere, 16:9"
    ),
    "storyteller": (
        "Split composition, dark moody background, "
        "{topic_context}, cinematic lighting, film grain, 16:9"
    ),
    "duality": (
        "Split frame, dramatic diagonal divide, dark vs light, {topic_context}, high contrast, 16:9"
    ),
    "case_file": (
        "Evidence board aesthetic, pinned documents, red string, dark background, "
        "{topic_context}, 16:9"
    ),
    "beauty_beast": (
        "Warm-to-cold gradient, glamorous lighting fading to darkness, {topic_context}, 16:9"
    ),
    "cold_case": (
        "Gritty desaturated scene, heavy film grain, fog, "
        "{topic_context}, abandoned atmosphere, 16:9"
    ),
}

# Text positioning per archetype: (anchor_keyword, x_frac, y_frac)
# x_frac / y_frac are fractions of THUMB_WIDTH / THUMB_HEIGHT.
_TEXT_LAYOUT: dict[ThumbnailArchetype, tuple[str, float, float]] = {
    "interrogation": ("ms", 0.50, 0.85),  # bottom center, minimal
    "storyteller": ("rs", 0.75, 0.50),  # right side
    "duality": ("ms", 0.50, 0.50),  # center divider
    "case_file": ("ms", 0.50, 0.50),  # center, typewriter feel
    "beauty_beast": ("ls", 0.25, 0.50),  # left side
    "cold_case": ("ms", 0.50, 0.50),  # bold center
}

# Topic keywords → archetype affinity for auto-selection
_TOPIC_AFFINITY: dict[str, list[ThumbnailArchetype]] = {
    "fraud": ["case_file", "duality"],
    "scam": ["case_file", "duality"],
    "financial": ["case_file", "duality"],
    "betrayal": ["storyteller", "beauty_beast"],
    "affair": ["beauty_beast", "storyteller"],
    "love": ["beauty_beast", "storyteller"],
    "cold case": ["cold_case", "interrogation"],
    "unsolved": ["cold_case", "interrogation"],
    "mystery": ["cold_case", "interrogation"],
    "murder": ["interrogation", "cold_case"],
    "killer": ["interrogation", "duality"],
    "serial": ["interrogation", "cold_case"],
    "disappear": ["cold_case", "storyteller"],
    "missing": ["cold_case", "storyteller"],
    "corruption": ["case_file", "duality"],
    "cartel": ["interrogation", "duality"],
    "drugs": ["interrogation", "cold_case"],
    "mafia": ["interrogation", "duality"],
}


class ThumbnailGenerator:
    """Generates YouTube thumbnails: AI background + Pillow text overlay.

    Follows the crime documentary aesthetic with 6 visual archetypes,
    archetype-specific color treatments, and bold text overlays optimised
    for click-through rate at small sizes.
    """

    def __init__(
        self,
        settings: Settings,
        image_generator: ImageGenerator,
        http_client: httpx.AsyncClient,
    ) -> None:
        self._settings = settings
        self._image_gen = image_generator
        self._http = http_client
        self._output_dir = Path(tempfile.gettempdir()) / "crimemill" / "thumbnails"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_thumbnail(self, input: ThumbnailInput) -> ThumbnailResult:
        """Full thumbnail pipeline: background → color treatment → text overlay.

        1. Select archetype (explicit or auto-rotate)
        2. Build fal.ai prompt from archetype template + topic
        3. Generate background via ImageGenerator (Flux Pro New, $0.055)
        4. Apply archetype-specific color treatment (saturation boost,
           vignette, red accent overlay)
        5. Composite bold text overlay with drop shadow
        6. Validate and save as JPEG quality 92
        7. Return result with file path and metadata
        """
        start = time.monotonic()

        archetype = self._select_archetype(input.topic, input.recent_archetypes)
        if input.archetype is not None:
            archetype = input.archetype

        prompt = self._build_background_prompt(
            topic=input.title,
            archetype=archetype,
            brand=input.brand_settings,
        )

        await logger.ainfo(
            "thumbnail_generation_started",
            video_id=str(input.video_id),
            archetype=archetype,
            text_overlay=input.text_overlay,
        )

        # 1. Generate background via fal.ai
        bg_result = await self._image_gen.generate_thumbnail_background(prompt)

        # 2-5. Post-process and composite (CPU-bound → thread pool)
        loop = asyncio.get_running_loop()
        final_path, file_size, warnings = await loop.run_in_executor(
            None,
            partial(
                self._compose_sync,
                bg_local_path=bg_result.local_path,
                text=input.text_overlay,
                archetype=archetype,
            ),
        )

        elapsed = round(time.monotonic() - start, 2)

        await logger.ainfo(
            "thumbnail_generation_completed",
            video_id=str(input.video_id),
            archetype=archetype,
            file_size_bytes=file_size,
            generation_time_seconds=elapsed,
            warnings=warnings,
        )

        return ThumbnailResult(
            file_path=final_path,
            archetype=archetype,
            resolution=THUMB_SIZE,
            file_size_bytes=file_size,
            text_overlay=input.text_overlay,
            background_prompt=prompt,
            cost_usd=float(BACKGROUND_COST),
            generation_time_seconds=elapsed,
            validation_warnings=warnings,
        )

    async def generate_variants(
        self,
        input: ThumbnailInput,
        count: int = 3,
    ) -> list[ThumbnailResult]:
        """Generate multiple thumbnail variants for YouTube Test & Compare.

        Each variant uses a different archetype.  YouTube supports max 3
        variants, so *count* is clamped to that.
        """
        count = min(count, MAX_VARIANTS)

        # Pick distinct archetypes
        archetypes = self._pick_variant_archetypes(
            input.topic,
            input.recent_archetypes,
            count,
        )

        tasks = []
        for arch in archetypes:
            variant_input = input.model_copy(update={"archetype": arch})
            tasks.append(self.generate_thumbnail(variant_input))

        results = await asyncio.gather(*tasks)
        return list(results)

    # ------------------------------------------------------------------
    # Background prompt
    # ------------------------------------------------------------------

    @staticmethod
    def _build_background_prompt(
        topic: str,
        archetype: ThumbnailArchetype,
        brand: BrandSettings,
    ) -> str:
        template = _ARCHETYPE_PROMPTS[archetype]
        prompt = template.format(topic_context=topic)
        if brand.cinematic_prompt_suffix:
            prompt = f"{prompt}, {brand.cinematic_prompt_suffix}"
        return prompt

    # ------------------------------------------------------------------
    # Archetype selection
    # ------------------------------------------------------------------

    @staticmethod
    def _select_archetype(
        topic: dict[str, object],
        recent_archetypes: list[str],
    ) -> ThumbnailArchetype:
        """Pick an archetype that fits the topic and avoids repetition.

        Weight by topic keyword affinity.  Never repeat the most recent
        archetype.
        """
        # Build a search string from all topic values
        topic_text = " ".join(str(v) for v in topic.values()).lower()

        # Score each archetype by keyword match
        scores: dict[ThumbnailArchetype, float] = {a: 1.0 for a in ALL_ARCHETYPES}
        for keyword, preferred in _TOPIC_AFFINITY.items():
            if keyword in topic_text:
                for i, arch in enumerate(preferred):
                    scores[arch] += 2.0 - (i * 0.5)

        # Penalise recent archetypes (never repeat the last one)
        for i, recent in enumerate(reversed(recent_archetypes)):
            arch_key = cast("ThumbnailArchetype", recent)
            if arch_key in scores:
                penalty = 100.0 if i == 0 else 3.0
                scores[arch_key] -= penalty

        # Return highest-scoring archetype
        best = max(scores, key=lambda a: scores[a])
        return best

    @staticmethod
    def _pick_variant_archetypes(
        topic: dict[str, object],
        recent_archetypes: list[str],
        count: int,
    ) -> list[ThumbnailArchetype]:
        """Select *count* distinct archetypes for variant generation."""
        topic_text = " ".join(str(v) for v in topic.values()).lower()

        scores: dict[ThumbnailArchetype, float] = {a: 1.0 for a in ALL_ARCHETYPES}
        for keyword, preferred in _TOPIC_AFFINITY.items():
            if keyword in topic_text:
                for i, arch in enumerate(preferred):
                    scores[arch] += 2.0 - (i * 0.5)

        for recent in recent_archetypes[-1:]:
            arch_key = cast("ThumbnailArchetype", recent)
            if arch_key in scores:
                scores[arch_key] -= 100.0

        ranked = sorted(scores, key=lambda a: scores[a], reverse=True)
        return ranked[:count]

    # ------------------------------------------------------------------
    # Synchronous compose pipeline (runs in thread pool)
    # ------------------------------------------------------------------

    def _compose_sync(
        self,
        bg_local_path: str,
        text: str,
        archetype: ThumbnailArchetype,
    ) -> tuple[str, int, list[str]]:
        """Open background → resize → color treatment → text → save.

        Returns (file_path, file_size_bytes, validation_warnings).
        """
        img = Image.open(bg_local_path).convert("RGB")

        # Ensure exact thumbnail resolution
        if img.size != THUMB_SIZE:
            img = img.resize(THUMB_SIZE, Image.Resampling.LANCZOS)

        # Color treatment
        img = self._apply_color_treatment(img, archetype)

        # Text overlay
        if text.strip():
            img = self._composite_text(img, text.strip(), archetype)

        # Validate
        warnings = self._validate_thumbnail(img)

        # Save — re-compress if over 2 MB
        out_path = str(self._output_dir / f"thumb_{archetype}_{int(time.time())}.jpg")
        quality = JPEG_QUALITY
        img.save(out_path, "JPEG", quality=quality)
        file_size = Path(out_path).stat().st_size

        while file_size > MAX_FILE_SIZE_BYTES and quality > 60:
            quality -= 5
            img.save(out_path, "JPEG", quality=quality)
            file_size = Path(out_path).stat().st_size
            warnings.append(f"Re-compressed to quality {quality} ({file_size} bytes)")

        return out_path, file_size, warnings

    # ------------------------------------------------------------------
    # Color treatment
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_color_treatment(
        image: Image.Image,
        archetype: ThumbnailArchetype,
    ) -> Image.Image:
        """Apply archetype-specific colour grading for feed competition.

        Thumbnails get the *opposite* of scene-image treatment:
        saturation is INCREASED 20-30% so they pop in the YouTube feed.
        Plus dark base, red accent overlay, and intensified vignette.
        """
        arr = np.array(image, dtype=np.float32)
        h, w = arr.shape[:2]

        # --- 1. Dark base: blend toward #0D0D0D at 15% ---
        dark_base = np.full_like(arr, 13.0)  # 0x0D
        arr = arr * 0.85 + dark_base * 0.15

        # --- 2. Red accent overlay in subject area (center 60%) ---
        # Red range depends on archetype
        if archetype == "beauty_beast":
            # Warmer tones — less red, more amber
            accent = np.array([200, 120, 40], dtype=np.float32)
            accent_opacity = 0.20
        elif archetype == "cold_case":
            # Desaturated blue tint instead of red
            accent = np.array([60, 80, 120], dtype=np.float32)
            accent_opacity = 0.15
        else:
            # Crime red: #8B0000 → #FF0000 gradient
            accent = np.array([200, 20, 10], dtype=np.float32)
            accent_opacity = 0.25

        # Apply accent only to the center 60% of the image
        margin_x = int(w * 0.20)
        margin_y = int(h * 0.20)
        accent_layer = np.zeros_like(arr)
        accent_layer[margin_y : h - margin_y, margin_x : w - margin_x] = accent
        # Soft-edge the mask with a gaussian approximation (radial falloff)
        cy, cx = h / 2, w / 2
        max_d = math.sqrt(cx**2 + cy**2)
        ys, xs = np.mgrid[0:h, 0:w]
        dist = np.sqrt((xs - cx) ** 2 + (ys - cy) ** 2) / max_d
        mask = np.clip(1.0 - dist * 1.5, 0, 1)[:, :, np.newaxis]
        arr = arr * (1 - accent_opacity * mask) + accent_layer * (accent_opacity * mask)

        # --- 3. Saturation boost 25% (opposite of scene desaturation) ---
        boosted = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        enhancer = ImageEnhance.Color(boosted)
        boosted = enhancer.enhance(1.25)
        arr = np.array(boosted, dtype=np.float32)

        # --- 4. Vignette intensified to 28% for thumbnails ---
        max_dist_vig = math.sqrt((w / 2) ** 2 + (h / 2) ** 2)
        dist_vig = np.sqrt((xs - w / 2) ** 2 + (ys - h / 2) ** 2)
        vig_mask = 1.0 - 0.28 * (dist_vig / max_dist_vig) ** 1.5
        vig_mask = np.clip(vig_mask, 0, 1)[:, :, np.newaxis]
        arr = arr * vig_mask

        # --- 5. Yellow highlight for alarm elements (subtle warm push) ---
        # Boost yellow channel in bright areas
        bright_mask = (arr.mean(axis=2, keepdims=True) > 160).astype(np.float32)
        arr[:, :, 0] = arr[:, :, 0] + bright_mask[:, :, 0] * 12  # R
        arr[:, :, 1] = arr[:, :, 1] + bright_mask[:, :, 0] * 10  # G

        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

    # ------------------------------------------------------------------
    # Text overlay
    # ------------------------------------------------------------------

    def _composite_text(
        self,
        image: Image.Image,
        text: str,
        archetype: ThumbnailArchetype,
    ) -> Image.Image:
        """Add bold text overlay with drop shadow and stroke.

        Text is 0-3 words, positioned per archetype layout.  Uses
        Bebas Neue Bold → Montserrat Extra Bold → Impact as fallback chain.
        """
        img = image.copy()
        draw = ImageDraw.Draw(img)

        # Resolve font
        font_size = self._compute_font_size(text)
        font = _load_font(font_size)

        # Layout position
        anchor, x_frac, y_frac = _TEXT_LAYOUT[archetype]
        x = int(THUMB_WIDTH * x_frac)
        y = int(THUMB_HEIGHT * y_frac)

        # Uppercase for impact
        text_upper = text.upper()

        # Drop shadow (black, offset by _DROP_SHADOW_OFFSET)
        sx, sy = _DROP_SHADOW_OFFSET
        draw.text(
            (x + sx, y + sy),
            text_upper,
            font=font,
            fill=(0, 0, 0, 200),
            anchor=anchor,
            stroke_width=_STROKE_WIDTH + 1,
            stroke_fill="black",
        )

        # Main text: white with black stroke
        draw.text(
            (x, y),
            text_upper,
            font=font,
            fill="white",
            anchor=anchor,
            stroke_width=_STROKE_WIDTH,
            stroke_fill="black",
        )

        return img

    @staticmethod
    def _compute_font_size(text: str) -> int:
        """Scale font size inversely with word count for readability."""
        word_count = len(text.split())
        if word_count <= 1:
            return 220
        if word_count <= 2:
            return 180
        return 140  # 3+ words

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_thumbnail(image: Image.Image) -> list[str]:
        """Run quality checks; return a list of warning strings (empty = pass)."""
        warnings: list[str] = []

        # Resolution check
        if image.size != THUMB_SIZE:
            warnings.append(f"Resolution {image.size} != expected {THUMB_SIZE}")

        # Text legibility proxy: down-scale to YouTube search-result size
        # (168×94) and check overall contrast (std dev of luminance).
        small = image.resize((168, 94), Image.Resampling.LANCZOS).convert("L")
        arr = np.array(small, dtype=np.float32)
        if arr.std() < 25:
            warnings.append(f"Low contrast at search-result size (std={arr.std():.1f}, want ≥25)")

        # Bottom-right clear zone (timestamp overlay): last 15% w, 10% h
        br_region = np.array(
            image.crop(
                (
                    int(THUMB_WIDTH * 0.85),
                    int(THUMB_HEIGHT * 0.90),
                    THUMB_WIDTH,
                    THUMB_HEIGHT,
                )
            ).convert("L"),
            dtype=np.float32,
        )
        if br_region.std() > 50:
            warnings.append(
                "Bottom-right zone has high detail — may clash with YouTube timestamp overlay"
            )

        return warnings


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load fonts from assets dir, then fall back to system fonts."""
    for name in _FONT_CANDIDATES:
        # Asset directory
        path = _ASSETS_DIR / name
        if path.is_file():
            return ImageFont.truetype(str(path), size)

        # System font (e.g. "Impact" on Windows)
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue

    # Last resort: Pillow default bitmap font (no sizing)
    return ImageFont.load_default()
