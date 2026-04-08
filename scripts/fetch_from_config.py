#!/usr/bin/env python3
"""Fetch articles based on YAML configuration.

Usage:
    python fetch_from_config.py                    # Fetch all from config
    python fetch_from_config.py --dry-run          # Preview what would be fetched
    python fetch_from_config.py --config path.yaml # Use custom config
    python fetch_from_config.py --force            # Re-fetch even if files exist
"""

import argparse
import sys
import time
from pathlib import Path

import yaml
from tqdm import tqdm

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.io import (
    save_json,
    get_output_path,
    sanitize_filename,
    setup_logging,
    check_api_credentials,
    DATA_DIR,
)
from src.fetchers import (
    fetch_revisions,
    analyze_article_edit_war,
    fetch_arbitration_cases,
    fetch_drn_page,
    parse_drn_sections,
    extract_case_metadata,
)

CONFIG_PATH = Path(__file__).parent.parent / "artifacts" / "sample_articles.yaml"

# Delay between article fetches (seconds) - be nice to Wikipedia
FETCH_DELAY = 2.0

# Global for graceful shutdown
_client = None
_logger = None


def shutdown_handler(signum, frame):
    """Handle Ctrl+C gracefully - log stats before exit."""
    print("\n\n⚠️  Interrupted! Logging stats before exit...")
    if _client:
        _client.log_stats()
        stats = _client.get_stats()
        print(
            f"📊 API Stats: {stats['total_requests']} requests in {stats['runtime_minutes']:.1f} min"
        )
    if _logger:
        _logger.info("Fetch interrupted by user")
    sys.exit(1)


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load article configuration from YAML."""
    with open(path) as f:
        return yaml.safe_load(f)


def article_already_fetched(title: str) -> bool:
    """Check if article data already exists."""
    safe_title = sanitize_filename(title)
    revisions_dir = DATA_DIR / "raw" / "revisions"
    editwar_dir = DATA_DIR / "raw" / "edit_wars"

    # Check for any file matching this article
    rev_files = (
        list(revisions_dir.glob(f"{safe_title}_*.json"))
        if revisions_dir.exists()
        else []
    )
    ew_files = (
        list(editwar_dir.glob(f"editwar_{safe_title}_*.json"))
        if editwar_dir.exists()
        else []
    )

    return len(rev_files) > 0 and len(ew_files) > 0


def arb_already_fetched() -> bool:
    """Check if arbitration data already exists."""
    arb_dir = DATA_DIR / "raw" / "arbitration"
    if not arb_dir.exists():
        return False
    return len(list(arb_dir.glob("arbitration_cases_*.json"))) > 0


def drn_already_fetched() -> bool:
    """Check if DRN data already exists."""
    drn_dir = DATA_DIR / "raw" / "drn"
    if not drn_dir.exists():
        return False
    return len(list(drn_dir.glob("drn_cases_*.json"))) > 0


def main():
    parser = argparse.ArgumentParser(description="Fetch articles from YAML config")
    parser.add_argument(
        "--config", type=Path, default=CONFIG_PATH, help="Path to config YAML"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without fetching"
    )
    parser.add_argument(
        "--skip-arb", action="store_true", help="Skip arbitration cases"
    )
    parser.add_argument("--skip-drn", action="store_true", help="Skip DRN cases")
    parser.add_argument(
        "--force", action="store_true", help="Re-fetch even if files exist"
    )
    args = parser.parse_args()

    config = load_config(args.config)
    defaults = config.get("defaults", {})
    rev_limit = defaults.get("revision_limit", 500)
    arb_limit = defaults.get("arb_limit", 5)

    high_conflict = config.get("high_conflict", [])
    low_conflict = config.get("low_conflict", [])
    all_articles = high_conflict + low_conflict

    print(f"Config: {args.config}")
    print(f"High-conflict articles: {len(high_conflict)}")
    print(f"Low-conflict articles: {len(low_conflict)}")
    print(f"Revision limit: {rev_limit}")
    print()

    if args.dry_run:
        print("[DRY RUN] Would fetch:")
        if not args.skip_arb:
            print(f"  - {arb_limit} arbitration cases")
        if not args.skip_drn:
            print("  - DRN cases")
        for article in all_articles:
            print(f"  - {article['title']} ({article['category']})")
        return

    check_api_credentials()
    logger = setup_logging("fetch_from_config")
    client = WikiClient()

    # Set globals for shutdown handler
    global _client, _logger
    _client = client
    _logger = logger

    failed = []

    # Fetch arbitration cases
    if not args.skip_arb:
        if not args.force and arb_already_fetched():
            print("=== Arbitration Cases === (skipped, already fetched)")
        else:
            print("=== Arbitration Cases ===")
            try:
                cases = fetch_arbitration_cases(client, limit=arb_limit)
                output_path = get_output_path("arbitration", prefix="arbitration_cases")
                save_json(cases, output_path)
                logger.info(f"Saved {len(cases)} arbitration cases to {output_path}")
            except Exception as e:
                logger.error(f"Failed to fetch arbitration cases: {e}")
                failed.append(("Arbitration cases", str(e)))

    # Fetch DRN cases
    if not args.skip_drn:
        if not args.force and drn_already_fetched():
            print("\n=== DRN Cases === (skipped, already fetched)")
        else:
            print("\n=== DRN Cases ===")
            try:
                drn_data = fetch_drn_page(client)
                cases = parse_drn_sections(drn_data["content"])
                cases = extract_case_metadata(cases)
                cases = [
                    c for c in cases if c["level"] == 2 and len(c["content"]) > 100
                ]
                drn_data["parsed_cases"] = cases
                drn_data["case_count"] = len(cases)
                del drn_data["content"]
                output_path = get_output_path("drn", prefix="drn_cases")
                save_json(drn_data, output_path)
                logger.info(f"Saved {len(cases)} DRN cases to {output_path}")
            except Exception as e:
                logger.error(f"Failed to fetch DRN cases: {e}")
                failed.append(("DRN cases", str(e)))

    # Fetch all articles with progress bar
    print("\n=== Fetching Articles ===")

    # Check which articles already exist
    skipped = 0
    to_fetch = []
    for article in all_articles:
        if not args.force and article_already_fetched(article["title"]):
            skipped += 1
        else:
            to_fetch.append(article)

    if skipped > 0:
        print(f"Skipping {skipped} already-fetched articles (use --force to re-fetch)")

    if not to_fetch:
        print("All articles already fetched!")
    else:
        pbar = tqdm(to_fetch, desc="Articles", unit="article")

        for article in pbar:
            title = article["title"]
            # category = article.get("category", "unknown")
            pbar.set_postfix_str(title[:30])

            try:
                # Fetch revisions
                data = fetch_revisions(client, title, limit=rev_limit)
                output_path = get_output_path(
                    "revisions", prefix=sanitize_filename(title)
                )
                save_json(data, output_path)

                # Run edit war analysis
                analysis = analyze_article_edit_war(client, title)
                output_path = get_output_path(
                    "edit_wars", prefix=f"editwar_{sanitize_filename(title)}"
                )
                save_json(analysis, output_path)

                logger.info(f"Completed: {title}")

            except Exception as e:
                logger.error(f"Failed to fetch {title}: {e}")
                failed.append((title, str(e)))
                tqdm.write(f"  ✗ Error: {e}")

            # Rate limiting delay
            time.sleep(FETCH_DELAY)

    # Summary
    print("\n" + "=" * 50)
    successful = len(to_fetch) - len(
        [f for f in failed if f[0] not in ("Arbitration cases", "DRN cases")]
    )
    print(f"✓ Fetched: {successful}/{len(to_fetch)} articles")
    if skipped > 0:
        print(f"✓ Skipped: {skipped} (already existed)")

    if failed:
        print(f"\n⚠️  Failed ({len(failed)}):")
        for name, error in failed:
            print(f"  - {name}: {error}")

    # Log API request stats
    client.log_stats()
    stats = client.get_stats()
    print(
        f"\n📊 API Stats: {stats['total_requests']} requests in {stats['runtime_minutes']:.1f} min"
    )

    print("\n✓ Fetch complete!")
    logger.info(
        f"Fetch complete: {successful}/{len(to_fetch)} articles, {len(failed)} failures"
    )


if __name__ == "__main__":
    main()
