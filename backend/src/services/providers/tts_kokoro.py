"""Kokoro-82M TTS provider — self-hosted, Apache 2.0 license.

Kokoro-82M (https://huggingface.co/hexgrad/Kokoro-82M):
  - Only 82M parameters — runs on CPU (no GPU needed)
  - Apache 2.0 license — fully permissive
  - Can run on Railway, Fly.io, or any VPS ($5-10/month)
  - Quality: good for secondary channels, not flagship
  - ~24 kHz output (lower than Fish Audio's 48 kHz)
  - Supports multiple languages and styles

Deployment:
  - Docker container with FastAPI wrapper
  - CPU inference: ~1x real-time (10s audio in ~10s)
  - RAM: ~512 MB
  - Cost: essentially free on existing infrastructure

API contract:
  POST http://{host}:{port}/v1/tts
  Body: {"text": "...", "voice": "af_sarah", "speed": 1.0}
  Response: audio/wav
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

# Kokoro runs on CPU — cost is just server hosting.
# At $10/month for a VPS handling all TTS, amortised per-char cost is negligible.
_COST_PER_CHAR = Decimal("0.0000001")  # ~$0/char (hosting amortised)
_SAMPLE_RATE = 24_000
_GENERATION_TIMEOUT = 180.0  # CPU inference is slower

# Default Kokoro voices
_DEFAULT_VOICES = [
    VoiceInfo(voice_id="af_sarah", name="Sarah (American Female)", provider="kokoro"),
    VoiceInfo(voice_id="am_michael", name="Michael (American Male)", provider="kokoro"),
    VoiceInfo(voice_id="bf_emma", name="Emma (British Female)", provider="kokoro"),
    VoiceInfo(voice_id="bm_george", name="George (British Male)", provider="kokoro"),
]


class KokoroProvider(TTSProvider):
    """Self-hosted Kokoro-82M TTS on CPU infrastructure.

    Best for: secondary channels, podcast feeds, bulk narration where
    cost matters more than top-tier audio quality.  Not recommended for
    flagship channels where Fish Audio or Chatterbox is preferred.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._base_url = (
            getattr(getattr(settings, "self_hosting", None), "tts_url", "")
            or "http://localhost:8881"
        )

    @async_retry(max_attempts=2, base_delay=5.0)
    async def generate(
        self,
        text: str,
        voice_id: str,
        **kwargs: Any,
    ) -> TTSResult:
        char_count = len(text)
        speed = kwargs.get("speed", 1.0)

        payload = {
            "text": text,
            "voice": voice_id or "af_sarah",
            "speed": speed,
            "format": "wav",
        }

        fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="crimemill_kk_")
        try:
            with open(fd, "wb") as f:
                async with self._http.stream(
                    "POST",
                    f"{self._base_url}/v1/tts",
                    json=payload,
                    timeout=_GENERATION_TIMEOUT,
                ) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        f.write(chunk)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

        duration, rate, file_size = _read_wav_metadata(tmp_path)
        cost = (_COST_PER_CHAR * char_count).quantize(Decimal("0.000001"))

        return TTSResult(
            file_path=tmp_path,
            duration_seconds=round(duration, 2),
            sample_rate=rate,
            file_size_bytes=file_size,
            character_count=char_count,
            cost_usd=cost,
            provider=self.provider_name(),
            voice_id=voice_id or "af_sarah",
        )

    async def list_voices(self) -> list[VoiceInfo]:
        """Return the built-in Kokoro voice list."""
        try:
            resp = await self._http.get(
                f"{self._base_url}/v1/voices",
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return [
                VoiceInfo(
                    voice_id=v.get("id", ""),
                    name=v.get("name", ""),
                    provider=self.provider_name(),
                )
                for v in data.get("voices", [])
            ]
        except Exception:
            return list(_DEFAULT_VOICES)

    def cost_per_character(self) -> Decimal:
        return _COST_PER_CHAR

    def provider_name(self) -> str:
        return "kokoro"

    def is_self_hosted(self) -> bool:
        return True


def _read_wav_metadata(file_path: str) -> tuple[float, int, int]:
    file_size = Path(file_path).stat().st_size
    with wave.open(file_path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        duration = frames / rate if rate > 0 else 0.0
    return duration, rate, file_size
