"""
Dispute lifecycle data collection logic.

Core library functions for tracing the full dispute resolution lifecycle
from an arbitration case name through all escalation stages:

    Talk Page → DRN → ANI → ArbCom

This module contains the reusable logic extracted from the CLI script
``scripts/fetch_dispute_lifecycle.py`` so that it can be tested and
imported by notebooks or other tools.

Public API
----------
- :func:`fetch_dispute_lifecycle` — main entry point (returns dict)
- :func:`find_arb_case_path` — resolve case name → Wikipedia page prefix
- :func:`get_arb_case_prefix` — default prefix for a case name
- :func:`extract_article_links` — pull article wikilinks from wikitext
- :func:`extract_participants` — pull User: mentions from wikitext
- :func:`search_drn_mentions` — search DRN current + archives
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime

import mwparserfromhell

from src.wiki import WikiClient
from src.fetchers import search_ani_mentions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Known arbitration case subpages (empty string = main page).
ARB_SUBPAGES = [
    "",  # Main page
    "/Evidence",
    "/Workshop",
    "/Proposed decision",
    "/Final decision",
    "/Remedies",
    "/Clarification requests",
]

#: Multiple path patterns for arbitration cases
#: (Wikipedia changed format over time).
ARB_PATH_PATTERNS = [
    "Wikipedia:Arbitration/Requests/Case/{name}",  # Current format (post-2010)
    "Wikipedia:Requests for arbitration/{name}",  # Older format
    "Wikipedia:Arbitration/{name}",  # Very old format
]

#: Subpages whose raw wikitext we persist in the JSON output so that
#: downstream parsers (``outcome.py``) can extract structured data.
SAVE_WIKITEXT_SUFFIXES = {"", "/Proposed decision", "/Final decision", "/Remedies"}


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def find_arb_case_path(client: WikiClient, case_name: str) -> tuple[str | None, str]:
    """
    Find the correct Wikipedia path for an arbitration case.

    Tries multiple path patterns since Wikipedia changed formats over time.

    Returns:
        Tuple of (working_prefix, pattern_used) or (None, "not_found")
    """
    if case_name.startswith("Wikipedia:"):
        # Already a full path
        page = client.get_page(case_name)
        if page.exists():
            return case_name, "provided"
        return None, "not_found"

    for pattern in ARB_PATH_PATTERNS:
        prefix = pattern.format(name=case_name)
        try:
            page = client.get_page(prefix)
            if page.exists():
                return prefix, pattern
        except Exception:
            pass

    return None, "not_found"


def get_arb_case_prefix(case_name: str) -> str:
    """Get the default Wikipedia page prefix for an arbitration case."""
    if case_name.startswith("Wikipedia:Arbitration"):
        return case_name
    return f"Wikipedia:Arbitration/Requests/Case/{case_name}"


# ---------------------------------------------------------------------------
# Wikitext extraction helpers
# ---------------------------------------------------------------------------


def extract_article_links(content: str) -> list[str]:
    """Extract article wikilinks from page content, filtering out non-articles."""
    wikicode = mwparserfromhell.parse(content)
    articles: set[str] = set()

    for link in wikicode.filter_wikilinks():
        title = str(link.title).strip()

        # Skip non-article namespaces
        skip_prefixes = (
            "User:",
            "User talk:",
            "Wikipedia:",
            "Wikipedia talk:",
            "Talk:",
            "Template:",
            "Template talk:",
            "Category:",
            "File:",
            "Image:",
            "WP:",
            "Special:",
            "Help:",
            "Portal:",
            "Draft:",
            "Module:",
        )
        if title.startswith(skip_prefixes):
            continue

        if title.startswith("#"):
            continue

        if "#" in title:
            title = title.split("#")[0]

        if title:
            articles.add(title)

    return list(articles)


def extract_participants(content: str) -> list[str]:
    """Extract user mentions from page content."""
    user_links = re.findall(r"\[\[User:([^\]|]+)", content, re.IGNORECASE)
    user_talk_links = re.findall(r"\[\[User talk:([^\]|]+)", content, re.IGNORECASE)

    all_users: set[str] = set()
    for user in user_links + user_talk_links:
        user = user.strip()
        if user and not user.startswith(("#", "/")):
            all_users.add(user)

    return list(all_users)


# ---------------------------------------------------------------------------
# DRN search
# ---------------------------------------------------------------------------


def search_drn_mentions(
    client: WikiClient,
    search_terms: list[str],
    archive_limit: int = 50,
) -> list[dict]:
    """
    Search DRN current page and archives for mentions of case/participants.

    Args:
        client: WikiClient instance
        search_terms: List of terms to search (case name, participants)
        archive_limit: Max archives to search

    Returns:
        List of DRN mention records
    """
    results: list[dict] = []
    consecutive_misses = 0

    # Current DRN page
    try:
        drn_page = client.get_page("Wikipedia:Dispute resolution noticeboard")
        if drn_page.exists():
            content = drn_page.text
            for term in search_terms:
                if term.lower() in content.lower():
                    results.append(
                        {
                            "type": "current_drn",
                            "search_term": term,
                            "url": drn_page.full_url(),
                            "found": True,
                        }
                    )
    except Exception:
        pass

    # Search DRN archives — try multiple naming patterns
    for i in range(1, archive_limit + 1):
        found_archive = False

        for pattern in [
            f"Wikipedia:Dispute resolution noticeboard/Archive {i}",
            f"Wikipedia:Dispute resolution noticeboard/Archive_{i}",
        ]:
            try:
                archive = client.get_page(pattern)
                if archive.exists():
                    found_archive = True
                    content = archive.text
                    for term in search_terms:
                        if term.lower() in content.lower():
                            results.append(
                                {
                                    "type": f"drn_archive_{i}",
                                    "search_term": term,
                                    "url": archive.full_url(),
                                    "found": True,
                                }
                            )
                    time.sleep(0.2)
                    break
            except Exception:
                pass

        if not found_archive:
            consecutive_misses += 1
            if consecutive_misses >= 3:
                break  # Stop after 3 consecutive missing archives
        else:
            consecutive_misses = 0

    return results


# ---------------------------------------------------------------------------
# Stage-specific fetchers (helpers for fetch_dispute_lifecycle)
# ---------------------------------------------------------------------------


def _fetch_arbcom_pages(
    client: WikiClient,
    case_prefix: str,
    revision_limit: int | None,
    delay: float,
) -> tuple[list[dict], set[str], set[str]]:
    """
    Fetch ArbCom case pages and extract articles/participants.

    Returns:
        Tuple of (page_data_list, articles_set, participants_set)
    """
    pages: list[dict] = []
    all_articles: set[str] = set()
    all_participants: set[str] = set()

    for suffix in ARB_SUBPAGES:
        page_title = f"{case_prefix}{suffix}"
        try:
            page = client.get_page(page_title)
            if page.exists():
                content = page.text
                page_data: dict = {
                    "title": page.title(),
                    "url": page.full_url(),
                    "subpage": suffix or "(main)",
                    "revisions": client.get_revisions(page_title, limit=revision_limit),
                    "revision_count": 0,
                    "content_length": len(content),
                }
                # Save full wikitext for pages needed by the outcome parser
                if suffix in SAVE_WIKITEXT_SUFFIXES:
                    page_data["content"] = content
                page_data["revision_count"] = len(page_data["revisions"])

                # Extract entities for linking to other venues
                all_articles.update(extract_article_links(content))
                all_participants.update(extract_participants(content))

                pages.append(page_data)
                logger.info(f"Fetched ArbCom page: {page.title()}")
                time.sleep(delay)
            else:
                logger.debug(f"ArbCom page not found: {page_title}")
        except Exception as e:
            logger.warning(f"Error fetching ArbCom page {page_title}: {e}")

    return pages, all_articles, all_participants


def _fetch_arbcom_talk_pages(
    client: WikiClient,
    case_prefix: str,
    revision_limit: int | None,
    delay: float,
) -> list[dict]:
    """Fetch ArbCom case talk pages."""
    talk_pages: list[dict] = []

    # Derive talk namespace from the case_prefix
    if case_prefix.startswith("Wikipedia:"):
        talk_prefix = "Wikipedia talk:" + case_prefix[len("Wikipedia:") :]
    else:
        talk_prefix = f"Talk:{case_prefix}"

    for suffix in ARB_SUBPAGES:
        talk_title = f"{talk_prefix}{suffix}"
        try:
            talk_page = client.get_page(talk_title)
            if talk_page.exists():
                talk_data: dict = {
                    "title": talk_page.title(),
                    "url": talk_page.full_url(),
                    "subpage": suffix or "(main)",
                    "revisions": client.get_revisions(talk_title, limit=revision_limit),
                    "revision_count": 0,
                }
                talk_data["revision_count"] = len(talk_data["revisions"])
                talk_pages.append(talk_data)
                logger.info(f"Fetched ArbCom talk page: {talk_page.title()}")
                time.sleep(delay)
        except Exception:
            pass

    return talk_pages


def _fetch_ani_reports(
    client: WikiClient,
    case_name: str,
    participants: list[str],
    ani_limit: int,
    delay: float,
) -> list[dict]:
    """Fetch ANI conduct reports for case and participants."""
    reports: list[dict] = []
    top_participants = participants[:5]
    ani_searches = [case_name] + top_participants

    for search_term in ani_searches:
        try:
            limit = ani_limit if search_term == case_name else 10
            ani_results = search_ani_mentions(client, search_term, limit=limit)
            for r in ani_results:
                r["search_term"] = search_term
                r["search_type"] = (
                    "case_name" if search_term == case_name else "participant"
                )
            reports.extend(ani_results)
            logger.info(f"Found {len(ani_results)} ANI mentions for '{search_term}'")
            time.sleep(delay)
        except Exception as e:
            logger.warning(f"ANI search failed for '{search_term}': {e}")

    # Deduplicate ANI results
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for r in reports:
        key = (r.get("title", ""), r.get("source", ""))
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return unique


def _fetch_article_talk_pages(
    client: WikiClient,
    articles: list[str],
    max_talk_pages: int,
    revision_limit: int | None,
    delay: float,
) -> list[dict]:
    """Fetch talk pages for disputed articles."""
    talk_pages: list[dict] = []
    articles_to_fetch = articles[:max_talk_pages]

    for article_title in articles_to_fetch:
        try:
            talk_page = client.get_talk_page(article_title)
            if talk_page:
                talk_data = {
                    "article": article_title,
                    "title": talk_page.title(),
                    "url": talk_page.full_url(),
                    "revisions": client.get_revisions(
                        talk_page.title(), limit=revision_limit
                    ),
                    "revision_count": 0,
                }
                talk_data["revision_count"] = len(talk_data["revisions"])
                talk_pages.append(talk_data)
                logger.info(f"Fetched talk page: Talk:{article_title}")
                time.sleep(delay)
        except Exception as e:
            logger.warning(f"Error fetching Talk:{article_title}: {e}")

    return talk_pages


def _compute_lifecycle_summary(result: dict) -> dict:
    """Compute summary statistics for the lifecycle data."""
    arbcom = result["lifecycle_stages"]["stage_5_arbcom"]
    ani = result["lifecycle_stages"]["stage_4_ani"]
    drn = result["lifecycle_stages"]["stage_3_drn"]
    talk = result["lifecycle_stages"]["stage_1_2_talk"]

    total_revisions = (
        sum(p.get("revision_count", 0) for p in arbcom["pages"])
        + sum(p.get("revision_count", 0) for p in arbcom["talk_pages"])
        + sum(p.get("revision_count", 0) for p in talk["pages"])
    )

    return {
        # Stage counts
        "arbcom_pages": len(arbcom["pages"]),
        "arbcom_talk_pages": len(arbcom["talk_pages"]),
        "ani_reports": len(ani["reports"]),
        "drn_mentions": len(drn["mentions"]),
        "talk_pages": len(talk["pages"]),
        # Entities
        "participants_extracted": len(result["participants"]),
        "articles_extracted": len(result["disputed_articles"]),
        # Totals
        "total_revisions": total_revisions,
        # Lifecycle coverage
        "lifecycle_stages_with_data": sum(
            [
                1 if arbcom["pages"] else 0,
                1 if ani["reports"] else 0,
                1 if drn["mentions"] else 0,
                1 if talk["pages"] else 0,
            ]
        ),
    }


# ---------------------------------------------------------------------------
# Main lifecycle fetcher
# ---------------------------------------------------------------------------


def fetch_dispute_lifecycle(
    client: WikiClient,
    case_name: str,
    max_talk_pages: int = 10,
    revision_limit: int | None = 100,
    ani_limit: int = 30,
    drn_archive_limit: int = 20,
    ani_archive_limit: int = 50,
    delay: float = 0.5,
) -> dict:
    """
    Trace the full dispute lifecycle from an arbitration case.

    Collects from each venue in the dispute resolution lifecycle:

    - **Stage 5** — ArbCom case pages and talk pages
    - **Stage 4** — ANI conduct reports for case name and top participants
    - **Stage 3** — DRN content dispute resolution attempts
    - **Stage 1-2** — Article talk pages where disputes originate

    Args:
        client: WikiClient instance
        case_name: Arbitration case name (e.g., "Climate change")
        max_talk_pages: Maximum article talk pages to fetch
        revision_limit: Max revisions per page (None = all)
        ani_limit: Max ANI results per search
        drn_archive_limit: Max DRN archives to search
        ani_archive_limit: Max ANI archives to search
        delay: Seconds between API calls

    Returns:
        Dictionary with dispute lifecycle data organised by venue
    """
    # Try to find the correct path pattern for this case
    case_prefix, path_pattern = find_arb_case_path(client, case_name)

    if case_prefix is None:
        case_prefix = get_arb_case_prefix(case_name)
        path_pattern = "not_found"
        logger.warning("Could not find ArbCom case page, trying default path...")

    result: dict = {
        "case_name": case_name,
        "case_prefix": case_prefix,
        "path_pattern": path_pattern,
        "fetched_at": datetime.now().isoformat(),
        # Dispute venues (organised by lifecycle stage)
        "lifecycle_stages": {
            "stage_5_arbcom": {
                "description": "Arbitration Committee - final binding decisions",
                "path_pattern_used": path_pattern,
                "pages": [],
                "talk_pages": [],
            },
            "stage_4_ani": {
                "description": "Administrators' Noticeboard/Incidents - conduct reports",
                "reports": [],
            },
            "stage_3_drn": {
                "description": "Dispute Resolution Noticeboard - moderated content disputes",
                "mentions": [],
            },
            "stage_1_2_talk": {
                "description": "Talk pages & RfC/3O - where disputes originate",
                "pages": [],
            },
        },
        # Entities extracted for cross-referencing
        "participants": [],
        "disputed_articles": [],
        "summary": {},
    }

    # =========================================================================
    # STAGE 5: ARBCOM (final stage — we start here and trace backwards)
    # =========================================================================
    logger.info(f"Stage 5: Fetching ArbCom case pages (pattern: {path_pattern})")

    arbcom_pages, all_articles, all_participants = _fetch_arbcom_pages(
        client, case_prefix, revision_limit, delay
    )
    result["lifecycle_stages"]["stage_5_arbcom"]["pages"] = arbcom_pages

    arbcom_talk_pages = _fetch_arbcom_talk_pages(
        client, case_prefix, revision_limit, delay
    )
    result["lifecycle_stages"]["stage_5_arbcom"]["talk_pages"] = arbcom_talk_pages

    # Store entities
    result["participants"] = list(all_participants)
    result["disputed_articles"] = list(all_articles)[:50]  # Limit for manageability

    # =========================================================================
    # STAGE 4: ANI (conduct escalation — before arbcom)
    # =========================================================================
    logger.info("Stage 4: Searching ANI for conduct reports...")

    ani_reports = _fetch_ani_reports(
        client, case_name, list(all_participants), ani_limit, delay
    )
    result["lifecycle_stages"]["stage_4_ani"]["reports"] = ani_reports

    # =========================================================================
    # STAGE 3: DRN (content dispute resolution)
    # =========================================================================
    logger.info("Stage 3: Searching DRN for content disputes...")

    top_participants = list(all_participants)[:3]
    drn_search_terms = [case_name] + top_participants
    drn_mentions = search_drn_mentions(
        client, drn_search_terms, archive_limit=drn_archive_limit
    )
    result["lifecycle_stages"]["stage_3_drn"]["mentions"] = drn_mentions
    logger.info(f"Found {len(drn_mentions)} DRN mentions")

    # =========================================================================
    # STAGE 1-2: TALK PAGES (where disputes originate — 3O/RfC happen here)
    # =========================================================================
    logger.info(f"Stage 1-2: Fetching article talk pages (max {max_talk_pages})...")

    article_talk_pages = _fetch_article_talk_pages(
        client, list(all_articles), max_talk_pages, revision_limit, delay
    )
    result["lifecycle_stages"]["stage_1_2_talk"]["pages"] = article_talk_pages

    # =========================================================================
    # SUMMARY
    # =========================================================================
    result["summary"] = _compute_lifecycle_summary(result)

    return result
