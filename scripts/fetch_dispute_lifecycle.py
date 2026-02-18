#!/usr/bin/env python3
"""
Dispute lifecycle fetcher for arbitration cases.

Given an arbitration case name, traces the FULL dispute resolution lifecycle
by collecting data from each venue in the escalation path:

    Talk Page → DRN → ANI → ArbCom

Venues collected (matching docs/wikipedia_dispute_resolution_lifecycle.md):
1. Talk Pages - Where disputes originate (Stage 1)
2. DRN - Dispute Resolution Noticeboard content disputes (Stage 3)
3. ANI - Administrators' Noticeboard/Incidents conduct reports (Stage 4)
4. ArbCom - Arbitration Committee case pages (Stage 5)

This is the correct approach for studying dispute escalation patterns,
as we need data from ALL stages of the lifecycle, not just arbitration.

Usage:
    python scripts/fetch_dispute_lifecycle.py "CaseName"
    python scripts/fetch_dispute_lifecycle.py "CaseName" --dry-run
    python scripts/fetch_dispute_lifecycle.py "CaseName" --max-talk-pages 10

Example:
    python scripts/fetch_dispute_lifecycle.py "Climate change"
    make fetch-lifecycle CASE="Climate change"
"""

import argparse
import logging
import re
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import mwparserfromhell

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.io import (
    save_json,
    get_output_path,
    sanitize_filename,
    setup_logging,
    check_api_credentials,
)
from src.fetchers import search_ani_mentions


def get_memory_mb() -> float:
    """Get current memory usage in MB."""
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        return usage.ru_maxrss / 1024 / 1024  # macOS returns bytes
    except Exception:
        return 0.0


logger: logging.Logger | None = None
_client: WikiClient | None = None


def shutdown_handler(signum, frame):
    """Handle Ctrl+C gracefully."""
    print("\n\n⚠️  Interrupted! Logging stats before exit...")
    if _client:
        _client.log_stats()
    sys.exit(130)


signal.signal(signal.SIGINT, shutdown_handler)


# Known arbitration case subpages
ARB_SUBPAGES = [
    "",  # Main page
    "/Evidence",
    "/Workshop",
    "/Proposed decision",
    "/Remedies",
]

# Multiple path patterns for arbitration cases (Wikipedia changed format over time)
ARB_PATH_PATTERNS = [
    "Wikipedia:Arbitration/Requests/Case/{name}",  # Current format (post-2010)
    "Wikipedia:Requests for arbitration/{name}",  # Older format
    "Wikipedia:Arbitration/{name}",  # Very old format
]


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


