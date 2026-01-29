"""File I/O utilities for saving and loading data."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"


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
