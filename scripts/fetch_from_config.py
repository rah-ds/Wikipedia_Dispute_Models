#!/usr/bin/env python3
"""Fetch articles based on YAML configuration.

Usage:
    python fetch_from_config.py                    # Fetch all from config
    python fetch_from_config.py --dry-run          # Preview what would be fetched
    python fetch_from_config.py --config path.yaml # Use custom config
"""

import argparse
import sys
from pathlib import Path

import yaml

# Add src to path
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
    fetch_revisions,
    analyze_article_edit_war,
    fetch_arbitration_cases,
    fetch_drn_page,
    parse_drn_sections,
    extract_case_metadata,
)

CONFIG_PATH = Path(__file__).parent.parent / "artifacts" / "sample_articles.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load article configuration from YAML."""
    with open(path) as f:
        return yaml.safe_load(f)


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

    # Fetch arbitration cases
    if not args.skip_arb:
        print("=== Arbitration Cases ===")
        cases = fetch_arbitration_cases(client, limit=arb_limit)
        output_path = get_output_path("arbitration", prefix="arbitration_cases")
        save_json(cases, output_path)
        logger.info(f"Saved {len(cases)} arbitration cases to {output_path}")

    # Fetch DRN cases
    if not args.skip_drn:
        print("\n=== DRN Cases ===")
        drn_data = fetch_drn_page(client)
        cases = parse_drn_sections(drn_data["content"])
        cases = extract_case_metadata(cases)
        cases = [c for c in cases if c["level"] == 2 and len(c["content"]) > 100]
        drn_data["parsed_cases"] = cases
        drn_data["case_count"] = len(cases)
        del drn_data["content"]
        output_path = get_output_path("drn", prefix="drn_cases")
        save_json(drn_data, output_path)
        logger.info(f"Saved {len(cases)} DRN cases to {output_path}")

    # Fetch high-conflict articles
    print("\n=== High-Conflict Articles ===")
    for article in high_conflict:
        title = article["title"]
        print(f"\n{title}")
        logger.info(f"Fetching: {title}")

        data = fetch_revisions(client, title, limit=rev_limit)
        output_path = get_output_path("revisions", prefix=sanitize_filename(title))
        save_json(data, output_path)

        analysis = analyze_article_edit_war(client, title)
        output_path = get_output_path(
            "edit_wars", prefix=f"editwar_{sanitize_filename(title)}"
        )
        save_json(analysis, output_path)

    # Fetch low-conflict articles
    print("\n=== Low-Conflict Articles ===")
    for article in low_conflict:
        title = article["title"]
        print(f"\n{title}")
        logger.info(f"Fetching: {title}")

        data = fetch_revisions(client, title, limit=rev_limit)
        output_path = get_output_path("revisions", prefix=sanitize_filename(title))
        save_json(data, output_path)

        analysis = analyze_article_edit_war(client, title)
        output_path = get_output_path(
            "edit_wars", prefix=f"editwar_{sanitize_filename(title)}"
        )
        save_json(analysis, output_path)

    print("\n✓ Fetch complete!")
    logger.info("Fetch complete")


if __name__ == "__main__":
    main()
