"""Target variable construction for Wikipedia dispute models.

Three primary questions, each requiring a different target:

  1. was_sanctioned  — binary
     Did the case result in any formal sanctions (topic bans, blocks, etc.)?
     Uses: remedy_count > 0
     Positive rate in current data: ~24% (21 / 87)

  2. was_closed  — binary
     Was the case formally closed (vs. still open or outcome unknown)?
     Uses: case_closed == 1
     Positive rate in current data: ~84% (73 / 87)

  3. outcome_class  — 3-class
     How did the case conclude?
     "sanctioned"  = closed with remedies (remedy_count > 0 AND case_closed)
     "dismissed"   = closed, no remedies (case_closed AND remedy_count == 0)
     "unresolved"  = still open or outcome unknown

  4. severity  — continuous / ordinal
     How many remedies were imposed? (remedy_count, range 0–22)
     Useful as a regression target once the class imbalance issue is addressed.

--- IMPORTANT SCOPE NOTE ---

All cases in data/raw/arbitration/ reached ArbCom — they ALL escalated.
The "did it escalate?" question therefore cannot be answered from this
dataset alone: there is no comparison group of disputes that stayed at
Talk / DRN / ANI and resolved without reaching arbitration.

To build a proper escalation classifier you need:
  - DRN cases resolved without ANI involvement  (Talk→DRN success)
  - ANI reports closed without ArbCom referral  (ANI success)
  - Control talk pages with no venue escalation  (Talk success)

See docs/survival_analysis.md §"Selection Bias" for the full discussion.

LEAKAGE GUARD
Columns excluded from PREDICTOR_COLS because they are outcomes:
  outcome_status, case_closed, has_active_remedies,
  remedy_count, finding_count, principle_count,
  has_proposed_decision  (proxy for case having reached a decision)
"""

from __future__ import annotations

import pandas as pd

# ---------------------------------------------------------------------------
# Feature columns that are legitimate predictors (not outcomes)
# ---------------------------------------------------------------------------

PREDICTOR_COLS: list[str] = [
    # Case volume
    "total_revisions",
    "case_pages_found",
    "talk_pages_found",
    "has_evidence_page",
    "has_workshop_page",
    "main_content_length",
    # Participant profile
    "participants_count",
    "participants_enriched",
    "participants_with_blocks",
    "participants_with_abuse_hits",
    # Article involvement
    "articles_extracted",
    "articles_with_revisions",
    # Cross-venue signals
    "ani_mentions",
    "drn_mentions",
    # Lifecycle (from dispute_venues/ — only populated when fetch_lifecycle ran)
    "has_lifecycle_data",
    "lifecycle_stages_with_data",
    "lifecycle_total_revisions",
    "lifecycle_ani_reports",
    "lifecycle_drn_mentions",
    "lifecycle_talk_pages",
    "lifecycle_has_stage_talk",
    "lifecycle_has_stage_drn",
    "lifecycle_has_stage_ani",
    # NOTE: lifecycle_has_stage_arbcom excluded — it mirrors the selection criterion
]


# ---------------------------------------------------------------------------
# Target constructors
# ---------------------------------------------------------------------------


def make_was_sanctioned(df: pd.DataFrame) -> pd.Series:
    """Binary: did the case result in any sanctions / remedies?

    Positive = at least one remedy was imposed (remedy_count > 0).
    Base rate in current 87-case dataset: ~24%.

    NOTE: has_active_remedies is currently unpopulated for most cases
    (outcome parser limitation). Using remedy_count > 0 instead.
    """
    return (df["remedy_count"] > 0).astype(int).rename("was_sanctioned")


def make_was_closed(df: pd.DataFrame) -> pd.Series:
    """Binary: was the case formally closed?

    Positive = case_closed == 1.
    Base rate in current 87-case dataset: ~84% (73 closed, 14 open/unknown).
    """
    return df["case_closed"].astype(int).rename("was_closed")


def make_outcome_class(df: pd.DataFrame) -> pd.Series:
    """Three-class outcome: sanctioned / dismissed / unresolved.

    Labels:
      "sanctioned"  — closed AND remedy_count > 0
      "dismissed"   — closed AND remedy_count == 0
      "unresolved"  — open or outcome unknown
    """
    closed = df["case_closed"] == 1
    sanctioned = df["remedy_count"] > 0

    result = pd.Series("unresolved", index=df.index, name="outcome_class")
    result[closed & sanctioned] = "sanctioned"
    result[closed & ~sanctioned] = "dismissed"
    return result


def make_severity(df: pd.DataFrame) -> pd.Series:
    """Continuous target: number of remedies imposed (0–22).

    Skewed distribution (median = 0, max = 22).
    Consider log1p transform before regression, or treat as ordinal.
    """
    return df["remedy_count"].clip(lower=0).rename("severity")


# ---------------------------------------------------------------------------
# Convenience: all targets in one call
# ---------------------------------------------------------------------------


def make_all_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame with all target columns attached to the index."""
    return pd.concat(
        [
            make_was_sanctioned(df),
            make_was_closed(df),
            make_outcome_class(df),
            make_severity(df),
        ],
        axis=1,
    )
