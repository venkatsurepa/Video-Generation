"""Per-niche script generators.

The financial-crime pipeline uses ``src.services.script_generator.ScriptGenerator``
directly (it predates this package). Newer niches add their own generators
here and are routed through ``src.services.niche_router.NicheRouter``.
"""

from __future__ import annotations

from src.services.script_generators.travel_safety_generator import (
    ImagePrompt,
    RhyoReport,
    Scene,
    ScriptArtifacts,
    TravelSafetyScriptGenerator,
    VideoDestination,
    parse_rhyo_report,
)

__all__ = [
    "ImagePrompt",
    "RhyoReport",
    "Scene",
    "ScriptArtifacts",
    "TravelSafetyScriptGenerator",
    "VideoDestination",
    "parse_rhyo_report",
]
