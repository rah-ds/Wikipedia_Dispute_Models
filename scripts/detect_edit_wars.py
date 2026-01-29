#!/usr/bin/env python3
"""
Detect edit wars on Wikipedia articles.

Identifies pages with high revert activity by analyzing:
- Edit summary keywords (revert, undo, restore)
- Rapid back-and-forth edits between users
- Page protection status

Usage:
    python detect_edit_wars.py "Article_Name"
    python detect_edit_wars.py "Article_Name" --threshold 0.1
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.analysis import analyze_edit_war
from src.io import save_json, get_output_path, sanitize_filename


def run_analysis(
    client: WikiClient,
    article_title: str,
    lookback: int = 500,
    threshold: float = 0.1,
) -> dict:
    """
    Run edit war analysis on an article.

    Args:
        client: WikiClient instance
        article_title: Wikipedia article title
        lookback: Number of revisions to analyze
        threshold: Revert ratio threshold for flagging

    Returns:
        Dictionary with analysis results
    """
    print(f"Analyzing: {article_title}")

    info = client.get_page_info(article_title)
    revisions = client.get_revisions(article_title, limit=lookback)
    protection = client.get_page_protection(article_title)

    metrics = analyze_edit_war(revisions, threshold=threshold)

    return {
        "title": info["title"],
        "url": info["url"],
        "analyzed_at": datetime.now().isoformat(),
        "protection": protection,
        **metrics,
    }


def print_report(analysis: dict) -> None:
    """Print human-readable report."""
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
    parser = argparse.ArgumentParser(
        description="Detect edit wars on Wikipedia articles"
    )
    parser.add_argument("article", help="Article title to analyze")
    parser.add_argument(
        "--lookback", type=int, default=500, help="Revisions to analyze"
    )
    parser.add_argument("--threshold", type=float, default=0.1, help="Revert threshold")

    args = parser.parse_args()

    client = WikiClient()
    analysis = run_analysis(
        client,
        args.article,
        lookback=args.lookback,
        threshold=args.threshold,
    )

    safe_title = sanitize_filename(args.article)
    output_path = get_output_path("edit_wars", prefix=f"editwar_{safe_title}")
    save_json(analysis, output_path)

    print_report(analysis)
    print(f"\nSaved to {output_path}")


if __name__ == "__main__":
    main()
