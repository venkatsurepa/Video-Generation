"""Epidemic Sound library music provider — wraps the existing music selector.

Uses a curated local library of pre-downloaded Epidemic Sound tracks.
Cost is $0 per selection (tracks are pre-paid via Epidemic Sound subscription).
Tracks are organised into 5 mood categories with BPM-based selection.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from src.services.providers.base import MusicProvider, MusicResult

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger()

_LIBRARY_PATH = Path(__file__).resolve().parents[3] / "assets" / "music" / "library.json"

_MOOD_MAP: dict[str, str] = {
    "tense": "suspenseful_investigation",
    "investigation": "suspenseful_investigation",
    "suspense": "suspenseful_investigation",
    "suspenseful": "suspenseful_investigation",
    "sad": "emotional_reflective",
    "emotional": "emotional_reflective",
    "reflective": "emotional_reflective",
    "somber": "emotional_reflective",
    "climax": "dramatic_reveal",
    "reveal": "dramatic_reveal",
    "dramatic": "dramatic_reveal",
    "intense": "dramatic_reveal",
    "introduction": "establishing_neutral",
    "context": "establishing_neutral",
    "neutral": "establishing_neutral",
    "dark": "eerie_dark_ambient",
    "eerie": "eerie_dark_ambient",
    "ominous": "eerie_dark_ambient",
    "creepy": "eerie_dark_ambient",
    "ambient": "eerie_dark_ambient",
}

_VALID_MOODS = frozenset(
    {
        "suspenseful_investigation",
        "emotional_reflective",
        "dramatic_reveal",
        "establishing_neutral",
        "eerie_dark_ambient",
    }
)


class EpidemicSoundLibraryProvider(MusicProvider):
    """Curated Epidemic Sound track library.

    Selects from pre-downloaded tracks based on mood and duration.
    Cost per selection: $0 (subscription-based).
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._cache: list[dict[str, Any]] | None = None

    async def generate(
        self,
        prompt: str,
        duration_seconds: float,
        **kwargs: Any,
    ) -> MusicResult:
        """Select a track matching the mood prompt and target duration."""
        mood = self._resolve_mood(prompt)
        tracks = self._load_library()
        exclude = set(kwargs.get("exclude_ids", []))

        # Filter by mood + file existence
        candidates = [
            t
            for t in tracks
            if t.get("mood_category") == mood
            and t.get("content_id_safe", True)
            and t.get("id") not in exclude
            and os.path.isfile(t.get("file_path", ""))
        ]

        # Fallback: any mood
        if not candidates:
            candidates = [
                t
                for t in tracks
                if t.get("content_id_safe", True)
                and t.get("id") not in exclude
                and os.path.isfile(t.get("file_path", ""))
            ]

        if not candidates:
            raise RuntimeError(f"No tracks available for mood '{prompt}'")

        # Score by duration fit
        def _score(t: dict[str, Any]) -> tuple[int, float]:
            diff = t.get("duration_seconds", 0) - duration_seconds
            return (0, diff) if diff >= 0 else (1, -diff)

        candidates.sort(key=_score)
        best = candidates[0]

        return MusicResult(
            file_path=best["file_path"],
            duration_seconds=best.get("duration_seconds", 0),
            cost_usd=Decimal("0"),
            provider=self.provider_name(),
            title=best.get("title", ""),
            bpm=best.get("bpm"),
        )

    def cost_per_generation(self) -> Decimal:
        return Decimal("0")

    def provider_name(self) -> str:
        return "epidemic_sound_library"

    def _load_library(self) -> list[dict[str, Any]]:
        if self._cache is not None:
            return self._cache

        if not _LIBRARY_PATH.exists():
            self._cache = []
            return self._cache

        try:
            raw = json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            self._cache = []
            return self._cache

        music_dir = _LIBRARY_PATH.parent
        tracks = raw.get("tracks", [])
        for t in tracks:
            if "file_path" in t and not Path(t["file_path"]).is_absolute():
                t["file_path"] = str(music_dir / t["file_path"])

        self._cache = tracks
        return self._cache

    @staticmethod
    def _resolve_mood(prompt: str) -> str:
        normalised = prompt.strip().lower().replace(" ", "_")
        if normalised in _VALID_MOODS:
            return normalised
        return _MOOD_MAP.get(normalised, "establishing_neutral")
