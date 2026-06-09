"""BaseHttpClient — retry + circuit breaker shared by all outbound HTTP clients."""
import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Any, TypeVar

T = TypeVar("T")


# ── Circuit Breaker ────────────────────────────────────────────────────────────

class CircuitBreakerOpenError(RuntimeError):
    """Raised when the circuit is OPEN and requests are blocked."""


class _CBState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class _CircuitBreaker:
    def __init__(self, failure_threshold: int, recovery_timeout: float) -> None:
        self._state = _CBState.CLOSED
        self._failures = 0
        self._last_failure_at: float | None = None
        self._threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._lock = asyncio.Lock()

    def _effective_state(self) -> _CBState:
        if (
            self._state == _CBState.OPEN
            and self._last_failure_at is not None
            and time.monotonic() - self._last_failure_at >= self._recovery_timeout
        ):
            self._state = _CBState.HALF_OPEN
        return self._state

    async def call(self, coro: Any) -> Any:
        async with self._lock:
            if self._effective_state() == _CBState.OPEN:
                raise CircuitBreakerOpenError(
                    "Circuit breaker OPEN – service temporarily unavailable"
                )
        try:
            result = await coro
        except Exception:
            async with self._lock:
                self._failures += 1
                self._last_failure_at = time.monotonic()
                if self._failures >= self._threshold:
                    self._state = _CBState.OPEN
            raise
        else:
            async with self._lock:
                self._failures = 0
                self._state = _CBState.CLOSED
            return result


# ── Base Client ────────────────────────────────────────────────────────────────

class BaseHttpClient:
    """Base class that provides retry + circuit breaker for any outbound HTTP call.

    Subclasses override _RETRYABLE with the exception types that warrant a retry
    (transient network / server-side errors). All other exceptions propagate immediately.

    Usage in subclasses:
        result = await self._protected_call(lambda: self._do_the_actual_request(...))
    """

    MAX_RETRIES: int = 2                   # retries after initial attempt (3 total)
    BASE_RETRY_DELAY: float = 1.0          # delay = BASE * 2^attempt + uniform(0,1)
    CIRCUIT_FAILURE_THRESHOLD: int = 5
    CIRCUIT_RECOVERY_TIMEOUT: float = 30.0
    _RETRYABLE: tuple[type[Exception], ...] = ()

    def __init__(self) -> None:
        self._circuit = _CircuitBreaker(
            failure_threshold=self.CIRCUIT_FAILURE_THRESHOLD,
            recovery_timeout=self.CIRCUIT_RECOVERY_TIMEOUT,
        )

    async def _protected_call(self, factory: Callable[[], Awaitable[T]]) -> T:
        """Run factory() under circuit breaker + retry.

        factory is called fresh on every attempt so the coroutine is recreated.
        """
        return await self._circuit.call(self._retry(factory))

    async def _retry(self, factory: Callable[[], Awaitable[T]]) -> T:
        last_exc: Exception | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return await factory()
            except self._RETRYABLE as exc:  # type: ignore[misc]
                last_exc = exc
                if attempt >= self.MAX_RETRIES:
                    break
                # delay: 1→~1.3s, 2→~2.3s
                delay = self.BASE_RETRY_DELAY * (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(delay)
        assert last_exc is not None
        raise last_exc
