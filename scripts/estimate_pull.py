#!/usr/bin/env python3
"""Estimate time and storage requirements for a full arbitration pull.

This script provides estimates before running a large data pull:
- Estimated time to complete
- Estimated storage requirements
- Current free disk space
- Warning if storage would drop below threshold

Usage:
    python scripts/estimate_pull.py
    python scripts/estimate_pull.py --case-file artifacts/arb_cases.txt
    python scripts/estimate_pull.py --threshold 20  # Warn if < 20GB free
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def get_free_space_gb(path: str = ".") -> float:
    """Get free disk space in GB."""
    total, used, free = shutil.disk_usage(path)
    return free / (1024**3)


def get_existing_cases(output_dir: str = "data/raw/arbitration") -> set[str]:
    """Get set of already-fetched case names."""
    output_path = Path(output_dir)
    if not output_path.exists():
        return set()

    existing = set()
    for f in output_path.glob("*.json"):
        # Convert filename back to case name
        name = f.stem.replace("_", " ").replace("/", "_")
        existing.add(name)

    return existing


def load_case_list(case_file: str) -> list[str]:
    """Load case list from file."""
    path = Path(case_file)
    if not path.exists():
        return []

    with open(path) as f:
        cases = [
            line.strip()
            for line in f
            if line.strip() and not line.startswith("#")
        ]
    return cases


def estimate_case_size_mb() -> dict:
    """Return estimated size per case based on typical data."""
    return {
        "case_pages": 0.5,  # 5 subpages, ~100KB each
        "talk_pages": 0.3,  # Talk pages
        "revisions": 1.0,  # Full revision history
        "participants": 0.2,  # User info, blocks
        "articles": 0.5,  # Article metadata
        "ani_drn": 0.3,  # ANI/DRN mentions
        "total_per_case": 2.8,  # MB per case average
    }


def estimate_api_calls_per_case() -> dict:
    """Return estimated API calls per case."""
    return {
        "case_pages": 10,  # 5 pages + 5 talk pages
        "participant_info": 2,  # Batch of 50
        "participant_blocks": 30,  # One per participant (top 30)
        "participant_abuse": 20,  # One per participant (top 20)
        "article_assessments": 20,  # One per article
        "article_protection": 20,  # One per article
        "article_revisions": 10,  # Top 10 articles
        "ani_search": 10,  # Case + top participants
        "drn_search": 5,  # Limited archives
        "total_per_case": 127,  # Total API calls per case
    }


def format_duration(hours: float) -> str:
    """Format hours as human-readable duration."""
    if hours < 1:
        return f"{hours * 60:.0f} minutes"
    elif hours < 24:
        return f"{hours:.1f} hours"
    else:
        days = hours / 24
        return f"{days:.1f} days ({hours:.0f} hours)"


def format_size(size_mb: float) -> str:
    """Format MB as human-readable size."""
    if size_mb < 1024:
        return f"{size_mb:.1f} MB"
    else:
        return f"{size_mb / 1024:.2f} GB"


def print_estimate(
    total_cases: int,
    pending_cases: int,
    completed_cases: int,
    free_space_gb: float,
    threshold_gb: float = 10.0,
) -> bool:
    """
    Print pull estimate and return True if safe to proceed.

    Returns:
        True if safe to proceed, False if storage warning
    """
    estimates = estimate_case_size_mb()
    api_estimates = estimate_api_calls_per_case()

    # Calculate estimates for pending cases
    estimated_size_mb = pending_cases * estimates["total_per_case"]
    estimated_api_calls = pending_cases * api_estimates["total_per_case"]

    # Time estimate based on rate limits
    # 5000 req/hr = 83 req/min, but with delays ~50 req/min effective
    effective_calls_per_min = 50
    estimated_minutes = estimated_api_calls / effective_calls_per_min
    estimated_hours = estimated_minutes / 60

    # Storage after pull
    remaining_space_gb = free_space_gb - (estimated_size_mb / 1024)
    storage_warning = remaining_space_gb < threshold_gb

    print("=" * 70)
    print("          ARBITRATION FULL PULL - ESTIMATE")
    print("=" * 70)
    print()

    # Case counts
    print("CASES:")
    print(f"  Total cases in list:     {total_cases:>6}")
    print(f"  Already completed:       {completed_cases:>6}")
    print(f"  Remaining to fetch:      {pending_cases:>6}")
    print()

    # Time estimate
    print("TIME ESTIMATE:")
    print(f"  API calls per case:      ~{api_estimates['total_per_case']}")
    print(f"  Total API calls:         ~{estimated_api_calls:,}")
    print(f"  Effective rate:          ~{effective_calls_per_min} calls/min")
    print(f"  Estimated duration:      {format_duration(estimated_hours)}")
    print()

    # Storage estimate
    print("STORAGE ESTIMATE:")
    print(f"  Size per case:           ~{estimates['total_per_case']:.1f} MB")
    print(f"  Total new data:          ~{format_size(estimated_size_mb)}")
    print()

    # Current storage
    print("DISK SPACE:")
    print(f"  Current free space:      {free_space_gb:.1f} GB")
    print(f"  After pull:              ~{remaining_space_gb:.1f} GB")
    print(f"  Warning threshold:       {threshold_gb:.1f} GB")
    print()

    # Data collected per case
    print("DATA COLLECTED PER CASE:")
    print("  - Case pages: main, evidence, workshop, proposed decision, remedies")
    print("  - Case talk pages with full revision history")
    print("  - Participant profiles (edit count, registration, groups)")
    print("  - Participant block history and abuse filter hits")
    print("  - Article assessments (quality, importance)")
    print("  - Article protection status and history")
    print("  - Article revision history with edit tags")
    print("  - ANI and DRN mentions")
    print("  - Case outcome (status, remedies, sanctions)")
    print()

    # Warning
    if storage_warning:
        print("!" * 70)
        print("!!! WARNING: Free space would drop below threshold !!!")
        print(f"!!!          Remaining: {remaining_space_gb:.1f} GB < {threshold_gb:.1f} GB")
        print("!" * 70)
        print()
        print("Options:")
        print("  1. Free up disk space before proceeding")
        print("  2. Run with --force to proceed anyway")
        print("  3. Archive existing results: make archive")
        print()
        return False
    else:
        print("-" * 70)
        print("Storage check: OK (sufficient space available)")
        print("-" * 70)
        print()
        return True


def main():
    parser = argparse.ArgumentParser(
        description="Estimate time and storage for full arbitration pull",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--case-file",
        default="artifacts/arb_cases.txt",
        help="Path to case list file (default: artifacts/arb_cases.txt)",
    )
    parser.add_argument(
        "--output-dir",
        default="data/raw/arbitration",
        help="Output directory to check for existing cases",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=10.0,
        help="GB threshold for storage warning (default: 10)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Proceed even with storage warning",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON (for scripting)",
    )

    args = parser.parse_args()

    # Load cases
    all_cases = load_case_list(args.case_file)
    if not all_cases:
        print(f"Error: No cases found in {args.case_file}")
        print("Run 'make update-arb-cases-list' to fetch the case list from Wikipedia")
        sys.exit(1)

    # Check existing
    completed = get_existing_cases(args.output_dir)
    pending = [c for c in all_cases if c not in completed]

    # Get free space
    free_space = get_free_space_gb()

    if args.json:
        estimates = estimate_case_size_mb()
        api_estimates = estimate_api_calls_per_case()
        result = {
            "total_cases": len(all_cases),
            "completed_cases": len(completed),
            "pending_cases": len(pending),
            "estimated_size_mb": len(pending) * estimates["total_per_case"],
            "estimated_api_calls": len(pending) * api_estimates["total_per_case"],
            "estimated_hours": (
                len(pending) * api_estimates["total_per_case"] / 50 / 60
            ),
            "free_space_gb": free_space,
            "threshold_gb": args.threshold,
            "storage_ok": free_space - (len(pending) * estimates["total_per_case"] / 1024) >= args.threshold,
        }
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["storage_ok"] else 1)

    # Print estimate
    safe = print_estimate(
        total_cases=len(all_cases),
        pending_cases=len(pending),
        completed_cases=len(completed),
        free_space_gb=free_space,
        threshold_gb=args.threshold,
    )

    if not safe and not args.force:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
