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

__all__ = [
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
]