def extract_article_links(content: str) -> list[str]:
    """Extract article wikilinks from page content, filtering out non-articles."""
    wikicode = mwparserfromhell.parse(content)
    articles = set()

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

    all_users = set()
    for user in user_links + user_talk_links:
        user = user.strip()
        if user and not user.startswith(("#", "/")):
            all_users.add(user)

    return list(all_users)


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
    results = []
    archives_checked = 0
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

    # Search DRN archives - try multiple naming patterns
    # Pattern 1: "Archive X" (most common)
    # Pattern 2: "Archive_X" (alternative)
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
                    archives_checked += 1
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
                # Stop after 3 consecutive missing archives
                break
        else:
            consecutive_misses = 0

    return results


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
    - Stage 5: ArbCom case pages and talk pages
    - Stage 4: ANI conduct reports for case name and top participants
    - Stage 3: DRN content dispute resolution attempts
    - Stage 1-2: Article talk pages where disputes originate

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
        Dictionary with dispute lifecycle data organized by venue
    """
    # Try to find the correct path pattern for this case
    case_prefix, path_pattern = find_arb_case_path(client, case_name)

    if case_prefix is None:
        # Fall back to default pattern (will likely 404 but we continue for other stages)
        case_prefix = get_arb_case_prefix(case_name)
        path_pattern = "not_found"
        print("   ⚠️  Could not find ArbCom case page, trying default path...")

    result = {
        "case_name": case_name,
        "case_prefix": case_prefix,
        "path_pattern": path_pattern,
        "fetched_at": datetime.now().isoformat(),
        # Dispute venues (organized by lifecycle stage)
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

    all_articles = set()
    all_participants = set()

    # =========================================================================
    # STAGE 5: ARBCOM (Final stage - we start here and trace backwards)
    # =========================================================================
    print(f"\n⚖️  Stage 5: Fetching ArbCom case pages... (pattern: {path_pattern})")

    for suffix in ARB_SUBPAGES:
        page_title = f"{case_prefix}{suffix}"
        try:
            page = client.get_page(page_title)
            if page.exists():
                content = page.text
                page_data = {
                    "title": page.title(),
                    "url": page.full_url(),
                    "subpage": suffix or "(main)",
                    "revisions": client.get_revisions(page_title, limit=revision_limit),
                    "revision_count": 0,
                    "content_length": len(content),
                }
                page_data["revision_count"] = len(page_data["revisions"])

                # Extract entities for linking to other venues
                all_articles.update(extract_article_links(content))
                all_participants.update(extract_participants(content))

                result["lifecycle_stages"]["stage_5_arbcom"]["pages"].append(page_data)
                print(f"   ✓ {page.title()}")
                time.sleep(delay)
            else:
                print(f"   ✗ {page_title} (not found)")
        except Exception as e:
            print(f"   ✗ {page_title}: {e}")

    # ArbCom talk pages - derive talk namespace from the case_prefix
    # Wikipedia:X -> Wikipedia talk:X
    if case_prefix.startswith("Wikipedia:"):
        talk_prefix = "Wikipedia talk:" + case_prefix[len("Wikipedia:") :]
    else:
        talk_prefix = f"Talk:{case_prefix}"

    for suffix in ARB_SUBPAGES:
        talk_title = f"{talk_prefix}{suffix}"
        try:
            talk_page = client.get_page(talk_title)
            if talk_page.exists():
                talk_data = {
                    "title": talk_page.title(),
                    "url": talk_page.full_url(),
                    "subpage": suffix or "(main)",
                    "revisions": client.get_revisions(talk_title, limit=revision_limit),
                    "revision_count": 0,
                }
                talk_data["revision_count"] = len(talk_data["revisions"])
                result["lifecycle_stages"]["stage_5_arbcom"]["talk_pages"].append(
                    talk_data
                )
                print(f"   ✓ {talk_page.title()}")
                time.sleep(delay)
        except Exception:
            pass

    # Store entities
    result["participants"] = list(all_participants)
    result["disputed_articles"] = list(all_articles)[:50]  # Limit for manageability

    # =========================================================================
    # STAGE 4: ANI (conduct escalation - before arbcom)
    # =========================================================================
    print("\n⚠️  Stage 4: Searching ANI for conduct reports...")

    # Search for case name and top participants
    top_participants = list(all_participants)[:5]
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
            result["lifecycle_stages"]["stage_4_ani"]["reports"].extend(ani_results)
            print(f"   Found {len(ani_results)} ANI mentions for '{search_term}'")
            time.sleep(delay)
        except Exception as e:
            print(f"   ✗ ANI search failed for '{search_term}': {e}")

    # Deduplicate ANI results
    seen = set()
    unique = []
    for r in result["lifecycle_stages"]["stage_4_ani"]["reports"]:
        key = (r.get("title", ""), r.get("source", ""))
        if key not in seen:
            seen.add(key)
            unique.append(r)
    result["lifecycle_stages"]["stage_4_ani"]["reports"] = unique

    # =========================================================================
    # STAGE 3: DRN (content dispute resolution)
    # =========================================================================
    print("\n📋 Stage 3: Searching DRN for content disputes...")

    drn_search_terms = [case_name] + top_participants[:3]
    drn_mentions = search_drn_mentions(
        client, drn_search_terms, archive_limit=drn_archive_limit
    )
    result["lifecycle_stages"]["stage_3_drn"]["mentions"] = drn_mentions
    print(f"   Found {len(drn_mentions)} DRN mentions")

    # =========================================================================
    # STAGE 1-2: TALK PAGES (where disputes originate - 3O/RfC happen here)
    # =========================================================================
    print(f"\n💬 Stage 1-2: Fetching article talk pages (max {max_talk_pages})...")

    articles_to_fetch = list(all_articles)[:max_talk_pages]

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
                result["lifecycle_stages"]["stage_1_2_talk"]["pages"].append(talk_data)
                print(f"   ✓ Talk:{article_title}")
                time.sleep(delay)
        except Exception as e:
            print(f"   ✗ Talk:{article_title}: {e}")

    # =========================================================================
    # SUMMARY
    # =========================================================================
    arbcom = result["lifecycle_stages"]["stage_5_arbcom"]
    ani = result["lifecycle_stages"]["stage_4_ani"]
    drn = result["lifecycle_stages"]["stage_3_drn"]
    talk = result["lifecycle_stages"]["stage_1_2_talk"]

    total_revisions = (
        sum(p.get("revision_count", 0) for p in arbcom["pages"])
        + sum(p.get("revision_count", 0) for p in arbcom["talk_pages"])
        + sum(p.get("revision_count", 0) for p in talk["pages"])
    )

    result["summary"] = {
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

    return result


def main():
    global logger, _client

    parser = argparse.ArgumentParser(
        description="Trace the full dispute resolution lifecycle for an arbitration case",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Lifecycle stages collected (from docs/wikipedia_dispute_resolution_lifecycle.md):
  Stage 1-2: Talk pages (where disputes originate, includes 3O and RfC)
  Stage 3:   DRN (Dispute Resolution Noticeboard - content disputes)
  Stage 4:   ANI (Administrators' Noticeboard/Incidents - conduct)
  Stage 5:   ArbCom (Arbitration Committee - final decisions)

Examples:
    python scripts/fetch_dispute_lifecycle.py "Climate change"
    python scripts/fetch_dispute_lifecycle.py "Abortion" --max-talk-pages 20
    python scripts/fetch_dispute_lifecycle.py "Macedonia" --dry-run
        """,
    )
    parser.add_argument("case", help="Arbitration case name")
    parser.add_argument(
        "--max-talk-pages",
        type=int,
        default=10,
        help="Maximum article talk pages to fetch (default: 10)",
    )
    parser.add_argument(
        "--revision-limit",
        type=int,
        default=100,
        help="Maximum revisions per page (default: 100, 0=all)",
    )
    parser.add_argument(
        "--ani-limit",
        type=int,
        default=30,
        help="Maximum ANI results per search (default: 30)",
    )
    parser.add_argument(
        "--drn-archives",
        type=int,
        default=20,
        help="Maximum DRN archives to search (default: 20)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be fetched without making API calls",
    )

    args = parser.parse_args()

    revision_limit = args.revision_limit if args.revision_limit > 0 else None

    if args.dry_run:
        case_prefix = get_arb_case_prefix(args.case)
        print("Wikipedia Dispute Lifecycle Fetcher")
        print("=" * 50)
        print("\n[DRY RUN] Preview mode - no API calls will be made\n")
        print(f"Case: {args.case}")
        print(f"Prefix: {case_prefix}")
        print("\nWould fetch from each lifecycle stage:")
        print("\n  Stage 5 - ArbCom:")
        for suffix in ARB_SUBPAGES:
            print(f"    • {case_prefix}{suffix}")
        print("\n  Stage 4 - ANI:")
        print(f"    • Search ANI for '{args.case}' + top 5 participants")
        print("\n  Stage 3 - DRN:")
        print(f"    • Search DRN current + {args.drn_archives} archives")
        print("\n  Stage 1-2 - Talk pages:")
        print(f"    • Up to {args.max_talk_pages} article talk pages")
        print(f"\n  Revisions: Up to {revision_limit or 'all'} per page")
        print("\n[DRY RUN] No files written.")
        return

    logger = setup_logging("fetch_dispute_lifecycle")
    logger.info("Wikipedia Dispute Lifecycle Fetcher")
    logger.info("=" * 50)

    check_api_credentials(logger)

    client = WikiClient()
    _client = client

    print(f"\n🔍 Tracing dispute lifecycle for: {args.case}")
    print("=" * 50)

    data = fetch_dispute_lifecycle(
        client,
        args.case,
        max_talk_pages=args.max_talk_pages,
        revision_limit=revision_limit,
        ani_limit=args.ani_limit,
        drn_archive_limit=args.drn_archives,
    )

    # Save output
    safe_name = sanitize_filename(args.case)
    output_path = get_output_path("dispute_venues", prefix=f"lifecycle_{safe_name}")
    save_json(data, output_path)

    # Print summary
    print("\n" + "=" * 50)
    print("DISPUTE LIFECYCLE SUMMARY")
    print("=" * 50)
    print("\n  Lifecycle stages with data:")
    print(
        f"    ⚖️  Stage 5 ArbCom: {data['summary']['arbcom_pages']} pages + {data['summary']['arbcom_talk_pages']} talk"
    )
    print(f"    ⚠️  Stage 4 ANI:    {data['summary']['ani_reports']} reports")
    print(f"    📋 Stage 3 DRN:    {data['summary']['drn_mentions']} mentions")
    print(f"    💬 Stage 1-2 Talk: {data['summary']['talk_pages']} pages")
    print(f"\n  Coverage: {data['summary']['lifecycle_stages_with_data']}/4 stages")
    print(f"  Participants: {data['summary']['participants_extracted']}")
    print(f"  Articles: {data['summary']['articles_extracted']}")
    print(f"  Total revisions: {data['summary']['total_revisions']}")
    print(f"\n📁 Saved to: {output_path}")

    # Memory footprint
    mem_mb = get_memory_mb()
    print(f"💾 Memory: {mem_mb:.1f} MB")

    client.log_stats()
    stats = client.get_stats()
    print(
        f"📊 API Stats: {stats['total_requests']} requests in {stats['runtime_minutes']:.1f} min"
    )


if __name__ == "__main__":
    main()
