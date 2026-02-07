#!/usr/bin/env python3
"""
Fetch Requests for Comment (RfC) cases from Wikipedia.

Pulls active and archived RfCs from multiple sources:
  - Active: 14 topic listing pages maintained by Legobot (flat link+template format)
  - Archived: Main User Conduct wikitable, sub-archives 1-8 (mixed wikitable/bullet),
    and AllPages master listing (~700+ individual case pages)

Entries are deduplicated across archive sources. A manual limit controls
how many entries are collected per mode.

How to call the file (mode is the considered status of RfC):
    python fetch_rfc_cases.py                          # Active RfCs, default limit
    python fetch_rfc_cases.py --mode active --limit 20
    python fetch_rfc_cases.py --mode archived --limit 50
    python fetch_rfc_cases.py --mode both --limit 30
"""

import re
import sys
import argparse
from datetime import datetime
from pathlib import Path

import mwparserfromhell

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.io import save_json, get_output_path

# ---------------------------------------------------------------------------
# Page Definitions
# ---------------------------------------------------------------------------

# Topic subpages where Legobot lists active RfCs.
# Each page covers a subject area and uses a flat format:
#   '''[[Talk:Article#rfc_ID|Display]]'''
#   {{rfcquote|text=...}}
RFC_ACTIVE_PAGES = [
    "Wikipedia:Requests for comment/Biographies",
    "Wikipedia:Requests for comment/Economy, trade, and companies",
    "Wikipedia:Requests for comment/History and geography",
    "Wikipedia:Requests for comment/Language and linguistics",
    "Wikipedia:Requests for comment/Mathematics, science, and technology",
    "Wikipedia:Requests for comment/Media, the arts, and architecture",
    "Wikipedia:Requests for comment/Politics, government, and law",
    "Wikipedia:Requests for comment/Religion and philosophy",
    "Wikipedia:Requests for comment/Society, sports, and culture",
    "Wikipedia:Requests for comment/Wikipedia policies and guidelines",
    "Wikipedia:Requests for comment/Wikipedia proposals",
    "Wikipedia:Requests for comment/Wikipedia information pages and essays",
    "Wikipedia:Requests for comment/Wikipedia style and naming",
    "Wikipedia:Requests for comment/Wikipedia templates, categories, and WikiProjects",
]

# Main archive page for closed User Conduct RfCs (wikitable format).
# Also links to numbered sub-archives (Archive 1-8) covering 2004-2012.
RFC_ARCHIVE_PAGES = [
    "Wikipedia:Requests for comment/User conduct/Archive",
]

# Master listing of all individual RfC case pages ever created.
# Numbered list format: # [[:Wikipedia:Requests for comment/Name]]
RFC_ALLPAGES = "Wikipedia:Request for comments/AllPages"

# ---------------------------------------------------------------------------
# Page Fetching
# ---------------------------------------------------------------------------


def fetch_rfc_listing_page(client: WikiClient, page_title: str) -> dict | None:
    """
    Fetch a single RfC listing page and return its content with metadata.

    Args:
        client: WikiClient instance
        page_title: Full page title to fetch

    Returns:
        Dictionary with page content and metadata, or None if page not found
    """
    page = client.get_page(page_title)

    if not page.exists():
        print(f"  WARNING: Page not found: {page_title}")
        return None

    return {
        "title": page.title(),
        "url": page.full_url(),
        "content": page.text,
    }


# ---------------------------------------------------------------------------
# Parsers — each handles a different wikitext format
# ---------------------------------------------------------------------------


