#!/usr/bin/env python3
"""
Unified CLI for Wikipedia dispute data collection.

Usage:
    python fetch_all.py                    # Run all collectors
    python fetch_all.py --arb              # Arbitration cases only
    python fetch_all.py --drn              # DRN cases only
    python fetch_all.py --revisions "Title" # Revisions for specific article
    python fetch_all.py --editwar "Title"  # Edit war analysis
    python fetch_all.py --venues "Title"   # All dispute venues for article
    python fetch_all.py --ani "Term"       # Search ANI for term
"""

import argparse
import logging
import signal
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.io import (
    save_json,
    get_output_path,
    sanitize_filename,
    setup_logging,
    check_api_credentials,
)
from src.fetchers import (
    fetch_arbitration_cases,
    fetch_drn_page,
    parse_drn_sections,
    extract_case_metadata,
    fetch_revisions,
    analyze_article_edit_war,
    # Phase 2 fetchers
    fetch_talk_page_revisions,
    search_ani_mentions,
    fetch_dispute_venues_for_article,
)

# Initialize logger (will be configured in main)
logger: logging.Logger | None = None

# Globals for graceful shutdown
_client: WikiClient | None = None


def shutdown_handler(signum, frame):
    """Handle Ctrl+C gracefully - log stats before exit."""
    print("\n\n⚠️  Interrupted! Logging stats before exit...")
    if _client:
        _client.log_stats()
        stats = _client.get_stats()
        print(
            f"📊 API Stats: {stats['total_requests']} requests in {stats['runtime_minutes']:.1f} min"
        )
    if logger:
        logger.info("Fetch interrupted by user")
    sys.exit(130)


# Register signal handler
signal.signal(signal.SIGINT, shutdown_handler)


def run_arbitration(client: WikiClient, limit: int = 50):
    """Fetch arbitration cases."""
    logger.info("=" * 50)
    logger.info("FETCHING ARBITRATION CASES")
    logger.info("=" * 50)

    cases = fetch_arbitration_cases(client, limit=limit)
    output_path = get_output_path("arbitration", prefix="arbitration_cases")
    save_json(cases, output_path)

    logger.info(f"Saved {len(cases)} cases to {output_path}")
    return cases


def run_drn(client: WikiClient):
    """Fetch DRN cases."""
    logger.info("=" * 50)
    logger.info("FETCHING DRN CASES")
    logger.info("=" * 50)

    drn_data = fetch_drn_page(client)
    cases = parse_drn_sections(drn_data["content"])
    cases = extract_case_metadata(cases)
    cases = [c for c in cases if c["level"] == 2 and len(c["content"]) > 100]

    drn_data["parsed_cases"] = cases
    drn_data["case_count"] = len(cases)
    del drn_data["content"]

    output_path = get_output_path("drn", prefix="drn_cases")
    save_json(drn_data, output_path)

    logger.info(f"Saved {len(cases)} cases to {output_path}")
    return drn_data


def run_revisions(client: WikiClient, article: str, limit: int | None = None):
    """Fetch revisions for an article."""
    logger.info("=" * 50)
    logger.info(f"FETCHING REVISIONS: {article}")
    logger.info("=" * 50)

    data = fetch_revisions(client, article, limit=limit)
    safe_title = sanitize_filename(article)
    output_path = get_output_path("revisions", prefix=safe_title)
    save_json(data, output_path)

    logger.info(f"Saved to {output_path}")
    return data


def run_editwar(client: WikiClient, article: str, threshold: float = 0.1):
    """Analyze article for edit war."""
    logger.info("=" * 50)
    logger.info(f"ANALYZING EDIT WAR: {article}")
    logger.info("=" * 50)

    analysis = analyze_article_edit_war(client, article, threshold=threshold)
    safe_title = sanitize_filename(article)
    output_path = get_output_path("edit_wars", prefix=f"editwar_{safe_title}")
    save_json(analysis, output_path)

    print_editwar_report(analysis)
    logger.info(f"Saved to {output_path}")
    return analysis


