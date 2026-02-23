"""Enhanced arbitration case data collection.

This module provides comprehensive arbitration case fetching with:
- Full case page collection (main + all subpages)
- Participant enrichment (user info, blocks, abuse filter)
- Article enrichment (assessments, protection)
- Case outcome parsing
- ANI/DRN venue integration

Excludes ORES and Pageviews (lower rate limits - separate enrichment pass).
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from typing import Optional

import mwparserfromhell

from wiki import WikiClient
from outcome import parse_case_outcome, outcome_to_dict
from fetchers import search_ani_mentions

logger = logging.getLogger(__name__)


# Arbitration case subpages to fetch
ARB_SUBPAGES = {
    "main": "",
    "evidence": "/Evidence",
    "workshop": "/Workshop",
    "proposed_decision": "/Proposed decision",
    "remedies": "/Remedies",
}

# Path patterns for arbitration cases (Wikipedia changed format over time)
ARB_PATH_PATTERNS = [
    "Wikipedia:Arbitration/Requests/Case/{name}",  # Current format (post-2010)
    "Wikipedia:Requests for arbitration/{name}",  # Older format
    "Wikipedia:Arbitration/{name}",  # Very old format
]


def find_case_path(client: WikiClient, case_name: str) -> tuple[str | None, str]:
    """
    Find the correct Wikipedia path for an arbitration case.

    Tries multiple path patterns since Wikipedia changed formats over time.

    Returns:
        Tuple of (working_prefix, pattern_used) or (None, "not_found")
    """
    # Already a full path
    if case_name.startswith("Wikipedia:"):
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


def _is_ip_address(text: str) -> bool:
    """
    Check if text looks like an IP address.

    Args:
        text: String to check

    Returns:
        True if text appears to be an IPv4 or IPv6 address
    """
    # IPv4 pattern
    ipv4_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"
    if re.match(ipv4_pattern, text):
        return True

    # IPv6 pattern (simplified - contains colons and hex digits)
    if ":" in text and re.match(r"^[0-9A-Fa-f:]+$", text):
        return True

    return False


def _is_valid_username(user: str) -> bool:
    """
    Check if a string is a valid Wikipedia username.

    Filters out:
    - IP addresses
    - Fragment anchors
    - Subpages
    - Magic words/templates
    - Usernames that are too long (likely extraction errors)
    - Usernames with invalid characters

    Args:
        user: Potential username to validate

    Returns:
        True if user appears to be a valid username
    """
    if not user:
        return False

    # Skip fragments and subpages starting with # or /
    if user.startswith(("#", "/")):
        return False

    # Skip if contains fragment anchor (e.g., "AGK#top")
    if "#" in user:
        return False

    # Skip subpages (e.g., "ArtifexMayhem/ArbAbort2011")
    if "/" in user:
        return False

    # Skip namespace prefixes
    if ":" in user:
        return False

    # Skip magic words and templates
    if user.startswith("{{") or "{{" in user:
        return False
    if user.startswith("{{{"):
        return False

    # Skip IP addresses
    if _is_ip_address(user):
        return False

    # Wikipedia usernames have a max length of 255 bytes
    # But most real usernames are under 50 chars
    # Long strings are likely extraction errors (paragraphs of text)
    if len(user) > 100:
        return False

    # Skip if contains newlines (definitely extraction error)
    if "\n" in user or "\r" in user:
        return False

    # Skip if contains certain patterns that indicate extraction errors
    # (quotes, brackets in the middle, etc.)
    if user.count('"') > 1:
        return False
    if "[[" in user or "]]" in user:
        return False
    if user.count("{") > 0 or user.count("}") > 0:
        return False

    return True


def extract_participants(content: str) -> set[str]:
    """
    Extract user mentions from page content.

    Filters out:
    - IP addresses (can't query user info for IPs)
    - Fragment anchors (e.g., "User#top")
    - Subpages (e.g., "User/sandbox")
    - Invalid username patterns
    - Magic words/templates
    - Long text strings (extraction errors)

    Args:
        content: Raw wikitext

    Returns:
        Set of unique valid usernames
    """
    users = set()

    # User: and User talk: links
    user_links = re.findall(r"\[\[User:([^\]|]+)", content, re.IGNORECASE)
    user_talk_links = re.findall(r"\[\[User talk:([^\]|]+)", content, re.IGNORECASE)

    for user in user_links + user_talk_links:
        user = user.strip()

        if _is_valid_username(user):
            users.add(user)

    return users


def _is_valid_article_title(title: str) -> bool:
    """
    Check if a title is a valid Wikipedia article title.

    Filters out:
    - Relative paths (../Workshop)
    - Interwiki prefixes (m:, meta:, wikt:, wmuk:, mail:, foundation:, etc.)
    - Leading colons (:Image:, :m:)
    - Magic words/templates ({{PAGENAME}})
    - URLs and external links
    - Titles that are too long (likely extraction errors)

    Args:
        title: Article title to validate

    Returns:
        True if title appears to be a valid local article
    """
    if not title:
        return False

    # Skip relative paths
    if title.startswith("..") or title.startswith("./"):
        return False

    # Skip leading colons (interwiki or file links)
    if title.startswith(":"):
        return False

    # Skip magic words and templates
    if title.startswith("{{") or title.startswith("{{{"):
        return False
    if "{{" in title:
        return False

    # Skip interwiki prefixes (lowercase prefix followed by colon)
    # These are links to other wikis like meta:, wikt:, m:, etc.
    interwiki_prefixes = (
        "m:",
        "meta:",
        "wikt:",
        "wiktionary:",
        "wmuk:",
        "mail:",
        "foundation:",
        "commons:",
        "s:",
        "wikisource:",
        "b:",
        "wikibooks:",
        "n:",
        "wikinews:",
        "q:",
        "wikiquote:",
        "v:",
        "wikiversity:",
        "wikidata:",
        "d:",
        "species:",
        "mw:",
        "mediawiki:",
        "phab:",
        "phabricator:",
        "bugzilla:",
        "gerrit:",
        "testwiki:",
        "oldwikisource:",
    )
    title_lower = title.lower()
    if title_lower.startswith(interwiki_prefixes):
        return False

    # Skip URLs
    if title.startswith(("http://", "https://", "//", "ftp://")):
        return False

    # Skip titles that are too long (likely extraction errors)
    # Wikipedia title limit is 256 bytes, but most real titles are under 100 chars
    if len(title) > 200:
        return False

    return True


def extract_article_links(content: str) -> set[str]:
    """
    Extract article wikilinks from page content, filtering out non-articles.

    Args:
        content: Raw wikitext

    Returns:
        Set of unique article titles
    """
    articles = set()

    try:
        wikicode = mwparserfromhell.parse(content)

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

            # Skip fragments and empty
            if title.startswith("#") or not title:
                continue

            # Remove fragment
            if "#" in title:
                title = title.split("#")[0]

            # Apply additional validation
            if not _is_valid_article_title(title):
                continue

            if title:
                articles.add(title)

    except Exception:
        pass

    return articles


def search_drn_mentions(
    client: WikiClient,
    search_terms: list[str],
    archive_limit: int = 20,
) -> list[dict]:
    """
    Search DRN current page and archives for mentions.

    Args:
        client: WikiClient instance
        search_terms: Terms to search for
        archive_limit: Max archives to search

    Returns:
        List of DRN mention records
    """
    results = []
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

    # Search archives
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
                break
        else:
            consecutive_misses = 0

    return results


def fetch_full_arbitration_case(
    client: WikiClient,
    case_name: str,
    revision_limit: int = 100,
    max_articles: int = 20,
    enrich_participants: bool = True,
    enrich_articles: bool = True,
    include_ani: bool = True,
    include_drn: bool = True,
    ani_limit: int = 20,
    drn_archive_limit: int = 20,
    delay: float = 0.3,
) -> dict:
    """
    Fetch comprehensive arbitration case data.

    Collects:
    - All case subpages (main, evidence, workshop, proposed decision, remedies)
    - Case talk pages
    - Participant enrichment (user info, blocks, abuse hits)
    - Article enrichment (assessments, protection)
    - Case outcome parsing
    - ANI/DRN venue mentions

    Does NOT include (separate enrichment pass):
    - ORES scores (lower rate limit)
    - Pageview data (lower rate limit)

    Args:
        client: WikiClient instance
        case_name: Arbitration case name (e.g., "Climate change")
        revision_limit: Max revisions per page (None = all)
        max_articles: Max articles to enrich
        enrich_participants: Fetch user info/blocks for participants
        enrich_articles: Fetch assessments/protection for articles
        include_ani: Search ANI for mentions
        include_drn: Search DRN for mentions
        ani_limit: Max ANI results
        drn_archive_limit: Max DRN archives to search
        delay: Seconds between API calls

    Returns:
        Comprehensive case data dictionary
    """
    logger.info(f"Fetching full arbitration case: {case_name}")

    # Find case path
    case_prefix, path_pattern = find_case_path(client, case_name)

    if case_prefix is None:
        case_prefix = f"Wikipedia:Arbitration/Requests/Case/{case_name}"
        path_pattern = "not_found"
        logger.warning(f"Could not find case page, using default path: {case_prefix}")

    result = {
        "case_name": case_name,
        "case_prefix": case_prefix,
        "path_pattern": path_pattern,
        "fetched_at": datetime.now().isoformat(),
        # Case pages
        "pages": {},
        "talk_pages": [],
        # Entities
        "all_participants": [],
        "all_articles": [],
        # Participant enrichment
        "participants": {},
        "participant_blocks": {},
        "participant_abuse_hits": {},
        # Article enrichment
        "articles": {},
        "article_revisions": {},
        # Outcome
        "outcome": {},
        # Venues
        "ani_mentions": [],
        "drn_mentions": [],
        # Summary
        "summary": {},
    }

    all_participants: set[str] = set()
    all_articles: set[str] = set()

    # =========================================================================
    # FETCH CASE PAGES
    # =========================================================================
    logger.info("Fetching case subpages...")

    for key, suffix in ARB_SUBPAGES.items():
        page_title = f"{case_prefix}{suffix}"
        try:
            page = client.get_page(page_title)
            if page.exists():
                content = page.text
                revisions = client.get_revisions(page_title, limit=revision_limit)

                result["pages"][key] = {
                    "title": page.title(),
                    "url": page.full_url(),
                    "content": content,
                    "content_length": len(content),
                    "revisions": revisions,
                    "revision_count": len(revisions),
                }

                # Extract entities
                all_participants.update(extract_participants(content))
                all_articles.update(extract_article_links(content))

                logger.debug(f"  Fetched: {page_title}")
                time.sleep(delay)
            else:
                logger.debug(f"  Not found: {page_title}")

        except Exception as e:
            logger.warning(f"Error fetching {page_title}: {e}")

    # =========================================================================
    # FETCH CASE TALK PAGES
    # =========================================================================
    logger.info("Fetching case talk pages...")

    # Convert Wikipedia: to Wikipedia talk:
    if case_prefix.startswith("Wikipedia:"):
        talk_prefix = "Wikipedia talk:" + case_prefix[len("Wikipedia:") :]
    else:
        talk_prefix = f"Talk:{case_prefix}"

    for key, suffix in ARB_SUBPAGES.items():
        talk_title = f"{talk_prefix}{suffix}"
        try:
            talk_page = client.get_page(talk_title)
            if talk_page.exists():
                revisions = client.get_revisions(talk_title, limit=revision_limit)
                result["talk_pages"].append(
                    {
                        "title": talk_page.title(),
                        "url": talk_page.full_url(),
                        "subpage": key,
                        "revisions": revisions,
                        "revision_count": len(revisions),
                    }
                )
                logger.debug(f"  Fetched: {talk_title}")
                time.sleep(delay)
        except Exception:
            pass

    # Store entities
    result["all_participants"] = sorted(all_participants)
    result["all_articles"] = sorted(all_articles)[:50]  # Limit for manageability

    # =========================================================================
    # PARSE CASE OUTCOME
    # =========================================================================
    logger.info("Parsing case outcome...")

    try:
        outcome = parse_case_outcome(result["pages"])
        result["outcome"] = outcome_to_dict(outcome)
    except Exception as e:
        logger.warning(f"Error parsing outcome: {e}")
        result["outcome"] = {"status": "unknown", "error": str(e)}

    # =========================================================================
    # PARTICIPANT ENRICHMENT
    # =========================================================================
    if enrich_participants and all_participants:
        # Filter to valid users only (already done in extract_participants,
        # but log for visibility)
        valid_users = [u for u in all_participants if not _is_ip_address(u)]
        logger.info(
            f"Enriching {len(valid_users)} valid participants "
            f"(filtered from {len(all_participants)} total mentions)"
        )

        # Batch fetch user info (50 at a time)
        if valid_users:
            try:
                user_info = client.get_users_info(valid_users)
                result["participants"] = user_info
                logger.info(f"Got user info for {len(user_info)} of {len(valid_users)} users")
            except Exception as e:
                logger.warning(f"Error fetching user info: {e}")
        else:
            logger.warning("No valid users to enrich after filtering")

        # Fetch block history for each participant
        for username in list(all_participants)[:30]:  # Limit to avoid too many calls
            try:
                blocks = client.get_user_blocks(username, limit=20)
                if blocks:
                    result["participant_blocks"][username] = blocks
                time.sleep(delay / 2)
            except Exception as e:
                logger.debug(f"Error fetching blocks for {username}: {e}")

        # Fetch abuse filter hits (limited - can be slow)
        for username in list(all_participants)[:20]:
            try:
                abuse = client.get_user_abuse_hits(username, limit=20)
                if abuse.get("total_hits", 0) > 0:
                    result["participant_abuse_hits"][username] = abuse
                time.sleep(delay / 2)
            except Exception as e:
                logger.debug(f"Error fetching abuse hits for {username}: {e}")

    # =========================================================================
    # ARTICLE ENRICHMENT
    # =========================================================================
    articles_to_enrich = list(all_articles)[:max_articles]

    if enrich_articles and articles_to_enrich:
        logger.info(f"Enriching {len(articles_to_enrich)} articles...")

        for article in articles_to_enrich:
            try:
                # Get page assessments
                assessments = client.get_page_assessments(article)

                # Get protection status
                protection = client.get_page_protection(article)

                # Get protection history
                protection_log = client.get_protection_log(article, limit=10)

                result["articles"][article] = {
                    "title": article,
                    "quality_class": assessments.get("highest_quality"),
                    "importance": assessments.get("highest_importance"),
                    "assessments": assessments.get("assessments", {}),
                    "protection_level": _get_protection_level(protection),
                    "protection": protection,
                    "protection_history": protection_log,
                    "protection_count": len(protection_log),
                }

                time.sleep(delay)

            except Exception as e:
                logger.debug(f"Error enriching article {article}: {e}")

        # Fetch article revisions with tags
        logger.info("Fetching article revision histories...")
        for article in articles_to_enrich[:10]:  # Limit to top 10
            try:
                revisions = client.get_revisions_with_tags(article, limit=revision_limit)
                result["article_revisions"][article] = revisions
                time.sleep(delay)
            except Exception as e:
                logger.debug(f"Error fetching revisions for {article}: {e}")

    # =========================================================================
    # ANI/DRN VENUE SEARCH
    # =========================================================================
    if include_ani:
        logger.info("Searching ANI for case mentions...")
        try:
            # Search for case name and top participants
            top_participants = list(all_participants)[:5]
            ani_searches = [case_name] + top_participants

            for search_term in ani_searches:
                limit = ani_limit if search_term == case_name else 10
                mentions = search_ani_mentions(
                    client, search_term, limit=limit, max_archives=50
                )
                for m in mentions:
                    m["search_term"] = search_term
                    m["search_type"] = (
                        "case_name" if search_term == case_name else "participant"
                    )
                result["ani_mentions"].extend(mentions)
                time.sleep(delay)

            # Deduplicate
            seen = set()
            unique = []
            for m in result["ani_mentions"]:
                key = (m.get("title", ""), m.get("source", ""))
                if key not in seen:
                    seen.add(key)
                    unique.append(m)
            result["ani_mentions"] = unique

            logger.debug(f"  Found {len(result['ani_mentions'])} ANI mentions")

        except Exception as e:
            logger.warning(f"Error searching ANI: {e}")

    if include_drn:
        logger.info("Searching DRN for case mentions...")
        try:
            drn_terms = [case_name] + list(all_participants)[:3]
            result["drn_mentions"] = search_drn_mentions(
                client, drn_terms, archive_limit=drn_archive_limit
            )
            logger.debug(f"  Found {len(result['drn_mentions'])} DRN mentions")
        except Exception as e:
            logger.warning(f"Error searching DRN: {e}")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    result["summary"] = {
        "case_pages_found": len(result["pages"]),
        "talk_pages_found": len(result["talk_pages"]),
        "participants_extracted": len(all_participants),
        "participants_enriched": len(result["participants"]),
        "participants_with_blocks": len(result["participant_blocks"]),
        "participants_with_abuse_hits": len(result["participant_abuse_hits"]),
        "articles_extracted": len(all_articles),
        "articles_enriched": len(result["articles"]),
        "articles_with_revisions": len(result["article_revisions"]),
        "ani_mentions": len(result["ani_mentions"]),
        "drn_mentions": len(result["drn_mentions"]),
        "outcome_status": result["outcome"].get("status", "unknown"),
        "remedy_count": result["outcome"].get("remedy_count", 0),
        "total_revisions": sum(
            p.get("revision_count", 0) for p in result["pages"].values()
        )
        + sum(p.get("revision_count", 0) for p in result["talk_pages"]),
    }

    logger.info(f"Completed: {result['summary']}")

    return result


def _get_protection_level(protection: dict) -> Optional[str]:
    """Extract the highest protection level from protection dict."""
    levels = {"sysop": 3, "autoconfirmed": 2, "": 1}
    highest = None
    highest_level = 0

    for ptype, info in protection.items():
        if isinstance(info, dict):
            level = info.get("level", "")
            if levels.get(level, 0) > highest_level:
                highest = level
                highest_level = levels[level]

    return highest
