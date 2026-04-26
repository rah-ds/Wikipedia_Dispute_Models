"""
process_arbitration_for_dashboard.py

Processes clean_arbitration_cases_*.json into a structured JSON payload
consumed by the React arbitration dashboard.

Also reads BPMN files from dashboard/public/bpmn/ folders to generate
per-case statistics from the corresponding raw data files.

Output: data/processed/dashboard_data.json
        dashboard/public/data/dashboard_data.json
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
DEFAULT_RAW_JSON = (
    BASE / "data" / "processed" / "clean_arbitration_cases_20260216_163707.json"
)
OUT_JSON = BASE / "data" / "processed" / "dashboard_data.json"
PUBLIC_OUT_JSON = BASE / "dashboard" / "public" / "data" / "dashboard_data.json"

BPMN_ARB_DIR = BASE / "dashboard" / "public" / "bpmn" / "arb"
BPMN_DRN_DIR = BASE / "dashboard" / "public" / "bpmn" / "drn"
BPMN_RFC_DIR = BASE / "dashboard" / "public" / "bpmn" / "rfc"


# ──────────────────────────────────────────────
# Data file discovery
# ──────────────────────────────────────────────

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


def find_drn_json() -> Path | None:
    candidates = sorted(
        BASE.glob("data/raw/drn/drn_all_cases_*.json"), reverse=True
    )
    return candidates[0] if candidates else None


def find_rfc_json() -> Path | None:
    candidates = sorted(
        BASE.glob("data/raw/rfc/all_requests_for_comments_*.json"), reverse=True
    )
    return candidates[0] if candidates else None


# ──────────────────────────────────────────────
# Regex helpers
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

# Wikilink patterns
USER_RE       = re.compile(r"\[\[User:([^\]|/\n]+)",           re.IGNORECASE)
USER_PIPE_RE  = re.compile(r"\{\{[Uu]ser\|([^}|]+)")
USER_TALK_RE  = re.compile(r"\[\[User[ _]talk:([^\]|/\n]+)",   re.IGNORECASE)
WIKI_REF_RE   = re.compile(r"\[\[(?:Wikipedia|WP):",           re.IGNORECASE)
WIKI_TALK_RE  = re.compile(r"\[\[Wikipedia[ _]talk:",          re.IGNORECASE)
RFC_STATUS_RE    = re.compile(r"\|[ \t]*status[ \t]*=[ \t]*(\w+)", re.IGNORECASE)
CASE_OPENED_YEAR = re.compile(r"Case Opened.*?(\d{4})", re.IGNORECASE | re.DOTALL)


# ──────────────────────────────────────────────
# Extraction helpers
# ──────────────────────────────────────────────

def extract_case_year(full_text: str) -> int | None:
    """Extract the year from the 'Case Opened' line in full_text."""
    m = CASE_OPENED_YEAR.search(full_text[:300])
    if m:
        year = int(m.group(1))
        if 2000 <= year <= 2100:
            return year
    return None


def parse_duration(full_text: str) -> int | None:
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
    return len(re.findall(r"Statement by", full_text, re.IGNORECASE))


def extract_users(text: str) -> set[str]:
    """Unique [[User:…]] wikilinks."""
    return set(USER_RE.findall(text))


def extract_user_talk(text: str) -> set[str]:
    """Unique [[User talk:…]] wikilinks."""
    return set(USER_TALK_RE.findall(text))


def extract_drn_users(text: str) -> set[str]:
    """Unique User: wikilinks and {{User|…}} template values."""
    users: set[str] = set()
    users.update(USER_RE.findall(text))
    users.update(USER_PIPE_RE.findall(text))
    return users


def count_wiki_refs(text: str) -> int:
    """Total (non-unique) count of [[Wikipedia: or [[WP: references."""
    return len(WIKI_REF_RE.findall(text))


def count_wiki_talk_refs(text: str) -> int:
    """Total count of [[Wikipedia talk: references."""
    return len(WIKI_TALK_RE.findall(text))


def extract_rfc_status(content: str) -> str | None:
    m = RFC_STATUS_RE.search(content)
    return m.group(1).lower() if m else None


def drn_source_url(source: str) -> str | None:
    """Convert DRN 'source' field to a Wikipedia URL when it's an archive page."""
    if not source or source == "live":
        return None
    # e.g. "Wikipedia:Dispute resolution noticeboard/Archive 8"
    #   → https://en.wikipedia.org/wiki/Wikipedia:Dispute_resolution_noticeboard/Archive_8
    slug = source.replace(" ", "_")
    return f"https://en.wikipedia.org/wiki/{slug}"


# ──────────────────────────────────────────────
# Case matching (BPMN stem → raw data entry)
# ──────────────────────────────────────────────

def _normalize(s: str) -> str:
    return re.sub(r"[\s_\-]+", " ", s).lower().strip()


def match_arb_case(stem: str, cases: list[dict]) -> dict | None:
    """Match a BPMN stem to an arb case by title fragment."""
    # Numbered: arb_0010_Abortion  → fragment "Abortion"
    m = re.match(r"arb_\d+_(.*)", stem, re.IGNORECASE)
    if m:
        frag = _normalize(m.group(1))
    else:
        # HF-style: arb_Wikipedia_Arbitration_Requests_Case_Abortion
        frag = _normalize(re.sub(r"^arb_", "", stem, flags=re.IGNORECASE))

    if not frag:
        return None

    for case in cases:
        title = _normalize(case.get("title", ""))
        if frag in title:
            return case
        # Partial: all words of short fragment present in title
        words = frag.split()
        if words and all(w in title for w in words[:4]):
            return case
    return None


def match_drn_case(stem: str, cases: list[dict]) -> dict | None:
    """Match a BPMN stem to a DRN case by title fragment."""
    m = re.match(r"case_\d+_(.*)", stem, re.IGNORECASE)
    frag = _normalize(m.group(1) if m else stem)
    if not frag:
        return None
    for case in cases:
        title = _normalize(case.get("title", ""))
        # Allow either direction of containment (titles can be truncated in filename)
        if frag[:20] in title or title[:20] in frag or title.startswith(frag[:15]):
            return case
    return None


def match_rfc_case(stem: str, rfcs: list[dict]) -> dict | None:
    """Match a BPMN stem to an RFC entry by title fragment."""
    m = re.match(r"rfc_\d+_(.*)", stem, re.IGNORECASE)
    frag = _normalize(m.group(1) if m else stem)
    if not frag:
        return None
    for rfc in rfcs:
        # RFC titles are like "Requests for comment/Global AbuseFilter"
        title = _normalize(rfc.get("title", "").split("/", 1)[-1])
        if frag[:20] in title or title[:20] in frag:
            return rfc
    return None


# ──────────────────────────────────────────────
# Per-case stat builders
# ──────────────────────────────────────────────

def arb_case_stats(case: dict) -> dict:
    text = (case.get("full_text") or "") + " " + " ".join(
        v for v in (case.get("sections") or {}).values() if v
    )
    return {
        "userLinks":    len(extract_users(text)),
        "userTalkLinks": len(extract_user_talk(text)),
        "wikiRefs":     count_wiki_refs(text),
        "wikiTalkRefs": count_wiki_talk_refs(text),
        "url":          case.get("url"),
    }


def drn_case_stats(case: dict) -> dict:
    content = case.get("content") or ""
    return {
        "userLinks":    len(extract_drn_users(content)),
        "userTalkLinks": len(extract_user_talk(content)),
        "wikiRefs":     count_wiki_refs(content),
        "sourceUrl":    drn_source_url(case.get("source", "")),
    }


def rfc_case_stats(rfc: dict) -> dict:
    content = rfc.get("content") or ""
    return {
        "userLinks":    len(extract_drn_users(content)),
        "userTalkLinks": len(extract_user_talk(content)),
        "wikiRefs":     count_wiki_refs(content),
        "status":       extract_rfc_status(content),
        "url":          rfc.get("url"),
    }


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main() -> None:
    # ── Load data ─────────────────────────────
    raw_json = find_raw_json()
    print(f"Loading {raw_json} …")
    with open(raw_json, encoding="utf-8") as fh:
        arb_cases = json.load(fh)

    drn_cases: list[dict] = []
    drn_path = find_drn_json()
    if drn_path:
        print(f"Loading {drn_path} …")
        with open(drn_path, encoding="utf-8") as fh:
            drn_cases = json.load(fh).get("cases", [])

    rfc_list: list[dict] = []
    rfc_path = find_rfc_json()
    if rfc_path:
        print(f"Loading {rfc_path} …")
        with open(rfc_path, encoding="utf-8") as fh:
            rfc_list = json.load(fh).get("rfcs", [])

    # ── Overview stats (all arb cases) ────────
    total_cases = len(arb_cases)
    all_users:      set[str] = set()
    all_user_talks: set[str] = set()
    stmt_distribution: Counter = Counter()
    durations: list[int] = []
    remedy_verbs: Counter = Counter()
    total_wiki_refs = 0
    year_counts: Counter = Counter()

    for case in arb_cases:
        full = case.get("full_text") or ""
        sections = case.get("sections") or {}
        all_text = full + " " + " ".join(v for v in sections.values() if v)

        all_users.update(extract_users(all_text))
        all_user_talks.update(extract_user_talk(all_text))
        total_wiki_refs += count_wiki_refs(all_text)

        stmt_distribution[count_statement_by(full)] += 1

        dur = parse_duration(full)
        if dur is not None:
            durations.append(dur)

        year = extract_case_year(full)
        if year is not None:
            year_counts[year] += 1

        remedy_text = sections.get("Remedies") or ""
        for m in ACTION_VERBS.finditer(remedy_text):
            remedy_verbs[m.group(0).lower()] += 1

    avg_duration = round(sum(durations) / len(durations), 1) if durations else None
    stmt_dist_list = [
        {"statementCount": k, "cases": v}
        for k, v in sorted(stmt_distribution.items())
    ]
    top_verbs = [
        {"verb": word, "count": cnt} for word, cnt in remedy_verbs.most_common(15)
    ]
    cases_per_year = [
        {"year": yr, "cases": cnt} for yr, cnt in sorted(year_counts.items())
    ]

    # ── Per-case stats from BPMN folders ──────
    case_stats: dict[str, dict] = {}

    SKIP = {"arb_aggregate_workflow", "drn_aggregate_workflow", "rfc_aggregate_workflow"}

    if BPMN_ARB_DIR.exists():
        print("\nMatching ARB cases …")
        for bpmn in sorted(BPMN_ARB_DIR.glob("*.bpmn")):
            stem = bpmn.stem
            if stem in SKIP:
                continue
            case = match_arb_case(stem, arb_cases)
            if case:
                case_stats[stem] = {"type": "arb", **arb_case_stats(case)}
                print(f"  ✓ {stem[:55]} → {case.get('title', '')[:45]}")
            else:
                print(f"  ✗ {stem[:55]}  (no match)")

    if BPMN_DRN_DIR.exists() and drn_cases:
        print("\nMatching DRN cases …")
        for bpmn in sorted(BPMN_DRN_DIR.glob("*.bpmn")):
            stem = bpmn.stem
            if stem in SKIP:
                continue
            case = match_drn_case(stem, drn_cases)
            if case:
                case_stats[stem] = {"type": "drn", **drn_case_stats(case)}
                print(f"  ✓ {stem[:55]} → {case.get('title', '')[:45]}")
            else:
                print(f"  ✗ {stem[:55]}  (no match)")

    if BPMN_RFC_DIR.exists() and rfc_list:
        print("\nMatching RFC cases …")
        for bpmn in sorted(BPMN_RFC_DIR.glob("*.bpmn")):
            stem = bpmn.stem
            if stem in SKIP:
                continue
            rfc = match_rfc_case(stem, rfc_list)
            if rfc:
                case_stats[stem] = {"type": "rfc", **rfc_case_stats(rfc)}
                print(f"  ✓ {stem[:55]} → {rfc.get('title', '')[:45]}")
            else:
                print(f"  ✗ {stem[:55]}  (no match)")

    # ── Build output ──────────────────────────
    dashboard = {
        "totalCases":              total_cases,
        "totalUserLinks":          len(all_users),
        "totalUserTalkLinks":      len(all_user_talks),
        "totalInvolvedParties":    len(all_users) + len(all_user_talks),
        "totalWikipediaRefs":      total_wiki_refs,
        "averageDurationDays":     avg_duration,
        "casesWithDuration":       len(durations),
        "statementByDistribution": stmt_dist_list,
        "topRemedyVerbs":          top_verbs,
        "casesPerYear":            cases_per_year,
        "caseStats":               case_stats,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(dashboard, fh, indent=2)
    with open(PUBLIC_OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(dashboard, fh, indent=2)

    print(f"\nWrote {OUT_JSON}")
    print(f"Wrote {PUBLIC_OUT_JSON}")
    print(f"  totalCases          : {total_cases}")
    print(f"  totalUserLinks      : {len(all_users)}")
    print(f"  totalUserTalkLinks  : {len(all_user_talks)}")
    print(f"  totalWikipediaRefs  : {total_wiki_refs}")
    print(f"  averageDurationDays : {avg_duration}")
    print(f"  caseStats entries   : {len(case_stats)}")
    print(f"  top verb            : {top_verbs[0] if top_verbs else 'n/a'}")


if __name__ == "__main__":
    main()
