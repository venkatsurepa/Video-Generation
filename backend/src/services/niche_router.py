"""Niche router — maps channel.niche to per-niche pipeline components.

Lightweight, additive routing layer. The crime pipeline does not need to know
about niches at all; the orchestrator's script handler asks the router which
generator to use given a channel's niche, and the router returns a callable
that produces the script artifacts.

Today the router only routes script generation. As travel-safety grows,
add accessors for topic_sources, thumbnail archetypes, and affiliate config.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.services.prompts import DEFAULT_NICHE, get_prompts_for_niche

if TYPE_CHECKING:
    from types import ModuleType

    import httpx

    from src.config import Settings
    from src.services.script_generators.travel_safety_generator import (
        TravelSafetyScriptGenerator,
    )


# Channels.niche allowed values (mirrors the DB CHECK constraint).
ALLOWED_NICHES = frozenset(
    {
        "financial_crime",
        "travel_safety",
        "true_crime",
        "business_documentary",
        "educational",
        "other",
    }
)

TRAVEL_NICHES = frozenset({"travel_safety"})


def normalize_niche(niche: str | None) -> str:
    """Return a niche string guaranteed to be in ALLOWED_NICHES."""
    if niche and niche in ALLOWED_NICHES:
        return niche
    return DEFAULT_NICHE


def is_travel_niche(niche: str | None) -> bool:
    return normalize_niche(niche) in TRAVEL_NICHES


class NicheRouter:
    """Per-channel router. Construct once per pipeline run with the niche."""

    def __init__(self, niche: str | None) -> None:
        self.niche: str = normalize_niche(niche)

    @property
    def prompts(self) -> ModuleType:
        """The prompts module for this niche (crime_prompts or travel_prompts)."""
        return get_prompts_for_niche(self.niche)

    @property
    def is_travel(self) -> bool:
        return is_travel_niche(self.niche)

    # ---------------------------------------------------------- static API
    # Static helpers requested by the niche-routing spec. They mirror the
    # instance API and let callers route without constructing a router.

    @staticmethod
    def get_script_generator_class(niche: str | None) -> type:
        """Return the script generator CLASS for a niche.

        ``travel_safety`` → ``TravelSafetyScriptGenerator``.
        Everything else → the legacy crime ``ScriptGenerator``.
        """
        if normalize_niche(niche) == "travel_safety":
            from src.services.script_generators.travel_safety_generator import (
                TravelSafetyScriptGenerator,
            )

            return TravelSafetyScriptGenerator
        from src.services.script_generator import ScriptGenerator

        return ScriptGenerator

    @staticmethod
    def get_prompts(niche: str | None) -> ModuleType:
        """Return the prompts module for a niche."""
        return get_prompts_for_niche(normalize_niche(niche))

    # ---------------------------------------------------------- instance API

    def build_travel_generator(
        self, settings: Settings, http_client: httpx.AsyncClient
    ) -> TravelSafetyScriptGenerator:
        """Construct the travel-safety generator. Only valid for travel niches."""
        if not self.is_travel:
            raise ValueError(f"build_travel_generator() called for non-travel niche {self.niche!r}")
        # Imported lazily so importing niche_router doesn't pull in anthropic
        # for callers that only need prompt routing.
        from src.services.script_generators.travel_safety_generator import (
            TravelSafetyScriptGenerator,
        )

        return TravelSafetyScriptGenerator(settings, http_client)


__all__ = [
    "ALLOWED_NICHES",
    "NicheRouter",
    "TRAVEL_NICHES",
    "is_travel_niche",
    "normalize_niche",
]
