from __future__ import annotations

import asyncio
import math
import tempfile
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from src.models.image import (
    FalModel,
    ImageCost,
    ImagePrompt,
    ImageResult,
    ImageTier,
)
from src.utils.retry import async_retry

if TYPE_CHECKING:
    import httpx

    from src.config import Settings
    from src.services.providers.base import ImageProvider as ImageProviderBase

logger = structlog.get_logger()

# Ken Burns headroom: generate 12% larger than output frame so the
# Remotion pan/zoom can crop without hitting edges.
KEN_BURNS_SCALE = 1.12

# fal.ai queue endpoint (async) and sync endpoint
FAL_QUEUE_URL = "https://queue.fal.run"
FAL_SYNC_URL = "https://fal.run"

# Concurrency guard — avoid hammering the API
DEFAULT_CONCURRENCY = 5

# Budget defaults per video (from bible §5.3)
_TIER_BUDGET = {
    ImageTier.HERO: 3,
    ImageTier.STANDARD: 12,
    ImageTier.BACKGROUND: 5,
}


def _scale_dimension(value: int) -> int:
    """Round up to nearest multiple of 8 after applying Ken Burns headroom."""
    scaled = math.ceil(value * KEN_BURNS_SCALE)
    return int(math.ceil(scaled / 8) * 8)


