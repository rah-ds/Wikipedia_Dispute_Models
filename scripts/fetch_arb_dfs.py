#!/usr/bin/env python3
"""
Depth-first search fetcher for arbitration cases.

Given an arbitration case name, performs a DFS to collect all related
conversations and talk pages:

1. The arbitration case main page
2. Subpages: /Evidence, /Workshop, /Proposed decision, etc.
3. The case talk page
4. All articles mentioned in the case
5. Talk pages for all mentioned articles

This is useful for sponsors who want a complete view of a single case
with all associated discussions.

Usage:
    python scripts/fetch_arb_dfs.py "CaseName"
    python scripts/fetch_arb_dfs.py "CaseName" --dry-run
    python scripts/fetch_arb_dfs.py "CaseName" --max-articles 10

Example:
    python scripts/fetch_arb_dfs.py "Climate change"
    make fetch-arb-dfs CASE="Climate change"
"""

import argparse
import logging
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


def get_arb_case_prefix(case_name: str) -> str:
    """Get the Wikipedia page prefix for an arbitration case."""
    # Handle if user provides full path or just case name
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

        # Skip section links within same page
        if title.startswith("#"):
            continue

        # Remove any anchor/section part
        if "#" in title:
            title = title.split("#")[0]

        if title:
            articles.add(title)

    return list(articles)


def fetch_arb_case_dfs(
    client: WikiClient,
    case_name: str,
    max_articles: int = 20,
    revision_limit: int | None = 100,
    delay: float = 0.5,
) -> dict:
    """
    Perform depth-first search from an arbitration case.

    Collects:
    1. All case subpages (main, evidence, workshop, etc.)
    2. Talk pages for the case
    3. All linked articles
    4. Talk pages for linked articles

    Args:
        client: WikiClient instance
        case_name: Arbitration case name (e.g., "Climate change")
        max_articles: Maximum linked articles to fetch (to avoid runaway)
        revision_limit: Max revisions per page (None = all)
        delay: Seconds between API calls

    Returns:
        Dictionary with all fetched data
    """
    case_prefix = get_arb_case_prefix(case_name)
    print(f"\n🔍 DFS starting from: {case_prefix}")

    result = {
        "case_name": case_name,
        "case_prefix": case_prefix,
        "fetched_at": datetime.now().isoformat(),
        "case_pages": [],
        "case_talk_pages": [],
        "linked_articles": [],
        "article_talk_pages": [],
        "summary": {},
    }

    all_linked_articles = set()

    # Step 1: Fetch all case subpages
    print("\n📄 Fetching case subpages...")
    for suffix in ARB_SUBPAGES:
        page_title = f"{case_prefix}{suffix}"
        try:
            page = client.get_page(page_title)
            if not page.exists():
                print(f"   ✗ {page_title} (not found)")
                continue

            print(f"   ✓ {page_title}")

            page_data = {
                "title": page.title(),
                "url": page.full_url(),
                "exists": True,
                "subpage": suffix or "(main)",
                "revisions": client.get_revisions(page_title, limit=revision_limit),
                "content": page.text,
            }

            # Extract linked articles from content
            links = extract_article_links(page.text)
            page_data["linked_articles"] = links
            all_linked_articles.update(links)

            # Don't store full content in output (too large), just metadata
            page_data["content_length"] = len(page.text)
            del page_data["content"]

            result["case_pages"].append(page_data)
            time.sleep(delay)

        except Exception as e:
            print(f"   ✗ {page_title}: {e}")
            result["case_pages"].append(
                {
                    "title": page_title,
                    "exists": False,
                    "error": str(e),
                }
            )

    # Step 2: Fetch case talk pages
    print("\n💬 Fetching case talk pages...")
    for suffix in ARB_SUBPAGES:
        page_title = f"{case_prefix}{suffix}"
        talk_title = f"Wikipedia talk:Arbitration/Requests/Case/{case_name}{suffix}"

        try:
            talk_page = client.get_page(talk_title)
            if not talk_page.exists():
                continue

            print(f"   ✓ {talk_title}")

            talk_data = {
                "title": talk_page.title(),
                "url": talk_page.full_url(),
                "for_page": page_title,
                "revisions": client.get_revisions(talk_title, limit=revision_limit),
                "revision_count": 0,
            }
            talk_data["revision_count"] = len(talk_data["revisions"])

            result["case_talk_pages"].append(talk_data)
            time.sleep(delay)

        except Exception as e:
            print(f"   ✗ {talk_title}: {e}")

    # Step 3: Fetch linked articles (limited)
    print(
        f"\n📚 Found {len(all_linked_articles)} linked articles, fetching up to {max_articles}..."
    )
    articles_to_fetch = list(all_linked_articles)[:max_articles]

    for article_title in articles_to_fetch:
        try:
            page = client.get_page(article_title)
            if not page.exists():
                print(f"   ✗ {article_title} (not found)")
                continue

            print(f"   ✓ {article_title}")

            article_data = {
                "title": page.title(),
                "url": page.full_url(),
                "revisions": client.get_revisions(article_title, limit=revision_limit),
                "revision_count": 0,
            }
            article_data["revision_count"] = len(article_data["revisions"])

            result["linked_articles"].append(article_data)
            time.sleep(delay)

        except Exception as e:
            print(f"   ✗ {article_title}: {e}")

    # Step 4: Fetch talk pages for linked articles
    print("\n💬 Fetching article talk pages...")
    for article_data in result["linked_articles"]:
        article_title = article_data["title"]
        try:
            talk_page = client.get_talk_page(article_title)
            if not talk_page:
                continue

            print(f"   ✓ Talk:{article_title}")

            talk_data = {
                "title": talk_page.title(),
                "url": talk_page.full_url(),
                "for_article": article_title,
                "revisions": client.get_revisions(
                    talk_page.title(), limit=revision_limit
                ),
                "revision_count": 0,
            }
            talk_data["revision_count"] = len(talk_data["revisions"])

            result["article_talk_pages"].append(talk_data)
            time.sleep(delay)

        except Exception as e:
            print(f"   ✗ Talk:{article_title}: {e}")

    # Summary
    result["summary"] = {
        "case_pages_found": len(
            [p for p in result["case_pages"] if p.get("exists", False)]
        ),
        "case_talk_pages_found": len(result["case_talk_pages"]),
        "total_linked_articles": len(all_linked_articles),
        "articles_fetched": len(result["linked_articles"]),
        "article_talk_pages_found": len(result["article_talk_pages"]),
        "total_revisions": sum(
            p.get("revision_count", len(p.get("revisions", [])))
            for p in (
                result["case_pages"]
                + result["case_talk_pages"]
                + result["linked_articles"]
                + result["article_talk_pages"]
            )
        ),
    }

    return result


