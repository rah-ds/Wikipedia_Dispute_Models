#!/usr/bin/env python3
"""
Fetch Dispute Resolution Noticeboard (DRN) cases from Wikipedia.

DRN is a volunteer-staffed board for resolving content disputes
before escalation to formal processes.

Source: Wikipedia:Dispute resolution noticeboard
"""

import re
import sys
from datetime import datetime
from pathlib import Path

import mwparserfromhell

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.io import save_json, get_output_path


def fetch_drn_page(client: WikiClient) -> dict:
    """
    Fetch the main DRN page content and metadata.

    Args:
        client: WikiClient instance

    Returns:
        Dictionary with page content and revision history
    """
    page = client.get_page("Wikipedia:Dispute resolution noticeboard")

    if not page.exists():
        raise ValueError("DRN page not found")

    print(f"Fetching: {page.title()}")

    return {
        "title": page.title(),
        "url": page.full_url(),
        "fetched_at": datetime.now().isoformat(),
        "content": page.text,
        "revisions": client.get_revisions(page.title(), limit=100),
    }


def parse_drn_sections(content: str) -> list[dict]:
    """
    Parse DRN page content into individual case sections.

    Args:
        content: Raw wikitext content

    Returns:
        List of case dictionaries
    """
    wikicode = mwparserfromhell.parse(content)

    cases = []
    current_section = None

    for node in wikicode.nodes:
        if isinstance(node, mwparserfromhell.nodes.Heading):
            if current_section and current_section.get("content"):
                cases.append(current_section)

            current_section = {
                "title": str(node.title).strip(),
                "level": node.level,
                "content": "",
                "templates": [],
                "links": [],
            }
        elif current_section is not None:
            current_section["content"] += str(node)

            if isinstance(node, mwparserfromhell.nodes.Template):
                current_section["templates"].append(str(node.name).strip())

            if isinstance(node, mwparserfromhell.nodes.Wikilink):
                current_section["links"].append(str(node.title).strip())

    if current_section and current_section.get("content"):
        cases.append(current_section)

    return cases


def extract_case_metadata(cases: list[dict]) -> list[dict]:
    """Extract structured metadata from parsed cases."""
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

        signatures = re.findall(r"\[\[User:([^\]|]+)", case.get("content", ""))
        case["participants"] = list(set(signatures))
        case["participant_count"] = len(case["participants"])

        article_links = [
            link
            for link in case.get("links", [])
            if not link.startswith(("User:", "Wikipedia:", "Talk:", "User talk:"))
        ]
        case["disputed_articles"] = article_links[:5]

    return cases


def main():
    print("Fetching Dispute Resolution Noticeboard Data")
    print("=" * 50)

    client = WikiClient()
    drn_data = fetch_drn_page(client)

    print("\nParsing cases...")
    cases = parse_drn_sections(drn_data["content"])
    cases = extract_case_metadata(cases)

    # Filter to actual cases (level 2 headings, skip instructions)
    cases = [c for c in cases if c["level"] == 2 and len(c["content"]) > 100]

    drn_data["parsed_cases"] = cases
    drn_data["case_count"] = len(cases)
    del drn_data["content"]  # Remove raw content to reduce file size

    output_path = get_output_path("drn", prefix="drn_cases")
    save_json(drn_data, output_path)

    # Summary
    print(f"\nSaved to {output_path}")
    print(f"Total cases: {len(cases)}")
    print(f"Active: {len([c for c in cases if c['status'] == 'active'])}")
    print(f"Resolved: {len([c for c in cases if c['status'] == 'resolved'])}")


if __name__ == "__main__":
    main()
