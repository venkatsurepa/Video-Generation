"""Local Flux Dev image provider — self-hosted on GPU.

Phase 2 target (month 3-4 of self-hosting roadmap):
  - Flux Dev on RTX 4090 or A10G
  - $349-574/month savings vs fal.ai at 100+ videos/month
  - Deployment: RunPod or Vast.ai with persistent storage
  - API: ComfyUI API or custom FastAPI wrapper around diffusers
  - Cold start: 30-60s (model loading into VRAM)
  - Per-image cost: ~$0.0005 (GPU time only)

ComfyUI API contract:
  POST http://{host}:{port}/api/generate
  Body: {"prompt": "...", "width": 1920, "height": 1080,
         "negative_prompt": "...", "steps": 25, "cfg_scale": 7.5}
  Response: {"image_url": "http://.../output.png"}
"""

from __future__ import annotations

import math
import tempfile
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from src.services.providers.base import ImageProvider, ImageResult
from src.utils.retry import async_retry

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger()

KEN_BURNS_SCALE = 1.12

# GPU cost model: RTX 4090 on Vast.ai at ~$0.50/hr.
# Flux Dev generates a 1024x1024 image in ~4s on RTX 4090.
# Cost per image: $0.50/3600 * 4 ≈ $0.00056
_COST_PER_IMAGE = Decimal("0.0006")
_GENERATION_TIMEOUT = 180.0  # includes possible cold start


def _scale_dimension(value: int) -> int:
    scaled = math.ceil(value * KEN_BURNS_SCALE)
    return int(math.ceil(scaled / 8) * 8)


class LocalFluxProvider(ImageProvider):
    """Self-hosted Flux Dev on GPU infrastructure.

    Requires a running ComfyUI or custom inference server.
    Configure endpoint via ``settings.self_hosting.image_url``.

    Break-even: ~80 images/month vs fal.ai Schnell,
    ~15 images/month vs fal.ai Pro Ultra.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._base_url = (
            getattr(getattr(settings, "self_hosting", None), "image_url", "")
            or "http://localhost:8188"
        )
        self._output_dir = Path(tempfile.gettempdir()) / "crimemill" / "images_local"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    @async_retry(max_attempts=2, base_delay=5.0)
    async def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        **kwargs: Any,
    ) -> ImageResult:
        negative_prompt = kwargs.get("negative_prompt", "")
        steps = kwargs.get("steps", 25)
        cfg_scale = kwargs.get("cfg_scale", 7.5)

        gen_width = _scale_dimension(width)
        gen_height = _scale_dimension(height)

        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": gen_width,
            "height": gen_height,
            "steps": steps,
            "cfg_scale": cfg_scale,
        }

        start = time.monotonic()
        resp = await self._http.post(
            f"{self._base_url}/api/generate",
            json=payload,
            timeout=_GENERATION_TIMEOUT,
        )
        resp.raise_for_status()
        latency_ms = int((time.monotonic() - start) * 1000)

        data = resp.json()
        image_url = data.get("image_url", "")

        # Download generated image
        local_path = await self._download(image_url)

        return ImageResult(
            file_path=str(local_path),
            width=gen_width,
            height=gen_height,
            cost_usd=_COST_PER_IMAGE,
            provider=self.provider_name(),
            model="flux-dev-local",
            prompt=prompt,
            url=image_url,
            latency_ms=latency_ms,
        )

    def cost_per_image(self) -> Decimal:
        return _COST_PER_IMAGE

    def provider_name(self) -> str:
        return "local_flux"

    def is_self_hosted(self) -> bool:
        return True

    async def _download(self, url: str) -> Path:
        resp = await self._http.get(url, timeout=60.0)
        resp.raise_for_status()
        dest = self._output_dir / f"{uuid.uuid4().hex}.png"
        dest.write_bytes(resp.content)
        return dest
