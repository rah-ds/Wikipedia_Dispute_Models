"""Tests for utility functions."""

from pathlib import Path
import pytest
from src.utils import get_project_root, get_data_path, get_results_path


def test_get_project_root():
    """Test that get_project_root returns a valid path."""
    root = get_project_root()
    assert isinstance(root, Path)
    assert root.exists()
    assert (root / 'src').exists()


def test_get_data_path():
    """Test that get_data_path constructs correct paths."""
    data_path = get_data_path('raw/test.csv')
    assert isinstance(data_path, Path)
    assert 'data' in str(data_path)
    assert 'raw' in str(data_path)
    assert str(data_path).endswith('test.csv')


def test_get_results_path():
    """Test that get_results_path constructs correct paths."""
    results_path = get_results_path('test/output.pkl')
    assert isinstance(results_path, Path)
    assert 'results' in str(results_path)
    assert str(results_path).endswith('output.pkl')
