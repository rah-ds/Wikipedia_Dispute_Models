#!/usr/bin/env python3
"""
Input/Output utilities for saving and loading data.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Any, Dict


def get_output_path(category: str, prefix: str = "data") -> Path:
    """
    Generate an output path with timestamp.
    
    Args:
        category: Data category (e.g., 'arbitration', 'drn')
        prefix: Filename prefix
    
    Returns:
        Path object for the output file
    """
    base_dir = Path(__file__).parent.parent / "data" / "raw" / category
    base_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.json"
    
    return base_dir / filename


def save_json(data: Any, filepath: Path) -> None:
    """
    Save data as JSON to the specified path.
    
    Args:
        data: Data to save
        filepath: Path to save file
    """
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(filepath: Path) -> Any:
    """
    Load JSON data from the specified path.
    
    Args:
        filepath: Path to JSON file
    
    Returns:
        Loaded data
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a string to be used as a filename.
    
    Args:
        filename: Original filename
    
    Returns:
        Sanitized filename
    """
    # Remove or replace invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip('. ')
    # Limit length
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    
    return sanitized
