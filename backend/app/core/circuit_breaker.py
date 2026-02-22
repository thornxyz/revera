"""Simple async circuit breaker for external API calls.

States:
  CLOSED   — normal operation; failures are counted.
  OPEN     — requests are rejected immediately until the cooldown expires.
  HALF_OPEN — one probe request is allowed through to test recovery.

Usage::

    breaker = CircuitBreaker(name="tavily", failure_threshold=5, cooldown_seconds=60)

    @breaker
    async def call_tavily(query: str):
        ...

Or as a context manager / standalone guard::

    async with breaker:
        result = await tavily_client.search(query)
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when a call is blocked because the circuit is OPEN."""

    def __init__(self, name: str, retry_after: float) -> None:
        self.name = name
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker '{name}' is OPEN. Retry after {retry_after:.1f}s."
        )


class CircuitBreaker:
    """Async-safe circuit breaker.

    Args:
        name: Human-readable identifier used in log messages.
        failure_threshold: Number of consecutive failures before opening.
        cooldown_seconds: Time (seconds) to wait in OPEN state before probing.
        success_threshold: Consecutive successes in HALF_OPEN needed to close.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        cooldown_seconds: float = 60.0,
        success_threshold: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._opened_at: float | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        return self._state

    def __call__(self, func: Callable) -> Callable:
        """Decorator — wraps an async function with circuit-breaker logic."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            await self._before_call()
            try:
                result = await func(*args, **kwargs)
                await self._on_success()
                return result
            except CircuitBreakerOpenError:
                raise
            except Exception as exc:
                await self._on_failure(exc)
                raise

        return wrapper

    async def __aenter__(self) -> "CircuitBreaker":
        await self._before_call()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            await self._on_success()
        elif exc_type is not CircuitBreakerOpenError:
            await self._on_failure(exc_val)
        return False  # do not suppress exceptions

    # ------------------------------------------------------------------
    # Internal state machine
    # ------------------------------------------------------------------

    async def _before_call(self) -> None:
        async with self._lock:
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - (self._opened_at or 0)
                remaining = self.cooldown_seconds - elapsed
                if remaining > 0:
                    raise CircuitBreakerOpenError(self.name, remaining)
                # Cooldown expired — transition to HALF_OPEN
                self._state = CircuitState.HALF_OPEN
                self._success_count = 0
                logger.info("[CIRCUIT_BREAKER] '%s' → HALF_OPEN (probing)", self.name)

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    logger.info(
                        "[CIRCUIT_BREAKER] '%s' → CLOSED (recovered)", self.name
                    )
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0  # Reset on any success

    async def _on_failure(self, exc: BaseException) -> None:
        async with self._lock:
            self._failure_count += 1
            logger.warning(
                "[CIRCUIT_BREAKER] '%s' failure %d/%d: %s",
                self.name,
                self._failure_count,
                self.failure_threshold,
                exc,
            )
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.error(
                    "[CIRCUIT_BREAKER] '%s' → OPEN (cooldown %.0fs)",
                    self.name,
                    self.cooldown_seconds,
                )
