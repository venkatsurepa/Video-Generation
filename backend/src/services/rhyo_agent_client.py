"""Client for fetching Rhyo intelligence reports.

Rhyo is the in-development safety intelligence system that produces detailed
markdown reports per destination (city / neighborhood / POI). The reports are
the SOURCE MATERIAL for the travel-safety YouTube channel — the
TravelSafetyGenerator restructures them into video scripts.

Initial implementation is a stub: it accepts pre-generated report markdown
(passed in or loaded from disk) and wraps it in a RhyoReport. A future
revision will hit the live agent (HTTP API or direct Hetzner connection).

Connection plan for the live implementation:
- Rhyo intelligence DB lives on Hetzner (88.198.50.202) PG16, accessible
  ONLY via a WireGuard tunnel exposing 127.0.0.1:5432.
- A future Rhyo HTTP agent endpoint (TBD) would let the backend fetch
  reports without holding a DB connection.
- Until either is wired up, this client raises NotImplementedError on
  fetch_report() and callers must use from_markdown() with a fixture.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import httpx

    from src.config import Settings


class RhyoReport(BaseModel):
    """A safety intelligence report for one destination."""

    destination_label: str = Field(..., description="Human label, e.g. 'Banjara Hills, Hyderabad, India'")
    country_code: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2")
    city: str
    region: str = ""
    raw_markdown: str = Field(..., description="The full intelligence report as markdown")
    generated_at: datetime
    source: Literal["stub", "live_agent", "fixture"] = "stub"

    @property
    def word_count(self) -> int:
        return len(self.raw_markdown.split())


class RhyoAgentClient:
    """Wraps fetching Rhyo intelligence reports.

    Stub implementation: ``fetch_report()`` raises NotImplementedError.
    Use ``from_markdown()`` to wrap a pre-generated report (test fixture or
    manually exported markdown) into a RhyoReport for the generator.
    """

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http_client

    async def fetch_report(
        self,
        *,
        destination_label: str,
        country_code: str,
        city: str,
        region: str = "",
    ) -> RhyoReport:
        """Fetch a fresh intelligence report from the live Rhyo agent.

        Not yet implemented — needs Hetzner WireGuard tunnel or a public
        HTTP agent endpoint. Callers should use from_markdown() until then.
        """
        raise NotImplementedError(
            "Live Rhyo agent fetch is not wired up yet. Use "
            "RhyoAgentClient.from_markdown() with a pre-generated report. "
            "See module docstring for the connection plan."
        )

    @staticmethod
    def from_markdown(
        markdown: str,
        *,
        destination_label: str,
        country_code: str,
        city: str,
        region: str = "",
        source: Literal["stub", "live_agent", "fixture"] = "fixture",
    ) -> RhyoReport:
        """Wrap pre-generated markdown into a RhyoReport (no network call)."""
        return RhyoReport(
            destination_label=destination_label,
            country_code=country_code.upper(),
            city=city,
            region=region,
            raw_markdown=markdown,
            generated_at=datetime.now(UTC),
            source=source,
        )


__all__ = ["RhyoAgentClient", "RhyoReport"]
