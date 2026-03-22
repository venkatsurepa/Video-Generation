"""fal.ai Flux image provider — wraps the existing fal.ai API integration.

Tiered approach:
  - Hero images:  Flux 2 Pro Ultra ($0.06/image)
  - Standard:     Flux Schnell ($0.003/image)
  - Backgrounds:  Flux Schnell ($0.003/image)
Total ≈ $0.16/video for 20 images.
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

FAL_SYNC_URL = "https://fal.run"
KEN_BURNS_SCALE = 1.12

# Default model and cost
_DEFAULT_MODEL = "fal-ai/flux/schnell"
_DEFAULT_COST = Decimal("0.003")

_MODEL_COSTS: dict[str, Decimal] = {
    "fal-ai/flux/schnell": Decimal("0.003"),
    "fal-ai/flux-pro/v1.1-ultra": Decimal("0.06"),
    "fal-ai/flux-pro/new": Decimal("0.055"),
}


def _scale_dimension(value: int) -> int:
    scaled = math.ceil(value * KEN_BURNS_SCALE)
    return int(math.ceil(scaled / 8) * 8)


class FalAIProvider(ImageProvider):
    """fal.ai Flux cloud image generation.

    Production provider for all channels.  Supports multiple Flux model
    tiers for cost-optimised image generation.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._output_dir = Path(tempfile.gettempdir()) / "crimemill" / "images"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    @async_retry(max_attempts=3, base_delay=2.0)
    async def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        **kwargs: Any,
    ) -> ImageResult:
        model = kwargs.get("model", _DEFAULT_MODEL)
        negative_prompt = kwargs.get("negative_prompt")
        gen_width = _scale_dimension(width)
        gen_height = _scale_dimension(height)

        payload: dict[str, object] = {
            "prompt": prompt,
            "image_size": {"width": gen_width, "height": gen_height},
            "num_images": 1,
            "enable_safety_checker": False,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        url = f"{FAL_SYNC_URL}/{model}"
        headers = {
            "Authorization": f"Key {self._settings.fal.api_key}",
            "Content-Type": "application/json",
        }

        start = time.monotonic()
        resp = await self._http.post(url, json=payload, headers=headers, timeout=120.0)
        resp.raise_for_status()
        latency_ms = int((time.monotonic() - start) * 1000)

        data = resp.json()
        image_url = data["images"][0]["url"]

        # Download to local file
        local_path = await self._download(image_url)
        cost = _MODEL_COSTS.get(model, _DEFAULT_COST)

        return ImageResult(
            file_path=str(local_path),
            width=gen_width,
            height=gen_height,
            cost_usd=cost,
            provider=self.provider_name(),
            model=model,
            prompt=prompt,
            url=image_url,
            latency_ms=latency_ms,
        )

    def cost_per_image(self) -> Decimal:
        return _DEFAULT_COST

    def provider_name(self) -> str:
        return "fal_ai"

    async def _download(self, url: str) -> Path:
        resp = await self._http.get(url, timeout=60.0)
        resp.raise_for_status()
        ext = ".webp" if "webp" in resp.headers.get("content-type", "") else ".png"
        dest = self._output_dir / f"{uuid.uuid4().hex}{ext}"
        dest.write_bytes(resp.content)
        return dest
