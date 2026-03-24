"""Common CLI utilities for data fetching scripts.

Provides shared functionality:
- Graceful shutdown handling (Ctrl+C)
- Standard script initialization
- Memory monitoring
"""

from __future__ import annotations

import signal
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.wiki import WikiClient
    import logging

# Global references for shutdown handler
_client: WikiClient | None = None
_logger: logging.Logger | None = None


def register_client(client: WikiClient) -> None:
    """Register WikiClient for graceful shutdown stats logging."""
    global _client
    _client = client


def register_logger(logger: logging.Logger) -> None:
    """Register logger for shutdown messages."""
    global _logger
    _logger = logger


def shutdown_handler(signum, frame):
    """Handle Ctrl+C gracefully - log stats before exit."""
    print("\n\n⚠️  Interrupted! Logging stats before exit...")
    if _client:
        _client.log_stats()
        stats = _client.get_stats()
        print(
            f"📊 API Stats: {stats['total_requests']} requests in {stats['runtime_minutes']:.1f} min"
        )
    if _logger:
        _logger.info("Fetch interrupted by user")
    sys.exit(130)


def setup_shutdown_handler() -> None:
    """Register the SIGINT handler for graceful Ctrl+C handling."""
    signal.signal(signal.SIGINT, shutdown_handler)


def get_memory_mb() -> float:
    """Get current memory usage in MB (macOS/Linux)."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        # macOS returns bytes, Linux returns KB
        if sys.platform == "darwin":
            return usage.ru_maxrss / 1024 / 1024
        else:
            return usage.ru_maxrss / 1024
    except Exception:
        return 0.0