def print_editwar_report(analysis: dict) -> None:
    """Print human-readable edit war report."""
    print("\n" + "=" * 50)
    print(f"EDIT WAR ANALYSIS: {analysis['title']}")
    print("=" * 50)

    print(f"\nRevisions analyzed: {analysis['revisions_analyzed']}")
    print(f"Revert count: {analysis['revert_count']}")
    print(f"Revert ratio: {analysis['revert_ratio']:.1%}")
    print(f"Unique editors: {analysis['unique_editors']}")

    if analysis["edit_war_detected"]:
        print("\n⚠️  EDIT WAR DETECTED")
    else:
        print("\n✓ No significant edit war activity")

    if analysis.get("protection"):
        print(f"\nPage protection: {analysis['protection']}")

    if analysis.get("top_reverters"):
        print("\nTop reverters:")
        for user, count in list(analysis["top_reverters"].items())[:5]:
            print(f"  {user}: {count}")


# =============================================================================
# Phase 2: Dispute Venue Runners
# =============================================================================


def run_dispute_venues(client: WikiClient, article: str, ani_limit: int = 20):
    """Fetch all dispute venues for an article."""
    logger.info("=" * 50)
    logger.info(f"FETCHING DISPUTE VENUES: {article}")
    logger.info("=" * 50)

    data = fetch_dispute_venues_for_article(
        client,
        article,
        include_talk=True,
        include_ani=True,
        include_3o=True,
        include_rfc=True,
        ani_limit=ani_limit,
    )

    safe_title = sanitize_filename(article)
    output_path = get_output_path("dispute_venues", prefix=f"venues_{safe_title}")
    save_json(data, output_path)

    print_venue_report(data)
    logger.info(f"Saved to {output_path}")
    return data


def run_ani_search(client: WikiClient, search_term: str, limit: int = 50):
    """Search ANI archives for a term."""
    logger.info("=" * 50)
    logger.info(f"SEARCHING ANI: {search_term}")
    logger.info("=" * 50)

    results = search_ani_mentions(client, search_term, limit=limit)

    safe_term = sanitize_filename(search_term)
    output_path = get_output_path("ani_search", prefix=f"ani_{safe_term}")
    save_json(
        {
            "search_term": search_term,
            "result_count": len(results),
            "results": results,
        },
        output_path,
    )

    print_ani_report(search_term, results)
    logger.info(f"Saved to {output_path}")
    return results


def run_talk_page(client: WikiClient, article: str, limit: int | None = None):
    """Fetch talk page revisions for an article."""
    logger.info("=" * 50)
    logger.info(f"FETCHING TALK PAGE: {article}")
    logger.info("=" * 50)

    data = fetch_talk_page_revisions(client, article, limit=limit)

    safe_title = sanitize_filename(article)
    output_path = get_output_path("talk_pages", prefix=f"talk_{safe_title}")
    save_json(data, output_path)

    if data["exists"]:
        print(f"\n✓ Talk page: {data['talk_title']}")
        print(f"  Revisions: {data['revision_count']}")
    else:
        print(f"\n✗ No talk page found for: {article}")

    logger.info(f"Saved to {output_path}")
    return data


def print_venue_report(data: dict) -> None:
    """Print human-readable dispute venue report."""
    print("\n" + "=" * 50)
    print(f"DISPUTE VENUES: {data['article']}")
    print("=" * 50)

    summary = data.get("summary", {})

    print("\n📝 Talk Page:")
    if summary.get("has_talk_page"):
        print(f"   ✓ Exists with {summary['talk_revision_count']} revisions")
    else:
        print("   ✗ No talk page")

    print(f"\n⚠️  ANI Mentions: {summary.get('ani_mention_count', 0)}")
    if data.get("ani_mentions"):
        for mention in data["ani_mentions"][:3]:
            print(f"   - {mention['title'][:50]}...")

    print(f"\n🔍 Third Opinion: {summary.get('third_opinion_count', 0)}")

    print(f"\n📋 RfCs: {summary.get('rfc_count', 0)}")


