#!/usr/bin/env python3
"""
Fetch Dispute Resolution Noticeboard (DRN) live + archive cases.

Pulls:
- Live DRN page
- All archive pages sequentially (Archive 1, Archive 2, ...)
- Parses and extracts structured metadata

Compatible with:
- WikiClient (OAuth + rate limiting)
- fetch_all.py CLI
- io.py utilities
"""

import re
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

import mwparserfromhell

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.io import save_json, get_output_path

# Load environment
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

DRN_TITLE = "Wikipedia:Dispute resolution noticeboard"


# ============================================================
# Page Fetching
# ============================================================


def fetch_live_page(client: WikiClient, throttle: float = 0.5) -> dict:
    """
    Fetch latest live DRN page revision.
    """
    print(f"Fetching live page: {DRN_TITLE}")

    rev = client.get_latest_revision(DRN_TITLE)

    if not rev or "text" not in rev:
        raise ValueError("Failed to fetch live DRN page")

    if throttle:
        time.sleep(throttle)

    return {
        "title": DRN_TITLE,
        "fetched_at": datetime.now().isoformat(),
        "content": rev["text"],
        "revision": rev,
    }


def fetch_archive_pages_sequential(
    client: WikiClient, throttle: float = 0.5
) -> list[dict]:
    """
    Fetch DRN archives sequentially: Archive 1, Archive 2, ... until a page does not exist.
    """
    archives = []
    index = 1

    while True:
        title = f"{DRN_TITLE}/Archive {index}"
        print(f"Fetching archive: {title}")

        try:
            rev = client.get_latest_revision(title)
        except Exception:
            # Page does not exist or error; stop
            break

        if not rev or "text" not in rev:
            break

        archives.append(
            {
                "title": title,
                "fetched_at": datetime.now().isoformat(),
                "content": rev["text"],
                "revision": rev,
            }
        )

        index += 1

        if throttle:
            time.sleep(throttle)

    return archives


# ============================================================
# Parsing
# ============================================================


def parse_drn_sections(content: str) -> list[dict]:
    """
    Parse DRN page content into case sections.
    Only returns sections starting at level 2.
    """
    wikicode = mwparserfromhell.parse(content)

    cases = []
    current = None

    for node in wikicode.nodes:
        if isinstance(node, mwparserfromhell.nodes.Heading):
            if current and current["level"] == 2 and len(current["content"]) > 100:
                cases.append(current)

            current = {
                "title": str(node.title).strip(),
                "level": node.level,
                "content": "",
                "templates": [],
                "links": [],
            }

        elif current is not None:
            current["content"] += str(node)

            if isinstance(node, mwparserfromhell.nodes.Template):
                current["templates"].append(str(node.name).strip())

            if isinstance(node, mwparserfromhell.nodes.Wikilink):
                current["links"].append(str(node.title).strip())

    if current and current["level"] == 2 and len(current["content"]) > 100:
        cases.append(current)

    return cases


def extract_case_metadata(cases: list[dict]) -> list[dict]:
    """
    Add structured metadata to cases.
    """
    for case in cases:
        templates_lower = [t.lower() for t in case.get("templates", [])]

        case["status"] = "unknown"

        if any("resolved" in t for t in templates_lower):
            case["status"] = "resolved"
        elif any("active" in t or "open" in t for t in templates_lower):
            case["status"] = "active"
        elif any("closed" in t for t in templates_lower):
            case["status"] = "closed"
        elif any("stale" in t for t in templates_lower):
            case["status"] = "stale"

        signatures = re.findall(r"\[\[User:([^\]|]+)", case["content"])
        case["participants"] = sorted(set(signatures))
        case["participant_count"] = len(case["participants"])

        case["disputed_articles"] = [
            link
            for link in case["links"]
            if not link.startswith(("User:", "Wikipedia:", "Talk:", "User talk:"))
        ][:5]

    return cases


# ============================================================
# Orchestrator
# ============================================================


def fetch_all_drn(client: WikiClient) -> dict:
    """
    Fetch live + archived DRN cases and return full dataset.
    Does NOT write to disk (CLI handles saving).
    """
    live_page = fetch_live_page(client)
    archives = fetch_archive_pages_sequential(client)

    all_cases = []

    # Live cases
    live_cases = extract_case_metadata(parse_drn_sections(live_page["content"]))
    for case in live_cases:
        case["source"] = "live"
    all_cases.extend(live_cases)

    # Archived cases
    for archive in archives:
        cases = extract_case_metadata(parse_drn_sections(archive["content"]))
        for case in cases:
            case["source"] = archive["title"]
        all_cases.extend(cases)

    return {
        "fetched_at": datetime.now().isoformat(),
        "live_page": DRN_TITLE,
        "archive_count": len(archives),
        "case_count": len(all_cases),
        "cases": all_cases,
    }


# ============================================================
# Standalone Execution
# ============================================================


def main():
    print("Fetching DRN (Live + Archives)")
    print("=" * 60)

    client = WikiClient(use_oauth=True)
    data = fetch_all_drn(client)

    print(f"Total cases parsed: {data['case_count']}")

    output_path = get_output_path("drn", prefix="drn_all_cases")
    save_json(data, output_path)

    print(f"Saved to {output_path}")
    print("Done.")


if __name__ == "__main__":
    main()
