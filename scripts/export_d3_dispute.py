#!/usr/bin/env python3
"""
Export a single arbitration case to a D3-ready JSON for the dispute timeline
visualization.

Output schema
─────────────
{
  "meta": { case identity, window, stages },
  "nodes": [ { editor identity, role, outcome, departure status } ],
  "events": [ { type, timestamp, actor, page_type, ... } ],   # chronological
  "links": [ { source, target, revert_count } ]               # for force-directed
}

Usage
─────
  python scripts/export_d3_dispute.py "Cold fusion 2"
  python scripts/export_d3_dispute.py "Cold fusion 2" --out viz/data/cold_fusion_2.json
  python scripts/export_d3_dispute.py --list            # show available cases
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

RAW_ARB = PROJECT_ROOT / "data" / "raw" / "arbitration"
D3_OUT = PROJECT_ROOT / "data" / "processed" / "d3"

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_REVERT_RE = re.compile(r"\b(revert|rv |undo|undid|rollback)\b", re.I)
_SECTION_RE = re.compile(r"/\*\s*(.+?)\s*\*/")
# Extracts the reverted username from comments like:
#   "Reverted edits by Foo" / "Undid revision 123 by Bar" / "Reverted 2 edits by Baz"
_REVERTED_BY_RE = re.compile(
    r"(?:reverted?\s+(?:\d+\s+)?edits?\s+by|undid?\s+revision\s+\d+\s+by)\s+([^\s\[\]|]+)",
    re.I,
)

PAGE_TYPE_MAP = {
    "main": "main",
    "evidence": "evidence",
    "workshop": "workshop",
    "proposed_decision": "proposed_decision",
    "final_decision": "final_decision",
}

BOT_SUFFIXES = ("bot", "Bot", "BOT")


def _is_bot(username: str) -> bool:
    return any(username.endswith(s) for s in BOT_SUFFIXES)


def _ts(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _days_between(a: str, b: str) -> int:
    return abs((_ts(b) - _ts(a)).days)


# ------------------------------------------------------------------
# Core build
# ------------------------------------------------------------------


def build_d3_payload(
    case_name: str, raw: dict, departure_threshold_days: int = 14
) -> dict:
    """Convert a raw case dict into the D3-ready payload."""

    pages = raw.get("pages", {})
    art_revs = raw.get("article_revisions", {})
    outcome = raw.get("outcome", {})
    participants_meta = raw.get("participants", {})  # dict username -> info
    participant_blocks = raw.get("participant_blocks", {})
    all_participants = set(raw.get("all_participants", []))

    # ------------------------------------------------------------------
    # 1. Collect all events from case pages (primary source of truth)
    # ------------------------------------------------------------------
    raw_events: list[dict] = []

    for page_key, page_data in pages.items():
        page_type = PAGE_TYPE_MAP.get(page_key, page_key)
        for rev in page_data.get("revisions", []):
            user = rev.get("user", "")
            if not user or _is_bot(user):
                continue
            comment = rev.get("comment", "") or ""
            is_revert = bool(_REVERT_RE.search(comment))
            section = ""
            m = _SECTION_RE.search(comment)
            if m:
                section = m.group(1).strip()

            reverted_from_comment = None
            if is_revert:
                m2 = _REVERTED_BY_RE.search(comment)
                if m2:
                    reverted_from_comment = m2.group(1).strip()

            raw_events.append(
                {
                    "revid": rev.get("revid"),
                    "timestamp": rev["timestamp"],
                    "actor": user,
                    "page_type": page_type,
                    "comment": comment[:120],
                    "size": rev.get("size"),
                    "is_revert": is_revert,
                    "section": section,
                    "reverted_from_comment": reverted_from_comment,
                }
            )

    if not raw_events:
        raise ValueError(f"No case page events found for '{case_name}'")

    raw_events.sort(key=lambda e: e["timestamp"])

    # Case start: first edit on the main page (when the case was filed)
    case_start_ts = raw_events[0]["timestamp"]

    # Case end: anchor to last substantive deliberation page rather than main,
    # which can receive minor maintenance edits years later.
    # Priority: proposed_decision > workshop > evidence > main
    def _last_ts_for_page(page_key: str) -> str | None:
        revs = pages.get(page_key, {}).get("revisions", [])
        non_bot = [r["timestamp"] for r in revs if not _is_bot(r.get("user", ""))]
        return max(non_bot) if non_bot else None

    case_end_ts = (
        _last_ts_for_page("proposed_decision")
        or _last_ts_for_page("final_decision")
        or _last_ts_for_page("workshop")
        or _last_ts_for_page("evidence")
        or raw_events[-1]["timestamp"]
    )

    # Clamp raw_events to the core window
    raw_events = [e for e in raw_events if e["timestamp"] <= case_end_ts]

    # ------------------------------------------------------------------
    # 2. Also collect article revisions that fall within the case window
    #    (only include editors already active on case pages, to avoid
    #     pulling in 300+ article-history editors who aren't part of the dispute)
    # ------------------------------------------------------------------
    case_page_editors = {e["actor"] for e in raw_events} | all_participants

    art_events: list[dict] = []
    for art_title, revs in art_revs.items():
        for rev in revs:
            user = rev.get("user", "")
            ts = rev.get("timestamp", "")
            if not user or _is_bot(user):
                continue
            if ts < case_start_ts or ts > case_end_ts:
                continue
            if user not in case_page_editors:
                continue
            comment = rev.get("comment", "") or ""
            is_revert = bool(_REVERT_RE.search(comment))
            art_events.append(
                {
                    "revid": rev.get("revid"),
                    "timestamp": ts,
                    "actor": user,
                    "page_type": "article",
                    "article": art_title,
                    "comment": comment[:120],
                    "size": rev.get("size"),
                    "is_revert": is_revert,
                    "section": "",
                }
            )

    all_events = sorted(raw_events + art_events, key=lambda e: e["timestamp"])

    # ------------------------------------------------------------------
    # 3. Stage boundaries (first/last edit on each page type)
    # ------------------------------------------------------------------
    stage_bounds: dict[str, dict] = {}
    for e in all_events:
        pt = e["page_type"]
        if pt not in stage_bounds:
            stage_bounds[pt] = {"start": e["timestamp"], "end": e["timestamp"]}
        else:
            stage_bounds[pt]["end"] = e["timestamp"]

    stages = [
        {"name": pt, **bounds}
        for pt, bounds in sorted(stage_bounds.items(), key=lambda kv: kv[1]["start"])
    ]

    # ------------------------------------------------------------------
    # 4. Build editor profiles
    # ------------------------------------------------------------------
    editor_first: dict[str, str] = {}
    editor_last: dict[str, str] = {}
    editor_edits: Counter = Counter()
    editor_reverts: Counter = Counter()
    editor_pages: dict[str, set] = defaultdict(set)

    for e in all_events:
        actor = e["actor"]
        ts = e["timestamp"]
        if actor not in editor_first or ts < editor_first[actor]:
            editor_first[actor] = ts
        if actor not in editor_last or ts > editor_last[actor]:
            editor_last[actor] = ts
        editor_edits[actor] += 1
        if e["is_revert"]:
            editor_reverts[actor] += 1
        editor_pages[actor].add(e["page_type"])

    # ------------------------------------------------------------------
    # 5. Determine roles
    #    Heuristic: arbitrators edit proposed_decision heavily;
    #    clerks show up in main early; filers named in all_participants.
    # ------------------------------------------------------------------
    arb_candidates = {
        e["actor"] for e in raw_events if e["page_type"] == "proposed_decision"
    }

    def _role(username: str) -> str:
        meta = participants_meta.get(username, {})
        if meta.get("is_admin") and username in arb_candidates:
            return "arbitrator"
        if username in all_participants:
            return "participant"
        if username in arb_candidates:
            return "arbitrator_candidate"
        return "observer"

    # ------------------------------------------------------------------
    # 6. Sanctions from outcome remedies
    # ------------------------------------------------------------------
    # Map target_user -> list of sanctions
    sanctions: dict[str, list] = defaultdict(list)
    for remedy in outcome.get("remedies", []):
        stype = remedy.get("sanction_type", "other")
        target = remedy.get("target_user", "")
        desc = remedy.get("description", "") or ""
        dur = remedy.get("duration")
        if target and stype in ("block", "restriction", "ban", "topic_ban"):
            sanctions[target].append(
                {
                    "sanction_type": stype,
                    "description": desc[:200],
                    "duration": dur,
                }
            )

    # ------------------------------------------------------------------
    # 7. Block history (actual Wikipedia blocks, not just case sanctions)
    # ------------------------------------------------------------------
    blocks: dict[str, list] = {}
    for user, block_list in participant_blocks.items():
        if isinstance(block_list, list) and block_list:
            blocks[user] = [
                {
                    "timestamp": b.get("timestamp"),
                    "expiry": b.get("expiry"),
                    "reason": (b.get("reason") or "")[:200],
                    "blocked_by": b.get("blocked_by"),
                }
                for b in block_list
            ]

    # ------------------------------------------------------------------
    # 8. Departure detection
    #    "departed" = editor had meaningful activity (>=2 edits) but their
    #    last edit was more than `departure_threshold_days` before case end
    #    OR before a proportional fraction of the case duration.
    #    Caps departure_threshold_days at 20% of case duration so short
    #    thresholds don't mark everyone as departed on long cases.
    # ------------------------------------------------------------------
    case_duration_days_total = _days_between(case_start_ts, case_end_ts)
    effective_threshold = max(
        departure_threshold_days,
        int(case_duration_days_total * 0.15),  # at least 15% of case duration
    )

    def _departed(username: str) -> bool:
        if editor_edits.get(username, 0) < 2:
            return False  # too little activity to call a "departure"
        last = editor_last.get(username, "")
        if not last:
            return False
        return _days_between(last, case_end_ts) > effective_threshold

    # ------------------------------------------------------------------
    # 9. Assemble nodes (only editors active during case)
    # ------------------------------------------------------------------
    nodes = []
    for username in sorted(editor_first.keys()):
        meta = participants_meta.get(username, {})
        node = {
            "id": f"editor:{username}",
            "username": username,
            "role": _role(username),
            "first_active": editor_first[username],
            "last_active": editor_last[username],
            "total_edits": editor_edits[username],
            "revert_count": editor_reverts[username],
            "pages_active": sorted(editor_pages[username]),
            "is_admin": meta.get("is_admin", False),
            "edit_count_global": meta.get("edit_count"),
            "registration": meta.get("registration"),
            # Outcome
            "sanctions": sanctions.get(username, []),
            "blocks": blocks.get(username, []),
            "departed": _departed(username),
            "days_active": _days_between(editor_first[username], editor_last[username]),
        }
        nodes.append(node)

    # Sort nodes: arbitrators first, then by first_active
    role_order = {
        "arbitrator": 0,
        "participant": 1,
        "arbitrator_candidate": 2,
        "observer": 3,
    }
    nodes.sort(key=lambda n: (role_order.get(n["role"], 9), n["first_active"]))

    # ------------------------------------------------------------------
    # 10. Build typed event stream
    # ------------------------------------------------------------------
    # Tag each event with its "display type"
    # For reverts, try to identify who was reverted (previous rev by different user)
    prev_by_page: dict[str, str] = {}  # page -> last editor

    events = []
    for e in all_events:
        pt = e["page_type"]
        actor = e["actor"]
        event_type = "revert" if e["is_revert"] else "edit"

        # Determine who was reverted:
        # Priority 1 – extracted directly from comment ("Undid revision X by Y")
        # Priority 2 – previous editor on same page (heuristic)
        reverted = e.get("reverted_from_comment")
        if not reverted and e["is_revert"]:
            prev = prev_by_page.get(pt)
            if prev and prev != actor:
                reverted = prev

        events.append(
            {
                "type": event_type,
                "timestamp": e["timestamp"],
                "actor": actor,
                "page_type": pt,
                "article": e.get("article"),
                "comment": e["comment"],
                "section": e.get("section", ""),
                "reverted": reverted,
                "revid": e.get("revid"),
            }
        )
        prev_by_page[pt] = actor

    # Add sanction pseudo-events at case end (we don't have exact vote timestamps)
    decision_date = outcome.get("decision_date") or case_end_ts
    for username, sanc_list in sanctions.items():
        for s in sanc_list:
            events.append(
                {
                    "type": "sanction",
                    "timestamp": decision_date,
                    "actor": username,
                    "page_type": "outcome",
                    "sanction_type": s["sanction_type"],
                    "description": s["description"],
                    "duration": s.get("duration"),
                }
            )

    events.sort(key=lambda e: e["timestamp"])

    # ------------------------------------------------------------------
    # 11. Build revert links (weighted directed pairs)
    # ------------------------------------------------------------------
    revert_pairs: Counter = Counter()
    for e in events:
        if e["type"] == "revert" and e.get("reverted"):
            revert_pairs[(e["actor"], e["reverted"])] += 1

    links = [
        {
            "source": f"editor:{src}",
            "target": f"editor:{tgt}",
            "revert_count": cnt,
        }
        for (src, tgt), cnt in revert_pairs.most_common()
    ]

    # ------------------------------------------------------------------
    # 12. Final payload
    # ------------------------------------------------------------------
    return {
        "meta": {
            "case_name": case_name,
            "case_prefix": raw.get("case_prefix", ""),
            "case_start": case_start_ts,
            "case_end": case_end_ts,
            "case_duration_days": _days_between(case_start_ts, case_end_ts),
            "total_events": len(events),
            "total_editors": len(nodes),
            "outcome_status": outcome.get("status"),
            "stages": stages,
        },
        "nodes": nodes,
        "events": events,
        "links": links,
    }


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------


def _find_case_file(case_name: str) -> Path:
    # Try exact stem match first
    candidate = RAW_ARB / f"{case_name}.json"
    if candidate.exists():
        return candidate
    # Search all enriched files
    for path in sorted(RAW_ARB.glob("*.json")):
        if path.name.startswith(("arb_dfs_", "arbitration_cases_")):
            continue
        try:
            with open(path) as f:
                d = json.load(f)
            if d.get("case_name") == case_name:
                return path
        except Exception:
            continue
    raise FileNotFoundError(f"No case JSON found for '{case_name}'")


def _list_cases():
    cases = []
    for path in sorted(RAW_ARB.glob("*.json")):
        if path.name.startswith(("arb_dfs_", "arbitration_cases_")):
            continue
        try:
            with open(path) as f:
                d = json.load(f)
            if isinstance(d.get("pages"), dict):
                cases.append(d.get("case_name", path.stem))
        except Exception:
            continue
    for c in sorted(cases):
        print(c)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "case_name", nargs="?", help="Arbitration case name (e.g. 'Cold fusion 2')"
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output JSON path (default: data/processed/d3/<slug>.json)",
    )
    parser.add_argument(
        "--list", action="store_true", help="List available cases and exit"
    )
    parser.add_argument(
        "--departure-days",
        type=int,
        default=14,
        help="Days before case end to call an editor 'departed' (default: 14)",
    )
    args = parser.parse_args()

    if args.list:
        _list_cases()
        return

    if not args.case_name:
        parser.error("case_name is required (or use --list to see options)")

    path = _find_case_file(args.case_name)
    with open(path) as f:
        raw = json.load(f)

    payload = build_d3_payload(
        args.case_name, raw, departure_threshold_days=args.departure_days
    )

    slug = args.case_name.lower().replace(" ", "_").replace("/", "_")
    out_path = args.out or (D3_OUT / f"{slug}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    meta = payload["meta"]
    print(f"Wrote {out_path}")
    print(f"  Case:        {meta['case_name']}")
    print(
        f"  Window:      {meta['case_start'][:10]} → {meta['case_end'][:10]}  ({meta['case_duration_days']} days)"
    )
    print(f"  Editors:     {meta['total_editors']}")
    print(f"  Events:      {meta['total_events']}")
    print(f"  Links:       {len(payload['links'])} revert pairs")

    sanctioned = [n for n in payload["nodes"] if n["sanctions"]]
    departed = [n for n in payload["nodes"] if n["departed"] and not n["sanctions"]]
    print(
        f"  Sanctioned:  {len(sanctioned)} editors → {[n['username'] for n in sanctioned]}"
    )
    print(f"  Departed:    {len(departed)} editors left before case end")


if __name__ == "__main__":
    main()