def print_ani_report(search_term: str, results: list) -> None:
    """Print human-readable ANI search report."""
    print("\n" + "=" * 50)
    print(f"ANI SEARCH: {search_term}")
    print("=" * 50)

    print(f"\nFound {len(results)} mentions")

    for i, result in enumerate(results[:5], 1):
        print(f"\n{i}. {result['title']}")
        print(f"   Source: {result.get('source', 'unknown')}")
        print(f"   Participants: {', '.join(result.get('participants', [])[:3])}")
        if result.get("content_preview"):
            preview = result["content_preview"][:100].replace("\n", " ")
            print(f"   Preview: {preview}...")


def main():
    global logger

    parser = argparse.ArgumentParser(
        description="Wikipedia dispute data collection CLI"
    )
    parser.add_argument("--arb", action="store_true", help="Fetch arbitration cases")
    parser.add_argument("--drn", action="store_true", help="Fetch DRN cases")
    parser.add_argument(
        "--revisions", metavar="TITLE", help="Fetch revisions for article"
    )
    parser.add_argument(
        "--editwar", metavar="TITLE", help="Analyze article for edit war"
    )
    # Phase 2 options
    parser.add_argument(
        "--venues", metavar="TITLE", help="Fetch all dispute venues for article"
    )
    parser.add_argument("--ani", metavar="TERM", help="Search ANI archives for term")
    parser.add_argument(
        "--talk", metavar="TITLE", help="Fetch talk page revisions for article"
    )
    parser.add_argument("--limit", type=int, default=50, help="Limit for fetching")
    parser.add_argument(
        "--threshold", type=float, default=0.1, help="Edit war threshold"
    )
    parser.add_argument("--all", action="store_true", help="Run all collectors")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be fetched without making API calls",
    )

    args = parser.parse_args()

    # Default to --all if no specific flags
    has_specific = any(
        [
            args.arb,
            args.drn,
            args.revisions,
            args.editwar,
            args.venues,
            args.ani,
            args.talk,
        ]
    )
    run_all = args.all or not has_specific

    # Set up logging (skip for dry-run)
    if not args.dry_run:
        logger = setup_logging("fetch_all")
        logger.info("Wikipedia Dispute Data Collection")
        logger.info("=" * 50)

        # Check for API credentials and warn if missing
        check_api_credentials(logger)
    else:
        print("Wikipedia Dispute Data Collection")
        print("=" * 50)

    if args.dry_run:
        print("[DRY RUN] Preview mode - no API calls will be made\n")
        if run_all or args.arb:
            print(f"[DRY RUN] Would fetch arbitration cases (limit: {args.limit})")
        if run_all or args.drn:
            print("[DRY RUN] Would fetch DRN cases")
        if args.revisions:
            print(f"[DRY RUN] Would fetch revisions for: {args.revisions}")
        if args.editwar:
            print(f"[DRY RUN] Would analyze edit war for: {args.editwar}")
        if args.venues:
            print(f"[DRY RUN] Would fetch dispute venues for: {args.venues}")
        if args.ani:
            print(f"[DRY RUN] Would search ANI for: {args.ani}")
        if args.talk:
            print(f"[DRY RUN] Would fetch talk page for: {args.talk}")
        print("\n[DRY RUN] No files written.")
        return

    client = WikiClient()

    # Set global for shutdown handler
    global _client
    _client = client

    if run_all or args.arb:
        run_arbitration(client, limit=args.limit)

    if run_all or args.drn:
        run_drn(client)

    if args.revisions:
        run_revisions(client, args.revisions, limit=args.limit)

    if args.editwar:
        run_editwar(client, args.editwar, threshold=args.threshold)

    # Phase 2 commands
    if args.venues:
        run_dispute_venues(client, args.venues, ani_limit=args.limit)

    if args.ani:
        run_ani_search(client, args.ani, limit=args.limit)

    if args.talk:
        run_talk_page(client, args.talk, limit=args.limit)

    # Log API stats
    client.log_stats()
    stats = client.get_stats()
    print(
        f"\n📊 API Stats: {stats['total_requests']} requests in {stats['runtime_minutes']:.1f} min"
    )

    logger.info("=" * 50)
    logger.info("COMPLETE")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
