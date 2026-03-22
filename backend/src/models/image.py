"""Image generation and processing models."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

ImageStatus = Literal["pending", "generating", "completed", "failed"]


# ---------------------------------------------------------------------------
# Model selection
# ---------------------------------------------------------------------------


class FalModel(StrEnum):
    """Supported fal.ai Flux model endpoints."""

    FLUX_SCHNELL = "fal-ai/flux-schnell"
    FLUX_PRO_NEW = "fal-ai/flux-pro"
    FLUX_PRO_ULTRA = "fal-ai/flux-pro/ultra"

    @property
    def cost_per_image(self) -> Decimal:
        """Approximate USD cost per image for this model."""
        costs = {
            FalModel.FLUX_SCHNELL: Decimal("0.003"),
            FalModel.FLUX_PRO_NEW: Decimal("0.055"),
            FalModel.FLUX_PRO_ULTRA: Decimal("0.06"),
        }
        return costs[self]


class ImageTier(StrEnum):
    """Budget tier — determines default model and count allocation."""

    HERO = "hero"
    STANDARD = "standard"
    BACKGROUND = "background"


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


class ImagePrompt(BaseModel):
    """A single image generation request."""

    prompt: str
    negative_prompt: str | None = None
    model: FalModel = FalModel.FLUX_SCHNELL
    width: int = 1920
    height: int = 1080
    tier: ImageTier = ImageTier.STANDARD
    scene_number: int | None = None

    @property
    def resolved_model(self) -> FalModel:
        """Return the model to use, respecting tier defaults."""
        return self.model


# ---------------------------------------------------------------------------
# Cost / result
# ---------------------------------------------------------------------------


class ImageCost(BaseModel):
    """Cost details for a single image generation."""

    provider: str
    model: str
    cost_usd: Decimal = Decimal("0")
    latency_ms: int = 0


class ImageResult(BaseModel):
    """Result of generating a single image."""

    prompt: str
    model: str
    width: int
    height: int
    local_path: str
    url: str = ""
    cost: ImageCost = Field(default_factory=lambda: ImageCost(provider="", model=""))


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


class ColorGrade(StrEnum):
    """Color grading presets for documentary aesthetic."""

    BLEACH_BYPASS = "bleach_bypass"
    KODAK_PORTRA = "kodak_portra"


class ProcessingStyle(StrEnum):
    """Image processing style preset."""

    RAW = "raw"
    DOCUMENTARY = "documentary"
    CINEMATIC = "cinematic"


class ProcessingParams(BaseModel):
    """Parameters for the image post-processing pipeline."""

    style: ProcessingStyle = ProcessingStyle.DOCUMENTARY
    grain_intensity: float = Field(default=0.20, ge=0, le=1)
    desaturation_amount: float = Field(default=0.15, ge=0, le=1)
    vignette_intensity: float = Field(default=0.20, ge=0, le=1)
    chromatic_aberration_px: int = Field(default=2, ge=0, le=10)
    color_grade: ColorGrade = ColorGrade.BLEACH_BYPASS
    jpeg_quality: int = Field(default=92, ge=1, le=100)


# ---------------------------------------------------------------------------
# DB response
# ---------------------------------------------------------------------------


class ImageResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    scene_number: int
    prompt: str
    image_url: str
    width: int
    height: int
    status: ImageStatus
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ImageResponse:
        return cls.model_validate(row)
