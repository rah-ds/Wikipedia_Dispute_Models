"""Centralized logging configuration for Wikipedia Dispute Models.

This module provides consistent, configurable logging across all modules.
Supports file output, console output, and structured logging for long-running pulls.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class JsonFormatter(logging.Formatter):
    """Format log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "extra_data"):
            log_obj["data"] = record.extra_data
        return json.dumps(log_obj)


class PullProgressHandler(logging.Handler):
    """Handler that tracks progress for data pull operations."""

    def __init__(self) -> None:
        super().__init__()
        self.stats: dict[str, int] = {
            "api_calls": 0,
            "pages_fetched": 0,
            "errors": 0,
            "warnings": 0,
            "retries": 0,
        }
        self.start_time = datetime.now()

    def emit(self, record: logging.LogRecord) -> None:
        # Track statistics based on log content
        msg = record.getMessage().lower()

        if "api request" in msg or "fetching" in msg:
            self.stats["api_calls"] += 1
        if "fetched" in msg or "saved" in msg:
            self.stats["pages_fetched"] += 1
        if record.levelno >= logging.ERROR:
            self.stats["errors"] += 1
        elif record.levelno >= logging.WARNING:
            self.stats["warnings"] += 1
        if "retry" in msg or "attempt" in msg:
            self.stats["retries"] += 1

    def get_summary(self) -> dict[str, Any]:
        runtime = (datetime.now() - self.start_time).total_seconds()
        return {
            **self.stats,
            "runtime_seconds": runtime,
            "pages_per_minute": (
                self.stats["pages_fetched"] / (runtime / 60) if runtime > 0 else 0
            ),
        }


def setup_logging(
    name: str = "wiki_disputes",
    level: int = logging.INFO,
    log_dir: str | Path | None = None,
    console: bool = True,
    json_format: bool = False,
    max_file_size: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> tuple[logging.Logger, PullProgressHandler | None]:
    """
    Configure logging for the application.

    Args:
        name: Logger name
        level: Logging level (default: INFO)
        log_dir: Directory for log files (default: artifacts/logs/data_pull)
        console: Whether to output to console
        json_format: Use JSON formatting for file logs
        max_file_size: Max size per log file before rotation
        backup_count: Number of backup files to keep

    Returns:
        Tuple of (logger, progress_handler) where progress_handler tracks pull stats
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Clear existing handlers
    logger.handlers.clear()

    # Console formatter
    console_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # File formatter
    file_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(console_fmt)
        logger.addHandler(console_handler)

    # File handler
    progress_handler = None
    if log_dir is not None:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        # Main log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_path / f"{name}_{timestamp}.log"

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(JsonFormatter() if json_format else file_fmt)
        logger.addHandler(file_handler)

        # Error-only file
        error_file = log_path / f"{name}_{timestamp}_errors.log"
        error_handler = RotatingFileHandler(
            error_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_fmt)
        logger.addHandler(error_handler)

        # Progress tracking handler
        progress_handler = PullProgressHandler()
        progress_handler.setLevel(logging.DEBUG)
        logger.addHandler(progress_handler)

    return logger, progress_handler


def get_logger(name: str) -> logging.Logger:
    """Get a child logger with the given name."""
    return logging.getLogger(f"wiki_disputes.{name}")


def log_api_call(
    logger: logging.Logger,
    endpoint: str,
    params: dict[str, Any] | None = None,
    response_size: int | None = None,
) -> None:
    """Log an API call with structured data."""
    msg = f"API call: {endpoint}"
    if params:
        msg += f" | params={params}"
    if response_size is not None:
        msg += f" | response_size={response_size}"
    logger.debug(msg)


def log_progress(
    logger: logging.Logger,
    current: int,
    total: int,
    item_name: str = "items",
    extra: str = "",
) -> None:
    """Log progress for batch operations."""
    pct = (current / total * 100) if total > 0 else 0
    msg = f"Progress: {current}/{total} {item_name} ({pct:.1f}%)"
    if extra:
        msg += f" | {extra}"
    logger.info(msg)


def log_error_with_context(
    logger: logging.Logger,
    message: str,
    error: Exception,
    context: dict[str, Any] | None = None,
) -> None:
    """Log an error with additional context for debugging."""
    ctx_str = ""
    if context:
        ctx_str = " | context=" + json.dumps(context)
    logger.error(f"{message}: {error}{ctx_str}", exc_info=True)
