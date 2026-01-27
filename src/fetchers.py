"""Data fetching functions for Wikipedia dispute data collection."""

from __future__ import annotations

import re
from datetime import datetime

import mwparserfromhell

from src.wiki import WikiClient
from src.analysis import analyze_edit_war


def fetch_arbitration_cases(client: WikiClient, limit: int = 100) -> list[dict]:
    """
    Fetch arbitration cases from Wikipedia.

    Args:
        client: WikiClient instance
        limit: Maximum number of cases to fetch

    Returns:
        List of case dictionaries with title, revisions, and content
    """
    pages = client.get_category_pages("Wikipedia arbitration cases", limit=limit)

    cases = []
    for page in pages:
        print(f"Fetching: {page.title()}")

        case_data = {
            "title": page.title(),
            "url": page.full_url(),
            "last_edit": None,
            "revisions": [],
            "content": None,
        }

        try:
            case_data["revisions"] = client.get_revisions(page.title())
            if case_data["revisions"]:
                case_data["last_edit"] = case_data["revisions"][0]["timestamp"]
            case_data["content"] = page.text
        except Exception as e:
            print(f"  Error: {e}")
            case_data["error"] = str(e)

        cases.append(case_data)

    return cases


def fetch_drn_page(client: WikiClient) -> dict:
    """Fetch the main DRN page content and metadata."""
    page = client.get_page("Wikipedia:Dispute resolution noticeboard")

    if not page.exists():
        raise ValueError("DRN page not found")

    print(f"Fetching: {page.title()}")

    return {
        "title": page.title(),
        "url": page.full_url(),
        "fetched_at": datetime.now().isoformat(),
        "content": page.text,
        "revisions": client.get_revisions(page.title(), limit=100),
    }


def parse_drn_sections(content: str) -> list[dict]:
    """Parse DRN page content into individual case sections."""
    wikicode = mwparserfromhell.parse(content)

    cases = []
    current_section = None

    for node in wikicode.nodes:
        if isinstance(node, mwparserfromhell.nodes.Heading):
            if current_section and current_section.get("content"):
                cases.append(current_section)

            current_section = {
                "title": str(node.title).strip(),
                "level": node.level,
                "content": "",
                "templates": [],
                "links": [],
            }
        elif current_section is not None:
            current_section["content"] += str(node)

            if isinstance(node, mwparserfromhell.nodes.Template):
                current_section["templates"].append(str(node.name).strip())

            if isinstance(node, mwparserfromhell.nodes.Wikilink):
                current_section["links"].append(str(node.title).strip())

    if current_section and current_section.get("content"):
        cases.append(current_section)

    return cases


def extract_case_metadata(cases: list[dict]) -> list[dict]:
    """Extract structured metadata from parsed DRN cases."""
    for case in cases:
        templates_lower = [t.lower() for t in case.get("templates", [])]

        case["status"] = "unknown"
        if any("resolved" in t for t in templates_lower):
            case["status"] = "resolved"
        elif any("active" in t or "open" in t for t in templates_lower):
            case["status"] = "active"
        elif any("closed" in t for t in templates_lower):
            case["status"] = "closed"
        elif any("stale" in t for t in templates_lower):
            case["status"] = "stale"

        signatures = re.findall(r"\[\[User:([^\]|]+)", case.get("content", ""))
        case["participants"] = list(set(signatures))
        case["participant_count"] = len(case["participants"])

        article_links = [
            link
            for link in case.get("links", [])
            if not link.startswith(("User:", "Wikipedia:", "Talk:", "User talk:"))
        ]
        case["disputed_articles"] = article_links[:5]

    return cases


def fetch_revisions(
    client: WikiClient,
    article_title: str,
    include_talk: bool = True,
    limit: int | None = None,
) -> dict:
    """
    Fetch revision history for an article and optionally its talk page.

    Args:
        client: WikiClient instance
        article_title: Wikipedia article title
        include_talk: Whether to include talk page revisions
        limit: Maximum revisions to fetch (None = all)

    Returns:
        Dictionary with article and talk page revision data
    """
    info = client.get_page_info(article_title)

    data = {
        "article": {
            "title": info["title"],
            "url": info["url"],
            "revisions": client.get_revisions(article_title, limit=limit),
        },
        "talk": None,
        "fetched_at": datetime.now().isoformat(),
    }

    print(f"Fetched {len(data['article']['revisions'])} revisions for {info['title']}")

    if include_talk:
        talk = client.get_talk_page(article_title)
        if talk:
            data["talk"] = {
                "title": talk.title(),
                "url": talk.full_url(),
                "revisions": client.get_revisions(talk.title(), limit=limit),
            }
            print(f"Fetched {len(data['talk']['revisions'])} talk page revisions")

    return data


def analyze_article_edit_war(
    client: WikiClient,
    article_title: str,
    lookback: int = 500,
    threshold: float = 0.1,
) -> dict:
    """
    Run edit war analysis on an article.

    Args:
        client: WikiClient instance
        article_title: Wikipedia article title
        lookback: Number of revisions to analyze
        threshold: Revert ratio threshold for flagging

    Returns:
        Dictionary with analysis results
    """
    print(f"Analyzing: {article_title}")

    info = client.get_page_info(article_title)
    revisions = client.get_revisions(article_title, limit=lookback)
    protection = client.get_page_protection(article_title)

    metrics = analyze_edit_war(revisions, threshold=threshold)

    return {
        "title": info["title"],
        "url": info["url"],
        "analyzed_at": datetime.now().isoformat(),
        "protection": protection,
        **metrics,
    }
