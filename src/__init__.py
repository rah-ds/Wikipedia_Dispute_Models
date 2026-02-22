"""Wikipedia Dispute Models - Core library for Wikipedia data collection."""

from .wiki import WikiClient
from .io import save_json, load_json, get_output_path
from .analysis import detect_reverts, analyze_edit_war
from .fetchers import (
    fetch_arbitration_cases,
    fetch_drn_page,
    fetch_revisions,
    analyze_article_edit_war,
)

# New infrastructure modules
from .logging_config import setup_logging, get_logger
from .network import CircuitBreaker, RetryConfig, retry_with_backoff
from .credentials import validate_environment, require_valid_environment
from .pull_config import PullConfig, get_sample_config, get_full_config
from .pull_state import StateManager, PullState

__all__ = [
    # Core
    "WikiClient",
    "save_json",
    "load_json",
    "get_output_path",
    "detect_reverts",
    "analyze_edit_war",
    "fetch_arbitration_cases",
    "fetch_drn_page",
    "fetch_revisions",
    "analyze_article_edit_war",
    # Logging
    "setup_logging",
    "get_logger",
    # Network
    "CircuitBreaker",
    "RetryConfig",
    "retry_with_backoff",
    # Credentials
    "validate_environment",
    "require_valid_environment",
    # Pull config
    "PullConfig",
    "get_sample_config",
    "get_full_config",
    # State management
    "StateManager",
    "PullState",
]
