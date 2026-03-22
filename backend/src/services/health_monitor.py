"""Health monitoring via Healthchecks.io pings and structured metric logging.

Healthchecks.io detects:
  - Jobs that start but never finish (via /start → timeout)
  - Pipeline failures (via /fail)
  - Periods of inactivity (missed success pings)

Grafana Cloud ingests the structlog JSON output and queries on ``metric_name``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import httpx

    from src.config import Settings

logger = structlog.get_logger()

_PING_TIMEOUT = 5.0


class HealthMonitor:
    """Sends heartbeat pings to Healthchecks.io and emits metrics for Grafana."""

    def __init__(self, settings: Settings, http_client: httpx.AsyncClient) -> None:
        self._base_url = settings.healthchecks_ping_url.rstrip("/")
        self._http = http_client

    # ------------------------------------------------------------------
    # Healthchecks.io pings
    # ------------------------------------------------------------------

    async def ping_start(self, check_name: str = "") -> None:
        """Signal that a job has started (detects jobs that never finish)."""
        await self._ping("/start", check_name)

    async def ping_success(self, check_name: str = "") -> None:
        """Signal successful job completion."""
        await self._ping("", check_name)

    async def ping_failure(self, check_name: str = "", error: str = "") -> None:
        """Signal job failure with optional error details in the body."""
        await self._ping("/fail", check_name, body=error)

    # ------------------------------------------------------------------
    # Metric logging (for Grafana Cloud / Loki)
    # ------------------------------------------------------------------

    async def report_metric(self, metric_name: str, value: float) -> None:
        """Emit a structured log line that Grafana can query.

        Example output (JSON mode):
        ``{"event": "metric", "metric_name": "job_duration_seconds", "value": 12.5}``
        """
        await logger.ainfo(
            "metric",
            metric_name=metric_name,
            value=value,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _ping(
        self,
        suffix: str,
        check_name: str,
        body: str = "",
    ) -> None:
        """Fire-and-forget ping — monitoring failures never block the pipeline."""
        if not self._base_url:
            return

        url = self._base_url
        if check_name:
            url = f"{url}/{check_name}"
        url = f"{url}{suffix}"

        try:
            if body:
                await self._http.post(url, content=body, timeout=_PING_TIMEOUT)
            else:
                await self._http.get(url, timeout=_PING_TIMEOUT)
        except Exception:
            await logger.awarning("healthcheck_ping_failed", url=url)