class ImageGenerator:
    """Generates scene images using the fal.ai Flux API.

    Supports a tiered approach:
      - 3 hero images per video  → Flux 2 Pro ($0.04-0.06 each)
      - 12 standard scenes       → Flux Schnell ($0.003 each)
      - 5 simple backgrounds     → Flux Schnell ($0.003 each)
    Total ≈ $0.16/video for 20 images.

    Accepts an optional ``provider`` to delegate to a different backend
    (e.g., self-hosted Flux Dev).  When a provider is given,
    ``generate_scene_image`` delegates to it; batch and hero methods
    still work through the same code path.
    """

    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
        provider: ImageProviderBase | None = None,
    ) -> None:
        self._settings = settings
        self._http = http_client
        self._provider = provider
        self._output_dir = Path(tempfile.gettempdir()) / "crimemill" / "images"
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_scene_image(
        self,
        prompt: str,
        negative_prompt: str | None = None,
        model: str = "flux-schnell",
        width: int = 1920,
        height: int = 1080,
    ) -> ImageResult:
        """Generate a single scene image via fal.ai (or injected provider)."""
        # Delegate to injected provider if present
        if self._provider is not None:
            provider_result = await self._provider.generate(
                prompt,
                width,
                height,
                negative_prompt=negative_prompt,
                model=model,
            )
            return ImageResult(
                prompt=prompt,
                model=provider_result.model or model,
                width=provider_result.width,
                height=provider_result.height,
                local_path=provider_result.file_path,
                url=provider_result.url,
                cost=ImageCost(
                    provider=provider_result.provider,
                    model=provider_result.model or model,
                    cost_usd=provider_result.cost_usd,
                    latency_ms=provider_result.latency_ms,
                ),
            )

        fal_model = _resolve_model_alias(model)
        return await self._generate_single(
            ImagePrompt(
                prompt=prompt,
                negative_prompt=negative_prompt,
                model=fal_model,
                width=width,
                height=height,
            ),
        )

    async def generate_hero_image(
        self,
        prompt: str,
        model: str = "flux-2-pro",
    ) -> ImageResult:
        """Generate a high-quality hero image (title card / key moment)."""
        fal_model = _resolve_model_alias(model)
        return await self._generate_single(
            ImagePrompt(
                prompt=prompt,
                tier=ImageTier.HERO,
                model=fal_model,
                width=1920,
                height=1080,
            ),
        )

    async def generate_thumbnail_background(
        self,
        prompt: str,
    ) -> ImageResult:
        """Generate a thumbnail background image (1280×720)."""
        return await self._generate_single(
            ImagePrompt(
                prompt=prompt,
                tier=ImageTier.BACKGROUND,
                model=FalModel.FLUX_PRO_NEW,
                width=1280,
                height=720,
            ),
        )

    async def generate_batch(
        self,
        prompts: list[ImagePrompt],
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> list[ImageResult]:
        """Generate images for a batch of prompts with concurrency limiting."""
        semaphore = asyncio.Semaphore(concurrency)

        async def _limited(p: ImagePrompt) -> ImageResult:
            async with semaphore:
                return await self._generate_single(p)

        tasks = [asyncio.create_task(_limited(p)) for p in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final: list[ImageResult] = []
        for i, r in enumerate(results):
            if isinstance(r, BaseException):
                await logger.aerror(
                    "batch_image_failed",
                    prompt=prompts[i].prompt[:80],
                    error=str(r),
                )
                raise r
            final.append(r)

        total_cost = sum(r.cost.cost_usd for r in final)
        await logger.ainfo(
            "batch_complete",
            count=len(final),
            total_cost_usd=str(total_cost),
        )
        return final

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @async_retry(max_attempts=3, base_delay=2.0)
    async def _generate_single(self, req: ImagePrompt) -> ImageResult:
        """Call fal.ai, download the image, return an ImageResult with cost."""
        fal_model = req.resolved_model
        gen_width = _scale_dimension(req.width)
        gen_height = _scale_dimension(req.height)

        payload: dict[str, object] = {
            "prompt": req.prompt,
            "image_size": {"width": gen_width, "height": gen_height},
            "num_images": 1,
            "enable_safety_checker": False,
        }
        if req.negative_prompt:
            payload["negative_prompt"] = req.negative_prompt

        url = f"{FAL_SYNC_URL}/{fal_model.value}"
        headers = {
            "Authorization": f"Key {self._settings.fal.api_key}",
            "Content-Type": "application/json",
        }

        await logger.ainfo(
            "fal_request",
            model=fal_model.value,
            width=gen_width,
            height=gen_height,
            prompt=req.prompt[:100],
        )

        start = time.monotonic()
        resp = await self._http.post(url, json=payload, headers=headers, timeout=120.0)
        resp.raise_for_status()
        latency_ms = int((time.monotonic() - start) * 1000)

        data = resp.json()
        image_url = data["images"][0]["url"]

        # Download image to local temp file
        local_path = await self._download_image(image_url, fal_model)

        cost = ImageCost(
            provider="fal.ai",
            model=fal_model.value,
            cost_usd=fal_model.cost_per_image,
            latency_ms=latency_ms,
        )

        await logger.ainfo(
            "image_generated",
            model=fal_model.value,
            cost_usd=str(cost.cost_usd),
            latency_ms=latency_ms,
            local_path=str(local_path),
        )

        return ImageResult(
            prompt=req.prompt,
            model=fal_model.value,
            width=gen_width,
            height=gen_height,
            local_path=str(local_path),
            url=image_url,
            cost=cost,
        )

    async def _download_image(self, url: str, model: FalModel) -> Path:
        """Download an image from a URL to a local temp file."""
        resp = await self._http.get(url, timeout=60.0)
        resp.raise_for_status()

        ext = ".webp" if "webp" in resp.headers.get("content-type", "") else ".png"
        filename = f"{uuid.uuid4().hex}{ext}"
        dest = self._output_dir / filename
        dest.write_bytes(resp.content)
        return dest


def _resolve_model_alias(alias: str) -> FalModel:
    """Map short user-friendly model names to FalModel enum members."""
    aliases: dict[str, FalModel] = {
        "flux-schnell": FalModel.FLUX_SCHNELL,
        "schnell": FalModel.FLUX_SCHNELL,
        "flux-2-pro": FalModel.FLUX_PRO_ULTRA,
        "flux-pro-ultra": FalModel.FLUX_PRO_ULTRA,
        "flux-pro": FalModel.FLUX_PRO_NEW,
        "flux-pro-new": FalModel.FLUX_PRO_NEW,
    }
    resolved = aliases.get(alias.lower())
    if resolved is None:
        # Try direct enum value match
        try:
            return FalModel(alias)
        except ValueError:
            raise ValueError(
                f"Unknown model alias '{alias}'. Valid aliases: {', '.join(aliases.keys())}"
            ) from None
    return resolved