def parse_rfc_entries_from_listings(content: str, source_page: str) -> list[dict]:
    """
    Parse active RfC listing pages populated by Legobot.

    These pages use a flat structure with no headings:
        '''[[Talk:Some Article#rfc_ID|Talk:Some Article]]'''
        {{rfcquote|text=Should we include X? ~~~~}}

    We iterate over all {{rfcquote}} templates and look backwards in the
    raw text to find the bold talk-page link that precedes each one.

    Args:
        content: Raw wikitext content of the listing page
        source_page: Title of the source listing page

    Returns:
        List of parsed RfC entry dictionaries
    """
    wikicode = mwparserfromhell.parse(content)
    templates = wikicode.filter_templates()

    raw_text = str(wikicode)
    entries = []

    for tmpl in templates:
        # Only process rfcquote templates
        if str(tmpl.name).strip().lower() != "rfcquote":
            continue

        # Extract the quote text from the template parameter
        quote_text = ""
        if tmpl.has("text"):
            quote_text = str(tmpl.get("text").value).strip()

        # Look backwards in raw text to find the bold talk-page link
        # that immediately precedes this template
        tmpl_pos = raw_text.find(str(tmpl))
        preceding = raw_text[:tmpl_pos] if tmpl_pos > 0 else ""

        # Match: '''[[Talk:Something#rfc_ID|Display Text]]'''
        link_match = re.search(
            r"'''\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]'''",
            preceding[max(0, len(preceding) - 500) :],
        )

        talk_page = ""
        display_title = ""
        if link_match:
            talk_page = link_match.group(1).strip()
            display_title = (link_match.group(2) or talk_page).strip()

        # Extract participants from User: links in the quote
        participants = list(set(re.findall(r"\[\[User:([^\]|]+)", quote_text)))

        # Extract article links (excluding user/meta namespaces)
        quote_links = re.findall(r"\[\[([^\]|]+)", quote_text)
        article_links = [
            link
            for link in quote_links
            if not link.startswith(
                ("User:", "User talk:", "Wikipedia:", "Talk:", "Special:")
            )
        ]

        # Try to find the earliest timestamp in the quote
        ts_match = re.search(
            r"(\d{2}:\d{2},\s+\d+\s+\w+\s+\d{4}\s+\(UTC\))",
            quote_text,
        )

        # Derive the article title from the talk page link
        # e.g. "Talk:Barry Keoghan#rfc_7C6FF4B" -> "Barry Keoghan"
        article_title = ""
        if talk_page:
            article_title = re.sub(r"#.*$", "", talk_page)
            article_title = re.sub(r"^Talk:", "", article_title)

        entries.append(
            {
                "title": display_title or article_title,
                "article": article_title,
                "talk_page": talk_page.split("#")[0] if talk_page else "",
                "rfc_id": talk_page.split("#")[-1] if "#" in talk_page else "",
                "level": 2,
                "content": quote_text,
                "templates": ["rfcquote"],
                "links": article_links[:10],
                "source_page": source_page,
                "participants": participants,
                "participant_count": len(participants),
                "earliest_timestamp": ts_match.group(1) if ts_match else None,
                "status": "active",
            }
        )

    return entries


