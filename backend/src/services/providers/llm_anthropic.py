"""Anthropic Claude LLM provider — wraps the existing Claude API integration.

Model routing:
  - Sonnet 4 (claude-sonnet-4-20250514): creative tasks ($3/$15 per M tokens)
  - Haiku 4.5 (claude-haiku-4-5-20251001): structured tasks ($1/$5 per M tokens)

Supports prompt caching via cache_control ephemeral on system prompts.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog

from src.services.providers.base import LLMProvider, LLMResult
from src.utils.retry import async_retry

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger()

_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"

MODEL_SONNET = "claude-sonnet-4-20250514"
MODEL_HAIKU = "claude-haiku-4-5-20251001"

# Per-token costs (USD)
_PRICING: dict[str, tuple[Decimal, Decimal]] = {
    MODEL_SONNET: (Decimal("0.000003"), Decimal("0.000015")),  # $3/$15 per M
    MODEL_HAIKU: (Decimal("0.000001"), Decimal("0.000005")),  # $1/$5 per M
}


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider.

    Production LLM for all script generation, segment identification, and
    content classification tasks.  No self-hosted alternative currently
    viable for quality-sensitive creative writing.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client
        self._api_key = settings.anthropic.api_key

    @async_retry(max_attempts=2, base_delay=2.0)
    async def generate(
        self,
        system: str,
        user: str,
        model: str | None = None,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResult:
        resolved_model = model or MODEL_SONNET
        cache_system = kwargs.get("cache_system", True)

        system_content: list[dict[str, Any]] | str
        if cache_system:
            system_content = [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_content = system

        payload: dict[str, Any] = {
            "model": resolved_model,
            "max_tokens": max_tokens,
            "system": system_content,
            "messages": [{"role": "user", "content": user}],
        }

        # Merge any extra params (temperature, etc.)
        for key in ("temperature", "top_p", "stop_sequences"):
            if key in kwargs:
                payload[key] = kwargs[key]

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }

        start = time.monotonic()
        resp = await self._http.post(
            _API_URL,
            json=payload,
            headers=headers,
            timeout=120.0,
        )
        resp.raise_for_status()
        latency_ms = int((time.monotonic() - start) * 1000)

        data = resp.json()
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block["text"]

        usage = data.get("usage", {})
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)

        input_cost_rate, output_cost_rate = _PRICING.get(resolved_model, _PRICING[MODEL_SONNET])
        cost = Decimal(input_tokens) * input_cost_rate + Decimal(output_tokens) * output_cost_rate

        return LLMResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            provider=self.provider_name(),
            model=resolved_model,
            latency_ms=latency_ms,
        )

    def cost_per_1k_input_tokens(self) -> Decimal:
        return Decimal("0.003")  # Sonnet default

    def cost_per_1k_output_tokens(self) -> Decimal:
        return Decimal("0.015")  # Sonnet default

    def provider_name(self) -> str:
        return "anthropic"
