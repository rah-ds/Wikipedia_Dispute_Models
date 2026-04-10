#!/usr/bin/env python3
"""Fetch articles based on YAML configuration.

Usage:
    python fetch_from_config.py                    # Fetch all from config
    python fetch_from_config.py --dry-run          # Preview what would be fetched
    python fetch_from_config.py --config path.yaml # Use custom config
    python fetch_from_config.py --force            # Re-fetch even if files exist
"""

import argparse
import os
import smtplib
import sys
import time
from email.mime.text import MIMEText
from pathlib import Path

import yaml
from tqdm import tqdm

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.wiki import WikiClient
from src.io import (
    save_json,
    get_output_path,
    sanitize_filename,
    setup_logging,
    check_api_credentials,
    DATA_DIR,
)
from src.fetchers import (
    fetch_revisions,
    analyze_article_edit_war,
    fetch_arbitration_cases,
    fetch_drn_page,
    parse_drn_sections,
    extract_case_metadata,
)

CONFIG_PATH = Path(__file__).parent.parent / "artifacts" / "sample_articles.yaml"

# Delay between article fetches (seconds) - be nice to Wikipedia
FETCH_DELAY = 2.0

# Email config — UVA relay discovered from Rivanna postfix config
_SMTP_HOST = "out.mail.virginia.edu"
_SMTP_PORT = 25
_SENDER = "rah5ff@virginia.edu"

# Global for graceful shutdown
_client = None
_logger = None


def send_milestone_email(
    notify_email: str,
    job_type: str,
    completed: int,
    total: int,
    failed: list[tuple[str, str]],
    client: WikiClient,
    current_article: str,
    last_article: str,
    skipped: int,
    start_time: float,
) -> None:
    """Send a progress email at 25/50/75% milestones."""
    if not notify_email:
        return

    pct = int(completed / total * 100) if total else 0
    elapsed = time.time() - start_time
    elapsed_fmt = time.strftime("%H:%M:%S", time.gmtime(elapsed))
    remaining = (elapsed / completed * (total - completed)) if completed else 0
    remaining_fmt = time.strftime("%H:%M:%S", time.gmtime(remaining))

    stats = client.get_stats()
    req_rate = stats["total_requests"] / (stats["runtime_minutes"] or 1)

    lines = [
        "Wikipedia Dispute Models — Progress Report",
        "═" * 43,
        "",
        f"Job:             {job_type}",
        f"Job ID:          {os.environ.get('SLURM_JOB_ID', 'local')}",
        f"Host:            {os.environ.get('HOSTNAME', 'unknown')}",
        f"Progress:        {pct}% — {completed} of {total} articles complete",
        f"Elapsed:         {elapsed_fmt}",
        f"Est. remaining:  ~{remaining_fmt}",
        "",
        "Summary Statistics",
        "─" * 18,
        f"  Completed:     {completed} / {total} articles",
        f"  Failed:        {len(failed)}",
        f"  Skipped:       {skipped} (already existed)",
        f"  API requests:  {stats['total_requests']:,} ({req_rate:.1f} req/min)",
        f"  Runtime:       {stats['runtime_minutes']:.1f} min",
        "",
        "Current Phase",
        "─" * 13,
        "  Fetching article revisions and edit war data.",
        f"  Currently processing: {current_article}",
        f"  Last completed: {last_article}",
    ]

    if failed:
        lines.append("")
        lines.append(f"  Errors ({len(failed)}):")
        for name, error in failed[-5:]:
            lines.append(f"    - {name}: {error}")
        if len(failed) > 5:
            lines.append(f"    ... and {len(failed) - 5} more")

    next_pct = pct + 25 if pct < 100 else None
    if next_pct and next_pct <= 100:
        lines.append("")
        lines.append(f"Next milestone email at {next_pct}%.")

    subject = f"[Rivanna] {job_type} — {pct}% complete ({completed}/{total} articles)"
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


