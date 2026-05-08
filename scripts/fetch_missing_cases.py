#!/usr/bin/env python3
"""
Fetch enriched data for every arbitration case that is listed in
artifacts/arb_cases.txt but does not yet have a file in data/raw/arbitration/.

Calls the same `fetch_full_arbitration_case` used by pull.py, so the output
format is identical to the 78 cases already collected.

Usage
-----
    python scripts/fetch_missing_cases.py              # fetch all missing
    python scripts/fetch_missing_cases.py --dry-run    # list missing, don't fetch
    python scripts/fetch_missing_cases.py --limit 10   # fetch at most N missing cases
    python scripts/fetch_missing_cases.py --workers 1  # serial (default, rate-limit safe)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dotenv import load_dotenv

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

RAW_ARB = PROJECT_ROOT / "data" / "raw" / "arbitration"
CASES_FILE = PROJECT_ROOT / "artifacts" / "arb_cases.txt"

logger = logging.getLogger("fetch_missing")


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def _load_case_list() -> list[str]:
    """Read artifacts/arb_cases.txt, return list of case names."""
    if not CASES_FILE.exists():
        logger.error(f"Case list not found: {CASES_FILE}")
        logger.error("Run: make update-arb-cases-list")
        sys.exit(1)
    with open(CASES_FILE) as f:
        return [ln.strip() for ln in f if ln.strip()]


def _have_data() -> set[str]:
    """Return set of case names we already have enriched data for (on disk)."""
    have = set()
    for path in RAW_ARB.glob("*.json"):
        if any(path.name.startswith(p) for p in ("arb_dfs_", "arbitration_cases_")):
            continue
        try:
            with open(path) as f:
                d = json.load(f)
            name = d.get("case_name", "")
            if name:
                have.add(name)
        except Exception:
            continue
    return have


def _missing(case_list: list[str], have: set[str]) -> list[str]:
    return [c for c in case_list if c not in have]


# ---------------------------------------------------------------------------
# Fetch one case
# ---------------------------------------------------------------------------


def _safe_filename(name: str) -> str:
    import re

    return re.sub(r'[<>:"/\\|?*]', "_", name)


def fetch_one(case_name: str, dry_run: bool = False) -> bool:
    """Fetch and save one case. Returns True on success."""
    out_path = RAW_ARB / f"{_safe_filename(case_name)}.json"

    if dry_run:
        logger.info(f"  [DRY] Would fetch: {case_name}")
        return True

    try:
        from arbitration import fetch_full_arbitration_case
        from wiki import WikiClient
    except ImportError as e:
        logger.error(f"Cannot import arbitration module: {e}")
        logger.error(
            "Make sure you're running from the project root with the venv active."
        )
        sys.exit(1)

    try:
        logger.info(f"  Fetching: {case_name}")
        client = WikiClient()
        result = fetch_full_arbitration_case(client, case_name)
        if result is None:
            logger.warning(f"  No result for: {case_name}")
            return False

        RAW_ARB.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        n_eds = result.get("summary", {}).get("participants_extracted", "?")
        n_revs = result.get("summary", {}).get("total_revisions", "?")
        logger.info(f"    → {out_path.name}  ({n_eds} editors, {n_revs} revisions)")
        return True

    except Exception as exc:
        logger.warning(f"  FAILED {case_name}: {exc}")
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List missing cases without fetching"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after fetching N cases (0 = no limit)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds to sleep between fetches (default: 1)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    case_list = _load_case_list()
    have = _have_data()
    missing = _missing(case_list, have)

    logger.info(f"Known cases:   {len(case_list)}")
    logger.info(f"Have on disk:  {len(have)}")
    logger.info(f"Missing:       {len(missing)}")

    if not missing:
        logger.info("Nothing to do — all cases already collected.")
        return

    if args.dry_run:
        print("\nMissing cases:")
        for name in missing:
            print(f"  {name}")
        return

    limit = args.limit or len(missing)
    to_fetch = missing[:limit]
    logger.info(f"Fetching {len(to_fetch)} cases (delay={args.delay}s)...")

    ok = err = 0
    for i, name in enumerate(to_fetch, 1):
        logger.info(f"[{i}/{len(to_fetch)}]")
        if fetch_one(name):
            ok += 1
        else:
            err += 1
        if i < len(to_fetch) and args.delay > 0:
            time.sleep(args.delay)

    logger.info(f"\nDone. {ok} fetched, {err} failed.")
    if err:
        logger.info("Run again to retry failures.")


if __name__ == "__main__":
    main()
