#!/usr/bin/env python3
"""
Fetch declined arbitration requests for negative-class labeling.

ArbCom cases in the dataset are *all* accepted cases — every dispute that
escalated all the way to a formal arbitration ruling.  Training a model to
predict "will this escalate to ArbCom?" requires a negative class: disputes
that were referred to ArbCom but *declined* (deemed not worth a full case).

This script fetches declined requests from:
  Wikipedia:Arbitration/Requests/Case  (current declined section)
  Category:Wikipedia_arbitration_declined_requests

Each declined request is stored with its revision history so it can be used
as a negative example alongside the accepted cases.

Usage:
    python scripts/fetch_declined_rfas.py
    python scripts/fetch_declined_rfas.py --limit 50
    python scripts/fetch_declined_rfas.py --dry-run
    make fetch-declined
"""

from __future__ import annotations

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
    setup_logging,
    check_api_credentials,
)

logger: logging.Logger | None = None
_client: WikiClient | None = None

# Categories and pages to look for declined requests
DECLINED_CATEGORIES = [
    "Wikipedia arbitration declined requests",
    "Wikipedia arbitration requests declined",
]

# The main ArbCom requests page — declined cases appear in a dedicated section
ARB_REQUESTS_PAGE = "Wikipedia:Arbitration/Requests/Case"


def shutdown_handler(signum, frame):
    print("\n\nInterrupted! Logging stats before exit...")
    if _client:
        _client.log_stats()
    sys.exit(130)


signal.signal(signal.SIGINT, shutdown_handler)


def _extract_declined_sections(wikitext: str) -> list[dict]:
    """
    Extract declined case sections from the ArbCom requests page.

    Looks for sections under headings containing "declined" or "rejected".
    """
    wikicode = mwparserfromhell.parse(wikitext)
    sections = []
    current: dict | None = None
    in_declined = False

    for node in wikicode.nodes:
        if isinstance(node, mwparserfromhell.nodes.Heading):
            heading_text = str(node.title).strip().lower()
            if "declined" in heading_text or "rejected" in heading_text:
                in_declined = True
            elif node.level <= 2:
                in_declined = False

            if current:
                sections.append(current)
            current = {
                "heading": str(node.title).strip(),
                "level": node.level,
                "content": "",
                "in_declined_section": in_declined,
            }
        elif current is not None:
            current["content"] += str(node)

    if current:
        sections.append(current)

    declined = [s for s in sections if s["in_declined_section"]]
    return declined


