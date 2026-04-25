#!/usr/bin/env python3
"""
Fetch revision history and edit-war analysis for all arbitration case articles.

This script extends the 51-article sample in sample_articles.yaml to the full
~330+ arbitration case corpus.  For each case it:
  1. Determines the primary disputed article(s) – first by reading
     arb_dfs_*.json files (if present), then falling back to the case name.
  2. Skips pure editor-conduct cases (IPs, usernames, "X and Y" names).
  3. Skips articles already present in data/raw/revisions/ and
     data/raw/edit_wars/ (fully idempotent).
  4. Calls fetch_revisions() + analyze_article_edit_war() for each article.

Usage (run from project root, with venv activated):

    # Dry-run – see what would be fetched without hitting the API
    python scripts/fetch_arb_revisions.py --dry-run

    # Full run (can take several hours for the complete corpus)
    python scripts/fetch_arb_revisions.py

    # Re-fetch even if files already exist
    python scripts/fetch_arb_revisions.py --force

    # Limit to first N articles (useful for testing)
    python scripts/fetch_arb_revisions.py --limit 20

    # Progress emails (Rivanna SMTP relay)
    python scripts/fetch_arb_revisions.py --notify-email you@virginia.edu

Rivanna SLURM example:
    sbatch scripts/slurm/fetch_arb_revisions.slurm
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import signal
import smtplib
import sys
import time
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.fetchers import fetch_revisions, analyze_article_edit_war
from src.io import (
    DATA_DIR,
    check_api_credentials,
    get_output_path,
    sanitize_filename,
    save_json,
    setup_logging,
)
from src.wiki import WikiClient

env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARB_RAW_DIR = DATA_DIR / "raw" / "arbitration"
REVISIONS_DIR = DATA_DIR / "raw" / "revisions"
EDITWARS_DIR = DATA_DIR / "raw" / "edit_wars"

REVISION_LIMIT = 500  # revisions per article

# Rivanna email relay
_SMTP_HOST = "out.mail.virginia.edu"
_SMTP_PORT = 25
_SENDER = "rah5ff@virginia.edu"

# Globals for graceful shutdown
_client: WikiClient | None = None
_logger: logging.Logger | None = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def is_editor_case(case_name: str) -> bool:
    """
    Return True if the arb case appears to be an editor-conduct case
    rather than an article-content dispute.

    Note: When arb_dfs_*.json files are present (as on Rivanna), article
    candidates come from their 'disputed_articles' field which is accurate.
    These heuristics are only the fallback for when DFS data is absent.

    Heuristics:
    - Bare IP address        (e.g. "168.209.97.34")
    - Obfuscated IP range    (e.g. "194x144x90x118")
    - Starts with punctuation (e.g. "-Ril-")
    - Starts with a digit    (e.g. "8bitJake") — real articles start uppercase
    - "X and Y" pattern      (e.g. "Abd and JzG") – two editors
    - Pure numeric id        (e.g. "172", "172 2")
    - Repeat-case suffix     (e.g. "Betacommand 3", "American politics 2")
      when the base name is not a recognisable topic keyword
    """
    name = case_name.strip()

    # Starts with a non-alphabetic character (e.g. -Ril-)
    if name and not name[0].isalpha():
        return True

    # IP address
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", name):
        return True

    # Obfuscated IP (e.g. 194x144x90x118)
    if re.fullmatch(r"\d{1,3}[x.]\d{1,3}[x.]\d{1,3}[x.]\d{1,3}", name):
        return True

    # "Editor1 and Editor2" — conduct case involving two users
    if re.search(r"\band\b", name, re.IGNORECASE) and len(name.split()) <= 6:
        return True

    # Numeric case identifier like "172" or "172 2"
    if re.fullmatch(r"\d+( \d+)?", name):
        return True

    # "Topic N" pattern — repeated cases about the same user/topic where N >= 2.
    # Real multi-part article titles rarely end with a bare digit.
    # Examples: "Betacommand 3", "American politics 2", "Armenia-Azerbaijan 3"
    if re.search(r"\s+[2-9]$", name):
        return True

    # "X vs. Y" or "X versus Y" — almost always two editors in a dispute
    if re.search(r"\bvs?\.?\s+\w", name, re.IGNORECASE):
        return True

    # CamelCase single token (no spaces, lowercase letter immediately followed by
    # uppercase letter): "AlisonW", "AndriyK", "ArmchairVexillologistDon", "BigDaddy777"
    # All-caps acronyms (ADHD, BJAODN) and plain Title-case (Abortion) are fine.
    if " " not in name and re.search(r"[a-z][A-Z]", name):
        return True

    # Username ending in bare digits (e.g. "Boothy443", "Carlossuarez46").
    # Real article names that end in digits almost always use a hyphen (COVID-19).
    if re.search(r"[a-zA-Z]\d+$", name) and "-" not in name and "/" not in name:
        return True

    return False


def get_arb_dfs_articles(dfs_path: Path) -> list[str]:
    """Extract disputed article titles from an arb_dfs JSON file."""
    with open(dfs_path) as f:
        data = json.load(f)
    articles = data.get("disputed_articles") or data.get("articles") or []
    return [a for a in articles if a and not a.startswith("Wikipedia")]


def load_article_candidates() -> list[str]:
    """
    Build a deduplicated list of Wikipedia article titles to fetch.

    Priority order:
    1. arb_dfs_*.json files  – contain accurate 'disputed_articles' lists
    2. Individual case JSON files  (e.g. Gamergate.json)
    3. Fall back to case name from arbitration_cases_*.json index
    """
    candidates: dict[str, str] = {}  # title → source

    # --- Source 1: arb_dfs files -------------------------------------------
    dfs_files = sorted(ARB_RAW_DIR.glob("arb_dfs_*.json"))
    for dfs_path in dfs_files:
        try:
            articles = get_arb_dfs_articles(dfs_path)
            for article in articles:
                if article not in candidates:
                    candidates[article] = f"dfs:{dfs_path.name}"
        except Exception:
            pass

    # --- Source 2: individual case JSON files (one JSON per case name) ------
    case_json_files = [
        p
        for p in ARB_RAW_DIR.glob("*.json")
        if not p.name.startswith("arbitration_cases_")
        and not p.name.startswith("arb_dfs_")
        and not p.name.endswith(".Zone.Identifier")
    ]
    for case_path in case_json_files:
        case_name = case_path.stem  # e.g. "Gamergate"
        if not is_editor_case(case_name) and case_name not in candidates:
            candidates[case_name] = f"case_file:{case_path.name}"

    # --- Source 3: arbitration_cases index (most recent file) ---------------
    index_files = sorted(
        ARB_RAW_DIR.glob("arbitration_cases_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    # filter out .Zone.Identifier sidecars
    index_files = [p for p in index_files if not p.name.endswith(".Zone.Identifier")]
    if index_files:
        with open(index_files[0]) as f:
            index_data = json.load(f)
        for item in index_data:
            case_name = item["title"].split("/")[-1]
            if not is_editor_case(case_name) and case_name not in candidates:
                candidates[case_name] = "index"

    return list(candidates.keys())


def already_fetched(title: str) -> bool:
    """Return True if both revisions and edit-war files exist for this title."""
    safe = sanitize_filename(title)
    rev_files = (
        list(REVISIONS_DIR.glob(f"{safe}_*.json")) if REVISIONS_DIR.exists() else []
    )
    ew_files = (
        list(EDITWARS_DIR.glob(f"editwar_{safe}_*.json"))
        if EDITWARS_DIR.exists()
        else []
    )
    return bool(rev_files) and bool(ew_files)


def send_milestone_email(
    notify_email: str,
    completed: int,
    total: int,
    failed: list[tuple[str, str]],
    skipped: int,
    start_time: float,
) -> None:
    """Send a progress email at 25 / 50 / 75 % milestones."""
    if not notify_email:
        return
    pct = int(completed / total * 100) if total else 0
    elapsed = time.time() - start_time
    elapsed_fmt = time.strftime("%H:%M:%S", time.gmtime(elapsed))
    remaining = (elapsed / completed * (total - completed)) if completed else 0
    remaining_fmt = time.strftime("%H:%M:%S", time.gmtime(remaining))

    lines = [
        "Wikipedia Dispute Models — fetch_arb_revisions Progress",
        "=" * 53,
        "",
        f"Job ID:        {os.environ.get('SLURM_JOB_ID', 'local')}",
        f"Host:          {os.environ.get('HOSTNAME', 'unknown')}",
        f"Progress:      {pct}% — {completed} of {total} articles done",
        f"Elapsed:       {elapsed_fmt}",
        f"Est. remaining: ~{remaining_fmt}",
        "",
        f"Completed:     {completed}",
        f"Skipped:       {skipped} (already existed)",
        f"Failed:        {len(failed)}",
    ]
    if failed:
        lines += ["", "Recent errors:"]
        for name, err in failed[-5:]:
            lines.append(f"  - {name}: {err}")

    subject = f"[Rivanna] fetch_arb_revisions — {pct}% ({completed}/{total})"
    body = "\n".join(lines)
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = _SENDER
        msg["To"] = notify_email
        with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as s:
            s.sendmail(_SENDER, [notify_email], msg.as_string())
    except Exception:
        pass  # never crash the job for a notification failure


# ---------------------------------------------------------------------------
# Shutdown handler
# ---------------------------------------------------------------------------


def shutdown_handler(signum, frame):
    print("\n\n⚠️  Interrupted! Logging stats before exit...")
    if _client:
        _client.log_stats()
        stats = _client.get_stats()
        print(
            f"API Stats: {stats['total_requests']} requests in "
            f"{stats['runtime_minutes']:.1f} min"
        )
    sys.exit(130)


signal.signal(signal.SIGINT, shutdown_handler)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    global _client, _logger

    parser = argparse.ArgumentParser(
        description="Batch-fetch revisions & edit-war data for arb case articles"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be fetched without making API calls",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch even if files already exist",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after fetching N articles (useful for testing)",
    )
    parser.add_argument(
        "--revision-limit",
        type=int,
        default=REVISION_LIMIT,
        metavar="N",
        help=f"Max revisions per article (default: {REVISION_LIMIT})",
    )
    parser.add_argument(
        "--notify-email",
        default=os.environ.get("NOTIFY_EMAIL", ""),
        help="Email address for milestone progress reports",
    )
    args = parser.parse_args()

    # ---- Discover candidate articles --------------------------------------
    print("Discovering article candidates from arb data...")
    all_candidates = load_article_candidates()
    print(f"  Found {len(all_candidates)} article candidates")

    # ---- Filter already-fetched -------------------------------------------
    if args.dry_run:
        to_fetch = all_candidates
    elif args.force:
        to_fetch = all_candidates
    else:
        to_fetch = [a for a in all_candidates if not already_fetched(a)]
        skipped_count = len(all_candidates) - len(to_fetch)
        if skipped_count:
            print(
                f"  Skipping {skipped_count} already-fetched articles "
                f"(use --force to re-fetch)"
            )

    # ---- Apply --limit ----------------------------------------------------
    if args.limit and args.limit < len(to_fetch):
        to_fetch = to_fetch[: args.limit]
        print(f"  Limited to first {args.limit} articles (--limit)")

    print(f"  Articles to fetch: {len(to_fetch)}")

    if args.dry_run:
        print("\n[DRY RUN] Would fetch the following articles:")
        for i, title in enumerate(to_fetch, 1):
            status = "✓ exists" if already_fetched(title) else "→ fetch"
            print(f"  {i:3d}. [{status}] {title}")
        return

    if not to_fetch:
        print("Nothing to fetch — all articles already have revision data.")
        return

    # ---- API credentials check -------------------------------------------
    check_api_credentials()

    # ---- Set up logging and client ----------------------------------------
    logger = setup_logging("fetch_arb_revisions")
    _logger = logger
    client = WikiClient(use_oauth=True)
    _client = client

    logger.info("fetch_arb_revisions starting")
    logger.info(f"Articles to fetch: {len(to_fetch)}")

    # ---- Batch fetch -------------------------------------------------------
    failed: list[tuple[str, str]] = []
    skipped = len(all_candidates) - len(to_fetch)
    completed_count = 0
    milestones_sent: set[int] = set()
    start_time = time.time()

    pbar = tqdm(to_fetch, desc="Articles", unit="article")
    for title in pbar:
        pbar.set_postfix_str(title[:35])

        try:
            # Revisions
            rev_data = fetch_revisions(client, title, limit=args.revision_limit)
            rev_path = get_output_path("revisions", prefix=sanitize_filename(title))
            save_json(rev_data, rev_path)

            # Edit war analysis
            ew_data = analyze_article_edit_war(client, title)
            ew_path = get_output_path(
                "edit_wars", prefix=f"editwar_{sanitize_filename(title)}"
            )
            save_json(ew_data, ew_path)

            logger.info(f"Completed: {title}")
            completed_count += 1

        except Exception as exc:
            logger.error(f"Failed: {title} — {exc}")
            failed.append((title, str(exc)))
            tqdm.write(f"  ✗ {title}: {exc}")
            completed_count += 1  # still count toward progress

        # Milestone emails
        if args.notify_email and len(to_fetch) > 0:
            pct_done = int(completed_count / len(to_fetch) * 100)
            for milestone in (25, 50, 75):
                if pct_done >= milestone and milestone not in milestones_sent:
                    milestones_sent.add(milestone)
                    send_milestone_email(
                        notify_email=args.notify_email,
                        completed=completed_count,
                        total=len(to_fetch),
                        failed=failed,
                        skipped=skipped,
                        start_time=start_time,
                    )

    # ---- Summary -----------------------------------------------------------
    elapsed = time.time() - start_time
    print(f"\n{'=' * 50}")
    print(f"Done in {elapsed / 60:.1f} min")
    print(f"  Completed: {completed_count - len(failed)}")
    print(f"  Skipped:   {skipped}")
    print(f"  Failed:    {len(failed)}")
    if failed:
        print("\nFailed articles:")
        for name, err in failed:
            print(f"  - {name}: {err}")

    client.log_stats()


if __name__ == "__main__":
    main()
