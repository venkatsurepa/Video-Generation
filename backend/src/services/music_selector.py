from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, cast

import structlog

if TYPE_CHECKING:
    import httpx

    from src.config import Settings
    from src.models.music import (
        MoodCategory,
        MusicLibraryStatus,
        MusicResult,
        MusicTrack,
    )
    from src.services.providers.base import MusicProvider as MusicProviderBase

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class NoTracksAvailableError(Exception):
    """Raised when no tracks match the selection criteria."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MusicSelector:
    """Selects music from a curated library for crime documentary videos.

    Primary source: 20-30 pre-downloaded Epidemic Sound tracks organised
    into five mood categories.  Secondary (optional): Suno API for custom
    generation of channel stingers or case-specific mood pieces.

    Music files live under ``backend/assets/music/{mood_category}/`` and
    are registered in ``backend/assets/music/library.json``.
    """

    _LIBRARY_PATH = (
        Path(__file__).resolve().parent.parent.parent / "assets" / "music" / "library.json"
    )

    # BPM ranges per mood category (reference / validation).
    _MOOD_BPM: dict[str, tuple[int, int]] = {
        "suspenseful_investigation": (80, 100),
        "emotional_reflective": (60, 80),
        "dramatic_reveal": (100, 120),
        "establishing_neutral": (70, 90),
        "eerie_dark_ambient": (50, 70),
    }

    _VALID_MOODS = frozenset(_MOOD_BPM)

    # Free-form script mood tags → canonical MoodCategory.
    _MOOD_MAP: dict[str, str] = {
        # suspenseful_investigation
        "tense": "suspenseful_investigation",
        "investigation": "suspenseful_investigation",
        "suspense": "suspenseful_investigation",
        "suspenseful": "suspenseful_investigation",
        "procedural": "suspenseful_investigation",
        # emotional_reflective
        "sad": "emotional_reflective",
        "emotional": "emotional_reflective",
        "victim_story": "emotional_reflective",
        "reflective": "emotional_reflective",
        "melancholy": "emotional_reflective",
        "somber": "emotional_reflective",
        # dramatic_reveal
        "climax": "dramatic_reveal",
        "reveal": "dramatic_reveal",
        "twist": "dramatic_reveal",
        "dramatic": "dramatic_reveal",
        "intense": "dramatic_reveal",
        # establishing_neutral
        "introduction": "establishing_neutral",
        "context": "establishing_neutral",
        "neutral": "establishing_neutral",
        "establishing": "establishing_neutral",
        "documentary": "establishing_neutral",
        # eerie_dark_ambient
        "dark": "eerie_dark_ambient",
        "eerie": "eerie_dark_ambient",
        "ominous": "eerie_dark_ambient",
        "horror": "eerie_dark_ambient",
        "creepy": "eerie_dark_ambient",
        "ambient": "eerie_dark_ambient",
        "unsettling": "eerie_dark_ambient",
    }

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
        provider: MusicProviderBase | None = None,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._provider = provider
        self._library_cache: list[MusicTrack] | None = None

    # ------------------------------------------------------------------
    # Library loading
    # ------------------------------------------------------------------

    def _load_library(self) -> list[MusicTrack]:
        """Load and cache the music library from ``library.json``.

        Relative ``file_path`` / ``stems_path`` values are resolved against
        the ``assets/music/`` directory so callers always receive absolute
        paths.
        """
        if self._library_cache is not None:
            return self._library_cache

        from src.models.music import MusicTrack

        if not self._LIBRARY_PATH.exists():
            logger.warning(
                "music_library_missing",
                path=str(self._LIBRARY_PATH),
            )
            self._library_cache = []
            return self._library_cache

        try:
            raw = json.loads(
                self._LIBRARY_PATH.read_text(encoding="utf-8"),
            )
        except json.JSONDecodeError:
            logger.warning(
                "music_library_invalid_json",
                path=str(self._LIBRARY_PATH),
            )
            self._library_cache = []
            return self._library_cache

        music_dir = self._LIBRARY_PATH.parent
        tracks: list[MusicTrack] = []
        for entry in raw.get("tracks", []):
            # Resolve relative paths against assets/music/.
            if "file_path" in entry and not Path(entry["file_path"]).is_absolute():
                entry["file_path"] = str(music_dir / entry["file_path"])
            if entry.get("stems_path") and not Path(entry["stems_path"]).is_absolute():
                entry["stems_path"] = str(music_dir / entry["stems_path"])
            try:
                tracks.append(MusicTrack.model_validate(entry))
            except Exception:
                logger.warning(
                    "music_track_parse_error",
                    track_id=entry.get("id", "unknown"),
                )

        self._library_cache = tracks
        logger.info("music_library_loaded", count=len(tracks))
        return self._library_cache

    def reload_library(self) -> None:
        """Invalidate the cached library so it reloads on next access."""
        self._library_cache = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def select_track(
        self,
        mood: str,
        duration_seconds: float,
        exclude_ids: list[str] | None = None,
    ) -> MusicResult:
        """Select the best-matching track from the curated library.

        1. Normalise *mood* to a canonical :data:`MoodCategory`.
        2. Filter by mood, Content ID safety, and exclude list.
        3. Score by duration fit — prefer tracks >= *duration_seconds*
           with minimal excess.
        4. Return the top match as a :class:`MusicResult`.

        Raises :class:`NoTracksAvailableError` when the library has no
        eligible tracks.
        """
        from src.models.music import MusicResult, MusicTrack

        # Delegate to injected provider if present (e.g., ACE-Step)
        if self._provider is not None:
            provider_result = await self._provider.generate(
                mood,
                duration_seconds,
                exclude_ids=exclude_ids or [],
            )
            track = MusicTrack(
                id=f"provider_{provider_result.provider}",
                title=provider_result.title or "Generated track",
                artist=provider_result.provider,
                source="custom",
                mood_category=self._match_mood_to_script(mood),
                bpm=provider_result.bpm or 80,
                duration_seconds=provider_result.duration_seconds,
                file_path=provider_result.file_path,
            )
            return MusicResult(
                track=track,
                file_path=provider_result.file_path,
                cost_usd=provider_result.cost_usd,
                selection_reason=f"Generated by {provider_result.provider}",
            )

        category = self._match_mood_to_script(mood)
        library = self._load_library()
        excluded = set(exclude_ids or [])

        # Primary filter: matching mood + safe + not excluded + file exists.
        candidates = [
            t
            for t in library
            if t.mood_category == category
            and t.content_id_safe
            and t.id not in excluded
            and os.path.isfile(t.file_path)
        ]

        # Fallback: any mood, keep other filters.
        if not candidates:
            await logger.awarning(
                "mood_fallback",
                requested=category,
                library_size=len(library),
            )
            candidates = [
                t
                for t in library
                if t.content_id_safe and t.id not in excluded and os.path.isfile(t.file_path)
            ]

        if not candidates:
            raise NoTracksAvailableError(
                f"No tracks available for mood '{mood}' "
                f"(category '{category}', "
                f"library={len(library)}, excluded={len(excluded)})"
            )

        # Score: (0, excess) for tracks >= target, (1, deficit) otherwise.
        def _score(track: MusicTrack) -> tuple[int, float]:
            diff = track.duration_seconds - duration_seconds
            if diff >= 0:
                return (0, diff)
            return (1, -diff)

        candidates.sort(key=_score)
        best = candidates[0]

        reason = (
            f"Selected '{best.title}' by {best.artist} "
            f"({best.mood_category}, {best.bpm} BPM, "
            f"{best.duration_seconds:.0f}s) "
            f"for requested mood '{mood}' / {duration_seconds:.0f}s"
        )
        await logger.ainfo(
            "track_selected",
            track_id=best.id,
            title=best.title,
            mood=category,
            duration=best.duration_seconds,
        )

        return MusicResult(
            track=best,
            file_path=best.file_path,
            cost_usd=Decimal("0"),
            selection_reason=reason,
        )

    async def generate_custom_track(self, prompt: str, duration_seconds: float) -> MusicResult:
        """Generate a custom track via Suno API.

        .. note::

            Suno does not offer a stable public REST API as of March 2026.
            Generate tracks manually via the Suno web UI, download the WAV,
            place it under ``backend/assets/music/{mood_category}/``, and
            register it in ``library.json``.  Set the profile to PRIVATE
            to prevent Content ID trolling.  Keep generation receipts
            (prompt + response ID) for dispute purposes.
        """
        raise NotImplementedError(
            "Suno does not provide a stable public API. "
            "Generate tracks manually at https://suno.com, set profile to "
            "PRIVATE, and register them in "
            "backend/assets/music/library.json."
        )

    async def download_epidemic_sound_track(self, track_id: str, include_stems: bool = True) -> str:
        """Download a track (and optional stems) from Epidemic Sound.

        .. note::

            Epidemic Sound does not expose a public download API.
            Manual workflow:

            1. Browse epidemicsound.com and find tracks matching a mood.
            2. Download the full mix WAV **and** stems (individual
               instrument tracks) — stems are critical for clean ducking
               under narration.
            3. Place files in ``backend/assets/music/{mood_category}/``.
            4. Register the track in ``backend/assets/music/library.json``
               with ``stems_path`` pointing to the stems directory.
        """
        raise NotImplementedError(
            "Epidemic Sound does not provide a public download API. "
            "Download tracks manually from epidemicsound.com, place WAV "
            "files in backend/assets/music/{mood_category}/, and register "
            "them in library.json. Include stems when available."
        )

    def get_library_status(self) -> MusicLibraryStatus:
        """Return count of tracks per mood category and total duration."""
        from src.models.music import MusicLibraryStatus

        library = self._load_library()
        per_mood: dict[str, int] = {m: 0 for m in self._VALID_MOODS}
        total_seconds = 0.0

        for track in library:
            per_mood[track.mood_category] = per_mood.get(track.mood_category, 0) + 1
            total_seconds += track.duration_seconds

        return MusicLibraryStatus(
            total_tracks=len(library),
            tracks_per_mood=per_mood,
            total_duration_minutes=round(total_seconds / 60, 1),
        )

    def _match_mood_to_script(self, script_mood: str) -> MoodCategory:
        """Map a free-form script mood tag to a canonical MoodCategory.

        Returns *script_mood* unchanged if it already matches a category.
        Falls back to ``establishing_neutral`` for unrecognised tags.

        Mapping examples::

            "tense"        → suspenseful_investigation
            "victim_story" → emotional_reflective
            "climax"       → dramatic_reveal
            "introduction" → establishing_neutral
            "ominous"      → eerie_dark_ambient
        """
        normalised = script_mood.strip().lower().replace(" ", "_")

        if normalised in self._VALID_MOODS:
            return cast("MoodCategory", normalised)

        category = self._MOOD_MAP.get(normalised)
        if category is not None:
            return cast("MoodCategory", category)

        logger.warning(
            "mood_mapping_fallback",
            raw=script_mood,
            resolved="establishing_neutral",
        )
        return "establishing_neutral"