def parse_rfc_archive_table(content: str, source_page: str) -> list[dict]:
    """
    Parse archive pages that use a wikitable format.

    Two column layouts exist:
        4 columns (main archive):    Name | Date | Description | Notes
        5 columns (sub-archives 2-8): Name | Date | Description | Certifiers | Notes

    We split on row delimiters (|-) and then split cells on || or newline-|.

    Args:
        content: Raw wikitext content of the archive page
        source_page: Title of the source archive page

    Returns:
        List of parsed RfC entry dictionaries
    """
    entries = []

    # Split on wikitable row delimiters
    rows = re.split(r"^\|\-", content, flags=re.MULTILINE)

    for row in rows:
        # Split cells by || (inline) or newline-| (block)
        cells = re.split(r"\|\||\n\|", row.strip())
        cells = [c.strip() for c in cells if c.strip()]

        # Skip header rows, comment rows, and rows with too few cells
        if len(cells) < 3:
            continue
        if cells[0].startswith("!") or cells[0].startswith("<!--"):
            continue

        name_cell = cells[0]
        date_cell = cells[1] if len(cells) > 1 else ""
        desc_cell = cells[2] if len(cells) > 2 else ""

        # Archives 2-8 have 5 columns: Name|Date|Description|Certifiers|Notes
        # Main archive has 4 columns: Name|Date|Description|Notes
        if len(cells) >= 5:
            certifiers_cell = cells[3]
            notes_cell = cells[4]
        else:
            certifiers_cell = ""
            notes_cell = cells[3] if len(cells) > 3 else ""

        # Extract the case page link from the name cell
        # Format: [[Wikipedia:Requests for comment/Case Name|Case Name]]
        link_match = re.search(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]", name_cell)
        if not link_match:
            continue

        case_page = link_match.group(1).strip()
        case_name = (link_match.group(2) or case_page.split("/")[-1]).strip()

        # Extract user links from description, certifiers, and notes
        combined_text = f"{desc_cell} {certifiers_cell} {notes_cell}"
        participants = list(set(re.findall(r"\[\[User:([^\]|]+)", combined_text)))

        entries.append(
            {
                "title": case_name,
                "case_page": case_page,
                "level": 2,
                "start_date": date_cell.strip(),
                "description": desc_cell.strip(),
                "certifiers": certifiers_cell.strip(),
                "notes": notes_cell.strip(),
                "content": combined_text,
                "templates": [],
                "links": [case_page],
                "source_page": source_page,
                "participants": participants,
                "participant_count": len(participants),
                "status": "archived",
                "topic_category": "User conduct",
            }
        )

    return entries


def discover_rfc_sub_archives(content: str) -> list[str]:
    """
    Extract links to numbered sub-archive pages from the main archive page.

    Only discovers Archive 1-8 under User Conduct. The older
    "Conflicts between users/archive1" page uses a pre-RfC format
    that is not supported and is intentionally excluded.

    Args:
        content: Raw wikitext of the main archive page

    Returns:
        List of sub-archive page titles
    """
    sub_archives = re.findall(
        r"\[\[(Wikipedia:Requests for comment/User conduct/Archive \d+)[|\]]",
        content,
    )
    return sub_archives


def parse_rfc_sub_archive(content: str, source_page: str) -> list[dict]:
    """
    Parse sub-archive pages that use a bullet-list format (Archive 1).

    Format:
        *[[Wikipedia:Requests for comment/Name]] Description text. Timestamp
        *[[Wikipedia:Requests for comment/Name|Display]] Description.

    Args:
        content: Raw wikitext content of the sub-archive page
        source_page: Title of the source sub-archive page

    Returns:
        List of parsed RfC entry dictionaries
    """
    entries = []

    for line in content.split("\n"):
        line = line.strip()
        if not line.startswith("*"):
            continue

        # Look for an RfC case link on this line
        link_match = re.search(
            r"\[\[(?::)?(Wikipedia:Requests for comment/([^\]|]+?))"
            r"(?:\|([^\]]+?))?\]\]",
            line,
        )
        if not link_match:
            continue

        full_page = link_match.group(1).strip()
        case_slug = link_match.group(2).strip()
        display = (link_match.group(3) or case_slug).strip()

        # Skip meta/process pages that aren't actual cases
        if any(
            skip in case_slug.lower()
            for skip in (
                "user conduct",
                "archive",
                "guidance",
                "userslist",
                "creation",
                "assistance",
                "/all",
                "user names",
            )
        ):
            continue

        # Everything after the closing ]] is the description
        after_link = line[link_match.end() :].strip()
        description = re.sub(r"^[.\s*]+", "", after_link).strip()

        entries.append(
            {
                "title": display,
                "case_page": full_page,
                "level": 2,
                "start_date": "",
                "description": description,
                "notes": "",
                "content": description,
                "templates": [],
                "links": [full_page],
                "source_page": source_page,
                "participants": [],
                "participant_count": 0,
                "status": "archived",
                "topic_category": "User conduct",
            }
        )

    return entries


