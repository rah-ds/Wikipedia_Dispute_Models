"""
process_arbitration_for_dashboard.py

Processes clean_arbitration_cases_*.json into a structured JSON payload
consumed by the React arbitration dashboard.

Output: data/processed/dashboard_data.json
"""

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
BASE = Path(__file__).resolve().parent.parent
DEFAULT_RAW_JSON = BASE / "data" / "processed" / "clean_arbitration_cases_20260216_163707.json"
OUT_JSON = BASE / "data" / "processed" / "dashboard_data.json"
PUBLIC_OUT_JSON = BASE / "dashboard" / "public" / "data" / "dashboard_data.json"


def find_raw_json() -> Path:
    if DEFAULT_RAW_JSON.exists():
        return DEFAULT_RAW_JSON

    candidates = sorted(
        BASE.glob("data/processed/clean_arbitration_cases_*.json"),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            "No clean_arbitration_cases_*.json file found in data/processed. "
            "Run scripts/clean_arbitration_cases_data.py first."
        )
    return candidates[0]


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
DATE_PAT = re.compile(r"\d{1,2}:\d{2}, \d{1,2} \w+ \d{4}")
DATE_FMT = "%H:%M, %d %B %Y"

ACTION_VERBS = re.compile(
    r"\b(banned|blocked|warned|counselled|reminded|admonished|restricted|"
    r"sanctioned|prohibited|placed|required|desysopped|removed|topic-banned|"
    r"community-banned|limited|barred|forbidden|cautioned|noted|revoked|"
    r"suspended|stripped)\b",
    re.IGNORECASE,
)


def parse_duration(full_text: str) -> int | None:
    """Return case duration in days from the first two timestamps in the text."""
    dates = DATE_PAT.findall(full_text[:600])
    if len(dates) < 2:
        return None
    try:
        d1 = datetime.strptime(dates[0], DATE_FMT)
        d2 = datetime.strptime(dates[1], DATE_FMT)
        delta = abs((d2 - d1).days)
        return delta if 0 < delta < 3000 else None
    except ValueError:
        return None


def count_statement_by(full_text: str) -> int:
    """Count 'Statement by' headers in the full page text."""
    return len(re.findall(r"Statement by", full_text, re.IGNORECASE))


def extract_users(full_text: str) -> set[str]:
    """Return all unique User: wikilinks."""
    return set(re.findall(r"\[\[User:([^\]|/\n]+)", full_text, re.IGNORECASE))


def extract_admins(full_text: str) -> set[str]:
    """Return all unique User_talk: wikilinks (proxy for admins/involved admins)."""
    return set(re.findall(r"\[\[User[ _]talk:([^\]|/\n]+)", full_text, re.IGNORECASE))


# ──────────────────────────────────────────────
# Main processing
# ──────────────────────────────────────────────
def main() -> None:
    raw_json = find_raw_json()
    print(f"Loading {raw_json} …")
    with open(raw_json, encoding="utf-8") as fh:
        cases = json.load(fh)

    total_cases = len(cases)
    all_users: set[str] = set()
    all_admins: set[str] = set()
    stmt_distribution: Counter = Counter()
    durations: list[int] = []
    remedy_verbs: Counter = Counter()

    for case in cases:
        full = case.get("full_text") or ""
        sections = case.get("sections") or {}

        # ── Parties ──────────────────────────────
        all_users.update(extract_users(full))
        all_admins.update(extract_admins(full))

        # ── Statement by count ───────────────────
        stmt_count = count_statement_by(full)
        stmt_distribution[stmt_count] += 1

        # ── Duration ─────────────────────────────
        dur = parse_duration(full)
        if dur is not None:
            durations.append(dur)

        # ── Remedy verbs ─────────────────────────
        remedy_text = sections.get("Remedies") or ""
        for m in ACTION_VERBS.finditer(remedy_text):
            remedy_verbs[m.group(0).lower()] += 1

    avg_duration = round(sum(durations) / len(durations), 1) if durations else None

    # Statement-by distribution as sorted list of {count, cases}
    stmt_dist_list = [
        {"statementCount": k, "cases": v} for k, v in sorted(stmt_distribution.items())
    ]

    # Top remedy verbs
    top_verbs = [
        {"verb": word, "count": cnt} for word, cnt in remedy_verbs.most_common(15)
    ]

    dashboard = {
        "totalCases": total_cases,
        "totalUserLinks": len(all_users),
        "totalAdminLinks": len(all_admins),
        "totalInvolvedParties": len(all_users) + len(all_admins),
        "averageDurationDays": avg_duration,
        "casesWithDuration": len(durations),
        "statementByDistribution": stmt_dist_list,
        "topRemedyVerbs": top_verbs,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(dashboard, fh, indent=2)

    with open(PUBLIC_OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(dashboard, fh, indent=2)

    print(f"Wrote {OUT_JSON}")
    print(f"Wrote {PUBLIC_OUT_JSON}")
    print(f"  totalCases            : {total_cases}")
    print(f"  totalUserLinks        : {len(all_users)}")
    print(f"  totalAdminLinks       : {len(all_admins)}")
    print(f"  averageDurationDays   : {avg_duration}")
    print(f"  top verb              : {top_verbs[0] if top_verbs else 'n/a'}")


if __name__ == "__main__":
    main()
