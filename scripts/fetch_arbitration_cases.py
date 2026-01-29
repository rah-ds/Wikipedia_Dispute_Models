#!/usr/bin/env python3
"""
Fetch Wikipedia Arbitration Committee (ArbCom) case data.

Retrieves case pages, evidence, and decisions from:
- Wikipedia:Arbitration/Requests/Case/{CaseName}
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.io import save_json, get_output_path


def get_arbitration_cases(client: WikiClient, limit: int = 100) -> list[dict]:
    """
    Fetch arbitration cases from Wikipedia.

    Args:
        client: WikiClient instance
        limit: Maximum number of cases to fetch

    Returns:
        List of case dictionaries with title, revisions, and content
    """
    pages = client.get_category_pages("Wikipedia arbitration cases", limit=limit)

    cases = []
    for page in pages:
        print(f"Fetching: {page.title()}")

        case_data = {
            "title": page.title(),
            "url": page.full_url(),
            "last_edit": None,
            "revisions": [],
            "content": None,
        }

        try:
            case_data["revisions"] = client.get_revisions(page.title())
            if case_data["revisions"]:
                case_data["last_edit"] = case_data["revisions"][0]["timestamp"]
            case_data["content"] = page.text
        except Exception as e:
            print(f"  Error: {e}")
            case_data["error"] = str(e)

        cases.append(case_data)

    return cases


def main(limit: int = 50):
    """Main entry point."""
    print("Fetching Wikipedia Arbitration Cases")
    print("=" * 40)

    client = WikiClient()
    cases = get_arbitration_cases(client, limit=limit)

    output_path = get_output_path("arbitration", prefix="arbitration_cases")
    save_json(cases, output_path)

    print(f"\nSaved {len(cases)} cases to {output_path}")
    print(f"Total revisions: {sum(len(c['revisions']) for c in cases)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch Wikipedia arbitration cases")
    parser.add_argument("--limit", type=int, default=50, help="Max cases to fetch")
    args = parser.parse_args()

    main(limit=args.limit)


if __name__ == "__main__":
    main()