def parse_rfc_allpages(content: str, source_page: str) -> list[dict]:
    """
    Parse the AllPages master listing of all RfC case pages.

    This is a simple numbered list of every individual RfC page:
        # [[:Wikipedia:Requests for comment/Name]]
        # [[:Wikipedia:Requests for comment/Name]]

    Many of these overlap with entries already found in the sub-archives.
    Deduplication is handled by the caller.

    Args:
        content: Raw wikitext content of the AllPages page
        source_page: Title of the AllPages page

    Returns:
        List of parsed RfC entry dictionaries
    """
    entries = []

    for line in content.split("\n"):
        line = line.strip()
        if not line.startswith("#"):
            continue

        # Match RfC case page links
        link_match = re.search(
            r"\[\[(?::)?(Wikipedia:Requests for comment/([^\]|]+?))"
            r"(?:\|([^\]]+?))?\]\]",
            line,
        )
        if not link_match:
            continue

        full_page = link_match.group(1).strip()
        case_slug = link_match.group(2).strip()
        display = (link_match.group(3) or case_slug).strip()

        # Skip meta/process/index pages that aren't actual cases
        if any(
            skip in case_slug.lower()
            for skip in (
                "user conduct",
                "archive",
                "guidance",
                "userslist",
                "creation",
                "assistance",
                "/all",
                "user names",
                "index",
                "allpages",
            )
        ):
            continue

        entries.append(
            {
                "title": display,
                "case_page": full_page,
                "level": 2,
                "start_date": "",
                "description": "",
                "notes": "",
                "content": "",
                "templates": [],
                "links": [full_page],
                "source_page": source_page,
                "participants": [],
                "participant_count": 0,
                "status": "archived",
                "topic_category": "User conduct",
            }
        )

    return entries


# ---------------------------------------------------------------------------
# Metadata Extraction (used by active RfC entries)
# ---------------------------------------------------------------------------


def extract_rfc_metadata(entries: list[dict]) -> list[dict]:
    """
    Extract structured metadata from parsed RfC entries.

    Pulls out status, participants, discussed pages, and timestamps
    from the raw wikitext content of each entry.

    Args:
        entries: List of parsed entry dictionaries from parse_rfc_entries

    Returns:
        Same list with added metadata fields
    """
    for entry in entries:
        templates_lower = [t.lower() for t in entry.get("templates", [])]

        # Determine status from templates
        entry["status"] = "unknown"
        if any("rfctag" in t or "rfc" == t for t in templates_lower):
            entry["status"] = "active"
        if any("resolved" in t or "closed" in t for t in templates_lower):
            entry["status"] = "resolved"
        if any("stale" in t for t in templates_lower):
            entry["status"] = "stale"

        # Extract participants from User: signatures
        signatures = re.findall(r"\[\[User:([^\]|]+)", entry.get("content", ""))
        entry["participants"] = list(set(signatures))
        entry["participant_count"] = len(entry["participants"])

        # Extract discussed article/page links (filter out user/meta pages)
        article_links = [
            link
            for link in entry.get("links", [])
            if not link.startswith(
                ("User:", "User talk:", "Wikipedia:", "Talk:", "Special:")
            )
        ]
        entry["discussed_pages"] = article_links[:10]

        # Extract topic category from source page title
        source = entry.get("source_page", "")
        if "/" in source:
            entry["topic_category"] = source.split("/")[-1]
        else:
            entry["topic_category"] = "unknown"

        # Try to extract a timestamp from entry content
        ts_match = re.search(
            r"(\d{2}:\d{2},\s+\d+\s+\w+\s+\d{4}\s+\(UTC\))",
            entry.get("content", ""),
        )
        entry["earliest_timestamp"] = ts_match.group(1) if ts_match else None

    return entries


# ---------------------------------------------------------------------------
# Fetchers — orchestrate page fetching and parsing
# ---------------------------------------------------------------------------