def main():
    global logger, _client

    parser = argparse.ArgumentParser(
        description="Depth-first search from arbitration case to collect all related pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/fetch_arb_dfs.py "Climate change"
    python scripts/fetch_arb_dfs.py "Abortion" --max-articles 5
    python scripts/fetch_arb_dfs.py "Macedonia" --dry-run
        """,
    )
    parser.add_argument("case", help="Arbitration case name")
    parser.add_argument(
        "--max-articles",
        type=int,
        default=20,
        help="Maximum linked articles to fetch (default: 20)",
    )
    parser.add_argument(
        "--revision-limit",
        type=int,
        default=100,
        help="Maximum revisions per page (default: 100, 0=all)",
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
        print("Wikipedia Arbitration Case DFS Fetcher")
        print("=" * 50)
        print("\n[DRY RUN] Preview mode - no API calls will be made\n")
        print(f"Case: {args.case}")
        print(f"Prefix: {case_prefix}")
        print("\nWould fetch:")
        for suffix in ARB_SUBPAGES:
            print(f"  • {case_prefix}{suffix}")
            print(f"  • Wikipedia talk:Arbitration/Requests/Case/{args.case}{suffix}")
        print(f"\n  + Up to {args.max_articles} linked articles and their talk pages")
        print(f"  + Up to {revision_limit or 'all'} revisions per page")
        print("\n[DRY RUN] No files written.")
        return

    logger = setup_logging("fetch_arb_dfs")
    logger.info("Wikipedia Arbitration Case DFS Fetcher")
    logger.info("=" * 50)

    check_api_credentials(logger)

    client = WikiClient()
    _client = client

    data = fetch_arb_case_dfs(
        client,
        args.case,
        max_articles=args.max_articles,
        revision_limit=revision_limit,
    )

    # Save output
    safe_name = sanitize_filename(args.case)
    output_path = get_output_path("arbitration", prefix=f"arb_dfs_{safe_name}")
    save_json(data, output_path)

    # Print summary
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    for key, value in data["summary"].items():
        print(f"  {key}: {value}")
    print(f"\n📁 Saved to: {output_path}")

    client.log_stats()
    stats = client.get_stats()
    print(
        f"\n📊 API Stats: {stats['total_requests']} requests in {stats['runtime_minutes']:.1f} min"
    )


if __name__ == "__main__":
    main()
