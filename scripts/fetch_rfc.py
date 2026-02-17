#!/usr/bin/env python3
"""
Fetch all Requests for Comments from Meta-Wiki using latest revision only.
"""

import sys
from pathlib import Path
import time

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from wiki import WikiClient
from src.io import save_json, get_output_path
from dotenv import load_dotenv

RFC_CATEGORIES = [
    "Requests for comments (resolved)",
    "Requests for comments (unsuccessful)",
    "Requests for comments (invalid)",
    "Requests for comments (inactive)",
]

RATE_LIMIT = 0.5  # seconds to sleep between page fetches

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


def fetch_rfc_category(
    client: WikiClient, category: str, limit: int = None, rate_limit: float = RATE_LIMIT
) -> list[dict]:
    """
    Fetch RfCs from a specific category (latest revision only).
    """
    print(f"\nFetching category: {category}")
    pages = client.get_category_pages(category_name=category, limit=limit)
    print(f"  Found {len(pages)} pages")

    rfcs = []

    for i, page in enumerate(pages, 1):
        try:
            last_rev = client.get_latest_revision(page.title())
            if not last_rev:
                continue

            rfc_info = {
                "title": page.title(),
                "page_id": page.pageid,
                "category": category,
                "content": last_rev.get("text", ""),
                "last_revision_user": last_rev.get("user"),
                "last_revision_comment": last_rev.get("comment"),
                "last_revision_timestamp": last_rev.get("timestamp"),
                "url": page.full_url(),
            }
            rfcs.append(rfc_info)

            # Rate limit per page
            if rate_limit:
                time.sleep(rate_limit)

        except Exception as e:
            print(f"    Error fetching {page.title()}: {e}")
            continue

        if i % 50 == 0:
            print(f"    Fetched {i}/{len(pages)} pages")

    return rfcs


def fetch_all_rfcs(
    client: WikiClient, limit_per_category: int = None, rate_limit: float = RATE_LIMIT
) -> dict:
    """
    Fetch all RfCs from all categories (latest revision only).
    """
    all_rfcs = []
    category_counts = {}

    for cat in RFC_CATEGORIES:
        rfcs = fetch_rfc_category(
            client, cat, limit=limit_per_category, rate_limit=rate_limit
        )
        category_counts[cat] = len(rfcs)
        all_rfcs.extend(rfcs)

    return {
        "source": "Meta-Wiki Requests for Comments",
        "fetch_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "categories_fetched": RFC_CATEGORIES,
        "category_counts": category_counts,
        "total_rfcs": len(all_rfcs),
        "rfcs": all_rfcs,
    }


def main():
    """Main execution function."""
    print("=" * 60)
    print("Meta-Wiki Requests for Comments Fetcher (Latest Revision)")
    print("=" * 60)

    # Initialize client for Meta-Wiki
    client = WikiClient(lang="meta", project="meta", use_oauth=True)

    # Fetch all RfCs
    data = fetch_all_rfcs(client)

    # Save to file
    output_path = get_output_path("rfc", prefix="all_requests_for_comments")
    save_json(data, output_path)

    print("\n" + "=" * 60)
    print("SUCCESS: Saved RfCs to file")
    print(f"  Total RfCs: {data['total_rfcs']}")
    print("  By category:")
    for cat, count in data["category_counts"].items():
        print(f"    {cat}: {count}")
    print(f"\n  Output: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
