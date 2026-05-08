#!/usr/bin/env python3
"""
Rebuild ``data/processed/features.csv`` and ``features.parquet`` from all
raw data sources collected via Rivanna.

Data source priority per case (highest → lowest):
    1. Enriched file  (``data/raw/arbitration/<CaseName>.json``, pages-as-dict)
    2. Arb-DFS file   (``data/raw/arbitration/arb_dfs_<name>_*.json``, legacy)

Lifecycle data from ``data/raw/dispute_venues/lifecycle_*.json`` is merged
as supplementary columns regardless of which primary file was used.

Usage:
    python scripts/build_features.py
    python scripts/build_features.py --dry-run
    python scripts/build_features.py --out data/processed/features.csv
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.arbitration import ArbitrationCaseSummary

logger = logging.getLogger("build_features")

# ---------------------------------------------------------------------------
# Data discovery
# ---------------------------------------------------------------------------

RAW_ARB = PROJECT_ROOT / "data" / "raw" / "arbitration"
RAW_LC = PROJECT_ROOT / "data" / "raw" / "dispute_venues"
PROCESSED = PROJECT_ROOT / "data" / "processed"

# Prefixes to skip (index / manifest files, not individual cases)
SKIP_PREFIXES = ("arbitration_cases_",)


def _discover_primary_files() -> dict[str, Path]:
    """Return {case_name: best_path} for all arbitration case JSONs.

    Priority:
        1. Enriched file (non-arb_dfs_, has ``pages`` dict)
        2. Arb-DFS file with the most revisions
    """
    enriched: dict[str, Path] = {}
    arb_dfs: dict[str, list[Path]] = defaultdict(list)

    for path in sorted(RAW_ARB.glob("*.json")):
        if any(path.name.startswith(p) for p in SKIP_PREFIXES):
            continue
        if path.name.startswith("arb_dfs_"):
            # Extract case name from file, but we'll read JSON to be safe
            arb_dfs[path.name].append(path)
        else:
            enriched[path.stem] = path  # stem ≈ case name

    # Build best-per-case map
    best: dict[str, Path] = {}

    # First pass: enriched files (preferred, have participant data)
    for path in enriched.values():
        try:
            with open(path) as f:
                d = json.load(f)
            if not isinstance(d, dict):
                continue
            name = d.get("case_name", "")
            if name:
                best[name] = path
        except Exception:
            continue

    # Second pass: arb_dfs files (fill in missing cases)
    for path in sorted(RAW_ARB.glob("arb_dfs_*.json")):
        try:
            with open(path) as f:
                d = json.load(f)
            if not isinstance(d, dict):
                continue
            name = d.get("case_name", "")
            if not name or name in best:
                continue
            best[name] = path
        except Exception:
            continue

    return best


def _discover_lifecycle_files() -> dict[str, Path]:
    """Return {case_name: path} for all lifecycle JSONs."""
    result: dict[str, Path] = {}
    for path in sorted(RAW_LC.glob("lifecycle_*.json")):
        try:
            with open(path) as f:
                d = json.load(f)
            name = d.get("case_name", "")
            if name:
                # Keep latest file per case
                result[name] = path
        except Exception:
            continue
    return result


# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------


def _extract_enriched_extras(raw: dict) -> dict:
    """Extract features only available in enriched-format files."""
    summary = raw.get("summary", {})
    outcome = raw.get("outcome", {})

    return {
        # Participant enrichment
        "participants_count": summary.get("participants_extracted", 0),
        "participants_enriched": summary.get("participants_enriched", 0),
        "participants_with_blocks": summary.get("participants_with_blocks", 0),
        "participants_with_abuse_hits": summary.get("participants_with_abuse_hits", 0),
        # Article enrichment
        "articles_extracted": summary.get("articles_extracted", 0),
        "articles_with_revisions": summary.get("articles_with_revisions", 0),
        # ANI / DRN mentions from enriched fetch
        "enriched_ani_mentions": summary.get("ani_mentions", 0),
        "enriched_drn_mentions": summary.get("drn_mentions", 0),
        # Outcome from enriched fetch
        "enriched_outcome_status": outcome.get("status", ""),
        "enriched_case_closed": 1 if outcome.get("case_closed") else 0,
        "enriched_has_active_remedies": 1 if outcome.get("has_active_remedies") else 0,
        "enriched_remedy_count": outcome.get("remedy_count", 0),
        "enriched_finding_count": outcome.get("finding_count", 0),
        "enriched_principle_count": outcome.get("principle_count", 0),
    }


def _extract_lifecycle_features(raw: dict) -> dict:
    """Extract lifecycle-specific features from lifecycle JSON."""
    stages = raw.get("lifecycle_stages", {})
    summary = raw.get("summary", {})

    arbcom = stages.get("stage_5_arbcom", {})
    ani = stages.get("stage_4_ani", {})
    drn = stages.get("stage_3_drn", {})
    talk = stages.get("stage_1_2_talk", {})

    has_arbcom = bool(arbcom.get("pages"))
    has_ani = bool(ani.get("reports"))
    has_drn = bool(drn.get("mentions"))
    has_talk = bool(talk.get("pages"))

    return {
        "has_lifecycle_data": 1,
        "lifecycle_stages_with_data": sum([has_arbcom, has_ani, has_drn, has_talk]),
        "lifecycle_total_revisions": summary.get("total_revisions", 0),
        "lifecycle_arbcom_pages": summary.get("arbcom_pages", 0),
        "lifecycle_arbcom_talk_pages": summary.get("arbcom_talk_pages", 0),
        "lifecycle_ani_reports": summary.get("ani_reports", 0),
        "lifecycle_drn_mentions": summary.get("drn_mentions", 0),
        "lifecycle_talk_pages": summary.get("talk_pages", 0),
        "lifecycle_participants": summary.get("participants_extracted", 0),
        "lifecycle_articles": summary.get("articles_extracted", 0),
        "lifecycle_has_stage_talk": int(has_talk),
        "lifecycle_has_stage_drn": int(has_drn),
        "lifecycle_has_stage_ani": int(has_ani),
        "lifecycle_has_stage_arbcom": int(has_arbcom),
    }


LIFECYCLE_DEFAULTS = {
    "has_lifecycle_data": 0,
    "lifecycle_stages_with_data": 0,
    "lifecycle_total_revisions": 0,
    "lifecycle_arbcom_pages": 0,
    "lifecycle_arbcom_talk_pages": 0,
    "lifecycle_ani_reports": 0,
    "lifecycle_drn_mentions": 0,
    "lifecycle_talk_pages": 0,
    "lifecycle_participants": 0,
    "lifecycle_articles": 0,
    "lifecycle_has_stage_talk": 0,
    "lifecycle_has_stage_drn": 0,
    "lifecycle_has_stage_ani": 0,
    "lifecycle_has_stage_arbcom": 0,
}

ENRICHED_DEFAULTS = {
    "participants_count": 0,
    "participants_enriched": 0,
    "participants_with_blocks": 0,
    "participants_with_abuse_hits": 0,
    "articles_extracted": 0,
    "articles_with_revisions": 0,
    "enriched_ani_mentions": 0,
    "enriched_drn_mentions": 0,
    "enriched_outcome_status": "",
    "enriched_case_closed": 0,
    "enriched_has_active_remedies": 0,
    "enriched_remedy_count": 0,
    "enriched_finding_count": 0,
    "enriched_principle_count": 0,
}


def _case_summary_row(case: ArbitrationCaseSummary) -> dict:
    """Build a flat feature row from an ArbitrationCaseSummary.

    Like ``case.to_summary_dict()`` but restricts subpage edit columns to
    the standard ArbCom subpages so we get a fixed-width schema instead of
    thousands of article-level columns.
    """
    cs = case.consensus_signals()
    top = case.top_editors(5)

    # Only keep standard subpage edit counts
    STANDARD_SUBPAGES = {
        "(main)",
        "/Evidence",
        "/Workshop",
        "/Proposed decision",
        "/Final decision",
        "/Remedies",
        "/Clarification requests",
    }
    subpage_counts = case.subpage_edit_counts()
    case_subpage_edits = {
        f"edits_{k.replace('/', '_').replace(' ', '_').strip('_')}": v
        for k, v in subpage_counts.items()
        if k in STANDARD_SUBPAGES
    }
    # Sum article + talk page edits as aggregate columns
    article_edits = sum(
        v for k, v in subpage_counts.items() if k.startswith("article:")
    )
    talk_edits = sum(
        v
        for k, v in subpage_counts.items()
        if k not in STANDARD_SUBPAGES and not k.startswith("article:")
    )

    return {
        "case_name": case.case_name,
        "fetched_at": case.fetched_at,
        "total_revisions": case.total_revisions,
        "total_editors": case.total_editors,
        "total_case_pages": case.total_case_pages,
        "total_talk_pages": case.total_talk_pages,
        "total_linked_articles": case.total_linked_articles,
        "case_duration_days": case.case_duration_days,
        "earliest_activity": case.earliest_activity,
        "latest_activity": case.latest_activity,
        # Standard subpage breakdowns
        **case_subpage_edits,
        "edits_linked_articles_total": article_edits,
        "edits_talk_pages_total": talk_edits,
        # Consensus signals
        **{f"consensus_{k}": v for k, v in cs.items()},
        # Conflict
        "conflict_edge_count": len(case.conflict_edges),
        "max_conflict_reverts": (
            case.conflict_edges[0].count if case.conflict_edges else 0
        ),
        # Top editors
        "top_editor_1": top[0].username if len(top) > 0 else "",
        "top_editor_1_edits": top[0].total_edits if len(top) > 0 else 0,
        "top_editor_2": top[1].username if len(top) > 1 else "",
        "top_editor_2_edits": top[1].total_edits if len(top) > 1 else 0,
        # Decision outcome (from parsed wikitext, if available)
        **(case.decision_outcome.to_summary_dict() if case.decision_outcome else {}),
    }


def build_feature_row(
    case_name: str,
    primary_path: Path,
    lifecycle_path: Path | None,
) -> dict:
    """Build one feature row by loading primary + lifecycle data."""
    # Load primary data via ArbitrationCaseSummary
    case = ArbitrationCaseSummary.from_json_path(primary_path)
    row = _case_summary_row(case)
    row["data_source"] = (
        "enriched" if not primary_path.name.startswith("arb_dfs_") else "arb_dfs"
    )

    # Enriched extras (only available from enriched files)
    with open(primary_path) as f:
        raw = json.load(f)

    if isinstance(raw.get("pages"), dict):
        row.update(_extract_enriched_extras(raw))
    else:
        row.update(ENRICHED_DEFAULTS)

    # Lifecycle supplement
    if lifecycle_path:
        with open(lifecycle_path) as f:
            lc_raw = json.load(f)
        row.update(_extract_lifecycle_features(lc_raw))
    else:
        row.update(LIFECYCLE_DEFAULTS)

    return row


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Rebuild features from raw data.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show counts, don't write"
    )
    parser.add_argument("--out", type=Path, default=PROCESSED / "features.csv")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s - %(message)s",
    )

    logger.info("Discovering data files...")
    primary = _discover_primary_files()
    lifecycle = _discover_lifecycle_files()

    enriched_count = sum(
        1 for p in primary.values() if not p.name.startswith("arb_dfs_")
    )
    arb_dfs_count = sum(1 for p in primary.values() if p.name.startswith("arb_dfs_"))
    logger.info(
        f"  Primary files: {len(primary)} cases ({enriched_count} enriched, {arb_dfs_count} arb_dfs)"
    )
    logger.info(f"  Lifecycle files: {len(lifecycle)} cases")
    logger.info(
        f"  Lifecycle coverage: {len(set(primary) & set(lifecycle))}/{len(primary)} cases"
    )

    if args.dry_run:
        missing_lc = sorted(set(primary) - set(lifecycle))
        logger.info(f"  Missing lifecycle for {len(missing_lc)} cases")
        if missing_lc[:10]:
            logger.info(f"  Sample: {missing_lc[:10]}")
        return

    # Build feature rows
    rows = []
    errors = []
    for i, (name, path) in enumerate(sorted(primary.items()), 1):
        lc_path = lifecycle.get(name)
        try:
            row = build_feature_row(name, path, lc_path)
            rows.append(row)
        except Exception as exc:
            errors.append((name, str(exc)))
            logger.warning(f"  [{i}/{len(primary)}] FAILED {name}: {exc}")
            continue

        if i % 50 == 0 or i == len(primary):
            logger.info(f"  [{i}/{len(primary)}] processed")

    if errors:
        logger.warning(f"\n{len(errors)} cases failed to process:")
        for name, err in errors[:10]:
            logger.warning(f"  {name}: {err}")

    # Build DataFrame
    df = pd.DataFrame(rows)
    if "case_name" in df.columns:
        df = df.sort_values("case_name").reset_index(drop=True)

    # Write outputs
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False)
    logger.info(f"\nWrote {args.out} ({len(df)} rows, {len(df.columns)} columns)")

    parquet_path = args.out.with_suffix(".parquet")
    try:
        df.to_parquet(parquet_path, index=False)
        logger.info(f"Wrote {parquet_path}")
    except ImportError:
        logger.warning("pyarrow/fastparquet not installed — skipping .parquet output")

    # Summary stats
    with_revisions = (df["total_revisions"] > 0).sum()
    with_lifecycle = (df.get("has_lifecycle_data", pd.Series(dtype=int)) == 1).sum()
    with_outcome = df.get("outcome_total_items", pd.Series(dtype=float)).notna().sum()
    logger.info("\nSummary:")
    logger.info(f"  Total cases:        {len(df)}")
    logger.info(f"  With revisions:     {with_revisions}")
    logger.info(f"  With lifecycle:     {with_lifecycle}")
    logger.info(f"  With parsed outcome: {with_outcome}")
    logger.info(f"  Data sources:       {df['data_source'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
