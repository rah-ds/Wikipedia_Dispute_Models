#!/usr/bin/env python3
"""
Batch-export every enriched arbitration case JSON to a D3-ready payload and
write a manifest.json summarising all cases (including those that failed).

Output
------
  data/processed/d3/<slug>.json   — per-case D3 payload (only for successes)
  data/processed/d3/manifest.json — index of all cases with summary stats

Usage
-----
  python scripts/export_d3_all.py
  python scripts/export_d3_all.py --departure-days 14
  python scripts/export_d3_all.py --workers 4       # parallel (default: 4)
  python scripts/export_d3_all.py --force            # re-export existing files
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.export_d3_dispute import build_d3_payload

RAW_ARB = PROJECT_ROOT / "data" / "raw" / "arbitration"
D3_OUT = PROJECT_ROOT / "data" / "processed" / "d3"

SKIP_PREFIXES = ("arb_dfs_", "arbitration_cases_")

logger = logging.getLogger("export_d3_all")


_SUBPAGE_MAP = {
    "(main)": "main",
    "evidence": "evidence",
    "workshop": "workshop",
    "proposed decision": "proposed_decision",
    "proposed_decision": "proposed_decision",
}


def _normalize_new_format(raw: dict) -> dict:
    """Convert lifecycle_stages format → pages-dict format expected by build_d3_payload."""
    stages = raw.get("lifecycle_stages", {})
    arbcom = stages.get("stage_5_arbcom", {})
    pages_list = arbcom.get("pages", [])

    pages = {}
    for page in pages_list:
        subpage = page.get("subpage", "(main)").strip().lstrip("/").lower()
        key = _SUBPAGE_MAP.get(subpage, subpage.replace(" ", "_"))
        pages[key] = {
            "title": page.get("title", ""),
            "url": page.get("url", ""),
            "content": page.get("content", ""),
            "content_length": page.get("content_length", 0),
            "revisions": page.get("revisions", []),
            "revision_count": page.get("revision_count", 0),
        }

    # participants: list of usernames → dict keyed by username
    participants_raw = raw.get("participants", [])
    if isinstance(participants_raw, list):
        participants_meta = {u: {"username": u} for u in participants_raw}
    else:
        participants_meta = participants_raw

    normalized = dict(raw)
    normalized["pages"] = pages
    normalized["participants"] = participants_meta
    normalized.setdefault("all_participants", list(participants_meta.keys()))
    normalized.setdefault("participant_blocks", {})
    normalized.setdefault("outcome", {})
    normalized.setdefault("article_revisions", {})
    return normalized


def _slug(case_name: str) -> str:
    return case_name.lower().replace(" ", "_").replace("/", "_").replace("–", "-")


def _discover_enriched_files() -> list[Path]:
    paths = []
    for path in sorted(RAW_ARB.glob("*.json")):
        if any(path.name.startswith(p) for p in SKIP_PREFIXES):
            continue
        paths.append(path)
    return paths


def _process_one(args_tuple) -> dict:
    """Worker: load raw JSON, export D3 payload, write file, return summary record."""
    path, departure_days, force = args_tuple

    try:
        with open(path) as f:
            raw = json.load(f)
    except Exception as exc:
        return {
            "case_name": path.stem,
            "slug": path.stem,
            "has_data": False,
            "error": f"JSON load failed: {exc}",
        }

    # Normalize new lifecycle_stages format to pages-dict format
    if not isinstance(raw.get("pages"), dict):
        if "lifecycle_stages" in raw:
            raw = _normalize_new_format(raw)
        else:
            return {
                "case_name": raw.get("case_name", path.stem),
                "slug": _slug(raw.get("case_name", path.stem)),
                "has_data": False,
                "error": "Not an enriched file (no pages dict)",
            }

    # After normalization, still need at least one page with revisions
    if not any(v.get("revisions") for v in raw.get("pages", {}).values()):
        return {
            "case_name": raw.get("case_name", path.stem),
            "slug": _slug(raw.get("case_name", path.stem)),
            "has_data": False,
            "error": "No revisions found in any case page",
        }

    case_name = raw.get("case_name", path.stem)
    slug = _slug(case_name)
    out_path = D3_OUT / f"{slug}.json"

    if out_path.exists() and not force:
        # Load existing to compute summary
        try:
            with open(out_path) as f:
                payload = json.load(f)
            return _summarise(case_name, slug, payload)
        except Exception:
            pass  # fall through and re-export

    try:
        payload = build_d3_payload(
            case_name, raw, departure_threshold_days=departure_days
        )
    except Exception as exc:
        return {
            "case_name": case_name,
            "slug": slug,
            "has_data": False,
            "error": str(exc),
        }

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(payload, f, separators=(",", ":"), ensure_ascii=False)
    except Exception as exc:
        return {
            "case_name": case_name,
            "slug": slug,
            "has_data": False,
            "error": f"Write failed: {exc}",
        }

    return _summarise(case_name, slug, payload)


def _summarise(case_name: str, slug: str, payload: dict) -> dict:
    meta = payload["meta"]
    nodes = payload["nodes"]
    events = payload["events"]

    sanctioned = [n for n in nodes if n.get("sanctions")]
    departed = [n for n in nodes if n.get("departed")]

    # Edit counts by phase
    phase_edits: Counter = Counter()
    for e in events:
        if e["type"] in ("edit", "revert"):
            phase_edits[e["page_type"]] += 1

    # Starter retention (first 25% → last 25%)
    from datetime import datetime

    def ts(s):
        return datetime.fromisoformat(s.replace("Z", "+00:00"))

    case_ms = (ts(meta["case_end"]) - ts(meta["case_start"])).total_seconds()
    early_thresh = ts(meta["case_start"]).timestamp() + case_ms * 0.25
    late_thresh = ts(meta["case_end"]).timestamp() - case_ms * 0.25

    starters = [
        n
        for n in nodes
        if n["total_edits"] >= 2 and ts(n["first_active"]).timestamp() <= early_thresh
    ]
    saw_through = [
        n for n in starters if ts(n["last_active"]).timestamp() >= late_thresh
    ]

    n_editors = meta["total_editors"] or 1

    return {
        "case_name": case_name,
        "slug": slug,
        "has_data": True,
        "error": None,
        "case_start": meta["case_start"][:10],
        "case_end": meta["case_end"][:10],
        "case_duration_days": meta["case_duration_days"],
        "total_editors": meta["total_editors"],
        "total_events": meta["total_events"],
        "outcome_status": meta.get("outcome_status"),
        "sanctioned_count": len(sanctioned),
        "sanctioned_names": [n["username"] for n in sanctioned],
        "departed_count": len(departed),
        "departure_rate": round(len(departed) / n_editors, 4),
        "starters": len(starters),
        "saw_through": len(saw_through),
        "retention_rate": round(len(saw_through) / len(starters), 4) if starters else 0,
        "phase_edits": dict(phase_edits),
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--departure-days", type=int, default=14)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-export even if output file already exists",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")

    D3_OUT.mkdir(parents=True, exist_ok=True)

    paths = _discover_enriched_files()
    logger.info(f"Found {len(paths)} enriched case files")

    work = [(p, args.departure_days, args.force) for p in paths]
    results = []
    done = 0

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_process_one, w): w for w in work}
        for fut in as_completed(futs):
            done += 1
            rec = fut.result()
            results.append(rec)
            status = "OK " if rec["has_data"] else "ERR"
            if done % 50 == 0 or done == len(paths):
                ok = sum(1 for r in results if r["has_data"])
                err = len(results) - ok
                logger.info(f"[{done}/{len(paths)}] OK={ok} ERR={err}")
            elif not rec["has_data"]:
                logger.debug(f"{status} {rec['case_name']}: {rec.get('error')}")

    # Sort manifest: successes by case_name, then failures
    results.sort(key=lambda r: (not r["has_data"], r["case_name"].lower()))

    manifest = {
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "total_cases": len(results),
        "cases_with_data": sum(1 for r in results if r["has_data"]),
        "cases_no_data": sum(1 for r in results if not r["has_data"]),
        "cases": results,
    }

    manifest_path = D3_OUT / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    ok = manifest["cases_with_data"]
    err = manifest["cases_no_data"]
    logger.info(f"\nDone. {ok} exported, {err} skipped → {manifest_path}")

    if err:
        reasons: Counter = Counter()
        for r in results:
            if not r["has_data"]:
                reasons[r.get("error", "unknown")[:60]] += 1
        logger.info("Top failure reasons:")
        for reason, cnt in reasons.most_common(5):
            logger.info(f"  {cnt:4d}× {reason}")


if __name__ == "__main__":
    main()
