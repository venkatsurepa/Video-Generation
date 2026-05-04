from __future__ import annotations

import tempfile
import wave
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from src.models.voiceover import VoiceInfo, VoiceoverResult
from src.utils.retry import async_retry

if TYPE_CHECKING:
    import httpx

    from src.config import Settings
    from src.models.script import SceneBreakdown
    from src.services.providers.base import TTSProvider as TTSProviderBase

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Fish Audio S2 constants
# ---------------------------------------------------------------------------
_BASE_URL = "https://api.fish.audio"
_TTS_ENDPOINT = "/v1/tts"
_MODEL = "speech-01-turbo"
_SAMPLE_RATE = 44_100  # Fish Audio WAV supports 8000/16000/24000/32000/44100; 48000 is rejected with HTTP 400
_FORMAT = "wav"
_GENERATION_TIMEOUT = 120.0

# Fish Audio Plus plan: $11 / 200 min ≈ 170 000 chars → ~$0.0000647/char
_COST_PER_CHAR = Decimal("0.0000647")

# Scene stitching
_SCENE_SEPARATOR = "\n\n"
_PAUSE_TAG = "[pause]"


class VoiceoverGenerator:
    """Generates narration audio via Fish Audio S2 TTS API.

    Supports plain text and scene-based generation with inline emotion tags.
    Produces WAV at 48 kHz for downstream pipeline processing.

    Accepts an optional ``provider`` parameter to use a different TTS backend
    (e.g., self-hosted Chatterbox or Kokoro).  When a provider is given, all
    generation calls are delegated to it; the result is adapted to the existing
    VoiceoverResult format so downstream code is unchanged.
    """

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
        provider: TTSProviderBase | None = None,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._api_key = settings.fish_audio.api_key
        self._provider = provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_voiceover(
        self,
        script_text: str,
        voice_id: str,
        emotion_tags: dict[str, str] | None = None,
    ) -> VoiceoverResult:
        """Generate voiceover from text via Fish Audio S2.

        Args:
            script_text: Narration text to synthesize.
            voice_id: Fish Audio voice reference ID.
            emotion_tags: Optional emotion directives to prepend, e.g.
                ``{"tone": "[calm, measured tone]"}``.  Values are joined
                and placed before the script text.

        Returns:
            VoiceoverResult with file path, audio metadata, and cost.
        """
        text = _apply_emotion_tags(script_text, emotion_tags)
        char_count = len(text)

        # Delegate to injected provider if present
        if self._provider is not None:
            await logger.ainfo(
                "voiceover_started",
                provider=self._provider.provider_name(),
                voice_id=voice_id,
                character_count=char_count,
            )
            result = await self._provider.generate(text, voice_id)
            await logger.ainfo(
                "voiceover_completed",
                provider=self._provider.provider_name(),
                duration_seconds=result.duration_seconds,
                cost_usd=str(result.cost_usd),
            )
            return VoiceoverResult(
                file_path=result.file_path,
                duration_seconds=result.duration_seconds,
                sample_rate=result.sample_rate,
                file_size_bytes=result.file_size_bytes,
                character_count=result.character_count,
                cost_usd=result.cost_usd,
                voice_id=result.voice_id or voice_id,
            )

        await logger.ainfo(
            "voiceover_started",
            voice_id=voice_id,
            character_count=char_count,
        )

        # Validate voice exists before burning API credits
        await self.get_voice(voice_id)

        file_path = await self._call_tts(text, voice_id)
        duration, sample_rate, file_size = _read_wav_metadata(file_path)
        cost = _estimate_cost(char_count)

        await logger.ainfo(
            "voiceover_completed",
            voice_id=voice_id,
            duration_seconds=round(duration, 2),
            character_count=char_count,
            cost_usd=str(cost),
        )

        return VoiceoverResult(
            file_path=file_path,
            duration_seconds=round(duration, 2),
            sample_rate=sample_rate,
            file_size_bytes=file_size,
            character_count=char_count,
            cost_usd=cost,
            voice_id=voice_id,
        )

    async def generate_voiceover_from_scenes(
        self,
        scenes: list[SceneBreakdown],
        voice_id: str,
    ) -> VoiceoverResult:
        """Generate one continuous voiceover from a scene breakdown list.

        Embeds each scene's ``emotion_tag``, inserts ``[pause]`` markers at
        ad-break positions, and concatenates everything into a single
        long-form text for Fish Audio (one API call, one audio file).

        Args:
            scenes: Ordered scene breakdowns with narration and emotion tags.
            voice_id: Fish Audio voice reference ID.

        Returns:
            VoiceoverResult for the full continuous audio file.
        """
        text = _build_scene_text(scenes)

        await logger.ainfo(
            "scene_voiceover_started",
            voice_id=voice_id,
            scene_count=len(scenes),
            character_count=len(text),
        )

        return await self.generate_voiceover(script_text=text, voice_id=voice_id)

    @async_retry(max_attempts=2, base_delay=1.0, max_delay=30.0)
    async def list_voices(self) -> list[VoiceInfo]:
        """List available voices from Fish Audio."""
        resp = await self._http.get(
            f"{_BASE_URL}/model",
            headers=self._headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        return [_parse_voice(v) for v in items]

    @async_retry(max_attempts=2, base_delay=1.0, max_delay=30.0)
    async def get_voice(self, voice_id: str) -> VoiceInfo:
        """Fetch metadata for a single Fish Audio voice.

        Raises:
            httpx.HTTPStatusError: 404 if voice_id does not exist.
        """
        resp = await self._http.get(
            f"{_BASE_URL}/model/{voice_id}",
            headers=self._headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        return _parse_voice(resp.json())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    @async_retry(max_attempts=3, base_delay=2.0, max_delay=60.0)
    async def _call_tts(self, text: str, voice_id: str) -> str:
        """POST to Fish Audio TTS and stream the WAV response to a temp file.

        Returns:
            Filesystem path of the generated WAV file.
        """
        payload = {
            "model": _MODEL,
            "reference_id": voice_id,
            "text": text,
            "format": _FORMAT,
            "sample_rate": _SAMPLE_RATE,
        }

        fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="crimemill_vo_")
        try:
            with open(fd, "wb") as f:
                async with self._http.stream(
                    "POST",
                    f"{_BASE_URL}{_TTS_ENDPOINT}",
                    json=payload,
                    headers=self._headers(),
                    timeout=_GENERATION_TIMEOUT,
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

        return tmp_path


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _apply_emotion_tags(text: str, tags: dict[str, str] | None) -> str:
    """Prepend emotion tag values to the script text."""
    if not tags:
        return text
    prefix = " ".join(tags.values())
    return f"{prefix} {text}"


def _build_scene_text(scenes: list[SceneBreakdown]) -> str:
    """Assemble scenes into a single narration with emotion tags and pauses."""
    parts: list[str] = []
    for scene in scenes:
        if scene.emotion_tag:
            tag = scene.emotion_tag
            if not tag.startswith("["):
                tag = f"[{tag}]"
            chunk = f"{tag} {scene.narration_text}"
        else:
            chunk = scene.narration_text

        parts.append(chunk)

        if scene.is_ad_break:
            parts.append(_PAUSE_TAG)

    return _SCENE_SEPARATOR.join(parts)


def _parse_voice(data: dict[str, object]) -> VoiceInfo:
    """Convert a Fish Audio API voice dict to a VoiceInfo model."""
    return VoiceInfo(
        voice_id=str(data["_id"]),
        name=str(data.get("title", "")),
        description=str(data.get("description", "")),
        preview_url=str(data.get("cover_image", "")),
        languages=data.get("languages", []),  # type: ignore[arg-type]
        created_at=data.get("created_at"),  # type: ignore[arg-type]
    )


def _read_wav_metadata(file_path: str) -> tuple[float, int, int]:
    """Extract duration, sample rate, and file size from a WAV file."""
    file_size = Path(file_path).stat().st_size
    with wave.open(file_path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        duration = frames / rate if rate > 0 else 0.0
    return duration, rate, file_size


def _estimate_cost(character_count: int) -> Decimal:
    """Estimate USD cost based on Fish Audio Plus plan rates.

    Plus plan: $11/month for 200 minutes (~850 chars/min).
    Effective rate ≈ $0.0000647 per character.
    """
    return (_COST_PER_CHAR * character_count).quantize(Decimal("0.000001"))
