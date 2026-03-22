from __future__ import annotations

import asyncio
import random
from functools import wraps
from typing import TYPE_CHECKING, ParamSpec, TypeVar

import httpx
import structlog

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

logger = structlog.get_logger()

P = ParamSpec("P")
T = TypeVar("T")


def _is_retryable_http_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


DEFAULT_RETRYABLE: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    httpx.ConnectError,
    httpx.ReadTimeout,
)


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple[type[BaseException], ...] = DEFAULT_RETRYABLE,
) -> Callable[
    [Callable[P, Coroutine[object, object, T]]],
    Callable[P, Coroutine[object, object, T]],
]:
    """Async retry decorator with exponential backoff and jitter."""

    def decorator(
        func: Callable[P, Coroutine[object, object, T]],
    ) -> Callable[P, Coroutine[object, object, T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exc: BaseException | None = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exc = exc
                except httpx.HTTPStatusError as exc:
                    if _is_retryable_http_error(exc):
                        last_exc = exc
                    else:
                        raise
                else:
                    break

                if attempt < max_attempts - 1:
                    delay = min(base_delay * (2**attempt) + random.random(), max_delay)
                    await logger.awarning(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        delay=round(delay, 2),
                        error=str(last_exc),
                    )
                    await asyncio.sleep(delay)

            if last_exc is not None:
                raise last_exc
            raise RuntimeError("Retry loop exited unexpectedly")

        return wrapper

    return decorator
