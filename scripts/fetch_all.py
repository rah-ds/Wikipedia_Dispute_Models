#!/usr/bin/env python3
"""
Unified CLI for Wikipedia dispute data collection.

Usage:
    python fetch_all.py                    # Run all collectors
    python fetch_all.py --arb              # Arbitration cases only
    python fetch_all.py --drn              # DRN cases only
    python fetch_all.py --revisions "Title" # Revisions for specific article
    python fetch_all.py --editwar "Title"  # Edit war analysis
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
    run_all = args.all or not any([args.arb, args.drn, args.revisions, args.editwar])

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
