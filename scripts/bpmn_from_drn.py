"""
DRN (Dispute Resolution Noticeboard) to BPMN Model Generator

Dual approach:
1. processpiper for PNG visualization (good visuals, pools/lanes)
2. Direct BPMN 2.0 XML generation for complete .bpmn files

Install: pip install processpiper
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from collections import defaultdict
from xml.etree import ElementTree as ET
from xml.dom import minidom

# processpiper for PNG visualization
from processpiper.text2diagram import render as render_piperflow


# =============================================================================
# Helper function for writing to both artifacts and dashboard
# =============================================================================


def _write_bpmn_to_both_locations(
    bpmn_path: Path, xml_content: str, dashboard_type: str = "drn"
) -> None:
    """
    Write BPMN XML to both artifacts and dashboard folders.

    Args:
        bpmn_path: Path to write in artifacts folder
        xml_content: BPMN XML content
        dashboard_type: Type for dashboard path ('rfc', 'drn', 'arbitration')
    """
    # Write to primary location (artifacts)
    bpmn_path.write_text(xml_content, encoding="utf-8")

    # Also write to dashboard if the project structure includes it
    try:
        dashboard_dir = (
            bpmn_path.resolve().parent.parent.parent
            / "dashboard"
            / "public"
            / "bpmn"
            / dashboard_type
        )
        if dashboard_dir.parent.parent.exists():  # Check if dashboard/public exists
            dashboard_dir.mkdir(parents=True, exist_ok=True)
            dashboard_path = dashboard_dir / bpmn_path.name
            dashboard_path.write_text(xml_content, encoding="utf-8")
    except Exception:
        pass  # Silently skip dashboard write if structure doesn't exist


# =============================================================================
# BPMN 2.0 XML Generator
# =============================================================================

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

DRN_LANES = ["Filer", "Volunteer"]
DRN_AGG_LANES_BASE = ["Filer", "Volunteer"]
DRN_AGG_LANES_ESC = ["Filer", "Volunteer", "Admin"]


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
        eid = (
            etype[:6].replace("Event", "Evt").replace("Gatew", "GW_")
            + "_"
            + uuid.uuid4().hex[:8]
        )
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
        return self._add(
            label, "exclusiveGateway" if exclusive else "parallelGateway", lane
        )

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
                "exporter": "DRN-BPMN-Generator",
                "exporterVersion": "2.0",
            },
        )

        collab = ET.SubElement(
            root, f"{{{_NS_BPMN}}}collaboration", {"id": self._collab_id}
        )
        ET.SubElement(
            collab,
            f"{{{_NS_BPMN}}}participant",
            {
                "id": self._part_id,
                "name": self.process_name,
                "processRef": self._proc_id,
            },
        )

        process = ET.SubElement(
            root,
            f"{{{_NS_BPMN}}}process",
            {"id": self._proc_id, "isExecutable": "false"},
        )

        lane_set = ET.SubElement(
            process, f"{{{_NS_BPMN}}}laneSet", {"id": "LS_" + uuid.uuid4().hex[:8]}
        )
        for lane_name in self.lanes:
            lane_el = ET.SubElement(
                lane_set,
                f"{{{_NS_BPMN}}}lane",
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
            el = ET.SubElement(
                process, f"{{{_NS_BPMN}}}{etype}", {"id": eid, "name": label}
            )
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

        diagram = ET.SubElement(
            root, f"{{{_NS_BPMNDI}}}BPMNDiagram", {"id": "Diag_" + uuid.uuid4().hex[:8]}
        )
        plane = ET.SubElement(
            diagram,
            f"{{{_NS_BPMNDI}}}BPMNPlane",
            {"id": "Plane_" + uuid.uuid4().hex[:8], "bpmnElement": self._collab_id},
        )

        ps = ET.SubElement(
            plane,
            f"{{{_NS_BPMNDI}}}BPMNShape",
            {
                "id": self._part_id + "_di",
                "bpmnElement": self._part_id,
                "isHorizontal": "true",
            },
        )
        ET.SubElement(
            ps,
            f"{{{_NS_DC}}}Bounds",
            {
                "x": str(_POOL_X),
                "y": str(_POOL_Y),
                "width": str(pool_w),
                "height": str(pool_h),
            },
        )

        for i, lane_name in enumerate(self.lanes):
            lid = self._lane_ids[lane_name]
            ls = ET.SubElement(
                plane,
                f"{{{_NS_BPMNDI}}}BPMNShape",
                {"id": lid + "_di", "bpmnElement": lid, "isHorizontal": "true"},
            )
            ET.SubElement(
                ls,
                f"{{{_NS_DC}}}Bounds",
                {
                    "x": str(_POOL_X + _POOL_HEADER_W),
                    "y": str(_POOL_Y + i * _LANE_H),
                    "width": str(pool_w - _POOL_HEADER_W),
                    "height": str(_LANE_H),
                },
            )

        bounds_cache: dict[str, tuple[int, int, int, int]] = {}
        for eid, _label, etype, lane, step in self._elements:
            x, y, w, h = self._bounds(etype, lane, step)
            bounds_cache[eid] = (x, y, w, h)
            shape = ET.SubElement(
                plane,
                f"{{{_NS_BPMNDI}}}BPMNShape",
                {"id": eid + "_di", "bpmnElement": eid},
            )
            ET.SubElement(
                shape,
                f"{{{_NS_DC}}}Bounds",
                {
                    "x": str(x),
                    "y": str(y),
                    "width": str(w),
                    "height": str(h),
                },
            )
            if etype in ("startEvent", "endEvent") or "Gateway" in etype:
                lbl_el = ET.SubElement(shape, f"{{{_NS_BPMNDI}}}BPMNLabel")
                ET.SubElement(
                    lbl_el,
                    f"{{{_NS_DC}}}Bounds",
                    {
                        "x": str(x - 10),
                        "y": str(y + h + 4),
                        "width": str(w + 20),
                        "height": "40",
                    },
                )

        for fid, src, tgt, label in self._flows:
            edge = ET.SubElement(
                plane,
                f"{{{_NS_BPMNDI}}}BPMNEdge",
                {"id": fid + "_di", "bpmnElement": fid},
            )
            if label:
                le = ET.SubElement(edge, f"{{{_NS_BPMNDI}}}BPMNLabel")
                sx, sy, sw, sh = bounds_cache.get(src, (0, 0, 0, 0))
                tx, ty, tw, th = bounds_cache.get(tgt, (0, 0, 0, 0))
                ET.SubElement(
                    le,
                    f"{{{_NS_DC}}}Bounds",
                    {
                        "x": str(int((sx + sw / 2 + tx + tw / 2) / 2 - 20)),
                        "y": str(int((sy + sh / 2 + ty + th / 2) / 2 - 10)),
                        "width": "60",
                        "height": "20",
                    },
                )
            sx, sy, sw, sh = bounds_cache.get(src, (0, 0, 0, 0))
            tx, ty, tw, th = bounds_cache.get(tgt, (0, 0, 0, 0))
            ET.SubElement(
                edge,
                f"{{{_NS_DI}}}waypoint",
                {
                    "x": str(sx + sw),
                    "y": str(int(sy + sh / 2)),
                },
            )
            ET.SubElement(
                edge,
                f"{{{_NS_DI}}}waypoint",
                {
                    "x": str(tx),
                    "y": str(int(ty + th / 2)),
                },
            )

        xml_str = ET.tostring(root, encoding="unicode")
        return minidom.parseString(xml_str).toprettyxml(indent="  ")


# =============================================================================
# Status Parsing
# =============================================================================

# Maps values found in {{DR case status|VALUE}} to (display_name, category)
STATUS_MAP = {
    "resolved": ("Resolved", "success"),
    "resolve": ("Resolved", "success"),
    "closed": ("Closed", "closed"),
    "close": ("Closed", "closed"),
    "failed": ("Failed", "failed"),
    "fail": ("Failed", "failed"),
    "open": ("Open", "active"),
    "needassist": ("Need Assist", "active"),
    "inprogress": ("In Progress", "active"),
    "hold": ("On Hold", "active"),
    "stale": ("Stale", "inactive"),
    "reject": ("Rejected", "closed"),
    "archive": ("Archived", "closed"),
    "rfc": ("To RFC", "escalated"),
    "arbcom": ("To ArbCom", "escalated"),
    "escalated": ("Escalated", "escalated"),
    "withdrawn": ("Withdrawn", "closed"),
    "declined": ("Declined", "closed"),
}


def parse_status(case: dict) -> tuple[str, str]:
    """
    Parse the real case status from content, with fallbacks.

    Priority:
    1. {{DR case status|VALUE}} in content  — most reliable
    2. {{drn archive top|...}} present      — case was archived/closed
    3. source == 'live'                      — still open
    4. Fallback: 'Closed'
    """
    content = case.get("content", "")
    templates = [t.lower() for t in case.get("templates", [])]

    # 1. Parse {{DR case status|VALUE}}
    m = re.search(r"\{\{DR case status\|([^|}]+)", content, re.I)
    if m:
        raw = m.group(1).strip().lower().rstrip("|")
        if raw in STATUS_MAP:
            return STATUS_MAP[raw]
        if raw:  # unknown value — still closed-ish
            return (raw.title(), "closed")

    # 2. drn archive top present → was formally archived
    if "drn archive top" in templates or "archive top" in templates:
        return ("Closed", "closed")

    # 3. Live page → open
    if case.get("source") == "live":
        return ("Open", "active")

    return ("Closed", "closed")


def load_drn_data(filepath: Path) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def get_cases(data: dict) -> list[dict]:
    """
    Return the cases list, handling both data schema versions:
      - New format: data["cases"]
      - Old format: data["parsed_cases"]
    """
    return data.get("cases", data.get("parsed_cases", []))


def safe_filename(title: str, max_len: int = 40) -> str:
    safe = re.sub(r"[^\w\-]", "_", title)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe[:max_len] if safe else "unnamed"


def safe_piperflow_title(title: str, max_len: int = 45) -> str:
    """Strip characters that break the PiperFlow DSL parser."""
    t = title[:max_len] + ("..." if len(title) > max_len else "")
    return (
        t.replace('"', "")
        .replace("'", "")
        .replace(":", "-")
        .replace("[", "")
        .replace("]", "")
    )


# =============================================================================
# Case BPMN Generation
# =============================================================================


def create_case_bpmn(case: dict, case_index: int, output_dir: Path) -> bool:
    title = case.get("title", f"Case_{case_index}")
    status_name, status_cat = parse_status(case)
    participant_count = case.get("participant_count", 0)
    participants = case.get("participants", [])  # noqa: F841
    disputed_articles = case.get("disputed_articles", [])
    source = case.get("source", "")

    safe_name = safe_filename(title)
    png_path = output_dir / f"case_{case_index:03d}_{safe_name}.png"
    bpmn_path = output_dir / f"case_{case_index:03d}_{safe_name}.bpmn"

    # Source is archive page name — shorten for footer
    source_short = re.sub(
        r"Wikipedia:Dispute resolution noticeboard/?", "DRN ", source
    )[:40]

    # === 1. BPMN XML ===
    bpmn = SwimlaneBpmnBuilder(f"DRN: {title[:50]}", DRN_LANES)
    start = bpmn.start("Dispute Filed", "Filer")
    file_task = bpmn.task("File DRN Case", "Filer", user=True)
    review = bpmn.task("Review Filing", "Volunteer")
    valid_gw = bpmn.gateway("Valid Case?", "Volunteer")
    bpmn.flow(start, file_task)
    bpmn.flow(file_task, review)
    bpmn.flow(review, valid_gw)

    if participant_count > 1:
        discuss = bpmn.task("Discussion Phase", "Filer", user=True)
        facilitate = bpmn.task("Facilitate", "Volunteer", user=True)
        outcome_gw = bpmn.gateway("Resolution?", "Volunteer")
        bpmn.flow(valid_gw, facilitate, "Yes")
        bpmn.flow(facilitate, discuss)
        bpmn.flow(discuss, outcome_gw)
        if status_cat == "success":
            end = bpmn.end("Resolved", "Volunteer")
            bpmn.flow(outcome_gw, end, "Agreement")
        elif status_cat == "escalated":
            escalate = bpmn.task("Escalate", "Volunteer")
            end = bpmn.end("Escalated", "Volunteer")
            bpmn.flow(outcome_gw, escalate, "Complex")
            bpmn.flow(escalate, end)
        elif status_cat == "inactive":
            end = bpmn.end("Stale", "Volunteer")
            bpmn.flow(outcome_gw, end, "Abandoned")
        else:
            end = bpmn.end("Closed", "Volunteer")
            bpmn.flow(outcome_gw, end, "No Resolution")
    else:
        if status_cat == "success":
            end = bpmn.end("Resolved", "Volunteer")
        elif status_cat == "escalated":
            end = bpmn.end("Escalated", "Volunteer")
        else:
            end = bpmn.end("Closed", "Volunteer")
        bpmn.flow(valid_gw, end, "Yes")

    declined = bpmn.end("Declined", "Volunteer")
    bpmn.flow(valid_gw, declined, "Invalid")

    try:
        _write_bpmn_to_both_locations(bpmn_path, bpmn.to_xml(), "drn")
    except Exception as e:
        print(f"  ERROR writing BPMN for '{title}': {e}")
        return False

    # === 2. PNG via PiperFlow ===
    display_title = safe_piperflow_title(title)
    article_note = disputed_articles[0][:30] if disputed_articles else "dispute"
    article_note = re.sub(r"[\"':\[\]]", "", article_note)

    if participant_count > 1:
        piperflow = (
            "title: DRN - " + display_title + "\n"
            "colourtheme: BLUEMOUNTAIN\n"
            "\n"
            "lane: Filer\n"
            "    (start) as start\n"
            "    [File DRN Case] as file_case\n"
            "    [Participate in Discussion] as discuss\n"
            "\n"
            "pool: DRN Process\n"
            "    lane: Volunteer\n"
            "        [Review Filing] as review\n"
            "        <Valid Case?> as valid_check\n"
            "        [Facilitate Discussion] as facilitate\n"
            "        <Resolution Possible?> as resolution_check\n"
            "        (end) as end_event\n"
            "        (end Declined) as end_declined\n"
            "\n"
            "start->file_case->review->valid_check\n"
            "valid_check->facilitate: Yes\n"
            "valid_check->end_declined: No\n"
            "facilitate->discuss->resolution_check\n"
            "resolution_check->end_event: " + status_name + "\n"
            "end_event@label: " + status_name + "\n"
            "end_declined@label: Declined\n"
            "\n"
            "footer: Status - "
            + status_name
            + " | Participants - "
            + str(participant_count)
            + " | "
            + source_short
            + "\n"
        )
    else:
        piperflow = (
            "title: DRN - " + display_title + "\n"
            "colourtheme: BLUEMOUNTAIN\n"
            "\n"
            "lane: Filer\n"
            "    (start) as start\n"
            "    [File DRN Case] as file_case\n"
            "\n"
            "pool: DRN Process\n"
            "    lane: Volunteer\n"
            "        [Review Filing] as review\n"
            "        <Valid Case?> as valid_check\n"
            "        (end) as end_event\n"
            "        (end Declined) as end_declined\n"
            "\n"
            "start->file_case->review->valid_check\n"
            "valid_check->end_event: Yes\n"
            "valid_check->end_declined: No\n"
            "\n"
            "footer: Status - "
            + status_name
            + " | Participants - "
            + str(participant_count)
            + " | "
            + source_short
            + "\n"
        )

    try:
        render_piperflow(piperflow, output_file=str(png_path))
    except Exception as e:
        print(f"  WARNING: PNG failed for '{title}': {e}")

    print(
        f"  [{case_index:03d}] {safe_name[:45]}  ({status_name}, {participant_count} participants)"
    )
    return True


# =============================================================================
# Aggregate Workflow
# =============================================================================


def create_aggregate_bpmn(cases: list[dict], output_dir: Path) -> None:
    # --- Compute outcome distribution across ALL categories ---
    cat_counts: dict[str, int] = defaultdict(int)
    cat_labels: dict[str, str] = {}
    for case in cases:
        name, cat = parse_status(case)
        cat_counts[cat] += 1
        cat_labels.setdefault(cat, name)
    total = sum(cat_counts.values()) or 1

    sorted_cats = sorted(cat_counts.items(), key=lambda x: -x[1])

    # Show top 2 outcomes; group the rest as Other — ensures 100% total.
    # (processpiper limit: 1 incoming + 3 outgoing = 4 max per node)
    top2 = sorted_cats[:2]
    remainder = sorted_cats[2:]

    other_count = sum(n for _, n in remainder)
    other_pct = round(100 * other_count / total)
    top2_pcts = [round(100 * n / total) for _, n in top2]
    top2_pcts[-1] = 100 - other_pct - sum(top2_pcts[:-1])  # adjust so sum == 100%

    other_detail = ", ".join(
        f"{cat_labels.get(cat, cat)} {round(100 * n / total)}%"
        for cat, n in remainder
        if n > 0
    )

    has_escalated = cat_counts.get("escalated", 0) > 0
    esc_pct = round(100 * cat_counts.get("escalated", 0) / total)

    # --- BPMN XML ---
    agg_lanes = DRN_AGG_LANES_ESC if has_escalated else DRN_AGG_LANES_BASE
    bpmn = SwimlaneBpmnBuilder("Wikipedia DRN Standard Workflow", agg_lanes)
    start = bpmn.start("Dispute Arises", "Filer")
    file_t = bpmn.task("File DRN Case", "Filer", user=True)
    review_t = bpmn.task("Review Filing", "Volunteer")
    valid_gw = bpmn.gateway("Valid?", "Volunteer")
    assess_t = bpmn.task("Assess Dispute", "Volunteer")
    path_gw = bpmn.gateway("Path?", "Volunteer")
    mediate_t = bpmn.task("Mediate Discussion", "Volunteer")
    discuss_t = bpmn.task("Discuss with Volunteer", "Filer", user=True)
    outcome_gw = bpmn.gateway("Outcome?", "Volunteer")

    end0 = bpmn.end(f"{cat_labels[top2[0][0]]} ({top2_pcts[0]}%)", "Volunteer")
    end1 = bpmn.end(f"{cat_labels[top2[1][0]]} ({top2_pcts[1]}%)", "Volunteer")
    end_other = bpmn.end(f"Other ({other_pct}%)", "Volunteer")
    declined = bpmn.end("Declined", "Volunteer")

    bpmn.flow(start, file_t)
    bpmn.flow(file_t, review_t)
    bpmn.flow(review_t, valid_gw)
    bpmn.flow(valid_gw, assess_t, "Yes")
    bpmn.flow(valid_gw, declined, "Invalid")
    bpmn.flow(assess_t, path_gw)
    bpmn.flow(path_gw, mediate_t, "Discussion")
    bpmn.flow(mediate_t, discuss_t)
    bpmn.flow(discuss_t, outcome_gw)
    bpmn.flow(outcome_gw, end0, cat_labels[top2[0][0]])
    bpmn.flow(outcome_gw, end1, cat_labels[top2[1][0]])
    bpmn.flow(outcome_gw, end_other, "Other")

    if has_escalated:
        escalate_t = bpmn.task("Escalate to RFC/ArbCom", "Admin")
        escalated = bpmn.end(f"Escalated ({esc_pct}%)", "Admin")
        bpmn.flow(path_gw, escalate_t, "Complex")
        bpmn.flow(escalate_t, escalated)

    _write_bpmn_to_both_locations(
        output_dir / "drn_aggregate_workflow.bpmn", bpmn.to_xml(), "drn"
    )

    # --- PNG via PiperFlow ---
    end0_label = "end " + cat_labels[top2[0][0]] + " " + str(top2_pcts[0]) + "%"
    end1_label = "end " + cat_labels[top2[1][0]] + " " + str(top2_pcts[1]) + "%"
    other_label = "end Other " + str(other_pct) + "%"

    if has_escalated:
        esc_extra_lane = [
            "    lane: Admin",
            "        [Escalate to RFC/ArbCom] as escalate",
            "        (end Escalated " + str(esc_pct) + "%) as escalated",
        ]
        esc_extra_flows = [
            "path_check->escalate: Complex",
            "escalate->escalated",
        ]
    else:
        esc_extra_lane = []
        esc_extra_flows = []

    lines = [
        "title: Wikipedia DRN Standard Workflow - Aggregate "
        + str(len(cases))
        + " cases",
        "colourtheme: BLUEMOUNTAIN",
        "",
        "lane: Disputing Parties",
        "    (start) as start",
        "    [Identify Dispute] as identify",
        "    [File DRN Case] as file",
        "    [Discuss with Other Party] as discuss",
        "",
        "pool: Dispute Resolution Noticeboard",
        "    lane: DRN Volunteer",
        "        [Review Filing] as review",
        "        <Valid Filing?> as valid_check",
        "        [Assess Dispute] as assess",
        "        <Resolution Path?> as path_check",
        "        [Mediate Discussion] as mediate",
        "        <Outcome?> as outcome_check",
        "        (" + end0_label + ") as end0",
        "        (" + end1_label + ") as end1",
        "        (" + other_label + ") as end_other",
        "        (end Declined) as declined",
    ]
    lines += esc_extra_lane
    lines += [
        "",
        "start->identify->file->review->valid_check",
        "valid_check->assess: Yes",
        "valid_check->declined: No",
        "assess->path_check",
        "path_check->mediate: Discussion",
    ]
    lines += esc_extra_flows
    lines += [
        "mediate->discuss->outcome_check",
        "outcome_check->end0: " + cat_labels[top2[0][0]],
        "outcome_check->end1: " + cat_labels[top2[1][0]],
        "outcome_check->end_other: Other",
        "",
        "footer: Other includes - "
        + (other_detail or "none")
        + " | "
        + str(len(cases))
        + " total cases",
    ]
    piperflow = "\n".join(lines) + "\n"

    png_path = output_dir / "drn_aggregate_workflow.png"
    try:
        render_piperflow(piperflow, output_file=str(png_path))
        print("  Aggregate workflow: PNG + BPMN ✓")
        print(
            f"  Outcomes: {cat_labels[top2[0][0]]} {top2_pcts[0]}%, {cat_labels[top2[1][0]]} {top2_pcts[1]}%, Other {other_pct}%  (sum=100%)"
        )
        if other_detail:
            print(f"  Other breakdown: {other_detail}")
    except Exception as e:
        print(f"  Aggregate PNG failed: {e}, BPMN created ✓")


# =============================================================================
# Main
# =============================================================================


def get_user_file_selection(files: list[Path]) -> list[Path]:
    print(f"\n{'=' * 60}\nAvailable DRN data files:\n{'=' * 60}")
    for i, f in enumerate(files, 1):
        print(f"  [{i}] {f.name}")
    print("\nWhich files? (numbers, range e.g. 1-3, or 'all') [Default: all]\n")
    while True:
        user_input = (
            input(f"Select files (1-{len(files)}, range, or 'all'): ").strip().lower()
        )
        if user_input in ("", "all"):
            return files
        try:
            selected = set()
            for part in user_input.split(","):
                part = part.strip()
                if "-" in part:
                    a, b = part.split("-")
                    selected.update(range(int(a), int(b) + 1))
                else:
                    selected.add(int(part))
            if all(1 <= i <= len(files) for i in selected):
                return [files[i - 1] for i in sorted(selected)]
            print(f"  Enter numbers between 1 and {len(files)}")
        except ValueError:
            print("  Invalid input. Use numbers, ranges (1-3), or 'all'")


def get_user_case_selection(total_cases: int) -> list[int]:
    """
    Prompt user to select which cases to generate individual diagrams for.
    Accepts specific indices, ranges, counts, or 'all'.

    Examples:
        all           → all cases
        10            → first 10 cases (1-10)
        100,200,305   → cases at positions 100, 200, 305
        1-50          → cases 1 through 50
        1,50-100,200  → case 1, cases 50-100, case 200
    """
    print(f"\nWhich cases to generate individual diagrams for? (1-{total_cases})")
    print("  Examples: all | 10 | 100,200,305,500 | 1-50 | 1,50-100,200")
    print("  [Default: all]\n")

    while True:
        user_input = input("Select cases: ").strip().lower()

        if user_input in ("", "all"):
            return list(range(1, total_cases + 1))

        try:
            selected: set[int] = set()
            for part in user_input.split(","):
                part = part.strip()
                if "-" in part:
                    a, b = part.split("-", 1)
                    selected.update(range(int(a), int(b) + 1))
                else:
                    n = int(part)
                    # If a plain number with no commas/ranges, treat as "first N"
                    if "," not in user_input and "-" not in user_input:
                        selected = set(range(1, n + 1))
                        break
                    selected.add(n)

            invalid = [i for i in selected if not (1 <= i <= total_cases)]
            if invalid:
                print(
                    f"  Out of range: {sorted(invalid)}. Enter numbers between 1 and {total_cases}."
                )
                continue

            indices = sorted(selected)
            print(
                f"  Selected {len(indices)} case(s): {indices[:5]}{'...' if len(indices) > 5 else ''}"
            )
            return indices

        except ValueError:
            print("  Invalid input. Use: all | 10 | 100,200,305 | 1-50")


def main():
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data" / "raw" / "drn"
    output_dir = project_root / "artifacts" / "bpmn" / "drn"
    output_dir.mkdir(parents=True, exist_ok=True)

    drn_files = sorted(data_dir.glob("*.json"))
    if not drn_files:
        print(f"No JSON files found in {data_dir}")
        return

    selected_files = get_user_file_selection(drn_files)
    print(f"\nSelected {len(selected_files)} file(s) for processing.")

    # Load ALL cases from selected files upfront — aggregate always uses the full dataset
    all_cases: list[dict] = []
    for drn_file in selected_files:
        data = load_drn_data(drn_file)
        cases = get_cases(data)
        if not cases:
            print(f"  WARNING: No cases in {drn_file.name}. Keys: {list(data.keys())}")
            continue
        all_cases.extend(cases)

    if not all_cases:
        print("No cases found across selected files.")
        return

    print(f"\nTotal cases across selected files: {len(all_cases)}")

    # Ask which specific cases to generate individual diagrams for
    selected_indices = get_user_case_selection(len(all_cases))
    print(f"\nGenerating {len(selected_indices)} individual case diagram(s)...\n")

    case_index = 0
    for idx in selected_indices:
        case_index += 1
        create_case_bpmn(all_cases[idx - 1], case_index, output_dir)

    # Aggregate always uses the full dataset regardless of how many individual diagrams were made
    print(
        f"\n{'=' * 60}\nCreating aggregate workflow ({len(all_cases)} cases)...\n{'=' * 60}"
    )
    create_aggregate_bpmn(all_cases, output_dir)

    print(f"\n{'=' * 60}")
    print("✓ COMPLETE")
    print(f"  Individual diagrams : {len(selected_indices)} of {len(all_cases)} cases")
    print(f"  Aggregate           : full dataset ({len(all_cases)} cases)")
    print(f"  Output              : {output_dir}")
    print(
        f"  Files               : {len(list(output_dir.glob('*.bpmn')))} BPMN, {len(list(output_dir.glob('*.png')))} PNG"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
