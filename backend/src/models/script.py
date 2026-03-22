"""Script generation models — all types used by ScriptGenerator and downstream stages.

Covers: topic input, channel/brand settings, script output with timing markers,
scene breakdowns, image prompts, title variants, and cost tracking.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class HookType(StrEnum):
    """Opening hook style for the script."""

    COLD_OPEN = "cold_open"
    PROVOCATIVE_QUESTION = "provocative_question"
    SHOCKING_STATISTIC = "shocking_statistic"
    CONTRADICTION = "contradiction"
    SENSORY_SCENE = "sensory_scene"


class TitleFormula(StrEnum):
    """Title formula for A/B test variants."""

    ADJECTIVE_CASE = "adjective_case"
    HOW_PERSON = "how_person"
    NOBODY_TALKS = "nobody_talks"
    WHY_QUESTION = "why_question"
    TRUTH_BEHIND = "truth_behind"
    WHAT_HAPPENED = "what_happened"


NarrationSpeed = Literal["NORMAL", "FAST", "SLOW", "REVEAL"]


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


class APICallCost(BaseModel):
    """Cost details for a single Claude API call."""

    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    cached_input_tokens: int = 0


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


class TopicInput(BaseModel):
    """Input to the script generation pipeline."""

    topic: str
    video_length_minutes: int = Field(ge=5, le=30)
    rotation_index: int = 0
    hook_type: HookType | None = None
    angle: str | None = None
    region: str | None = None
    era: str | None = None


class ChannelSettings(BaseModel):
    """Per-channel tone and audience configuration."""

    channel_name: str = ""
    channel_id: str = ""
    tone: str = "dark, measured, cinematic"
    target_audience: str = "true crime enthusiasts, 25-45"
    content_rating: str = "TV-14"


class BrandSettings(BaseModel):
    """Visual branding — controls image prompt style and thumbnail look."""

    primary_accent_color: str = "#8B0000"
    cinematic_prompt_suffix: str = "cinematic, dark, moody atmosphere"
    font_family: str = "BebasNeue-Bold"
    lighting_style: str = "low-key side lighting with blue fill"
    color_palette: str = "dark reds and blacks"
    mood: str = "ominous, foreboding"
    aspect_ratio: str = "16:9"
    master_prompt_suffix: str = "4k, professional grade, cinematic quality"
    negative_prompt: str = "blurry, low quality, washed out, text, watermark"


# ---------------------------------------------------------------------------
# Script output
# ---------------------------------------------------------------------------


class TwistPlacement(BaseModel):
    """A narrative twist/reveal embedded in the script."""

    position_percent: int = Field(ge=0, le=100)
    description: str


class ScriptOutput(BaseModel):
    """Complete script generation result."""

    script_text: str
    word_count: int = Field(ge=0)
    estimated_duration_seconds: float = Field(ge=0)
    hook_type: HookType
    open_loops: list[str] = Field(default_factory=list)
    twist_placements: list[TwistPlacement] = Field(default_factory=list)
    cost: APICallCost


# ---------------------------------------------------------------------------
# Scene breakdown
# ---------------------------------------------------------------------------


class SceneBreakdown(BaseModel):
    """A single scene in the script breakdown — used for image prompts,
    chapter timestamps, and voiceover timing.
    """

    scene_number: int = Field(ge=1)
    start_time_seconds: float = Field(ge=0)
    end_time_seconds: float = Field(ge=0)
    narration_text: str
    scene_description: str = ""
    emotion_tag: str = ""
    narration_speed: NarrationSpeed = "NORMAL"
    is_pattern_interrupt: bool = False
    is_ad_break: bool = False
    sfx_annotations: list[str] = Field(default_factory=list)


class SceneBreakdownResult(BaseModel):
    """Result of breaking the script into timed scenes."""

    scenes: list[SceneBreakdown]
    cost: APICallCost


# ---------------------------------------------------------------------------
# Image prompts
# ---------------------------------------------------------------------------


class ImagePrompt(BaseModel):
    """Image generation prompt derived from a scene breakdown."""

    scene_number: int = Field(ge=1)
    prompt: str
    negative_prompt: str = ""
    aspect_ratio: str = "16:9"
    lighting: str = ""
    mood: str = ""
    reference_scene_description: str = ""


class ImagePromptsResult(BaseModel):
    """Result of generating image prompts for all scenes."""

    prompts: list[ImagePrompt]
    cost: APICallCost


# ---------------------------------------------------------------------------
# Title variants
# ---------------------------------------------------------------------------


class TitleVariant(BaseModel):
    """A single title option with CTR prediction."""

    title: str
    formula: TitleFormula
    word_count: int = Field(ge=0)
    char_count: int = Field(ge=0)
    power_words: list[str] = Field(default_factory=list)
    estimated_ctr_rank: int = Field(ge=1)


class TitlesResult(BaseModel):
    """Result of title generation (up to 5 variants)."""

    variants: list[TitleVariant]
    cost: APICallCost


# ---------------------------------------------------------------------------
# Description
# ---------------------------------------------------------------------------


class DescriptionResult(BaseModel):
    """Result of YouTube description generation."""

    description: str
    cost: APICallCost


# ---------------------------------------------------------------------------
# API response model (DB row)
# ---------------------------------------------------------------------------


class SceneScript(BaseModel):
    scene_number: int = Field(ge=1)
    narration: str
    image_prompt: str
    duration_seconds: float = Field(gt=0)


class ScriptResponse(BaseModel):
    id: uuid.UUID
    video_id: uuid.UUID
    title: str
    hook: str
    scenes: list[SceneScript]
    outro: str
    total_duration_seconds: float
    created_at: datetime

    @classmethod
    def from_row(cls, row: dict[str, object]) -> ScriptResponse:
        return cls.model_validate(row)
