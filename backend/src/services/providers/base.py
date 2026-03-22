"""Abstract base classes for all provider types.

Each provider type defines a standard interface so the pipeline can swap
between API services and self-hosted models without changing business logic.

Provider types:
  - TTSProvider     — text-to-speech (Fish Audio, Chatterbox, Kokoro)
  - ImageProvider   — image generation (fal.ai Flux, local Flux Dev)
  - MusicProvider   — music generation (Epidemic Sound library, ACE-Step)
  - LLMProvider     — large language model (Anthropic Claude API)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Shared result types
# ---------------------------------------------------------------------------


class TTSResult(BaseModel):
    """Standardised result from any TTS provider."""

    file_path: str
    duration_seconds: float
    sample_rate: int
    file_size_bytes: int
    character_count: int
    cost_usd: Decimal
    provider: str
    voice_id: str = ""
    latency_ms: int = 0


class VoiceInfo(BaseModel):
    """Voice metadata returned by any TTS provider."""

    voice_id: str
    name: str
    description: str = ""
    preview_url: str = ""
    languages: list[str] = Field(default_factory=list)
    provider: str = ""


class ImageResult(BaseModel):
    """Standardised result from any image provider."""

    file_path: str
    width: int
    height: int
    cost_usd: Decimal
    provider: str
    model: str = ""
    prompt: str = ""
    url: str = ""
    latency_ms: int = 0


class MusicResult(BaseModel):
    """Standardised result from any music provider."""

    file_path: str
    duration_seconds: float
    cost_usd: Decimal
    provider: str
    title: str = ""
    bpm: int | None = None


class LLMResult(BaseModel):
    """Standardised result from any LLM provider."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal("0")
    provider: str = ""
    model: str = ""
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# Abstract base classes
# ---------------------------------------------------------------------------


class TTSProvider(ABC):
    """Interface for text-to-speech providers."""

    @abstractmethod
    async def generate(
        self,
        text: str,
        voice_id: str,
        **kwargs: Any,
    ) -> TTSResult:
        """Synthesise text to speech and return a WAV file path."""

    @abstractmethod
    async def list_voices(self) -> list[VoiceInfo]:
        """Return available voices for this provider."""

    @abstractmethod
    def cost_per_character(self) -> Decimal:
        """Return the per-character cost in USD."""

    @abstractmethod
    def provider_name(self) -> str:
        """Return a human-readable provider identifier."""

    def is_self_hosted(self) -> bool:
        """Whether this provider runs on self-managed infrastructure."""
        return False


class ImageProvider(ABC):
    """Interface for image generation providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        **kwargs: Any,
    ) -> ImageResult:
        """Generate an image and return its local file path."""

    @abstractmethod
    def cost_per_image(self) -> Decimal:
        """Return the average per-image cost in USD."""

    @abstractmethod
    def provider_name(self) -> str:
        """Return a human-readable provider identifier."""

    def is_self_hosted(self) -> bool:
        return False


class MusicProvider(ABC):
    """Interface for music generation / selection providers."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        duration_seconds: float,
        **kwargs: Any,
    ) -> MusicResult:
        """Generate or select a music track."""

    @abstractmethod
    def cost_per_generation(self) -> Decimal:
        """Return the per-track cost in USD."""

    @abstractmethod
    def provider_name(self) -> str:
        """Return a human-readable provider identifier."""

    def is_self_hosted(self) -> bool:
        return False


class LLMProvider(ABC):
    """Interface for large language model providers."""

    @abstractmethod
    async def generate(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResult:
        """Send a prompt and return the model's text response."""

    @abstractmethod
    def cost_per_1k_input_tokens(self) -> Decimal:
        """Return the cost per 1,000 input tokens."""

    @abstractmethod
    def cost_per_1k_output_tokens(self) -> Decimal:
        """Return the cost per 1,000 output tokens."""

    @abstractmethod
    def provider_name(self) -> str:
        """Return a human-readable provider identifier."""