def fetch_active_rfcs(
    client: WikiClient,
    limit: int | None = None,
) -> dict:
    """
    Fetch currently active RfCs from all topic listing pages.

    Scans each of the 14 topic subpages, parses the Legobot-maintained
    flat listing format, and collects entries up to the limit.

    Args:
        client: WikiClient instance
        limit: Maximum total RfC entries to collect (None = no limit)

    Returns:
        Dictionary with fetched RfC data and metadata
    """
    print("Fetching active RfCs...")
    print(f"  Limit: {limit or 'no limit'}")
    print(f"  Topic pages to scan: {len(RFC_ACTIVE_PAGES)}")

    all_entries = []
    pages_fetched = 0

    for page_title in RFC_ACTIVE_PAGES:
        if limit and len(all_entries) >= limit:
            print(f"  Reached limit of {limit}, stopping.")
            break

        short_name = page_title.split("/")[-1]
        print(f"  Fetching: {short_name}...")

        page_data = fetch_rfc_listing_page(client, page_title)
        if not page_data:
            continue

        pages_fetched += 1
        entries = parse_rfc_entries_from_listings(page_data["content"], page_title)

        # Tag each entry with its topic category
        for e in entries:
            e["topic_category"] = page_title.split("/")[-1]

        # Apply remaining limit
        if limit:
            remaining = limit - len(all_entries)
            entries = entries[:remaining]

        print(f"    Found {len(entries)} entries")
        all_entries.extend(entries)

    return {
        "fetch_type": "active",
        "fetched_at": datetime.now().isoformat(),
        "pages_scanned": pages_fetched,
        "total_pages_available": len(RFC_ACTIVE_PAGES),
        "entry_count": len(all_entries),
        "limit_applied": limit,
        "entries": all_entries,
    }


