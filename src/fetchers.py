"""Data fetching functions for Wikipedia dispute data collection."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Optional

import mwparserfromhell
from tqdm import tqdm

from src.wiki import WikiClient
from src.analysis import analyze_edit_war

logger = logging.getLogger(__name__)


def fetch_arbitration_cases(
    client: WikiClient,
    limit: int = 100,
    delay: float = 1.0,
) -> list[dict]:
    """
    Fetch arbitration cases from Wikipedia.

    Args:
        client: WikiClient instance
        limit: Maximum number of cases to fetch
        delay: Seconds to wait between fetches (rate limiting)

    Returns:
        List of case dictionaries with title, revisions, and content
    """
    pages = client.get_category_pages("Wikipedia arbitration cases", limit=limit)

    cases = []
    for page in tqdm(pages, desc="Arbitration cases", unit="case"):
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
            tqdm.write(f"  Error fetching {page.title()}: {e}")
            case_data["error"] = str(e)

        cases.append(case_data)
        time.sleep(delay)  # Rate limiting

    return cases


def fetch_drn_page(client: WikiClient) -> dict:
    """Fetch the main DRN page content and metadata."""
    page = client.get_page("Wikipedia:Dispute resolution noticeboard")

    if not page.exists():
        raise ValueError("DRN page not found")

    tqdm.write(f"Fetching: {page.title()}")

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

    tqdm.write(f"  {info['title']}: {len(data['article']['revisions'])} revisions")

    if include_talk:
        talk = client.get_talk_page(article_title)
        if talk:
            data["talk"] = {
                "title": talk.title(),
                "url": talk.full_url(),
                "revisions": client.get_revisions(talk.title(), limit=limit),
            }
            tqdm.write(f"  {talk.title()}: {len(data['talk']['revisions'])} revisions")

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
    info = client.get_page_info(article_title)
    revisions = client.get_revisions(article_title, limit=lookback)
    protection = client.get_page_protection(article_title)

    metrics = analyze_edit_war(revisions, threshold=threshold)

    status = "⚠️ WAR" if metrics["edit_war_detected"] else "✓"
    tqdm.write(f"  {info['title']}: {metrics['revert_ratio']:.1%} reverts {status}")

    return {
        "title": info["title"],
        "url": info["url"],
        "analyzed_at": datetime.now().isoformat(),
        "protection": protection,
        **metrics,
    }


# =============================================================================
# Phase 2: Dispute Venue Fetchers
# =============================================================================


def fetch_talk_page_revisions(
    client: WikiClient,
    article_title: str,
    limit: int | None = None,
) -> dict:
    """
    Fetch talk page revision history for an article.

    Args:
        client: WikiClient instance
        article_title: Wikipedia article title (not the talk page)
        limit: Maximum revisions to fetch (None = all)

    Returns:
        Dictionary with talk page metadata and revisions
    """
    talk = client.get_talk_page(article_title)

    if not talk:
        logger.debug(f"No talk page for: {article_title}")
        return {
            "article": article_title,
            "talk_title": f"Talk:{article_title}",
            "exists": False,
            "revisions": [],
            "fetched_at": datetime.now().isoformat(),
        }

    revisions = client.get_revisions(talk.title(), limit=limit)

    return {
        "article": article_title,
        "talk_title": talk.title(),
        "talk_url": talk.full_url(),
        "exists": True,
        "revisions": revisions,
        "revision_count": len(revisions),
        "fetched_at": datetime.now().isoformat(),
    }


def search_ani_mentions(
    client: WikiClient,
    search_term: str,
    limit: int = 50,
    max_archives: int = 50,
) -> list[dict]:
    """
    Search ANI archives for mentions of an article or user.

    Searches both the main ANI page and the archive pages.

    Args:
        client: WikiClient instance
        search_term: Article title or username to search for
        limit: Maximum results to return
        max_archives: Maximum archive pages to search

    Returns:
        List of ANI sections mentioning the search term
    """
    results = []
    consecutive_misses = 0

    # Search current ANI page
    ani_page = client.get_page("Wikipedia:Administrators' noticeboard/Incidents")
    if ani_page.exists():
        content = ani_page.text
        if search_term.lower() in content.lower():
            sections = _extract_ani_sections(content, search_term)
            for section in sections[:limit]:
                section["source"] = "current_ani"
                section["source_url"] = ani_page.full_url()
                results.append(section)

    # Search archives (most recent first)
    archive_count = 0

    for i in range(1, max_archives + 1):
        if len(results) >= limit:
            break

        archive_title = f"Wikipedia:Administrators' noticeboard/IncidentArchive{i}"
        try:
            archive = client.get_page(archive_title)
            if not archive.exists():
                consecutive_misses += 1
                if consecutive_misses >= 3:
                    break  # Stop after 3 consecutive missing archives
                continue

            consecutive_misses = 0
            content = archive.text
            if search_term.lower() in content.lower():
                sections = _extract_ani_sections(content, search_term)
                for section in sections:
                    if len(results) >= limit:
                        break
                    section["source"] = f"archive_{i}"
                    section["source_url"] = archive.full_url()
                    results.append(section)

            archive_count += 1
            time.sleep(0.3)  # Rate limit
        except Exception as e:
            logger.warning(f"Error fetching {archive_title}: {e}")
            consecutive_misses += 1
            if consecutive_misses >= 3:
                break

    logger.info(
        f"ANI search for '{search_term}': {len(results)} mentions in {archive_count + 1} pages"
    )

    return results


def _extract_ani_sections(content: str, search_term: str) -> list[dict]:
    """Extract ANI sections containing the search term."""
    wikicode = mwparserfromhell.parse(content)
    sections = []

    current_section = None
    for node in wikicode.nodes:
        if isinstance(node, mwparserfromhell.nodes.Heading):
            # Save previous section if it contains the search term
            if (
                current_section
                and search_term.lower() in current_section["content"].lower()
            ):
                sections.append(current_section)

            current_section = {
                "title": str(node.title).strip(),
                "level": node.level,
                "content": "",
                "participants": [],
                "links": [],
            }
        elif current_section is not None:
            current_section["content"] += str(node)

    # Don't forget the last section
    if current_section and search_term.lower() in current_section["content"].lower():
        sections.append(current_section)

    # Extract participants from each section
    for section in sections:
        signatures = re.findall(r"\[\[User:([^\]|]+)", section["content"])
        section["participants"] = list(set(signatures))

        # Extract linked articles
        article_links = re.findall(r"\[\[([^\]:|]+)\]\]", section["content"])
        section["links"] = [
            link
            for link in article_links
            if not link.startswith(("User", "Wikipedia", "Talk", "WP:", "Special:"))
        ][:10]

        # Truncate content for storage
        section["content_preview"] = section["content"][:500]
        if len(section["content"]) > 500:
            section["content_preview"] += "..."
        section["content_length"] = len(section["content"])
        del section["content"]  # Don't store full content

    return sections


def fetch_third_opinion_requests(
    client: WikiClient,
    article_title: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    """
    Fetch Third Opinion (3O) requests.

    If article_title is provided, searches for requests about that article.
    Otherwise, returns active 3O requests.

    Args:
        client: WikiClient instance
        article_title: Optional article to filter for
        limit: Maximum results

    Returns:
        List of 3O request dictionaries
    """
    # 3O active requests page
    page = client.get_page("Wikipedia:Third opinion/Active")

    if not page.exists():
        # Try the main 3O page
        page = client.get_page("Wikipedia:Third opinion")

    if not page.exists():
        logger.warning("Third Opinion page not found")
        return []

    content = page.text
    wikicode = mwparserfromhell.parse(content)

    requests = []
    current_request = None

    for node in wikicode.nodes:
        if isinstance(node, mwparserfromhell.nodes.Heading):
            if current_request:
                # Filter by article if specified
                if (
                    article_title is None
                    or article_title.lower() in current_request["title"].lower()
                ):
                    requests.append(current_request)

            current_request = {
                "title": str(node.title).strip(),
                "level": node.level,
                "content": "",
                "disputants": [],
                "article_links": [],
            }
        elif current_request is not None:
            current_request["content"] += str(node)

    # Last request
    if current_request:
        if (
            article_title is None
            or article_title.lower() in current_request["title"].lower()
        ):
            requests.append(current_request)

    # Process each request
    for req in requests:
        # Extract disputants (typically 2 for 3O)
        signatures = re.findall(r"\[\[User:([^\]|]+)", req["content"])
        req["disputants"] = list(set(signatures))[:2]

        # Extract article links
        article_links = re.findall(r"\[\[([^\]:|]+)\]\]", req["content"])
        req["article_links"] = [
            link
            for link in article_links
            if not link.startswith(("User", "Wikipedia", "Talk", "WP:"))
        ][:5]

        # Content preview
        req["content_preview"] = req["content"][:300]
        req["content_length"] = len(req["content"])
        del req["content"]

    return requests[:limit]


def fetch_rfc_for_article(
    client: WikiClient,
    article_title: str,
) -> list[dict]:
    """
    Search for Requests for Comment (RfC) related to an article.

    Checks the article's talk page for RfC templates and searches
    the RfC listings.

    Args:
        client: WikiClient instance
        article_title: Article title to search for

    Returns:
        List of RfC entries
    """
    rfcs = []

    # Check talk page for RfC templates
    talk = client.get_talk_page(article_title)
    if talk:
        try:
            content = talk.text
            wikicode = mwparserfromhell.parse(content)

            for template in wikicode.filter_templates():
                template_name = str(template.name).strip().lower()
                if "rfc" in template_name or "request for comment" in template_name:
                    rfc_entry = {
                        "source": "talk_page",
                        "article": article_title,
                        "template": str(template.name).strip(),
                        "params": {
                            str(p.name).strip(): str(p.value).strip()
                            for p in template.params
                        },
                    }
                    rfcs.append(rfc_entry)
        except Exception as e:
            logger.warning(f"Error parsing talk page for RfCs: {e}")

    # Search RfC listings (limit to avoid excessive requests)
    rfc_categories = [
        "Category:Wikipedia requests for comment",
    ]

    for cat_name in rfc_categories:
        try:
            pages = client.get_category_pages(cat_name, limit=50)
            for page in pages:
                if article_title.lower() in page.title().lower():
                    rfcs.append(
                        {
                            "source": "rfc_category",
                            "article": article_title,
                            "rfc_page": page.title(),
                            "rfc_url": page.full_url(),
                        }
                    )
        except Exception as e:
            logger.debug(f"Error searching RfC category {cat_name}: {e}")

    return rfcs


def fetch_dispute_venues_for_article(
    client: WikiClient,
    article_title: str,
    include_talk: bool = True,
    include_ani: bool = True,
    include_3o: bool = True,
    include_rfc: bool = True,
    ani_limit: int = 20,
) -> dict:
    """
    Fetch all dispute venue data for an article.

    This is the main entry point for Phase 2 data collection.
    Gathers talk page history, ANI mentions, 3O requests, and RfCs.

    Args:
        client: WikiClient instance
        article_title: Article to analyze
        include_talk: Fetch talk page revisions
        include_ani: Search ANI archives
        include_3o: Search Third Opinion
        include_rfc: Search RfC listings
        ani_limit: Max ANI results

    Returns:
        Dictionary with all dispute venue data
    """
    logger.info(f"Fetching dispute venues for: {article_title}")

    result = {
        "article": article_title,
        "fetched_at": datetime.now().isoformat(),
        "talk_page": None,
        "ani_mentions": [],
        "third_opinion": [],
        "rfc": [],
    }

    if include_talk:
        tqdm.write("  Fetching talk page...")
        result["talk_page"] = fetch_talk_page_revisions(client, article_title)

    if include_ani:
        tqdm.write("  Searching ANI archives...")
        result["ani_mentions"] = search_ani_mentions(
            client, article_title, limit=ani_limit
        )

    if include_3o:
        tqdm.write("  Checking Third Opinion...")
        result["third_opinion"] = fetch_third_opinion_requests(client, article_title)

    if include_rfc:
        tqdm.write("  Searching RfCs...")
        result["rfc"] = fetch_rfc_for_article(client, article_title)

    # Summary
    result["summary"] = {
        "has_talk_page": result["talk_page"]["exists"]
        if result["talk_page"]
        else False,
        "talk_revision_count": result["talk_page"]["revision_count"]
        if result["talk_page"] and result["talk_page"]["exists"]
        else 0,
        "ani_mention_count": len(result["ani_mentions"]),
        "third_opinion_count": len(result["third_opinion"]),
        "rfc_count": len(result["rfc"]),
    }

    tqdm.write(f"  Summary: {result['summary']}")

    return result
