"""ACE-Step v1.5 music provider — self-hosted, Apache 2.0 license.

ACE-Step (https://github.com/ace-step/ACE-Step):
  - Full songs with vocals up to 10 minutes
  - Apache 2.0 license — no restrictions
  - <4 GB VRAM — can share GPU with image generation
  - LoRA fine-tuning from reference songs
  - 3,600 songs for $2.20/month on Vast.ai RTX 3090

Deployment:
  - Vast.ai RTX 3090: ~$0.40/hr
  - Generation time: ~30s per 3-minute track
  - Can batch-generate mood library on a schedule
  - Cost per track: ~$0.003 (GPU time only)

API contract (self-hosted FastAPI wrapper):
  POST http://{host}:{port}/v1/generate
  Body: {"prompt": "dark ambient crime documentary...",
         "duration_seconds": 180, "bpm": 80, "style": "ambient"}
  Response: {"audio_url": "http://.../output.wav",
             "duration_seconds": 180.5, "bpm": 78}
"""

from __future__ import annotations

import tempfile
import time
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from src.services.providers.base import MusicProvider, MusicResult
from src.utils.retry import async_retry

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger()

# Vast.ai RTX 3090 at $0.40/hr. 30s generation → $0.40/3600 * 30 ≈ $0.0033
_COST_PER_TRACK = Decimal("0.003")
_GENERATION_TIMEOUT = 300.0  # music gen can take a while


class ACEStepProvider(MusicProvider):
    """Self-hosted ACE-Step v1.5 music generation.

    Generates custom background music for videos.  Uses <4 GB VRAM so it
    can share a GPU with image generation (Flux Dev) without conflict.

    Best used to pre-generate a mood library of 20-30 tracks, then
    select from the library at render time (same as Epidemic Sound flow).
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._base_url = (
            getattr(getattr(settings, "self_hosting", None), "music_url", "")
            or "http://localhost:8890"
        )

    @async_retry(max_attempts=2, base_delay=5.0)
    async def generate(
        self,
        prompt: str,
        duration_seconds: float,
        **kwargs: Any,
    ) -> MusicResult:
        """Generate a custom music track via self-hosted ACE-Step."""
        bpm = kwargs.get("bpm", 80)
        style = kwargs.get("style", "ambient")

        payload = {
            "prompt": prompt,
            "duration_seconds": duration_seconds,
            "bpm": bpm,
            "style": style,
        }

        start = time.monotonic()
        resp = await self._http.post(
            f"{self._base_url}/v1/generate",
            json=payload,
            timeout=_GENERATION_TIMEOUT,
        )
        resp.raise_for_status()
        latency_ms = int((time.monotonic() - start) * 1000)

        data = resp.json()
        audio_url = data.get("audio_url", "")
        actual_duration = data.get("duration_seconds", duration_seconds)
        actual_bpm = data.get("bpm", bpm)

        # Download generated audio
        local_path = await self._download(audio_url)

        await logger.ainfo(
            "ace_step_generated",
            duration=actual_duration,
            bpm=actual_bpm,
            latency_ms=latency_ms,
            cost_usd=str(_COST_PER_TRACK),
        )

        return MusicResult(
            file_path=str(local_path),
            duration_seconds=actual_duration,
            cost_usd=_COST_PER_TRACK,
            provider=self.provider_name(),
            title=f"ACE-Step {style} {bpm}bpm",
            bpm=actual_bpm,
        )

    def cost_per_generation(self) -> Decimal:
        return _COST_PER_TRACK

    def provider_name(self) -> str:
        return "ace_step"

    def is_self_hosted(self) -> bool:
        return True

    async def _download(self, url: str) -> Path:
        resp = await self._http.get(url, timeout=120.0)
        resp.raise_for_status()
        fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="crimemill_ace_")
        with open(fd, "wb") as f:
            f.write(resp.content)
        return Path(tmp_path)
