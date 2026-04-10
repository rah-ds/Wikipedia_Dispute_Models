#!/usr/bin/env python3
"""
Enrich arbitration case JSONs with evidence page diffs.

ArbCom evidence pages contain ``[[Special:Diff/REVID]]`` references pointing
to the exact article edits that were submitted as evidence.  The DFS fetcher
discards the raw wikitext, so this script re-fetches each evidence page,
extracts diff references, retrieves the actual diff content via the MediaWiki
compare API, and writes enriched JSON files alongside the originals.

Output files are named ``<original_stem>_evidence_diffs.json`` in the same
directory as the source JSON.

Usage:
    python scripts/enrich_evidence_diffs.py
    python scripts/enrich_evidence_diffs.py --case "Gamergate"
    python scripts/enrich_evidence_diffs.py --max-diffs 30 --dry-run
    make enrich-diffs
    make enrich-diffs CASE="Gamergate"
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.evidence import extract_diff_refs, fetch_evidence_diffs
from src.io import (
    setup_logging,
    check_api_credentials,
)

logger: logging.Logger | None = None
_client: WikiClient | None = None

ARB_DATA_DIR = Path("data/raw/arbitration")


def shutdown_handler(signum, frame):
    print("\n\nInterrupted! Logging stats before exit...")
    if _client:
        _client.log_stats()
    sys.exit(130)


signal.signal(signal.SIGINT, shutdown_handler)


def _find_arb_jsons(case_filter: str | None) -> list[Path]:
    """Return DFS JSON files, optionally filtered by case name."""
    if not ARB_DATA_DIR.exists():
        return []
    jsons = sorted(ARB_DATA_DIR.glob("arb_dfs_*.json"))
    if case_filter:
        needle = case_filter.lower().replace(" ", "_")
        jsons = [p for p in jsons if needle in p.stem.lower()]
    return jsons


def _evidence_page_title(case_data: dict) -> str | None:
    """Extract the evidence page title from a DFS JSON."""
    for page in case_data.get("case_pages", []):
        subpage = page.get("subpage", "")
        if subpage == "/Evidence" and page.get("exists", False):
            return page.get("title")
    return None


def enrich_case(
    client: WikiClient,
    json_path: Path,
    max_diffs: int,
    dry_run: bool,
) -> dict:
    """
    Enrich a single case JSON with evidence diffs.

    Returns a summary dict with stats for the case.
    """
    with open(json_path) as f:
        case_data = json.load(f)

    case_name = case_data.get("case_name", json_path.stem)
    evidence_title = _evidence_page_title(case_data)

    if not evidence_title:
        print(f"  [{case_name}] No evidence page found — skipping")
        return {"case": case_name, "skipped": True, "reason": "no_evidence_page"}

    print(f"  [{case_name}] Evidence page: {evidence_title}")

    if dry_run:
        print(f"  [{case_name}] [DRY RUN] Would fetch diffs from {evidence_title}")
        return {"case": case_name, "dry_run": True}

    # Re-fetch evidence page wikitext (the DFS script discards it)
    evidence_page = client.get_page(evidence_title)
    if not evidence_page.exists():
        print(f"  [{case_name}] Evidence page does not exist on Wikipedia")
        return {"case": case_name, "skipped": True, "reason": "page_missing"}

    wikitext = evidence_page.text
    if not wikitext:
        print(f"  [{case_name}] Evidence page is empty")
        return {"case": case_name, "skipped": True, "reason": "empty_page"}

    refs = extract_diff_refs(wikitext)
    print(f"  [{case_name}] Found {len(refs)} diff references")

    if not refs:
        return {"case": case_name, "diff_refs": 0, "diffs_fetched": 0}

    diffs = fetch_evidence_diffs(client, refs, max_diffs=max_diffs)
    successful = [d for d in diffs if "error" not in d]
    print(f"  [{case_name}] Fetched {len(successful)}/{len(diffs)} diffs successfully")

    enrichment = {
        "evidence_page": evidence_title,
        "diff_refs_found": len(refs),
        "diffs_fetched": len(diffs),
        "diffs_successful": len(successful),
        "diffs": diffs,
    }

    out_path = json_path.parent / f"{json_path.stem}_evidence_diffs.json"
    with open(out_path, "w") as f:
        json.dump(enrichment, f, indent=2, ensure_ascii=False)

    print(f"  [{case_name}] Saved to {out_path}")
    return {
        "case": case_name,
        "diff_refs": len(refs),
        "diffs_fetched": len(diffs),
        "diffs_successful": len(successful),
        "output": str(out_path),
    }


def main():
    global logger, _client

    parser = argparse.ArgumentParser(
        description="Enrich arbitration case JSONs with evidence page diffs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/enrich_evidence_diffs.py
    python scripts/enrich_evidence_diffs.py --case "Gamergate"
    python scripts/enrich_evidence_diffs.py --max-diffs 20 --dry-run
        """,
    )
    parser.add_argument(
        "--case",
        default=None,
        help="Filter to a specific case name (substring match)",
    )
    parser.add_argument(
        "--max-diffs",
        type=int,
        default=50,
        help="Maximum diffs to fetch per evidence page (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fetched without making API calls",
    )

    args = parser.parse_args()

    logger = setup_logging("enrich_evidence_diffs")
    logger.info("Evidence Diffs Enricher")
    logger.info("=" * 50)

    json_files = _find_arb_jsons(args.case)
    if not json_files:
        print(f"No DFS JSON files found in {ARB_DATA_DIR}")
        if args.case:
            print(f"(filtering for case: {args.case!r})")
        sys.exit(0)

    print(f"\nFound {len(json_files)} case JSON(s) to process")
    if args.dry_run:
        print("[DRY RUN] No API calls or files will be written\n")

    if not args.dry_run:
        check_api_credentials(logger)

    client = WikiClient()
    _client = client

    summaries = []
    for json_path in json_files:
        print(f"\nProcessing: {json_path.name}")
        summary = enrich_case(client, json_path, args.max_diffs, args.dry_run)
        summaries.append(summary)
        time.sleep(0.5)

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    total_refs = sum(s.get("diff_refs", 0) for s in summaries)
    total_fetched = sum(s.get("diffs_fetched", 0) for s in summaries)
    total_ok = sum(s.get("diffs_successful", 0) for s in summaries)
    skipped = sum(1 for s in summaries if s.get("skipped"))
    print(f"  Cases processed: {len(summaries)}")
    print(f"  Cases skipped:   {skipped}")
    print(f"  Diff refs found: {total_refs}")
    print(f"  Diffs fetched:   {total_fetched} ({total_ok} successful)")

    if not args.dry_run:
        client.log_stats()


if __name__ == "__main__":
    main()