def _parse_case_names_from_section(content: str) -> list[str]:
    """Extract individual case names from a declined section."""
    names = []
    # Look for wikilinks to arbitration case pages
    pattern = re.compile(
        r"\[\[Wikipedia:Arbitration/Requests/Case/([^\]|]+)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(content):
        name = m.group(1).strip()
        if name:
            names.append(name)
    return list(dict.fromkeys(names))  # deduplicate while preserving order


def fetch_declined_from_category(
    client: WikiClient,
    limit: int,
    revision_limit: int | None,
    delay: float,
) -> list[dict]:
    """Fetch declined requests from Wikipedia categories."""
    results = []

    for cat_name in DECLINED_CATEGORIES:
        print(f"\n  Category: {cat_name}")
        try:
            pages = client.get_category_pages(cat_name, limit=limit)
        except Exception as exc:
            print(f"    Could not fetch category '{cat_name}': {exc}")
            continue

        for page in pages:
            if len(results) >= limit:
                break
            title = page.title()
            print(f"    ✓ {title}")

            try:
                revisions = client.get_revisions(title, limit=revision_limit)
                result = {
                    "title": title,
                    "url": page.full_url(),
                    "fetched_at": datetime.now().isoformat(),
                    "outcome": "declined",
                    "source": f"category:{cat_name}",
                    "revisions": revisions,
                    "revision_count": len(revisions),
                    "content_length": len(page.text) if page.exists() else 0,
                }
                results.append(result)
            except Exception as exc:
                print(f"    ✗ {title}: {exc}")

            time.sleep(delay)

        if len(results) >= limit:
            break

    return results


def fetch_declined_from_requests_page(
    client: WikiClient,
    revision_limit: int | None,
    delay: float,
) -> list[dict]:
    """
    Fetch declined requests from the main ArbCom requests page.

    Parses the page for declined sections and extracts individual case links.
    """
    results = []

    page = client.get_page(ARB_REQUESTS_PAGE)
    if not page.exists():
        print(f"  ArbCom requests page not found: {ARB_REQUESTS_PAGE}")
        return []

    print(f"  Parsing {ARB_REQUESTS_PAGE}...")
    declined_sections = _extract_declined_sections(page.text)

    for section in declined_sections:
        case_names = _parse_case_names_from_section(section["content"])
        for case_name in case_names:
            full_title = f"Wikipedia:Arbitration/Requests/Case/{case_name}"
            try:
                case_page = client.get_page(full_title)
                if not case_page.exists():
                    continue

                print(f"    ✓ {full_title}")
                revisions = client.get_revisions(full_title, limit=revision_limit)
                results.append(
                    {
                        "title": full_title,
                        "url": case_page.full_url(),
                        "fetched_at": datetime.now().isoformat(),
                        "outcome": "declined",
                        "source": "requests_page_declined_section",
                        "case_name": case_name,
                        "revisions": revisions,
                        "revision_count": len(revisions),
                    }
                )
            except Exception as exc:
                print(f"    ✗ {full_title}: {exc}")

            time.sleep(delay)

    return results


def main():
    global logger, _client

    parser = argparse.ArgumentParser(
        description="Fetch declined ArbCom requests for negative-class labeling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/fetch_declined_rfas.py
    python scripts/fetch_declined_rfas.py --limit 50
    python scripts/fetch_declined_rfas.py --dry-run
        """,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum declined cases to fetch (default: 200)",
    )
    parser.add_argument(
        "--revision-limit",
        type=int,
        default=50,
        help="Maximum revisions per case (default: 50, 0=all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be fetched without making API calls",
    )

    args = parser.parse_args()
    revision_limit = args.revision_limit if args.revision_limit > 0 else None

    if args.dry_run:
        print("Declined ArbCom Requests Fetcher")
        print("=" * 50)
        print("\n[DRY RUN] No API calls will be made\n")
        print("Would search:")
        for cat in DECLINED_CATEGORIES:
            print(f"  • Category: {cat}")
        print(f"  • Declined sections of {ARB_REQUESTS_PAGE}")
        print(f"\n  Up to {args.limit} cases, {revision_limit or 'all'} revisions each")
        print("\n[DRY RUN] No files written.")
        return

    logger = setup_logging("fetch_declined_rfas")
    logger.info("Declined ArbCom Requests Fetcher")
    logger.info("=" * 50)

    check_api_credentials(logger)

    client = WikiClient()
    _client = client

    print("\nFetching declined requests from categories...")
    category_results = fetch_declined_from_category(
        client,
        limit=args.limit,
        revision_limit=revision_limit,
        delay=0.5,
    )

    print("\nFetching declined requests from ArbCom requests page...")
    requests_page_results = fetch_declined_from_requests_page(
        client,
        revision_limit=revision_limit,
        delay=0.5,
    )

    # Merge and deduplicate by title
    all_results = {r["title"]: r for r in category_results}
    for r in requests_page_results:
        if r["title"] not in all_results:
            all_results[r["title"]] = r

    results = list(all_results.values())[: args.limit]

    output = {
        "fetched_at": datetime.now().isoformat(),
        "outcome": "declined",
        "description": (
            "Declined ArbCom arbitration requests — negative class for "
            "escalation models.  These disputes were brought to ArbCom but "
            "declined without a full case."
        ),
        "cases": results,
        "summary": {
            "total_cases": len(results),
            "from_categories": len(category_results),
            "from_requests_page": len(requests_page_results),
            "total_revisions": sum(r.get("revision_count", 0) for r in results),
        },
    }

    output_path = get_output_path("arbitration", prefix="declined_rfas")
    save_json(output, output_path)

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for key, value in output["summary"].items():
        print(f"  {key}: {value}")
    print(f"\nSaved to: {output_path}")

    client.log_stats()


if __name__ == "__main__":
    main()
