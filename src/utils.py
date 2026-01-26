"""Utility functions for the Wikipedia Dispute Models project.

This module contains common utility functions used across the project.
"""

import os
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory.
    
    Returns:
        Path: Path to the project root directory
    """
    return Path(__file__).parent.parent


def get_data_path(relative_path: str) -> Path:
    """Get the full path to a data file.
    
    Args:
        relative_path: Relative path from the data directory
        
    Returns:
        Path: Full path to the data file
        
    Example:
        >>> data_path = get_data_path('raw/sample.csv')
    """
    return get_project_root() / 'data' / relative_path


def get_results_path(relative_path: str) -> Path:
    """Get the full path to a results file.
    
    Args:
        relative_path: Relative path from the results directory
        
    Returns:
        Path: Full path to the results file
        
    Example:
        >>> results_path = get_results_path('2026-01/model_output.pkl')
    """
    results_dir = get_project_root() / 'results' / relative_path
    results_dir.parent.mkdir(parents=True, exist_ok=True)
    return results_dir
