"""Per-niche prompt registry.

Each niche module re-exports (or defines) the prompt constants the script
generation pipeline expects. Use ``get_prompts_for_niche()`` to look up the
correct module for a given channel.

The crime module re-exports the existing constants from
``src.services.script_generator`` so the existing financial-crime pipeline
remains byte-identical. The travel module defines its own constants for the
warm conversational travel-safety voice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.services.prompts import crime_prompts, travel_prompts

if TYPE_CHECKING:
    from types import ModuleType

PROMPT_REGISTRY: dict[str, ModuleType] = {
    "financial_crime": crime_prompts,
    "true_crime": crime_prompts,
    "true_crime_general": crime_prompts,
    "travel_safety": travel_prompts,
}

DEFAULT_NICHE = "financial_crime"


def get_prompts_for_niche(niche: str | None) -> ModuleType:
    """Return the prompts module for a niche, falling back to crime prompts."""
    if not niche:
        return PROMPT_REGISTRY[DEFAULT_NICHE]
    return PROMPT_REGISTRY.get(niche, PROMPT_REGISTRY[DEFAULT_NICHE])


__all__ = ["DEFAULT_NICHE", "PROMPT_REGISTRY", "get_prompts_for_niche"]
