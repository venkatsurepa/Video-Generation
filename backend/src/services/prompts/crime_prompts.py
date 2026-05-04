"""Financial-crime prompt module — re-exports existing constants.

This module is a thin re-export shim. The actual prompt strings still live
inside ``src.services.script_generator`` so the existing crime pipeline stays
byte-identical and untouched. New niches (e.g. travel_safety) can sit alongside
this module in ``src.services.prompts``.

If/when the crime prompts are extracted into their own module, the import
below is the only line that needs to change.
"""

from __future__ import annotations

from src.services.script_generator import (
    DESCRIPTION_SYSTEM_PROMPT,
    IMAGE_PROMPT_SYSTEM_PROMPT,
    SCENE_BREAKDOWN_SYSTEM_PROMPT,
    SCRIPT_SYSTEM_PROMPT,
    TITLE_SYSTEM_PROMPT,
)

NICHE = "financial_crime"

__all__ = [
    "DESCRIPTION_SYSTEM_PROMPT",
    "IMAGE_PROMPT_SYSTEM_PROMPT",
    "NICHE",
    "SCENE_BREAKDOWN_SYSTEM_PROMPT",
    "SCRIPT_SYSTEM_PROMPT",
    "TITLE_SYSTEM_PROMPT",
]
