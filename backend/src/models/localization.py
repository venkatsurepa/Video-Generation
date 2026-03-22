"""Models for the localization pipeline.

Defines language configuration, translation outputs, and cost estimates
for producing localized versions of completed English videos.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Language configuration
# ---------------------------------------------------------------------------

PRIORITY_LANGUAGES: dict[str, dict[str, object]] = {
    "es": {"name": "Spanish", "word_adjustment": 1.17, "font": "Montserrat-ExtraBold.ttf"},
    "pt": {"name": "Portuguese", "word_adjustment": 1.12, "font": "Montserrat-ExtraBold.ttf"},
    "hi": {"name": "Hindi", "word_adjustment": 0.93, "font": "NotoSansDevanagari-Bold.ttf"},
    "fr": {"name": "French", "word_adjustment": 1.13, "font": "Montserrat-ExtraBold.ttf"},
}

ALL_SUPPORTED_LANGUAGES: set[str] = {
    "es",
    "pt",
    "hi",
    "fr",
    "de",
    "it",
    "ja",
    "ko",
    "zh",
    "ar",
    "ru",
    "tr",
    "pl",
    "nl",
    "id",
    "th",
    "vi",
}


class LanguageConfig(BaseModel):
    """Per-language configuration for localization."""

    code: str = Field(min_length=2, max_length=5, description="ISO 639-1 code")
    name: str
    word_count_adjustment: float = Field(
        ge=0.5,
        le=2.0,
        description="Multiplier for target word count vs English (e.g., 1.17 for Spanish)",
    )
    font_family: str = Field(
        default="Montserrat-ExtraBold.ttf",
        description="Font file for thumbnail text in this language",
    )
    youtube_category: str = Field(
        default="22",
        description="YouTube category ID (may differ by region)",
    )
    common_crime_keywords: list[str] = Field(
        default_factory=list,
        description="SEO keywords for crime content in this language",
    )


# ---------------------------------------------------------------------------
# Translation outputs
# ---------------------------------------------------------------------------


class TranslatedScript(BaseModel):
    """Result of creative script translation via Claude."""

    source_language: str = "en"
    target_language: str
    translated_text: str = Field(description="Full translated script with markers preserved")
    source_word_count: int = Field(ge=0)
    translated_word_count: int = Field(ge=0)
    word_count_ratio: float = Field(
        ge=0,
        description="translated / source — should be close to language adjustment factor",
    )
    markers_preserved: bool = Field(
        default=True,
        description="Whether all timing markers were correctly preserved",
    )
    cost: Decimal = Field(default=Decimal("0"), ge=0)
    model: str = Field(default="", description="Claude model used for translation")


class TranslatedMetadata(BaseModel):
    """Translated YouTube metadata (title, description, tags)."""

    title: str = Field(max_length=100)
    description: str
    tags: list[str] = Field(default_factory=list)
    target_language: str
    cost: Decimal = Field(default=Decimal("0"), ge=0)


# ---------------------------------------------------------------------------
# Localization result
# ---------------------------------------------------------------------------


class LocalizationResult(BaseModel):
    """Final output of the localization pipeline for one language."""

    source_video_id: uuid.UUID
    localized_video_id: uuid.UUID = Field(
        description="New video record created for the localized version"
    )
    source_channel_id: uuid.UUID
    target_channel_id: uuid.UUID
    target_language: str
    title: str
    translated_word_count: int = Field(ge=0)
    voiceover_duration_seconds: float = Field(ge=0)
    file_path: str = Field(description="R2 object key for localized MP4")
    file_url: str = Field(description="Public or signed URL")
    file_size_bytes: int = Field(ge=0)

    # Cost breakdown
    translation_cost: Decimal = Field(default=Decimal("0"), ge=0)
    voiceover_cost: Decimal = Field(default=Decimal("0"), ge=0)
    caption_cost: Decimal = Field(default=Decimal("0"), ge=0)
    assembly_cost: Decimal = Field(default=Decimal("0"), ge=0)
    total_cost_usd: Decimal = Field(default=Decimal("0"), ge=0)

    created_at: datetime = Field(default_factory=datetime.utcnow)


class CostEstimate(BaseModel):
    """Pre-commit cost estimate for localizing a video into one language."""

    source_video_id: uuid.UUID
    target_language: str
    source_word_count: int = Field(ge=0)
    estimated_translated_words: int = Field(ge=0)
    estimated_voiceover_chars: int = Field(ge=0)
    estimated_voiceover_duration_minutes: float = Field(ge=0)

    translation_cost: Decimal = Field(default=Decimal("0"), ge=0)
    voiceover_cost: Decimal = Field(default=Decimal("0"), ge=0)
    caption_cost: Decimal = Field(default=Decimal("0"), ge=0)
    assembly_cost: Decimal = Field(default=Decimal("0"), ge=0)
    thumbnail_cost: Decimal = Field(default=Decimal("0"), description="~$0 — Pillow local")
    total_estimated_usd: Decimal = Field(default=Decimal("0"), ge=0)


# ---------------------------------------------------------------------------
# Database config row model
# ---------------------------------------------------------------------------


class LocalizationConfigRow(BaseModel):
    """Maps a source channel → target language channel with voice config."""

    source_channel_id: uuid.UUID
    target_channel_id: uuid.UUID
    target_language: str
    voice_id: str = Field(description="Fish Audio voice ID for this language")
    font_family: str | None = Field(default=None, description="Override font for thumbnail text")
    auto_localize: bool = Field(
        default=False, description="Auto-trigger localization after English publish"
    )

    @classmethod
    def from_row(cls, row: dict[str, object]) -> LocalizationConfigRow:
        return cls.model_validate(row)
