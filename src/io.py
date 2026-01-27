"""File I/O utilities for saving and loading data."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "artifacts" / "logs"
DATA_PULL_LOGS_DIR = LOGS_DIR / "data_pull"


def check_api_credentials(logger: logging.Logger | None = None) -> bool:
    """
    Check if Wikimedia API credentials are configured and warn if not.

    Looks for environment variables or pywikibot user-config.py.
    
    Args:
        logger: Logger instance for warnings. If None, uses module logger.
    
    Returns:
        True if credentials appear to be configured, False otherwise.
    """
    if logger is None:
        logger = logging.getLogger(__name__)
    
    # Check for common API credential indicators
    has_credentials = False
    
    # Check environment variables
    if os.environ.get("WIKI_API_KEY") or os.environ.get("PYWIKIBOT_PASSWORD"):
        has_credentials = True
    
    # Check for pywikibot user-config.py
    user_config = Path.home() / ".pywikibot" / "user-config.py"
    if user_config.exists():
        has_credentials = True
    
    # Check for .env file with credentials
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        content = env_file.read_text()
        if "WIKI_API_KEY" in content or "PYWIKIBOT" in content:
            has_credentials = True
    
    if not has_credentials:
        logger.warning("=" * 70)
        logger.warning("⚠️  NO WIKIMEDIA API CREDENTIALS DETECTED")
        logger.warning("=" * 70)
        logger.warning("You are using the Wikipedia API without authentication.")
        logger.warning("")
        logger.warning("Rate limits for unauthenticated requests:")
        logger.warning("  • 500 requests per hour (vs 5,000+ with API key)")
        logger.warning("  • Aggressive throttling during peak times")
        logger.warning("  • May be blocked during high-traffic periods")
        logger.warning("")
        logger.warning("To get better rate limits:")
        logger.warning("  1. Create a Wikimedia account: https://en.wikipedia.org/wiki/Special:CreateAccount")
        logger.warning("  2. Get API credentials: https://api.wikimedia.org/wiki/Getting_started")
        logger.warning("  3. Set WIKI_API_KEY in your .env file")
        logger.warning("  4. Or configure pywikibot: https://www.mediawiki.org/wiki/Manual:Pywikibot/user-config.py")
        logger.warning("=" * 70)
    
    return has_credentials


def setup_logging(
    name: str,
    level: int = logging.INFO,
    log_file: str | None = None,
    log_dir: Path | None = None,
) -> logging.Logger:
    """
    Set up logging with file and console handlers.

    Args:
        name: Logger name (typically script name)
        level: Logging level
        log_file: Log filename (without path). If None, uses {name}_{timestamp}.log
        log_dir: Directory for log files. Defaults to DATA_PULL_LOGS_DIR for data fetch scripts.

    Returns:
        Configured logger instance
    """
    if log_dir is None:
        log_dir = DATA_PULL_LOGS_DIR
    
    log_dir.mkdir(parents=True, exist_ok=True)

    if log_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"{name}_{timestamp}.log"

    log_path = log_dir / log_file

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding handlers multiple times
    if not logger.handlers:
        # File handler
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter("%(levelname)s - %(message)s")
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    logger.info(f"Logging to {log_path}")
    return logger


def get_output_path(
    subdir: str,
    filename: str | None = None,
    prefix: str = "",
    timestamp: bool = True,
) -> Path:
    """
    Get output file path, creating directories as needed.

    Args:
        subdir: Subdirectory under data/raw/ (e.g., "arbitration", "revisions")
        filename: Base filename (optional)
        prefix: Filename prefix
        timestamp: Whether to add timestamp to filename

    Returns:
        Path object for output file
    """
    output_dir = DATA_DIR / "raw" / subdir
    output_dir.mkdir(parents=True, exist_ok=True)

    if filename:
        return output_dir / filename

    ts = datetime.now().strftime("%Y%m%d_%H%M%S") if timestamp else ""
    name = f"{prefix}_{ts}.json" if ts else f"{prefix}.json"
    return output_dir / name.lstrip("_")


def save_json(data: dict | list, path: Path | str) -> Path:
    """
    Save data to JSON file.

    Args:
        data: Data to save
        path: Output file path

    Returns:
        Path to saved file
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    return path


def load_json(path: Path | str) -> dict | list:
    """
    Load data from JSON file.

    Args:
        path: Input file path

    Returns:
        Loaded data
    """
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def sanitize_filename(name: str) -> str:
    """Convert a string to a safe filename."""
    return name.replace("/", "_").replace(" ", "_").replace(":", "_")
