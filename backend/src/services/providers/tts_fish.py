"""Fish Audio S2 TTS provider — wraps the existing Fish Audio API integration.

Fish Audio Plus plan: $11/month for 200 minutes (~170,000 chars).
Effective rate: ~$0.0000647 per character.
API: https://api.fish.audio/v1/tts
"""

from __future__ import annotations

import tempfile
import wave
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from src.services.providers.base import TTSProvider, TTSResult, VoiceInfo
from src.utils.retry import async_retry

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger()

_BASE_URL = "https://api.fish.audio"
_TTS_ENDPOINT = "/v1/tts"
_MODEL = "speech-01-turbo"
_SAMPLE_RATE = 48_000
_FORMAT = "wav"
_GENERATION_TIMEOUT = 120.0
_COST_PER_CHAR = Decimal("0.0000647")


class FishAudioProvider(TTSProvider):
    """Fish Audio S2 cloud TTS.

    Production-grade quality for flagship channels.  Uses the speech-01-turbo
    model at 48 kHz sample rate.  Supports emotion tags and voice cloning.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._api_key = settings.fish_audio.api_key

    async def generate(
        self,
        text: str,
        voice_id: str,
        **kwargs: Any,
    ) -> TTSResult:
        char_count = len(text)
        file_path = await self._call_tts(text, voice_id)
        duration, sample_rate, file_size = _read_wav_metadata(file_path)
        cost = (_COST_PER_CHAR * char_count).quantize(Decimal("0.000001"))

        return TTSResult(
            file_path=file_path,
            duration_seconds=round(duration, 2),
            sample_rate=sample_rate,
            file_size_bytes=file_size,
            character_count=char_count,
            cost_usd=cost,
            provider=self.provider_name(),
            voice_id=voice_id,
        )

    @async_retry(max_attempts=2, base_delay=1.0, max_delay=30.0)
    async def list_voices(self) -> list[VoiceInfo]:
        resp = await self._http.get(
            f"{_BASE_URL}/model",
            headers=self._headers(),
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", [])
        return [
            VoiceInfo(
                voice_id=str(v["_id"]),
                name=str(v.get("title", "")),
                description=str(v.get("description", "")),
                preview_url=str(v.get("cover_image", "")),
                languages=v.get("languages", []),
                provider=self.provider_name(),
            )
            for v in items
        ]

    def cost_per_character(self) -> Decimal:
        return _COST_PER_CHAR

    def provider_name(self) -> str:
        return "fish_audio"

    # -- internal --

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    @async_retry(max_attempts=3, base_delay=2.0, max_delay=60.0)
    async def _call_tts(self, text: str, voice_id: str) -> str:
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


def _read_wav_metadata(file_path: str) -> tuple[float, int, int]:
    file_size = Path(file_path).stat().st_size
    with wave.open(file_path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        duration = frames / rate if rate > 0 else 0.0
    return duration, rate, file_size
