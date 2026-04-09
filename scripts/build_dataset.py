#!/usr/bin/env python3
"""Build a model-ready feature matrix from raw Wikipedia dispute data.

Reads:
  data/raw/arbitration/*.json            — arbitration case files
  data/raw/dispute_venues/*_lifecycle.json — lifecycle stage files (optional)

Writes:
  data/processed/features.parquet        — primary output (used by models)
  data/processed/features.csv            — human-readable copy

Usage:
  python scripts/build_dataset.py
  python scripts/build_dataset.py --dry-run
  python scripts/build_dataset.py --arb-dir data/raw/arbitration --output data/processed/features.parquet
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from logging_config import setup_logging

logger = logging.getLogger(__name__)

RAW_ARB_DIR = Path("data/raw/arbitration")
RAW_LIFECYCLE_DIR = Path("data/raw/dispute_venues")
OUT_PARQUET = Path("data/processed/features.parquet")
OUT_CSV = Path("data/processed/features.csv")


def _safe_len(obj: object) -> int:
    """Return len() for lists/dicts, 0 for None or unexpected types."""
    if isinstance(obj, (list, dict)):
        return len(obj)
    return 0


def extract_arb_features(path: Path) -> dict:
    """Extract model features from a single arbitration case JSON."""
    with path.open() as f:
        d: dict = json.load(f)

    summary = d.get("summary", {})
    outcome = d.get("outcome", {})
    pages: dict = d.get("pages", {})
    participants: dict = d.get("participants", {})
    participant_blocks: dict = d.get("participant_blocks", {})
    participant_abuse: dict = d.get("participant_abuse_hits", {})
    ani_mentions: list = d.get("ani_mentions", [])
    drn_mentions: list = d.get("drn_mentions", [])

    # Revision totals per subpage type
    total_revisions = summary.get("total_revisions", 0)
    page_types = list(pages.keys())
    has_evidence_page = int("evidence" in " ".join(page_types).lower())
    has_workshop_page = int("workshop" in " ".join(page_types).lower())
    has_proposed_decision = int(
        "proposed decision" in " ".join(page_types).lower()
        or "proposed_decision" in " ".join(page_types).lower()
    )

    # Content length of main case page
    main_page = pages.get("main", {})
    main_content_length = (
        main_page.get("content_length", 0) if isinstance(main_page, dict) else 0
    )

    return {
        "case_name": d.get("case_name", path.stem),
        # Volume
        "total_revisions": total_revisions,
        "case_pages_found": summary.get("case_pages_found", len(pages)),
        "talk_pages_found": summary.get("talk_pages_found", 0),
        "has_evidence_page": has_evidence_page,
        "has_workshop_page": has_workshop_page,
        "has_proposed_decision": has_proposed_decision,
        "main_content_length": main_content_length,
        # Participants
        "participants_count": summary.get("participants_extracted", len(participants)),
        "participants_enriched": summary.get("participants_enriched", 0),
        "participants_with_blocks": summary.get(
            "participants_with_blocks", _safe_len(participant_blocks)
        ),
        "participants_with_abuse_hits": summary.get(
            "participants_with_abuse_hits", _safe_len(participant_abuse)
        ),
        # Articles
        "articles_extracted": summary.get("articles_extracted", 0),
        "articles_with_revisions": summary.get("articles_with_revisions", 0),
        # Cross-venue signals
        "ani_mentions": _safe_len(ani_mentions)
        if isinstance(ani_mentions, list)
        else summary.get("ani_mentions", 0),
        "drn_mentions": _safe_len(drn_mentions)
        if isinstance(drn_mentions, list)
        else summary.get("drn_mentions", 0),
        # Outcome (target variables)
        "outcome_status": outcome.get("status", "unknown"),
        "case_closed": int(outcome.get("case_closed", False)),
        "has_active_remedies": int(outcome.get("has_active_remedies", False)),
        "remedy_count": outcome.get("remedy_count", 0),
        "finding_count": outcome.get("finding_count", 0),
        "principle_count": outcome.get("principle_count", 0),
        # Metadata
        "fetched_at": d.get("fetched_at", ""),
    }


def extract_lifecycle_features(case_name: str, lifecycle_dir: Path) -> dict:
    """Extract lifecycle stage features if a lifecycle file exists for this case."""
    slug = case_name.replace(" ", "_")
    path = lifecycle_dir / f"{slug}_lifecycle.json"

    if not path.exists():
        return {
            "has_lifecycle_data": 0,
            "lifecycle_stages_with_data": 0,
            "lifecycle_total_revisions": 0,
            "lifecycle_ani_reports": 0,
            "lifecycle_drn_mentions": 0,
            "lifecycle_talk_pages": 0,
            "lifecycle_has_stage_talk": 0,
            "lifecycle_has_stage_drn": 0,
            "lifecycle_has_stage_ani": 0,
            "lifecycle_has_stage_arbcom": 0,
        }

    with path.open() as f:
        d: dict = json.load(f)

    lc_summary = d.get("summary", {})
    stages: dict = d.get("lifecycle_stages", {})

    return {
        "has_lifecycle_data": 1,
        "lifecycle_stages_with_data": lc_summary.get(
            "lifecycle_stages_with_data", len(stages)
        ),
        "lifecycle_total_revisions": lc_summary.get("total_revisions", 0),
        "lifecycle_ani_reports": lc_summary.get("ani_reports", 0),
        "lifecycle_drn_mentions": lc_summary.get("drn_mentions", 0),
        "lifecycle_talk_pages": lc_summary.get("talk_pages", 0),
        "lifecycle_has_stage_talk": int("stage_1_2_talk" in stages),
        "lifecycle_has_stage_drn": int("stage_3_drn" in stages),
        "lifecycle_has_stage_ani": int("stage_4_ani" in stages),
        "lifecycle_has_stage_arbcom": int("stage_5_arbcom" in stages),
    }


def build_features(arb_dir: Path, lifecycle_dir: Path) -> pd.DataFrame:
    """Build the full feature matrix from all available case files."""
    case_files = sorted(arb_dir.glob("*.json"))
    if not case_files:
        logger.warning("No arbitration case files found in %s", arb_dir)
        return pd.DataFrame()

    logger.info("Processing %d arbitration case files", len(case_files))

    rows = []
    skipped = 0
    for path in case_files:
        try:
            arb_feats = extract_arb_features(path)
            lc_feats = extract_lifecycle_features(arb_feats["case_name"], lifecycle_dir)
            rows.append({**arb_feats, **lc_feats})
        except Exception as e:
            logger.warning("Skipping %s: %s", path.name, e)
            skipped += 1

    if skipped:
        logger.warning("Skipped %d files due to errors", skipped)

    df = pd.DataFrame(rows)
    logger.info("Built feature matrix: %d rows × %d columns", len(df), len(df.columns))
    return df


def print_summary(df: pd.DataFrame) -> None:
    """Print a human-readable summary of the dataset."""
    print(f"\nDataset: {len(df)} cases × {len(df.columns)} features")
    print("\nOutcome distribution (outcome_status):")
    for status, count in df["outcome_status"].value_counts().items():
        print(f"  {status}: {count}")
    print(f"\nCases closed:              {df['case_closed'].sum()} / {len(df)}")
    print(f"Cases with active remedies:{df['has_active_remedies'].sum()} / {len(df)}")
    print(f"Cases with lifecycle data: {df['has_lifecycle_data'].sum()} / {len(df)}")
    print(f"Avg revisions per case:    {df['total_revisions'].mean():.1f}")
    print(f"Avg participants per case: {df['participants_count'].mean():.1f}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--arb-dir",
        default=str(RAW_ARB_DIR),
        help="Directory containing arbitration case JSON files",
    )
    parser.add_argument(
        "--lifecycle-dir",
        default=str(RAW_LIFECYCLE_DIR),
        help="Directory containing lifecycle JSON files",
    )
    parser.add_argument(
        "--output",
        default=str(OUT_PARQUET),
        help="Output parquet path (CSV written to same location)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show statistics without writing files",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(name="build_dataset", level=level)

    arb_dir = Path(args.arb_dir)
    lifecycle_dir = Path(args.lifecycle_dir)
    out_path = Path(args.output)

    if not arb_dir.exists():
        logger.error("Arbitration data directory not found: %s", arb_dir)
        logger.error("Run 'make pull' or 'make fetch-arb' first.")
        sys.exit(1)

    df = build_features(arb_dir, lifecycle_dir)
    if df.empty:
        logger.error("No data extracted. Check %s.", arb_dir)
        sys.exit(1)

    print_summary(df)

    if args.dry_run:
        print("\nDry run — no files written.")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(out_path, index=False)
    logger.info("Wrote %s", out_path)

    csv_path = out_path.with_suffix(".csv")
    df.to_csv(csv_path, index=False)
    logger.info("Wrote %s", csv_path)

    print(f"\nOutput:\n  {out_path}\n  {csv_path}")


if __name__ == "__main__":
    main()
