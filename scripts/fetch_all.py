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
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.io import save_json, get_output_path, sanitize_filename


def run_arbitration(client: WikiClient, limit: int = 50):
    """Fetch arbitration cases."""
    from fetch_arbitration_cases import get_arbitration_cases

    print("\n" + "=" * 50)
    print("FETCHING ARBITRATION CASES")
    print("=" * 50)

    cases = get_arbitration_cases(client, limit=limit)
    output_path = get_output_path("arbitration", prefix="arbitration_cases")
    save_json(cases, output_path)

    print(f"Saved {len(cases)} cases to {output_path}")
    return cases


def run_drn(client: WikiClient):
    """Fetch DRN cases."""
    from fetch_drn_cases import (
        fetch_drn_page,
        parse_drn_sections,
        extract_case_metadata,
    )

    print("\n" + "=" * 50)
    print("FETCHING DRN CASES")
    print("=" * 50)

    drn_data = fetch_drn_page(client)
    cases = parse_drn_sections(drn_data["content"])
    cases = extract_case_metadata(cases)
    cases = [c for c in cases if c["level"] == 2 and len(c["content"]) > 100]

    drn_data["parsed_cases"] = cases
    drn_data["case_count"] = len(cases)
    del drn_data["content"]

    output_path = get_output_path("drn", prefix="drn_cases")
    save_json(drn_data, output_path)

    print(f"Saved {len(cases)} cases to {output_path}")
    return drn_data


def run_revisions(client: WikiClient, article: str, limit: int | None = None):
    """Fetch revisions for an article."""
    from fetch_revisions import fetch_revisions

    print("\n" + "=" * 50)
    print(f"FETCHING REVISIONS: {article}")
    print("=" * 50)

    data = fetch_revisions(client, article, limit=limit)
    safe_title = sanitize_filename(article)
    output_path = get_output_path("revisions", prefix=safe_title)
    save_json(data, output_path)

    print(f"Saved to {output_path}")
    return data


def run_editwar(client: WikiClient, article: str, threshold: float = 0.1):
    """Analyze article for edit war."""
    from detect_edit_wars import run_analysis, print_report

    print("\n" + "=" * 50)
    print(f"ANALYZING EDIT WAR: {article}")
    print("=" * 50)

    analysis = run_analysis(client, article, threshold=threshold)
    safe_title = sanitize_filename(article)
    output_path = get_output_path("edit_wars", prefix=f"editwar_{safe_title}")
    save_json(analysis, output_path)

    print_report(analysis)
    print(f"\nSaved to {output_path}")
    return analysis


def main():
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

    args = parser.parse_args()

    # Default to --all if no specific flags
    run_all = args.all or not any([args.arb, args.drn, args.revisions, args.editwar])

    print("Wikipedia Dispute Data Collection")
    print("=" * 50)

    client = WikiClient()

    if run_all or args.arb:
        run_arbitration(client, limit=args.limit)

    if run_all or args.drn:
        run_drn(client)

    if args.revisions:
        run_revisions(client, args.revisions, limit=args.limit)

    if args.editwar:
        run_editwar(client, args.editwar, threshold=args.threshold)

    print("\n" + "=" * 50)
    print("COMPLETE")
    print("=" * 50)


if __name__ == "__main__":
    main()
