"""Circuit breaker pattern for external API protection.

Three states:
  CLOSED    — requests flow normally; consecutive failures are counted.
  OPEN      — requests fail immediately with CircuitOpenError.
  HALF_OPEN — one probe request allowed; success resets, failure reopens.

Each external API (Anthropic, Fish Audio, fal.ai, Groq, YouTube) gets its
own CircuitBreaker instance with appropriate thresholds.
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger()

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit is open and calls are rejected."""

    def __init__(self, name: str, remaining_seconds: float) -> None:
        self.name = name
        self.remaining_seconds = remaining_seconds
        super().__init__(
            f"Circuit '{name}' is OPEN. Retry in {remaining_seconds:.1f}s."
        )


class CircuitBreaker:
    """Async circuit breaker for external service protection.

    Parameters
    ----------
    name:
        Identifier for logging (e.g. ``"fish_audio"``, ``"fal_ai"``).
    failure_threshold:
        Consecutive failures before opening the circuit.
    recovery_timeout:
        Seconds to wait in OPEN state before allowing a probe request.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current state, with lazy OPEN → HALF_OPEN transition."""
        if (
            self._state == CircuitState.OPEN
            and time.monotonic() - self._opened_at >= self.recovery_timeout
        ):
            return CircuitState.HALF_OPEN
        return self._state

    async def call(self, func: Any, *args: Any, **kwargs: Any) -> T:
        """Invoke *func* through the circuit breaker.

        Raises ``CircuitOpenError`` if the circuit is open.
        """
        current = self.state

        if current == CircuitState.OPEN:
            remaining = self.recovery_timeout - (time.monotonic() - self._opened_at)
            raise CircuitOpenError(self.name, max(0.0, remaining))

        try:
            result = await func(*args, **kwargs)
        except Exception as exc:
            await self._on_failure(exc)
            raise
        else:
            await self._on_success()
            return result  # type: ignore[no-any-return]

    async def _on_success(self) -> None:
        async with self._lock:
            if self._failure_count > 0:
                await logger.ainfo(
                    "circuit_reset",
                    circuit=self.name,
                    previous_failures=self._failure_count,
                )
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    async def _on_failure(self, exc: Exception) -> None:
        async with self._lock:
            self._failure_count += 1

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                await logger.awarning(
                    "circuit_reopened",
                    circuit=self.name,
                    error=str(exc),
                )
                return

            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                await logger.awarning(
                    "circuit_opened",
                    circuit=self.name,
                    failure_count=self._failure_count,
                    recovery_timeout=self.recovery_timeout,
                    error=str(exc),
                )