def fetch_archived_rfcs(
    client: WikiClient,
    limit: int | None = None,
    include_sub_archives: bool = True,
    include_allpages: bool = True,
) -> dict:
    """
    Fetch archived/closed RfCs from all known archive sources.

    Three sources are fetched in order, with deduplication across all:
        1. Main User Conduct archive — wikitable with 4 columns (2013-2014)
        2. Sub-archives 1-8 — Archive 1 is bullet-list (2004-2007),
           Archives 2-8 are wikitables with 5 columns (2005-2012)
        3. AllPages master listing — numbered list of every RfC page ever

    Args:
        client: WikiClient instance
        limit: Maximum total RfC entries to collect (None = no limit)
        include_sub_archives: Whether to fetch numbered sub-archives
        include_allpages: Whether to fetch the AllPages master listing

    Returns:
        Dictionary with fetched archived RfC data and metadata
    """
    print("Fetching archived RfCs...")
    print(f"  Limit: {limit or 'no limit'}")

    all_entries = []
    seen_pages = set()  # Track case_page values to deduplicate across sources
    pages_fetched = 0

    # --- Source 1: Main archive page (wikitable, 4 columns) ---
    pages_to_fetch = []

    for page_title in RFC_ARCHIVE_PAGES:
        page_data = fetch_rfc_listing_page(client, page_title)
        if not page_data:
            continue

        pages_fetched += 1
        entries = parse_rfc_archive_table(page_data["content"], page_title)

        # Add entries, tracking seen pages for dedup
        for e in entries:
            key = e.get("case_page", e["title"])
            if key not in seen_pages:
                seen_pages.add(key)
                all_entries.append(e)

        print(f"  Main archive: {len(entries)} entries")

        # Discover numbered sub-archive pages linked from the main archive
        if include_sub_archives:
            sub_archives = discover_rfc_sub_archives(page_data["content"])
            print(f"  Found {len(sub_archives)} sub-archive pages")
            pages_to_fetch.extend(sub_archives)

    # --- Source 2: Sub-archives (mixed formats) ---
    for page_title in pages_to_fetch:
        if limit and len(all_entries) >= limit:
            print(f"  Reached limit of {limit}, stopping.")
            break

        short_name = page_title.split("/")[-1]
        print(f"  Fetching sub-archive: {short_name}...")

        page_data = fetch_rfc_listing_page(client, page_title)
        if not page_data:
            continue

        pages_fetched += 1

        # Auto-detect format: wikitable (Archives 2-8) vs bullet list (Archive 1)
        if '{| class="wikitable"' in page_data["content"]:
            entries = parse_rfc_archive_table(page_data["content"], page_title)
        else:
            entries = parse_rfc_sub_archive(page_data["content"], page_title)

        # Deduplicate against previously seen entries
        new_entries = []
        for e in entries:
            key = e.get("case_page", e["title"])
            if key not in seen_pages:
                seen_pages.add(key)
                new_entries.append(e)

        if limit:
            remaining = limit - len(all_entries)
            new_entries = new_entries[:remaining]

        print(f"    Found {len(new_entries)} new entries")
        all_entries.extend(new_entries)

    # --- Source 3: AllPages master listing (catches anything missed above) ---
    if include_allpages:
        if not (limit and len(all_entries) >= limit):
            print("  Fetching AllPages master listing...")

            page_data = fetch_rfc_listing_page(client, RFC_ALLPAGES)
            if page_data:
                pages_fetched += 1
                entries = parse_rfc_allpages(page_data["content"], RFC_ALLPAGES)

                # Deduplicate — many AllPages entries overlap with sub-archives
                new_entries = []
                for e in entries:
                    key = e.get("case_page", e["title"])
                    if key not in seen_pages:
                        seen_pages.add(key)
                        new_entries.append(e)

                if limit:
                    remaining = limit - len(all_entries)
                    new_entries = new_entries[:remaining]

                print(f"    Found {len(new_entries)} new entries (after dedup)")
                all_entries.extend(new_entries)

    return {
        "fetch_type": "archived",
        "fetched_at": datetime.now().isoformat(),
        "pages_scanned": pages_fetched,
        "entry_count": len(all_entries),
        "unique_case_pages": len(seen_pages),
        "limit_applied": limit,
        "sources": {
            "main_archive": [p for p in RFC_ARCHIVE_PAGES],
            "sub_archives_included": include_sub_archives,
            "allpages_included": include_allpages,
        },
        "entries": all_entries,
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Fetch Requests for Comment (RfC) cases from Wikipedia"
    )
    parser.add_argument(
        "--mode",
        choices=["active", "archived", "both"],
        default="active",
        help="Which RfCs to fetch (default: active)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum entries to fetch per mode (default: 50)",
    )

    args = parser.parse_args()

    print("Fetching Requests for Comment (RfC) Data")
    print("=" * 50)

    client = WikiClient()

    # --- Active: scan Legobot topic pages for open RfCs ---
    if args.mode in ("active", "both"):
        active_data = fetch_active_rfcs(client, limit=args.limit)

        output_path = get_output_path("rfc", prefix="rfc_active")
        save_json(active_data, output_path)

        print(f"\nActive RfCs saved to {output_path}")
        print(f"  Total entries: {active_data['entry_count']}")

    # --- Archived: pull from wikitables, bullet lists, and AllPages ---
    if args.mode in ("archived", "both"):
        archived_data = fetch_archived_rfcs(client, limit=args.limit)

        output_path = get_output_path("rfc", prefix="rfc_archived")
        save_json(archived_data, output_path)

        print(f"\nArchived RfCs saved to {output_path}")
        print(f"  Total entries: {archived_data['entry_count']}")

    # --- Summary ---
    print("\n" + "=" * 50)
    if args.mode in ("active", "both"):
        by_topic = {}
        for e in active_data["entries"]:
            cat = e.get("topic_category", "unknown")
            by_topic[cat] = by_topic.get(cat, 0) + 1
        print("Active RfCs by topic:")
        for topic, count in sorted(by_topic.items(), key=lambda x: -x[1]):
            print(f"  {topic}: {count}")

    if args.mode in ("archived", "both"):
        by_status = {}
        for e in archived_data["entries"]:
            s = e.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
        print("Archived RfCs by status:")
        for status, count in sorted(by_status.items(), key=lambda x: -x[1]):
            print(f"  {status}: {count}")


if __name__ == "__main__":
    main()
