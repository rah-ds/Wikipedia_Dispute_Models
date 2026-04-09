"""Network resilience utilities for Wikipedia API access.

Provides circuit breaker pattern, retry logic, and connection management
for reliable long-running data pulls.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """States for circuit breaker pattern."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreaker:
    """
    Circuit breaker to prevent cascading failures.

    When too many failures occur, the circuit opens and requests
    are rejected immediately. After a timeout, the circuit enters
    half-open state where a single request is allowed through.
    If it succeeds, the circuit closes; if it fails, it opens again.
    """

    failure_threshold: int = 5
    recovery_timeout: float = 60.0  # seconds
    half_open_max_calls: int = 3

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: datetime | None = field(default=None, init=False)
    _half_open_calls: int = field(default=0, init=False)

    @property
    def state(self) -> CircuitState:
        """Get current circuit state, transitioning if needed."""
        if self._state == CircuitState.OPEN:
            if self._last_failure_time is not None:
                elapsed = (datetime.now() - self._last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout:
                    logger.info("Circuit breaker transitioning to half-open")
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
        return self._state

    def record_success(self) -> None:
        """Record a successful call."""
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_calls += 1
            if self._half_open_calls >= self.half_open_max_calls:
                logger.info("Circuit breaker closing after successful recovery")
                self._state = CircuitState.CLOSED
                self._failure_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = datetime.now()

        if self._state == CircuitState.HALF_OPEN:
            logger.warning("Circuit breaker reopening after failed recovery attempt")
            self._state = CircuitState.OPEN
        elif (
            self._state == CircuitState.CLOSED
            and self._failure_count >= self.failure_threshold
        ):
            logger.warning(
                f"Circuit breaker opening after {self._failure_count} failures"
            )
            self._state = CircuitState.OPEN

    def can_execute(self) -> bool:
        """Check if a request can be executed."""
        state = self.state  # This may transition the state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return True
        return False

    def get_wait_time(self) -> float:
        """Get time to wait before circuit might close."""
        if self._state != CircuitState.OPEN or self._last_failure_time is None:
            return 0.0
        elapsed = (datetime.now() - self._last_failure_time).total_seconds()
        return max(0, self.recovery_timeout - elapsed)


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open."""

    def __init__(self, wait_time: float):
        self.wait_time = wait_time
        super().__init__(f"Circuit breaker is open. Retry in {wait_time:.1f}s")


def with_circuit_breaker(
    circuit: CircuitBreaker,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator to wrap a function with circuit breaker protection.

    Args:
        circuit: CircuitBreaker instance to use

    Returns:
        Decorated function
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            if not circuit.can_execute():
                wait_time = circuit.get_wait_time()
                raise CircuitOpenError(wait_time)

            try:
                result = func(*args, **kwargs)
                circuit.record_success()
                return result
            except Exception:
                circuit.record_failure()
                raise

        return wrapper

    return decorator


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 10
    base_delay: float = 2.0
    max_delay: float = 300.0  # 5 minutes
    exponential_base: float = 2.0
    jitter: float = 0.5  # +/- 50%

    # Errors that should trigger retries
    retryable_errors: tuple[type[Exception], ...] = field(
        default_factory=lambda: (
            ConnectionError,
            TimeoutError,
            OSError,
        )
    )

    # Error codes/messages that indicate rate limiting
    rate_limit_indicators: tuple[str, ...] = field(
        default_factory=lambda: (
            "ratelimit",
            "maxlag",
            "429",
            "too many requests",
            "rate limit exceeded",
        )
    )


def calculate_backoff(
    attempt: int,
    config: RetryConfig,
) -> float:
    """Calculate backoff delay for a retry attempt."""
    delay = min(
        config.base_delay * (config.exponential_base**attempt),
        config.max_delay,
    )
    jitter_range = delay * config.jitter
    delay += random.uniform(-jitter_range, jitter_range)
    return max(0, delay)


def is_rate_limit_error(error: Exception, config: RetryConfig) -> bool:
    """Check if an error indicates rate limiting."""
    error_str = str(error).lower()
    return any(indicator in error_str for indicator in config.rate_limit_indicators)


def retry_with_backoff(
    config: RetryConfig | None = None,
    circuit: CircuitBreaker | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        config: Retry configuration
        circuit: Optional circuit breaker for additional protection

    Returns:
        Decorated function
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Exception | None = None

            for attempt in range(config.max_retries + 1):
                # Check circuit breaker if provided
                if circuit is not None and not circuit.can_execute():
                    wait_time = circuit.get_wait_time()
                    logger.info(f"Circuit open, waiting {wait_time:.1f}s")
                    time.sleep(wait_time)
                    # Re-check after waiting
                    if not circuit.can_execute():
                        raise CircuitOpenError(circuit.get_wait_time())

                try:
                    result = func(*args, **kwargs)
                    if circuit is not None:
                        circuit.record_success()
                    return result

                except Exception as e:
                    last_exception = e

                    # Check if we should retry
                    should_retry = isinstance(
                        e, config.retryable_errors
                    ) or is_rate_limit_error(e, config)

                    if not should_retry:
                        if circuit is not None:
                            circuit.record_failure()
                        raise

                    if attempt < config.max_retries:
                        delay = calculate_backoff(attempt, config)
                        logger.warning(
                            f"Retry {attempt + 1}/{config.max_retries} for {getattr(func, '__name__', repr(func))}: "
                            f"{e}. Waiting {delay:.1f}s"
                        )
                        time.sleep(delay)
                    else:
                        if circuit is not None:
                            circuit.record_failure()

            # All retries exhausted
            logger.error(
                f"All {config.max_retries} retries exhausted for {getattr(func, '__name__', repr(func))}"
            )
            if last_exception is not None:
                raise last_exception
            raise RuntimeError(
                f"Retries exhausted for {getattr(func, '__name__', repr(func))}"
            )

        return wrapper

    return decorator


@dataclass
class ConnectionPool:
    """
    Simple connection pool for managing API connections.

    Tracks connection health and provides automatic failover
    for multi-endpoint scenarios.
    """

    endpoints: list[str] = field(default_factory=list)
    _health: dict[str, bool] = field(default_factory=dict, init=False)
    _last_check: dict[str, datetime] = field(default_factory=dict, init=False)
    health_check_interval: float = 60.0  # seconds

    def __post_init__(self) -> None:
        for endpoint in self.endpoints:
            self._health[endpoint] = True

    def get_healthy_endpoint(self) -> str | None:
        """Get a healthy endpoint, or None if all are unhealthy."""
        for endpoint in self.endpoints:
            if self._health.get(endpoint, True):
                return endpoint
        return None

    def mark_unhealthy(self, endpoint: str) -> None:
        """Mark an endpoint as unhealthy."""
        self._health[endpoint] = False
        self._last_check[endpoint] = datetime.now()
        logger.warning(f"Endpoint marked unhealthy: {endpoint}")

    def mark_healthy(self, endpoint: str) -> None:
        """Mark an endpoint as healthy."""
        self._health[endpoint] = True
        logger.info(f"Endpoint recovered: {endpoint}")

    def should_retry_endpoint(self, endpoint: str) -> bool:
        """Check if enough time has passed to retry an unhealthy endpoint."""
        if self._health.get(endpoint, True):
            return True
        last_check = self._last_check.get(endpoint)
        if last_check is None:
            return True
        elapsed = (datetime.now() - last_check).total_seconds()
        return elapsed >= self.health_check_interval
