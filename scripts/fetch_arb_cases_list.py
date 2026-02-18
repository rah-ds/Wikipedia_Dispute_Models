#!/usr/bin/env python3
"""
Fetch the complete list of Wikipedia arbitration cases from the category page.

This script queries the Wikipedia API to get all pages in the category
"Wikipedia arbitration cases" and extracts the case names.

Usage:
    python scripts/fetch_arb_cases_list.py                    # Print all cases
    python scripts/fetch_arb_cases_list.py --output cases.txt # Save to file
    python scripts/fetch_arb_cases_list.py --count            # Just count cases
"""

import argparse
import sys
from pathlib import Path

import httpx


def fetch_category_members(category: str, cmtype: str = "page") -> list[str]:
    """Fetch all pages in a Wikipedia category using the API.

    Args:
        category: Category name (without "Category:" prefix)
        cmtype: Type of members to fetch ("page", "subcat", "file")

    Returns:
        List of page titles in the category
    """
    api_url = "https://en.wikipedia.org/w/api.php"
    members = []
    cmcontinue = None

    # Wikipedia requires a User-Agent header
    headers = {
        "User-Agent": "WikipediaDisputeModels/1.0 (https://github.com/example/wikipedia-dispute-models; research@example.edu)"
    }

    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmtype": cmtype,
            "cmlimit": 500,  # Max per request
            "format": "json",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        response = httpx.get(api_url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        for member in data.get("query", {}).get("categorymembers", []):
            members.append(member["title"])

        # Check for continuation
        if "continue" in data and "cmcontinue" in data["continue"]:
            cmcontinue = data["continue"]["cmcontinue"]
        else:
            break

    return members


def extract_case_name(page_title: str) -> str | None:
    """Extract the case name from a Wikipedia arbitration page title.

    Args:
        page_title: Full page title like "Wikipedia:Arbitration/Requests/Case/Climate change"

    Returns:
        Case name like "Climate change", or None if not a valid case page
    """
    # Handle different arbitration page formats
    prefixes = [
        "Wikipedia:Arbitration/Requests/Case/",
        "Wikipedia:Requests for arbitration/",
    ]

    for prefix in prefixes:
        if page_title.startswith(prefix):
            return page_title[len(prefix) :]

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Fetch list of Wikipedia arbitration cases from category"
    )
    parser.add_argument(
        "--output", "-o", help="Output file path (default: print to stdout)"
    )
    parser.add_argument(
        "--count", "-c", action="store_true", help="Just print the count of cases"
    )
    parser.add_argument(
        "--makefile", action="store_true", help="Output in Makefile variable format"
    )
    args = parser.parse_args()

    print("Fetching arbitration cases from Wikipedia...", file=sys.stderr)

    # Fetch all pages in the arbitration cases category
    pages = fetch_category_members("Wikipedia_arbitration_cases")

    # Extract case names
    cases = []
    for page in pages:
        case_name = extract_case_name(page)
        if case_name:
            cases.append(case_name)

    # Sort alphabetically
    cases.sort()

    print(f"Found {len(cases)} arbitration cases", file=sys.stderr)

    if args.count:
        print(len(cases))
        return

    if args.makefile:
        # Output in Makefile variable format
        print("ALL_ARB_CASES := \\")
        for i, case in enumerate(cases):
            # Escape quotes for shell
            escaped = case.replace('"', '\\"')
            if i < len(cases) - 1:
                print(f'\t"{escaped}" \\')
            else:
                print(f'\t"{escaped}"')
        return

    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            for case in cases:
                f.write(f"{case}\n")
        print(f"Saved to {output_path}", file=sys.stderr)
    else:
        for case in cases:
            print(case)


if __name__ == "__main__":
    main()
