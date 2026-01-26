#!/usr/bin/env python3
"""
Fetch complete revision history for a Wikipedia article.

Usage:
    python fetch_revisions.py "Article_Name"
    python fetch_revisions.py "Climate change" --limit 1000
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.io import save_json, get_output_path, sanitize_filename


def fetch_revisions(
    client: WikiClient,
    article_title: str,
    include_talk: bool = True,
    limit: int | None = None,
) -> dict:
    """
    Fetch revision history for an article and optionally its talk page.

    Args:
        client: WikiClient instance
        article_title: Wikipedia article title
        include_talk: Whether to include talk page revisions
        limit: Maximum revisions to fetch (None = all)

    Returns:
        Dictionary with article and talk page revision data
    """
    info = client.get_page_info(article_title)

    data = {
        "article": {
            "title": info["title"],
            "url": info["url"],
            "revisions": client.get_revisions(article_title, limit=limit),
        },
        "talk": None,
        "fetched_at": datetime.now().isoformat(),
    }

    print(f"Fetched {len(data['article']['revisions'])} revisions for {info['title']}")

    if include_talk:
        talk = client.get_talk_page(article_title)
        if talk:
            data["talk"] = {
                "title": talk.title(),
                "url": talk.full_url(),
                "revisions": client.get_revisions(talk.title(), limit=limit),
            }
            print(f"Fetched {len(data['talk']['revisions'])} talk page revisions")

    return data


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Wikipedia article revision history"
    )
    parser.add_argument("article", help="Article title to fetch")
    parser.add_argument("--no-talk", action="store_true", help="Skip talk page")
    parser.add_argument("--limit", type=int, default=None, help="Max revisions")

    args = parser.parse_args()

    print("Fetching Wikipedia Revision History")
    print("=" * 40)

    client = WikiClient()
    data = fetch_revisions(
        client,
        args.article,
        include_talk=not args.no_talk,
        limit=args.limit,
    )

    safe_title = sanitize_filename(args.article)
    output_path = get_output_path("revisions", prefix=safe_title)
    save_json(data, output_path)

    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
