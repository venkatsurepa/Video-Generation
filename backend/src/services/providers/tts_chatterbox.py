"""Chatterbox TTS provider — self-hosted, MIT license.

Chatterbox (https://github.com/resemble-ai/chatterbox):
  - Beats ElevenLabs 63.8% in blind tests
  - MIT license — no usage restrictions
  - Requires GPU: RTX 3090/4090 or cloud (RunPod Serverless, Vast.ai)
  - Cold start: <10s
  - Savings: ~$186-516/month vs Fish Audio at scale (50-150 videos/month)

Deployment options:
  1. RunPod Serverless — $0.00031/s on RTX 4090, auto-scales to zero
  2. Vast.ai — $0.40-0.80/hr for RTX 4090, manual management
  3. Dedicated GPU — $150-300/month for always-on RTX 3090

API contract (self-hosted HTTP wrapper):
  POST http://{host}:{port}/v1/tts
  Body: {"text": "...", "voice_id": "...", "sample_rate": 48000}
  Response: streaming audio/wav
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

# Cost model: RunPod Serverless RTX 4090 at $0.00031/s.
# Average TTS generation: ~0.3x real-time (10s audio in ~3s).
# For 200 minutes of audio/month:  200 * 60 * 0.3 * 0.00031 = $1.116/month.
# Compare Fish Audio Plus plan at $11/month.
_COST_PER_SECOND_GPU = Decimal("0.00031")
_REALTIME_FACTOR = Decimal("0.3")  # generates faster than real-time
_COST_PER_CHAR = Decimal("0.0000065")  # ~10x cheaper than Fish Audio

_SAMPLE_RATE = 48_000
_GENERATION_TIMEOUT = 120.0


class ChatterboxProvider(TTSProvider):
    """Self-hosted Chatterbox TTS on GPU infrastructure.

    Requires a running Chatterbox inference server accessible via HTTP.
    Configure the endpoint via ``SELF_HOSTED_TTS_URL`` environment variable
    or ``settings.self_hosting.tts_url``.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._base_url = (
            getattr(getattr(settings, "self_hosting", None), "tts_url", "")
            or "http://localhost:8880"
        )

    @async_retry(max_attempts=2, base_delay=3.0)
    async def generate(
        self,
        text: str,
        voice_id: str,
        **kwargs: Any,
    ) -> TTSResult:
        char_count = len(text)
        sample_rate = kwargs.get("sample_rate", _SAMPLE_RATE)

        payload = {
            "text": text,
            "voice_id": voice_id,
            "sample_rate": sample_rate,
            "format": "wav",
        }

        fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="crimemill_cb_")
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
        cost = self._estimate_cost(duration)

        return TTSResult(
            file_path=tmp_path,
            duration_seconds=round(duration, 2),
            sample_rate=rate,
            file_size_bytes=file_size,
            character_count=char_count,
            cost_usd=cost,
            provider=self.provider_name(),
            voice_id=voice_id,
        )

    async def list_voices(self) -> list[VoiceInfo]:
        """List voices from the self-hosted server."""
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
                    description=v.get("description", ""),
                    provider=self.provider_name(),
                )
                for v in data.get("voices", [])
            ]
        except Exception:
            await logger.awarning("chatterbox_list_voices_failed")
            return []

    def cost_per_character(self) -> Decimal:
        return _COST_PER_CHAR

    def provider_name(self) -> str:
        return "chatterbox"

    def is_self_hosted(self) -> bool:
        return True

    @staticmethod
    def _estimate_cost(audio_duration_seconds: float) -> Decimal:
        """Estimate GPU compute cost based on audio duration.

        Chatterbox generates at ~0.3x real-time on RTX 4090.
        RunPod Serverless charges $0.00031/second of GPU time.
        """
        gpu_seconds = Decimal(str(audio_duration_seconds)) * _REALTIME_FACTOR
        return (gpu_seconds * _COST_PER_SECOND_GPU).quantize(Decimal("0.000001"))


def _read_wav_metadata(file_path: str) -> tuple[float, int, int]:
    file_size = Path(file_path).stat().st_size
    with wave.open(file_path, "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        duration = frames / rate if rate > 0 else 0.0
    return duration, rate, file_size
