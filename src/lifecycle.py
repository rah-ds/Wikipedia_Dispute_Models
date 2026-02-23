"""
Dispute lifecycle collection module.

Wraps the fetch_dispute_lifecycle script for use by pull.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure scripts/ is importable so we can reuse fetch_dispute_lifecycle
_scripts_dir = str(Path(__file__).parent.parent / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)

from fetch_dispute_lifecycle import fetch_dispute_lifecycle  # noqa: E402
from src.wiki import WikiClient  # noqa: E402


def collect_dispute_lifecycle(
    client: WikiClient,
    case_name: str,
    revision_limit: int | None = 100,
    max_talk_pages: int = 10,
) -> dict:
    """
    Collect full dispute lifecycle data for an arbitration case.

    This is a convenience wrapper around fetch_dispute_lifecycle
    with the parameter interface expected by pull.py.

    Args:
        client: WikiClient instance
        case_name: Arbitration case name (e.g., "Climate change")
        revision_limit: Max revisions per page (None = all)
        max_talk_pages: Maximum article talk pages to fetch

    Returns:
        Dictionary with dispute lifecycle data organized by venue/stage
    """
    return fetch_dispute_lifecycle(
        client=client,
        case_name=case_name,
        max_talk_pages=max_talk_pages,
        revision_limit=revision_limit,
    )