def shutdown_handler(signum, frame):
    """Handle Ctrl+C gracefully - log stats before exit."""
    print("\n\n⚠️  Interrupted! Logging stats before exit...")
    if _client:
        _client.log_stats()
        stats = _client.get_stats()
        print(
            f"📊 API Stats: {stats['total_requests']} requests in {stats['runtime_minutes']:.1f} min"
        )
    if _logger:
        _logger.info("Fetch interrupted by user")
    sys.exit(1)


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load article configuration from YAML."""
    with open(path) as f:
        return yaml.safe_load(f)


def article_already_fetched(title: str) -> bool:
    """Check if article data already exists."""
    safe_title = sanitize_filename(title)
    revisions_dir = DATA_DIR / "raw" / "revisions"
    editwar_dir = DATA_DIR / "raw" / "edit_wars"

    # Check for any file matching this article
    rev_files = (
        list(revisions_dir.glob(f"{safe_title}_*.json"))
        if revisions_dir.exists()
        else []
    )
    ew_files = (
        list(editwar_dir.glob(f"editwar_{safe_title}_*.json"))
        if editwar_dir.exists()
        else []
    )

    return len(rev_files) > 0 and len(ew_files) > 0


def arb_already_fetched() -> bool:
    """Check if arbitration data already exists."""
    arb_dir = DATA_DIR / "raw" / "arbitration"
    if not arb_dir.exists():
        return False
    return len(list(arb_dir.glob("arbitration_cases_*.json"))) > 0


def drn_already_fetched() -> bool:
    """Check if DRN data already exists."""
    drn_dir = DATA_DIR / "raw" / "drn"
    if not drn_dir.exists():
        return False
    return len(list(drn_dir.glob("drn_cases_*.json"))) > 0


def main():
    parser = argparse.ArgumentParser(description="Fetch articles from YAML config")
    parser.add_argument(
        "--config", type=Path, default=CONFIG_PATH, help="Path to config YAML"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without fetching"
    )
    parser.add_argument(
        "--skip-arb", action="store_true", help="Skip arbitration cases"
    )
    parser.add_argument("--skip-drn", action="store_true", help="Skip DRN cases")
    parser.add_argument(
        "--force", action="store_true", help="Re-fetch even if files exist"
    )
    parser.add_argument(
        "--notify-email",
        default=os.environ.get("NOTIFY_EMAIL", ""),
        help="Email address for progress reports (default: $NOTIFY_EMAIL)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    defaults = config.get("defaults", {})
    rev_limit = defaults.get("revision_limit", 500)
    arb_limit = defaults.get("arb_limit", 5)

    high_conflict = config.get("high_conflict", [])
    low_conflict = config.get("low_conflict", [])
    all_articles = high_conflict + low_conflict

    print(f"Config: {args.config}")
    print(f"High-conflict articles: {len(high_conflict)}")
    print(f"Low-conflict articles: {len(low_conflict)}")
    print(f"Revision limit: {rev_limit}")
    print()

    if args.dry_run:
        print("[DRY RUN] Would fetch:")
        if not args.skip_arb:
            print(f"  - {arb_limit} arbitration cases")
        if not args.skip_drn:
            print("  - DRN cases")
        for article in all_articles:
            print(f"  - {article['title']} ({article['category']})")
        return

    check_api_credentials()
    logger = setup_logging("fetch_from_config")
    client = WikiClient()

    # Set globals for shutdown handler
    global _client, _logger
    _client = client
    _logger = logger

    failed = []

    # Fetch arbitration cases
    if not args.skip_arb:
        if not args.force and arb_already_fetched():
            print("=== Arbitration Cases === (skipped, already fetched)")
        else:
            print("=== Arbitration Cases ===")
            try:
                cases = fetch_arbitration_cases(client, limit=arb_limit)
                output_path = get_output_path("arbitration", prefix="arbitration_cases")
                save_json(cases, output_path)
                logger.info(f"Saved {len(cases)} arbitration cases to {output_path}")
            except Exception as e:
                logger.error(f"Failed to fetch arbitration cases: {e}")
                failed.append(("Arbitration cases", str(e)))

    # Fetch DRN cases
    if not args.skip_drn:
        if not args.force and drn_already_fetched():
            print("\n=== DRN Cases === (skipped, already fetched)")
        else:
            print("\n=== DRN Cases ===")
            try:
                drn_data = fetch_drn_page(client)
                cases = parse_drn_sections(drn_data["content"])
                cases = extract_case_metadata(cases)
                cases = [
                    c for c in cases if c["level"] == 2 and len(c["content"]) > 100
                ]
                drn_data["parsed_cases"] = cases
                drn_data["case_count"] = len(cases)
                del drn_data["content"]
                output_path = get_output_path("drn", prefix="drn_cases")
                save_json(drn_data, output_path)
                logger.info(f"Saved {len(cases)} DRN cases to {output_path}")
            except Exception as e:
                logger.error(f"Failed to fetch DRN cases: {e}")
                failed.append(("DRN cases", str(e)))

    # Fetch all articles with progress bar
    print("\n=== Fetching Articles ===")

    # Check which articles already exist
    skipped = 0
    to_fetch = []
    for article in all_articles:
        if not args.force and article_already_fetched(article["title"]):
            skipped += 1
        else:
            to_fetch.append(article)

    if skipped > 0:
        print(f"Skipping {skipped} already-fetched articles (use --force to re-fetch)")

    if not to_fetch:
        print("All articles already fetched!")
    else:
        pbar = tqdm(to_fetch, desc="Articles", unit="article")
        completed_count = 0
        milestones_sent: set[int] = set()
        loop_start = time.time()
        last_completed_title = ""

        for article in pbar:
            title = article["title"]
            # category = article.get("category", "unknown")
            pbar.set_postfix_str(title[:30])

            try:
                # Fetch revisions
                data = fetch_revisions(client, title, limit=rev_limit)
                output_path = get_output_path(
                    "revisions", prefix=sanitize_filename(title)
                )
                save_json(data, output_path)

                # Run edit war analysis
                analysis = analyze_article_edit_war(client, title)
                output_path = get_output_path(
                    "edit_wars", prefix=f"editwar_{sanitize_filename(title)}"
                )
                save_json(analysis, output_path)

                logger.info(f"Completed: {title}")
                completed_count += 1
                last_completed_title = title

            except Exception as e:
                logger.error(f"Failed to fetch {title}: {e}")
                failed.append((title, str(e)))
                tqdm.write(f"  ✗ Error: {e}")
                completed_count += 1  # count toward progress even on failure

            # Check for milestone email (25%, 50%, 75%)
            if args.notify_email and len(to_fetch) > 0:
                pct_done = int(completed_count / len(to_fetch) * 100)
                for milestone in (25, 50, 75):
                    if pct_done >= milestone and milestone not in milestones_sent:
                        milestones_sent.add(milestone)
                        send_milestone_email(
                            notify_email=args.notify_email,
                            job_type="fetch_full",
                            completed=completed_count,
                            total=len(to_fetch),
                            failed=failed,
                            client=client,
                            current_article=title,
                            last_article=last_completed_title,
                            skipped=skipped,
                            start_time=loop_start,
                        )
                        logger.info(f"Sent {milestone}% milestone email")

            # Rate limiting delay
            time.sleep(FETCH_DELAY)

    # Summary
    print("\n" + "=" * 50)
    successful = len(to_fetch) - len(
        [f for f in failed if f[0] not in ("Arbitration cases", "DRN cases")]
    )
    print(f"✓ Fetched: {successful}/{len(to_fetch)} articles")
    if skipped > 0:
        print(f"✓ Skipped: {skipped} (already existed)")

    if failed:
        print(f"\n⚠️  Failed ({len(failed)}):")
        for name, error in failed:
            print(f"  - {name}: {error}")

    # Log API request stats
    client.log_stats()
    stats = client.get_stats()
    print(
        f"\n📊 API Stats: {stats['total_requests']} requests in {stats['runtime_minutes']:.1f} min"
    )

    print("\n✓ Fetch complete!")
    logger.info(
        f"Fetch complete: {successful}/{len(to_fetch)} articles, {len(failed)} failures"
    )


if __name__ == "__main__":
    main()
