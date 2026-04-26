#!/usr/bin/env python3
"""
Fetch Wikipedia Arbitration Committee (ArbCom) case data with throttling.

Retrieves case pages, evidence, and decisions from:
- Wikipedia:Arbitration/Requests/Case/{CaseName}
"""

import sys
from pathlib import Path
from dotenv import load_dotenv
import time

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.io import save_json, get_output_path

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)


def get_arbitration_cases(
    client: WikiClient, limit: int | None = None, sleep_time: float = 1.0
) -> list[dict]:
    """
    Fetch arbitration cases from Wikipedia with throttling.

    Args:
        client: WikiClient instance
        limit: Maximum number of cases to fetch
        sleep_time: Seconds to sleep between page fetches

    Returns:
        List of case dictionaries with title, revisions, and content
    """
    pages = client.get_category_pages("Wikipedia arbitration cases", limit=limit)
    print(f"Found {len(pages)} arbitration pages")

    all_cases = []

    for i, page in enumerate(pages, 1):
        print(f"Fetching {i}/{len(pages)}: {page.title()}")

        case_data = {
            "title": page.title(),
            "url": page.full_url(),
            "last_edit": None,
            "revisions": [],
            "content": None,
        }

        try:
            # Fetch the latest revision only
            latest = client.get_latest_revision(page.title())
            if latest:
                case_data["last_edit"] = latest.get("timestamp", "")
                case_data["revisions"] = [latest]
                case_data["user"] = latest.get("user", "")
                case_data["comment"] = latest.get("comment", "")
                case_data["content"] = latest.get("text", "")
        except Exception as e:
            print(f"  Error fetching {page.title()}: {e}")
            case_data["error"] = str(e)

        all_cases.append(case_data)
        time.sleep(sleep_time)  # Throttle to avoid rate limiting

    return all_cases


def main(limit: int | None = None):
    """Main entry point."""
    print("Fetching Wikipedia Arbitration Cases")
    print("=" * 40)

    client = WikiClient(use_oauth=True)

    cases = get_arbitration_cases(client, limit=limit, sleep_time=1.0)

    output_path = get_output_path("arbitration", prefix="arbitration_cases")
    save_json(cases, output_path)

    print(f"\nSaved {len(cases)} cases to {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch Wikipedia arbitration cases")
    parser.add_argument("--limit", type=int, default=None, help="Max cases to fetch")
    args = parser.parse_args()

    main(limit=args.limit)
