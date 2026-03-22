"""Provider abstraction layer for seamless switching between API and self-hosted models.

Usage:
    from src.services.providers import ProviderFactory

    tts = ProviderFactory.get_tts_provider("fish_audio", settings, http_client)
    result = await tts.generate("Hello world", voice_id="abc123")

    # Switch to self-hosted without changing any business logic:
    tts = ProviderFactory.get_tts_provider("chatterbox", settings, http_client)
    result = await tts.generate("Hello world", voice_id="abc123")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from src.services.providers.base import (
    ImageProvider,
    ImageResult,
    LLMProvider,
    LLMResult,
    MusicProvider,
    MusicResult,
    TTSProvider,
    TTSResult,
    VoiceInfo,
)

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

# Registry of provider name → class (lazy imports to avoid circular deps)
_TTS_REGISTRY: dict[str, str] = {
    "fish_audio": "src.services.providers.tts_fish.FishAudioProvider",
    "chatterbox": "src.services.providers.tts_chatterbox.ChatterboxProvider",
    "kokoro": "src.services.providers.tts_kokoro.KokoroProvider",
}

_IMAGE_REGISTRY: dict[str, str] = {
    "fal_ai": "src.services.providers.image_fal.FalAIProvider",
    "local_flux": "src.services.providers.image_local.LocalFluxProvider",
}

_MUSIC_REGISTRY: dict[str, str] = {
    "epidemic_sound_library": "src.services.providers.music_library.EpidemicSoundLibraryProvider",
    "ace_step": "src.services.providers.music_ace_step.ACEStepProvider",
}

_LLM_REGISTRY: dict[str, str] = {
    "anthropic": "src.services.providers.llm_anthropic.AnthropicProvider",
}


def _import_class(dotted_path: str) -> type[Any]:
    """Dynamically import a class from a dotted module path."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    cls: type[Any] = getattr(module, class_name)
    return cls


class ProviderFactory:
    """Factory for instantiating providers by name.

    Supports lazy importing so unused providers don't load their dependencies.
    Provider names are stable identifiers used in config and DB records.
    """

    @staticmethod
    def get_tts_provider(
        provider_name: str,
        settings: Settings,
        http_client: httpx.AsyncClient,
    ) -> TTSProvider:
        """Instantiate a TTS provider.

        Available providers:
          - ``fish_audio``  — Fish Audio S2 API (production default)
          - ``chatterbox``  — Self-hosted Chatterbox (GPU, MIT license)
          - ``kokoro``      — Self-hosted Kokoro-82M (CPU, Apache 2.0)
        """
        dotted = _TTS_REGISTRY.get(provider_name)
        if dotted is None:
            raise ValueError(
                f"Unknown TTS provider '{provider_name}'. Available: {', '.join(_TTS_REGISTRY)}"
            )
        cls = _import_class(dotted)
        return cast("TTSProvider", cls(settings, http_client))

    @staticmethod
    def get_image_provider(
        provider_name: str,
        settings: Settings,
        http_client: httpx.AsyncClient,
    ) -> ImageProvider:
        """Instantiate an image provider.

        Available providers:
          - ``fal_ai``     — fal.ai Flux API (production default)
          - ``local_flux`` — Self-hosted Flux Dev on GPU
        """
        dotted = _IMAGE_REGISTRY.get(provider_name)
        if dotted is None:
            raise ValueError(
                f"Unknown image provider '{provider_name}'. Available: {', '.join(_IMAGE_REGISTRY)}"
            )
        cls = _import_class(dotted)
        return cast("ImageProvider", cls(settings, http_client))

    @staticmethod
    def get_music_provider(
        provider_name: str,
        settings: Settings,
        http_client: httpx.AsyncClient,
    ) -> MusicProvider:
        """Instantiate a music provider.

        Available providers:
          - ``epidemic_sound_library`` — Curated Epidemic Sound tracks (default)
          - ``ace_step``               — Self-hosted ACE-Step v1.5 generation
        """
        dotted = _MUSIC_REGISTRY.get(provider_name)
        if dotted is None:
            raise ValueError(
                f"Unknown music provider '{provider_name}'. Available: {', '.join(_MUSIC_REGISTRY)}"
            )
        cls = _import_class(dotted)
        return cast("MusicProvider", cls(settings, http_client))

    @staticmethod
    def get_llm_provider(
        provider_name: str,
        settings: Settings,
        http_client: httpx.AsyncClient,
    ) -> LLMProvider:
        """Instantiate an LLM provider.

        Available providers:
          - ``anthropic`` — Claude API (only option for quality-sensitive tasks)
        """
        dotted = _LLM_REGISTRY.get(provider_name)
        if dotted is None:
            raise ValueError(
                f"Unknown LLM provider '{provider_name}'. Available: {', '.join(_LLM_REGISTRY)}"
            )
        cls = _import_class(dotted)
        return cast("LLMProvider", cls(settings, http_client))

    @staticmethod
    def available_tts_providers() -> list[str]:
        return list(_TTS_REGISTRY)

    @staticmethod
    def available_image_providers() -> list[str]:
        return list(_IMAGE_REGISTRY)

    @staticmethod
    def available_music_providers() -> list[str]:
        return list(_MUSIC_REGISTRY)

    @staticmethod
    def available_llm_providers() -> list[str]:
        return list(_LLM_REGISTRY)


__all__ = [
    "ImageProvider",
    "ImageResult",
    "LLMProvider",
    "LLMResult",
    "MusicProvider",
    "MusicResult",
    "ProviderFactory",
    "TTSProvider",
    "TTSResult",
    "VoiceInfo",
]
