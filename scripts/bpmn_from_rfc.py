"""
RFC (Requests for Comments) to BPMN Model Generator
=====================================================

Reads Wikipedia Meta-Wiki RFC data from JSON and generates:
  - Polished PNG diagrams via processpiper (swimlane layout, BLUEMOUNTAIN theme)
  - Complete BPMN 2.0 XML files (viewable in bpmn.io / Camunda Modeler)

Install: pip install processpiper

Usage:
    python bpmn_from_rfc.py
    python bpmn_from_rfc.py --input data/all_requests_for_comments.json
    python bpmn_from_rfc.py --input data/all_rfcs.json --max-cases 10 --output artifacts/bpmn/rfc

View output:
    PNG  -- open directly in any image viewer
    BPMN -- drag & drop at https://demo.bpmn.io
            or use Camunda Modeler: https://camunda.com/download/modeler/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET

from processpiper.text2diagram import render as render_piperflow


# ---------------------------------------------------------------------------
# BPMN 2.0 XML namespaces and layout constants
# ---------------------------------------------------------------------------

_NS_BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
_NS_BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
_NS_DC = "http://www.omg.org/spec/DD/20100524/DC"
_NS_DI = "http://www.omg.org/spec/DD/20100524/DI"

_POOL_X = 100
_POOL_Y = 80
_POOL_HEADER_W = 30
_LANE_H = 160
_TASK_W = 130
_TASK_H = 60
_GW_W = 50
_GW_H = 50
_EVT_W = 36
_EVT_H = 36
_STEP_GAP = 160
_FIRST_X = _POOL_X + _POOL_HEADER_W + 80

RFC_CASE_LANES = ["Submitter", "Steward"]
RFC_AGG_LANES = ["Community Member", "Screening", "Steward"]


# ---------------------------------------------------------------------------
# Swimlane BPMN 2.0 XML Builder
# ---------------------------------------------------------------------------


class SwimlaneBpmnBuilder:
    """Builds BPMN 2.0 XML with a collaboration pool containing swimlanes."""

    def __init__(self, process_name: str, lanes: list[str]):
        self.process_name = process_name
        self.lanes = lanes
        self._lane_ids = {name: "Lane_" + uuid.uuid4().hex[:8] for name in lanes}
        self._collab_id = "Collab_" + uuid.uuid4().hex[:8]
        self._part_id = "Participant_" + uuid.uuid4().hex[:8]
        self._proc_id = "Process_" + uuid.uuid4().hex[:8]
        self._elements: list[tuple[str, str, str, str, int]] = []
        self._flows: list[tuple[str, str, str, str]] = []
        self._step = 0

    def _add(self, label: str, etype: str, lane: str) -> str:
        eid = etype[:6].replace("Event", "Evt").replace("Gatew", "GW_") + "_" + uuid.uuid4().hex[:8]
        self._elements.append((eid, label, etype, lane, self._step))
        self._step += 1
        return eid

    def start(self, label: str, lane: str) -> str:
        return self._add(label, "startEvent", lane)

    def end(self, label: str, lane: str) -> str:
        return self._add(label, "endEvent", lane)

    def task(self, label: str, lane: str, user: bool = False) -> str:
        return self._add(label, "userTask" if user else "task", lane)

    def gateway(self, label: str, lane: str, exclusive: bool = True) -> str:
        return self._add(label, "exclusiveGateway" if exclusive else "parallelGateway", lane)

    def flow(self, src: str, tgt: str, label: str = "") -> str:
        fid = "Flow_" + uuid.uuid4().hex[:8]
        self._flows.append((fid, src, tgt, label))
        return fid

    def _bounds(self, etype: str, lane: str, step: int) -> tuple[int, int, int, int]:
        lane_idx = self.lanes.index(lane)
        lane_top = _POOL_Y + lane_idx * _LANE_H
        cx = _FIRST_X + step * _STEP_GAP
        if etype in ("startEvent", "endEvent"):
            w, h = _EVT_W, _EVT_H
        elif "Gateway" in etype:
            w, h = _GW_W, _GW_H
        else:
            w, h = _TASK_W, _TASK_H
        y = lane_top + (_LANE_H - h) // 2
        return cx, y, w, h

    def to_xml(self) -> str:
        for prefix, uri in (
            ("bpmn", _NS_BPMN),
            ("bpmndi", _NS_BPMNDI),
            ("dc", _NS_DC),
            ("di", _NS_DI),
        ):
            ET.register_namespace(prefix, uri)

        root = ET.Element(
            f"{{{_NS_BPMN}}}definitions",
            {
                "id": "Defs_" + uuid.uuid4().hex[:8],
                "targetNamespace": "http://bpmn.io/schema/bpmn",
                "exporter": "RFC-BPMN-Generator",
                "exporterVersion": "2.0",
            },
        )

        collab = ET.SubElement(root, f"{{{_NS_BPMN}}}collaboration", {"id": self._collab_id})
        ET.SubElement(
            collab, f"{{{_NS_BPMN}}}participant",
            {"id": self._part_id, "name": self.process_name, "processRef": self._proc_id},
        )

        process = ET.SubElement(
            root, f"{{{_NS_BPMN}}}process", {"id": self._proc_id, "isExecutable": "false"}
        )

        lane_set = ET.SubElement(process, f"{{{_NS_BPMN}}}laneSet", {"id": "LS_" + uuid.uuid4().hex[:8]})
        for lane_name in self.lanes:
            lane_el = ET.SubElement(
                lane_set, f"{{{_NS_BPMN}}}lane",
                {"id": self._lane_ids[lane_name], "name": lane_name},
            )
            for eid, _lbl, _et, elane, _step in self._elements:
                if elane == lane_name:
                    ET.SubElement(lane_el, f"{{{_NS_BPMN}}}flowNodeRef").text = eid

        incoming: dict[str, list[str]] = defaultdict(list)
        outgoing: dict[str, list[str]] = defaultdict(list)
        for fid, src, tgt, _lbl in self._flows:
            outgoing[src].append(fid)
            incoming[tgt].append(fid)

        for eid, label, etype, _lane, _step in self._elements:
            el = ET.SubElement(process, f"{{{_NS_BPMN}}}{etype}", {"id": eid, "name": label})
            for fid in incoming.get(eid, []):
                ET.SubElement(el, f"{{{_NS_BPMN}}}incoming").text = fid
            for fid in outgoing.get(eid, []):
                ET.SubElement(el, f"{{{_NS_BPMN}}}outgoing").text = fid

        for fid, src, tgt, label in self._flows:
            attrs: dict[str, str] = {"id": fid, "sourceRef": src, "targetRef": tgt}
            if label:
                attrs["name"] = label
            ET.SubElement(process, f"{{{_NS_BPMN}}}sequenceFlow", attrs)

        max_step = max((e[4] for e in self._elements), default=0)
        pool_w = _FIRST_X - _POOL_X + (max_step + 1) * _STEP_GAP + 80
        pool_h = _LANE_H * len(self.lanes)

        diagram = ET.SubElement(root, f"{{{_NS_BPMNDI}}}BPMNDiagram", {"id": "Diag_" + uuid.uuid4().hex[:8]})
        plane = ET.SubElement(
            diagram, f"{{{_NS_BPMNDI}}}BPMNPlane",
            {"id": "Plane_" + uuid.uuid4().hex[:8], "bpmnElement": self._collab_id},
        )

        ps = ET.SubElement(
            plane, f"{{{_NS_BPMNDI}}}BPMNShape",
            {"id": self._part_id + "_di", "bpmnElement": self._part_id, "isHorizontal": "true"},
        )
        ET.SubElement(ps, f"{{{_NS_DC}}}Bounds", {
            "x": str(_POOL_X), "y": str(_POOL_Y), "width": str(pool_w), "height": str(pool_h),
        })

        for i, lane_name in enumerate(self.lanes):
            lid = self._lane_ids[lane_name]
            ls = ET.SubElement(
                plane, f"{{{_NS_BPMNDI}}}BPMNShape",
                {"id": lid + "_di", "bpmnElement": lid, "isHorizontal": "true"},
            )
            ET.SubElement(ls, f"{{{_NS_DC}}}Bounds", {
                "x": str(_POOL_X + _POOL_HEADER_W),
                "y": str(_POOL_Y + i * _LANE_H),
                "width": str(pool_w - _POOL_HEADER_W),
                "height": str(_LANE_H),
            })

        bounds_cache: dict[str, tuple[int, int, int, int]] = {}
        for eid, _label, etype, lane, step in self._elements:
            x, y, w, h = self._bounds(etype, lane, step)
            bounds_cache[eid] = (x, y, w, h)
            shape = ET.SubElement(
                plane, f"{{{_NS_BPMNDI}}}BPMNShape", {"id": eid + "_di", "bpmnElement": eid}
            )
            ET.SubElement(shape, f"{{{_NS_DC}}}Bounds", {
                "x": str(x), "y": str(y), "width": str(w), "height": str(h),
            })
            if etype in ("startEvent", "endEvent") or "Gateway" in etype:
                lbl_el = ET.SubElement(shape, f"{{{_NS_BPMNDI}}}BPMNLabel")
                ET.SubElement(lbl_el, f"{{{_NS_DC}}}Bounds", {
                    "x": str(x - 10), "y": str(y + h + 4), "width": str(w + 20), "height": "40",
                })

        for fid, src, tgt, label in self._flows:
            edge = ET.SubElement(
                plane, f"{{{_NS_BPMNDI}}}BPMNEdge", {"id": fid + "_di", "bpmnElement": fid}
            )
            if label:
                le = ET.SubElement(edge, f"{{{_NS_BPMNDI}}}BPMNLabel")
                sx, sy, sw, sh = bounds_cache.get(src, (0, 0, 0, 0))
                tx, ty, tw, th = bounds_cache.get(tgt, (0, 0, 0, 0))
                ET.SubElement(le, f"{{{_NS_DC}}}Bounds", {
                    "x": str(int((sx + sw / 2 + tx + tw / 2) / 2 - 20)),
                    "y": str(int((sy + sh / 2 + ty + th / 2) / 2 - 10)),
                    "width": "60", "height": "20",
                })
            sx, sy, sw, sh = bounds_cache.get(src, (0, 0, 0, 0))
            tx, ty, tw, th = bounds_cache.get(tgt, (0, 0, 0, 0))
            ET.SubElement(edge, f"{{{_NS_DI}}}waypoint", {
                "x": str(sx + sw), "y": str(int(sy + sh / 2)),
            })
            ET.SubElement(edge, f"{{{_NS_DI}}}waypoint", {
                "x": str(tx), "y": str(int(ty + th / 2)),
            })

        xml_str = ET.tostring(root, encoding="unicode")
        return minidom.parseString(xml_str).toprettyxml(indent="  ")


# ---------------------------------------------------------------------------
# RFC Data Parsing
# ---------------------------------------------------------------------------

STATUS_MAP = {
    "resolved": "Resolved",
    "closed": "Closed",
    "withdrawn": "Withdrawn",
    "declined": "Unsuccessful",
    "unsuccessful": "Unsuccessful",
    "failed": "Unsuccessful",
    "no consensus": "No Consensus",
    "invalid": "Invalid",
    "inactive": "Inactive / Stale",
    "stale": "Inactive / Stale",
    "open": "Open",
}

CATEGORY_MAP = {
    "Requests for comments (resolved)": "Resolved",
    "Requests for comments (unsuccessful)": "Unsuccessful",
    "Requests for comments (invalid)": "Invalid",
    "Requests for comments (inactive)": "Inactive / Stale",
}


def load_rfc_data(filepath: str | Path) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_rfc(rfc: dict) -> dict:
    content = rfc.get("content", "")
    status_m = re.search(r"\|status\s*=\s*([^\n|}\]]+)", content, re.I)
    status_raw = status_m.group(1).strip().lower() if status_m else ""
    status_raw = re.sub(r"<!--.*?-->", "", status_raw).strip()

    date_m = re.search(r"\|date\s*=\s*([^\n|}\]]+)", content, re.I)
    filed_date_raw = date_m.group(1).strip() if date_m else None
    if filed_date_raw:
        filed_date_raw = re.sub(r"<!--.*?-->", "", filed_date_raw).strip()
        d_m = re.search(r"(\d{4}-\d{2}-\d{2})", filed_date_raw)
        filed_date = d_m.group(1) if d_m else None
    else:
        filed_date = None

    comment_m = re.search(r"\|comment\s*=\s*([^\n|}\]]+)", content, re.I)
    close_comment = comment_m.group(1).strip() if comment_m else None

    user_mentions = re.findall(r"\[\[User:([^\]|]+)", content, re.I)
    participants = set(u.strip().lower() for u in user_mentions)

    normalised = STATUS_MAP.get(status_raw, "")
    if not normalised:
        normalised = CATEGORY_MAP.get(rfc.get("category", ""), "Unknown")

    short_title = re.sub(
        r"^Requests for comment/", "", rfc.get("title", ""), flags=re.I
    ).strip()

    return {
        "title": short_title,
        "page_id": rfc.get("page_id"),
        "category": rfc.get("category", ""),
        "outcome": normalised,
        "status_raw": status_raw,
        "filed_date": filed_date,
        "closed_date": rfc.get("last_revision_timestamp"),
        "closer_user": rfc.get("last_revision_user"),
        "close_comment": close_comment,
        "participant_count": len(participants),
        "discussion_turns": len(user_mentions),
        "has_discussion": len(user_mentions) > 0,
        "url": rfc.get("url", ""),
    }


def safe_filename(title: str, max_len: int = 45) -> str:
    safe = re.sub(r"[^\w\-]", "_", title)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe[:max_len] if safe else "unnamed"


# ---------------------------------------------------------------------------
# PiperFlow helpers
# ---------------------------------------------------------------------------


def _piperflow_case(parsed: dict) -> str:
    """
    Build a PiperFlow DSL string for one RFC case.
    Swimlanes:
        Lane: Submitter        -- start, submit, discussion (if active)
        Pool: RFC Process
            Lane: Steward      -- review, valid gateway, facilitate, outcome
    NOTE: Do NOT use // in PiperFlow strings -- the parser treats them as
          Python integer division and raises a SyntaxError.
          Use @label to annotate named end events instead.
    """
    outcome = parsed["outcome"]
    has_discussion = parsed["has_discussion"]
    participant_count = parsed["participant_count"]
    filed_date = parsed["filed_date"] or "unknown date"
    cat_short = parsed["category"].replace("Requests for comments ", "").strip("()")
    display_title = parsed["title"][:48] + ("..." if len(parsed["title"]) > 48 else "")
    # Strip characters that break the PiperFlow parser (quotes, colons)
    display_title = display_title.replace('"', "").replace("'", "").replace(":", "-")

    if has_discussion:
        discuss_label = (
            "Discuss RFC - "
            + str(parsed["discussion_turns"])
            + " turns, "
            + str(participant_count)
            + " participants"
        )
        return (
            "title: RFC - " + display_title + "\n"
            "colourtheme: BLUEMOUNTAIN\n"
            "\n"
            "lane: Submitter\n"
            "    (start) as start\n"
            "    [Submit RFC - " + filed_date + "] as submit\n"
            "    [" + discuss_label + "] as discuss\n"
            "\n"
            "pool: RFC Process\n"
            "    lane: Steward\n"
            "        [Submission Review] as review\n"
            "        <Valid RFC?> as valid_gw\n"
            "        [Assess and Facilitate] as facilitate\n"
            "        <Outcome?> as outcome_gw\n"
            "        (end) as end_main\n"
            "        (end) as end_invalid\n"
            "\n"
            "start->submit->review->valid_gw\n"
            "valid_gw->facilitate: Yes\n"
            "valid_gw->end_invalid: No - Invalid\n"
            "facilitate->discuss->outcome_gw\n"
            "outcome_gw->end_main: " + outcome + "\n"
            "end_main@label: " + outcome + "\n"
            "end_invalid@label: Marked Invalid\n"
            "\n"
            "footer: Category: "
            + cat_short
            + " | Participants: "
            + str(participant_count)
            + "\n"
        )
    else:
        return (
            "title: RFC - " + display_title + "\n"
            "colourtheme: BLUEMOUNTAIN\n"
            "\n"
            "lane: Submitter\n"
            "    (start) as start\n"
            "    [Submit RFC - " + filed_date + "] as submit\n"
            "\n"
            "pool: RFC Process\n"
            "    lane: Steward\n"
            "        [Submission Review] as review\n"
            "        <Valid RFC?> as valid_gw\n"
            "        <Outcome?> as outcome_gw\n"
            "        (end) as end_main\n"
            "        (end) as end_invalid\n"
            "\n"
            "start->submit->review->valid_gw\n"
            "valid_gw->outcome_gw: Yes\n"
            "valid_gw->end_invalid: No - Invalid\n"
            "outcome_gw->end_main: " + outcome + "\n"
            "end_main@label: " + outcome + "\n"
            "end_invalid@label: Marked Invalid\n"
            "\n"
            "footer: Category: " + cat_short + " | No discussion recorded\n"
        )


def _piperflow_aggregate(all_parsed: list[dict]) -> str:
    """
    Build a PiperFlow DSL string for the aggregate RFC workflow.

    Shows top 2 outcomes individually; groups the rest as Other so
    percentages always sum to 100% regardless of how many outcomes exist.
    (processpiper limit: 1 incoming + 3 outgoing = 4 max per node)
    """
    total = len(all_parsed)
    outcome_counts: dict[str, int] = {}
    for p in all_parsed:
        o = p["outcome"]
        outcome_counts[o] = outcome_counts.get(o, 0) + 1

    sorted_outcomes = sorted(outcome_counts.items(), key=lambda x: -x[1])
    top2 = sorted_outcomes[:2]
    remainder = sorted_outcomes[2:]

    other_count = sum(n for _, n in remainder)
    other_pct = round(100 * other_count / total) if total else 0
    top2_pcts = [round(100 * n / total) if total else 0 for _, n in top2]
    top2_pcts[-1] = 100 - other_pct - sum(top2_pcts[:-1])  # adjust so sum == 100%

    other_detail = ", ".join(
        o + " " + str(round(100 * n / total)) + "%" for o, n in remainder if n > 0
    )

    end0_label = "end " + top2[0][0] + " " + str(top2_pcts[0]) + "%"
    end1_label = "end " + top2[1][0] + " " + str(top2_pcts[1]) + "%"
    other_label = "end Other " + str(other_pct) + "%"

    lines = [
        "title: RFC Standard Workflow - Aggregate " + str(total) + " cases",
        "colourtheme: BLUEMOUNTAIN",
        "",
        "lane: Community Member",
        "    (start) as start",
        "    [Submit RFC] as submit",
        "    [Participate in Discussion] as discuss",
        "",
        "pool: RFC Process",
        "    lane: Screening",
        "        [Categorise and Screen] as screen",
        "        <Valid RFC?> as valid_gw",
        "        (end Invalid - Closed) as end_invalid",
        "",
        "    lane: Steward",
        "        [Assess RFC] as assess",
        "        [Community Discussion Period] as discussion",
        "        [Closer Reviews Outcome] as closer",
        "        (" + end0_label + ") as end0",
        "        (" + end1_label + ") as end1",
        "        (" + other_label + ") as end_other",
        "",
        "start->submit->screen->valid_gw",
        "valid_gw->assess: Yes - Valid",
        "valid_gw->end_invalid: No - Invalid",
        "assess->discussion->discuss->closer",
        "closer->end0: " + top2[0][0],
        "closer->end1: " + top2[1][0],
        "closer->end_other: Other",
        "",
        "footer: Other includes - "
        + (other_detail or "none")
        + " | "
        + str(total)
        + " total cases",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Diagram creation functions
# ---------------------------------------------------------------------------


def create_rfc_case_bpmn(
    parsed: dict, case_idx: int, output_dir: Path
) -> tuple[Path, Path | None]:
    """Generate PNG + BPMN XML for one RFC case. Returns (bpmn_path, png_path)."""
    slug = safe_filename(parsed["title"])
    stem = f"rfc_{case_idx:04d}_{slug}"
    bpmn_path = output_dir / f"{stem}.bpmn"
    png_path = output_dir / f"{stem}.png"

    # PNG
    png_out = None
    try:
        render_piperflow(_piperflow_case(parsed), output_file=str(png_path))
        png_out = png_path
    except Exception as e:
        print(f"    WARNING: PNG failed for case {case_idx}: {e}")

    # BPMN XML
    outcome = parsed["outcome"]
    filed_date = parsed["filed_date"] or "unknown date"
    has_disc = parsed["has_discussion"]
    disc_label = (
        "Discuss RFC - "
        + str(parsed["discussion_turns"])
        + " turns, "
        + str(parsed["participant_count"])
        + " participants"
        if has_disc
        else "Discuss RFC"
    )

    b = SwimlaneBpmnBuilder("RFC: " + parsed["title"][:60], RFC_CASE_LANES)
    start = b.start("RFC Filed", "Submitter")
    submit = b.task("Submission - " + filed_date, "Submitter", user=True)
    review = b.task("Submission Review", "Steward")
    gw_valid = b.gateway("Valid RFC?", "Steward")
    inv_end = b.end("Marked Invalid", "Steward")
    b.flow(gw_valid, inv_end, "No - Invalid")

    if has_disc:
        discuss = b.task(disc_label[:60], "Submitter", user=True)
        facilitate = b.task("Assess and Facilitate", "Steward", user=True)
        gw_out = b.gateway("Outcome?", "Steward")
        b.flow(gw_valid, facilitate, "Yes")
        b.flow(facilitate, discuss)
        b.flow(discuss, gw_out)
    else:
        gw_out = b.gateway("Outcome?", "Steward")
        b.flow(gw_valid, gw_out, "Yes")

    end_main = b.end(outcome, "Steward")
    b.flow(gw_out, end_main, outcome)
    b.flow(start, submit)
    b.flow(submit, review)
    b.flow(review, gw_valid)

    bpmn_path.write_text(b.to_xml(), encoding="utf-8")
    return bpmn_path, png_out


def create_aggregate_rfc_bpmn(
    all_parsed: list[dict], output_dir: Path
) -> tuple[Path, Path | None]:
    """Generate aggregate PNG + BPMN XML. Returns (bpmn_path, png_path)."""
    bpmn_path = output_dir / "rfc_aggregate_workflow.bpmn"
    png_path = output_dir / "rfc_aggregate_workflow.png"

    # PNG
    png_out = None
    try:
        render_piperflow(_piperflow_aggregate(all_parsed), output_file=str(png_path))
        png_out = png_path
    except Exception as e:
        print(f"  WARNING: Aggregate PNG failed: {e}")

    # BPMN XML — same top2 + Other grouping as the PNG
    total = len(all_parsed)
    outcome_counts: dict[str, int] = {}
    for p in all_parsed:
        o = p["outcome"]
        outcome_counts[o] = outcome_counts.get(o, 0) + 1

    sorted_outcomes = sorted(outcome_counts.items(), key=lambda x: -x[1])
    top2 = sorted_outcomes[:2]
    remainder = sorted_outcomes[2:]
    other_count = sum(n for _, n in remainder)
    other_pct = round(100 * other_count / total) if total else 0
    top2_pcts = [round(100 * n / total) if total else 0 for _, n in top2]
    top2_pcts[-1] = 100 - other_pct - sum(top2_pcts[:-1])

    other_detail = ", ".join(
        o + " " + str(round(100 * n / total)) + "%" for o, n in remainder if n > 0
    )

    b = SwimlaneBpmnBuilder("RFC Standard Workflow (Aggregate)", RFC_AGG_LANES)
    start = b.start("RFC Filed", "Community Member")
    submit = b.task("RFC Submission", "Community Member", user=True)
    screen = b.task("Categorise and Screen", "Screening")
    gw_valid = b.gateway("Valid RFC?", "Screening")
    inv_end = b.end("Invalid - Closed", "Screening")
    assess = b.task("Assess RFC", "Steward", user=True)
    discuss = b.task("Discussion Period", "Community Member", user=True)
    closer = b.task("Closer Reviews Outcome", "Steward", user=True)
    gw_out = b.gateway("Resolution Outcome?", "Steward")

    b.flow(start, submit)
    b.flow(submit, screen)
    b.flow(screen, gw_valid)
    b.flow(gw_valid, inv_end, "No - Invalid")
    b.flow(gw_valid, assess, "Yes - Valid")
    b.flow(assess, discuss)
    b.flow(discuss, closer)
    b.flow(closer, gw_out)

    for i, (o, _) in enumerate(top2):
        end = b.end(o + " (" + str(top2_pcts[i]) + "%)", "Steward")
        b.flow(gw_out, end, o)
    end_other = b.end(
        "Other (" + str(other_pct) + "%): " + (other_detail or "none"), "Steward"
    )
    b.flow(gw_out, end_other, "Other")

    bpmn_path.write_text(b.to_xml(), encoding="utf-8")
    return bpmn_path, png_out


# ---------------------------------------------------------------------------
# CLI & Main
# ---------------------------------------------------------------------------


def get_user_case_selection(total: int) -> list[int]:
    """
    Prompt user to select which cases to generate individual diagrams for.
    Accepts specific indices, ranges, counts, or 'all'.

    Examples:
        all           -> all cases
        10            -> first 10 cases (1-10)
        100,200,305   -> cases at positions 100, 200, 305
        1-50          -> cases 1 through 50
        1,50-100,200  -> case 1, cases 50-100, case 200
    """
    print(f"\nWhich cases to generate individual diagrams for? (1-{total})")
    print("  Examples: all | 10 | 100,200,305 | 1-50 | 1,50-100,200")
    print("  [Default: all]\n")

    while True:
        user_input = input("Select cases: ").strip().lower()

        if user_input in ("", "all"):
            return list(range(1, total + 1))

        try:
            selected: set[int] = set()
            for part in user_input.split(","):
                part = part.strip()
                if "-" in part:
                    a, b = part.split("-", 1)
                    selected.update(range(int(a), int(b) + 1))
                else:
                    n = int(part)
                    # Plain number with no commas/ranges = "first N"
                    if "," not in user_input and "-" not in user_input:
                        selected = set(range(1, n + 1))
                        break
                    selected.add(n)

            invalid = [i for i in selected if not (1 <= i <= total)]
            if invalid:
                print(
                    f"  Out of range: {sorted(invalid)}. Enter numbers between 1 and {total}."
                )
                continue

            indices = sorted(selected)
            print(
                f"  Selected {len(indices)} case(s): {indices[:5]}{'...' if len(indices) > 5 else ''}"
            )
            return indices

        except ValueError:
            print("  Invalid input. Use: all | 10 | 100,200,305 | 1-50")


def select_input_file(data_dir: Path) -> Path | None:
    json_files = sorted(data_dir.glob("*.json"))
    if not json_files:
        return None
    if len(json_files) == 1:
        return json_files[0]
    print("\nAvailable RFC data files:")
    print("=" * 50)
    for i, f in enumerate(json_files, 1):
        print(f"  [{i}] {f.name}")
    choice = input("\nSelect file number [default: 1]: ").strip()
    try:
        idx = int(choice) - 1 if choice else 0
        return json_files[max(0, min(idx, len(json_files) - 1))]
    except ValueError:
        return json_files[0]


def main():
    parser = argparse.ArgumentParser(
        description="Generate BPMN + PNG models from Wikipedia RFC data."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default=None,
        help="Path to RFC JSON file. If omitted, searches ./data/raw/rfc/",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output directory. Default: ./artifacts/bpmn/rfc/",
    )
    parser.add_argument(
        "--max-cases",
        "-n",
        type=int,
        default=None,
        help="Max individual case diagrams to generate.",
    )
    parser.add_argument(
        "--no-aggregate",
        action="store_true",
        help="Skip the aggregate workflow diagram.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data" / "raw" / "rfc"

    if args.input:
        input_path = Path(args.input)
    else:
        input_path = select_input_file(data_dir)
        if input_path is None:
            print(f"No JSON files found in {data_dir}. Use --input to specify a file.")
            sys.exit(1)

    output_dir = (
        Path(args.output)
        if args.output
        else project_root / "artifacts" / "bpmn" / "rfc"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("RFC -> BPMN + PNG Generator")
    print(f"{'='*60}")
    print(f"Input : {input_path}")
    print(f"Output: {output_dir}")
    print(f"{'='*60}")

    raw_data = load_rfc_data(input_path)
    rfcs_raw = raw_data.get("rfcs", [])
    print(f"\nLoaded {len(rfcs_raw)} RFCs")
    print(f"Source  : {raw_data.get('source', 'unknown')}")
    print(f"Fetched : {raw_data.get('fetch_timestamp', 'unknown')}")

    all_parsed = [parse_rfc(r) for r in rfcs_raw]

    print("\nOutcome distribution:")
    outcome_counts: dict[str, int] = {}
    for p in all_parsed:
        outcome_counts[p["outcome"]] = outcome_counts.get(p["outcome"], 0) + 1
    for outcome, count in sorted(outcome_counts.items(), key=lambda x: -x[1]):
        bar = "X" * (count // 5)
        print(f"  {outcome:<25} {count:>4}  {bar}")

    agg_bpmn = agg_png = None
    if not args.no_aggregate:
        print("\nGenerating aggregate workflow...")
        agg_bpmn, agg_png = create_aggregate_rfc_bpmn(all_parsed, output_dir)
        print(f"  + {agg_bpmn.name}")
        if agg_png:
            print(f"  + {agg_png.name}")

    if args.max_cases is not None:
        selected_indices = list(range(1, min(args.max_cases, len(all_parsed)) + 1))
    else:
        selected_indices = get_user_case_selection(len(all_parsed))

    print(f"\nGenerating {len(selected_indices)} case diagram(s)...\n")
    bpmn_files: list[Path] = []
    png_files: list[Path] = []

    for i, idx in enumerate(selected_indices, start=1):
        bpmn_p, png_p = create_rfc_case_bpmn(all_parsed[idx - 1], i, output_dir)
        bpmn_files.append(bpmn_p)
        if png_p:
            png_files.append(png_p)
        label = "PNG + BPMN" if png_p else "BPMN only"
        print(f"  [{i:>4}/{len(selected_indices)}] {bpmn_p.stem[:55]}  {label}")

    total_bpmn = len(bpmn_files) + (1 if agg_bpmn else 0)
    total_png = len(png_files) + (1 if agg_png else 0)

    print(f"\n{'='*60}")
    print("Done!")
    print(f"  Individual diagrams : {len(selected_indices)} of {len(all_parsed)} cases")
    print(f"  Aggregate           : full dataset ({len(all_parsed)} cases)")
    print(f"  BPMN files : {total_bpmn}")
    print(f"  PNG files  : {total_png}")
    print(f"  Output dir : {output_dir}")
    print("\nTo view:")
    print("  PNG  -- open any .png directly")
    print("  BPMN -- drag & drop at https://demo.bpmn.io")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
