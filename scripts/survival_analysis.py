#!/usr/bin/env python3
"""Survival analysis scaffold for Wikipedia dispute timelines.

Answers two time-based questions:
  1. How long until a case is resolved? (time-to-resolution)
  2. What factors predict faster or slower resolution? (Cox regression)

For the full conceptual design — including multi-stage models,
censoring strategy, and what additional data enables the escalation
analysis — see docs/survival_analysis.md.

Current data limitations
-------------------------
The feature matrix (data/processed/features.parquet) does not yet
contain case filing dates or resolution dates. This script extracts
them directly from the raw arbitration JSON files, specifically from
the revision history of the main case page:

  case_opened  = timestamp of the first revision on the main case page
  case_closed  = timestamp of the last revision (approximation; a proper
                 "closed" timestamp would come from parsing the case
                 closure template in the wikitext)

These are approximations. The actual ArbCom filing date is when the
case was formally accepted, which may be a few days after the first edit.
This script uses what's available and notes where to improve.

Usage:
  python scripts/survival_analysis.py
  python scripts/survival_analysis.py --km-only          # skip Cox
  python scripts/survival_analysis.py --output artifacts/imgs/survival/
  python scripts/survival_analysis.py --demo             # synthetic demo

Requires:
  make install-ml    (installs lifelines, matplotlib)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from features import load_features
from targets import make_was_sanctioned

logger = logging.getLogger(__name__)

RAW_ARB_DIR = Path("data/raw/arbitration")
DEFAULT_OUTPUT_DIR = Path("artifacts/imgs/survival")


# ---------------------------------------------------------------------------
# Timestamp extraction from raw JSON
# ---------------------------------------------------------------------------


def _parse_ts(ts_str: str) -> datetime | None:
    """Parse ISO-8601 timestamp string to timezone-aware datetime."""
    if not ts_str:
        return None
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_case_timestamps(
    case_name: str, arb_dir: Path
) -> dict[str, datetime | None]:
    """Extract case_opened / case_closed approximations from raw JSON.

    Opened  = first revision timestamp on the main case page.
    Closed  = last revision timestamp across ALL case pages (approximation).

    Returns: {"case_opened": datetime | None, "case_closed": datetime | None}
    """
    slug = case_name.replace(" ", "_").replace("/", "_")
    # Try both exact name and slug
    candidates = [
        arb_dir / f"{case_name}.json",
        arb_dir / f"{slug}.json",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        return {"case_opened": None, "case_closed": None}

    with path.open() as f:
        d: dict = json.load(f)

    pages: dict = d.get("pages", {})
    all_timestamps: list[datetime] = []

    for page_data in pages.values():
        if not isinstance(page_data, dict):
            continue
        for rev in page_data.get("revisions", []):
            ts = _parse_ts(rev.get("timestamp", ""))
            if ts:
                all_timestamps.append(ts)

    if not all_timestamps:
        return {"case_opened": None, "case_closed": None}

    all_timestamps.sort()
    return {
        "case_opened": all_timestamps[0],
        "case_closed": all_timestamps[-1],
    }


def build_survival_dataset(df: pd.DataFrame, arb_dir: Path) -> pd.DataFrame:
    """Build survival dataset with duration_days and event indicator.

    duration_days:  days from case_opened to case_closed (or observation end)
    event_observed: 1 = case closed, 0 = still open (right-censored)
    """
    rows = []
    today = datetime.now(tz=timezone.utc)

    for _, row in df.iterrows():
        ts = extract_case_timestamps(row["case_name"], arb_dir)
        opened = ts["case_opened"]
        closed = ts["case_closed"]

        if opened is None:
            logger.debug("No timestamps found for: %s", row["case_name"])
            continue

        event_observed = int(row["case_closed"])

        if event_observed and closed and closed > opened:
            duration = (closed - opened).days
        else:
            # Censored: use today as the observation end point
            duration = (today - opened).days

        if duration <= 0:
            continue

        rows.append(
            {
                "case_name": row["case_name"],
                "duration_days": duration,
                "event_observed": event_observed,
                "was_sanctioned": make_was_sanctioned(row.to_frame().T).iloc[0],
                # Covariates for Cox model
                "participants_count": row.get("participants_count", 0),
                "total_revisions": row.get("total_revisions", 0),
                "main_content_length": row.get("main_content_length", 0),
                "participants_with_blocks": row.get("participants_with_blocks", 0),
                "ani_mentions": row.get("ani_mentions", 0),
                "has_evidence_page": row.get("has_evidence_page", 0),
                "has_workshop_page": row.get("has_workshop_page", 0),
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Kaplan-Meier
# ---------------------------------------------------------------------------


def plot_km(
    survival_df: pd.DataFrame,
    output_dir: Path,
    group_col: str | None = None,
) -> None:
    """Plot Kaplan-Meier survival (time-to-resolution) curves.

    If group_col is provided, separate curves are drawn per group.
    """
    try:
        import matplotlib.pyplot as plt
        from lifelines import KaplanMeierFitter
    except ImportError:
        print("lifelines / matplotlib not installed. Run: make install-ml")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 5))

    if group_col and group_col in survival_df.columns:
        groups = survival_df[group_col].unique()
        for g in sorted(groups):
            sub = survival_df[survival_df[group_col] == g]
            kmf = KaplanMeierFitter(label=f"{group_col}={g}  (n={len(sub)})")
            kmf.fit(sub["duration_days"], event_observed=sub["event_observed"])
            kmf.plot_survival_function(ax=ax, ci_show=True)
        title = f"Time-to-Resolution by {group_col}"
        fname = f"km_{group_col}.png"
    else:
        kmf = KaplanMeierFitter(label=f"All cases  (n={len(survival_df)})")
        kmf.fit(
            survival_df["duration_days"],
            event_observed=survival_df["event_observed"],
        )
        kmf.plot_survival_function(ax=ax, ci_show=True)
        median = kmf.median_survival_time_
        print(f"  Median time-to-resolution: {median:.0f} days")
        title = "Time-to-Resolution (all ArbCom cases)"
        fname = "km_overall.png"

    ax.set_title(title, fontsize=13)
    ax.set_xlabel("Days since case opened")
    ax.set_ylabel("Probability of remaining open")
    ax.set_ylim(0, 1)
    ax.legend(fontsize=9)
    plt.tight_layout()

    out = output_dir / fname
    fig.savefig(out, dpi=150)
    print(f"  Saved: {out}")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Cox proportional hazards
# ---------------------------------------------------------------------------


COX_COVARIATES = [
    "participants_count",
    "total_revisions",
    "main_content_length",
    "participants_with_blocks",
    "ani_mentions",
    "has_evidence_page",
    "has_workshop_page",
]


def run_cox(survival_df: pd.DataFrame) -> None:
    """Fit a Cox proportional hazards model and print the summary.

    Interprets hazard ratios:
      HR > 1  → factor associated with FASTER resolution (higher hazard of closing)
      HR < 1  → factor associated with SLOWER resolution (lower hazard of closing)
    """
    try:
        from lifelines import CoxPHFitter
        from lifelines.statistics import proportional_hazard_test
    except ImportError:
        print("lifelines not installed. Run: make install-ml")
        return

    available = [c for c in COX_COVARIATES if c in survival_df.columns]
    model_cols = ["duration_days", "event_observed"] + available

    cox_df = survival_df[model_cols].dropna()
    if len(cox_df) < 20:
        print(f"  Insufficient data for Cox model ({len(cox_df)} complete cases).")
        print("  Fetch more lifecycle data to enable this analysis.")
        return

    # Normalize covariates (Cox is sensitive to scale)
    from sklearn.preprocessing import StandardScaler  # type: ignore[import]

    scaler = StandardScaler()
    cox_df = cox_df.copy()
    cox_df[available] = scaler.fit_transform(cox_df[available])

    cph = CoxPHFitter()
    cph.fit(cox_df, duration_col="duration_days", event_col="event_observed")

    print("\n  Cox PH model summary:")
    cph.print_summary()

    # Check proportional hazards assumption
    print("\n  Proportional hazards test (p > 0.05 = assumption not violated):")
    try:
        result = proportional_hazard_test(cph, cox_df, time_transform="rank")
        print(result.summary.to_string())
    except Exception as e:
        logger.debug("PH test failed: %s", e)


# ---------------------------------------------------------------------------
# Synthetic demo (when real data timestamps aren't available)
# ---------------------------------------------------------------------------


def run_demo(output_dir: Path) -> None:
    """Demonstrate KM + Cox with synthetic data matching our expected distribution.

    Useful for validating plots and model code before real timestamps are
    extracted. The synthetic parameters are calibrated to roughly match
    what ArbCom case durations look like historically (~60–365 day range).
    """
    import numpy as np

    rng = np.random.default_rng(42)
    n = 87

    # Simulate: sanctioned cases take longer (higher complexity)
    was_sanctioned = rng.binomial(1, 0.24, n)
    base_duration = rng.exponential(scale=180, size=n)
    duration_days = (base_duration * (1 + 0.5 * was_sanctioned)).astype(int).clip(min=1)
    event_observed = rng.binomial(1, 0.84, n)

    demo_df = pd.DataFrame(
        {
            "duration_days": duration_days,
            "event_observed": event_observed,
            "was_sanctioned": was_sanctioned,
            "participants_count": rng.integers(5, 100, n),
            "total_revisions": rng.integers(50, 700, n),
            "main_content_length": rng.integers(5000, 100000, n),
            "participants_with_blocks": rng.integers(0, 10, n),
            "ani_mentions": rng.integers(0, 50, n),
            "has_evidence_page": rng.binomial(1, 0.7, n),
            "has_workshop_page": rng.binomial(1, 0.6, n),
        }
    )

    print("\n--- DEMO MODE (synthetic data) ---")
    print("Kaplan-Meier (overall):")
    plot_km(demo_df, output_dir)
    print("\nKaplan-Meier (by sanctioned outcome):")
    plot_km(demo_df, output_dir, group_col="was_sanctioned")
    print("\nCox PH model:")
    run_cox(demo_df)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--arb-dir", default=str(RAW_ARB_DIR))
    parser.add_argument(
        "--output", default=str(DEFAULT_OUTPUT_DIR), help="Output directory for plots"
    )
    parser.add_argument(
        "--km-only", action="store_true", help="Skip Cox model, KM curves only"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with synthetic data (no real data required)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(message)s",
    )

    output_dir = Path(args.output)

    if args.demo:
        run_demo(output_dir)
        return

    # Load features
    try:
        df = load_features()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)

    arb_dir = Path(args.arb_dir)
    print(f"Extracting timestamps from {arb_dir} ...")
    survival_df = build_survival_dataset(df, arb_dir)

    if survival_df.empty:
        print(
            "No cases with timestamps found. "
            "This happens if data/raw/arbitration/ is empty "
            "or revision history wasn't fetched.\n"
            "Try: python scripts/survival_analysis.py --demo"
        )
        sys.exit(1)

    n_censored = (survival_df["event_observed"] == 0).sum()
    print(f"\nSurvival dataset: {len(survival_df)} cases")
    print(f"  Closed (event): {survival_df['event_observed'].sum()}")
    print(f"  Censored (open/unknown): {n_censored}")
    print(
        f"  Duration range: {survival_df['duration_days'].min()}–"
        f"{survival_df['duration_days'].max()} days"
    )

    print("\nKaplan-Meier (overall):")
    plot_km(survival_df, output_dir)

    print("\nKaplan-Meier by sanction outcome:")
    plot_km(survival_df, output_dir, group_col="was_sanctioned")

    if not args.km_only:
        print("\nCox proportional hazards:")
        run_cox(survival_df)


if __name__ == "__main__":
    main()
