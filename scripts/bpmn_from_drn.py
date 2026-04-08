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
from dataclasses import dataclass
from xml.etree import ElementTree as ET
from xml.dom import minidom

# processpiper for PNG visualization
from processpiper.text2diagram import render as render_piperflow


# =============================================================================
# BPMN 2.0 XML Generator
# =============================================================================

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"


@dataclass
class BpmnElement:
    id: str
    name: str
    elem_type: str
    x: float = 0
    y: float = 0
    width: float = 100
    height: float = 80


@dataclass
class BpmnFlow:
    id: str
    source_id: str
    target_id: str
    name: str = ""


class BpmnXmlBuilder:
    """Builds complete BPMN 2.0 XML that works in all editors."""

    def __init__(self, name: str):
        self.name = name
        self.process_id = f"Process_{uuid.uuid4().hex[:8]}"
        self.elements: list[BpmnElement] = []
        self.flows: list[BpmnFlow] = []
        self._x = 150
        self._y = 100

    def _uid(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    def add_start(self, name: str = "Start") -> str:
        eid = self._uid("StartEvent")
        self.elements.append(
            BpmnElement(eid, name, "startEvent", self._x, self._y, 36, 36)
        )
        self._x += 100
        return eid

    def add_end(self, name: str = "End") -> str:
        eid = self._uid("EndEvent")
        self.elements.append(
            BpmnElement(eid, name, "endEvent", self._x, self._y, 36, 36)
        )
        self._x += 100
        return eid

    def add_task(self, name: str) -> str:
        eid = self._uid("Task")
        self.elements.append(
            BpmnElement(eid, name, "task", self._x, self._y - 22, 100, 80)
        )
        self._x += 130
        return eid

    def add_user_task(self, name: str) -> str:
        eid = self._uid("UserTask")
        self.elements.append(
            BpmnElement(eid, name, "userTask", self._x, self._y - 22, 100, 80)
        )
        self._x += 130
        return eid

    def add_gateway(self, name: str = "", gw_type: str = "exclusive") -> str:
        eid = self._uid("Gateway")
        elem_type = f"{gw_type}Gateway"
        self.elements.append(
            BpmnElement(eid, name, elem_type, self._x, self._y - 7, 50, 50)

    def add_flow(self, source: str, target: str, name: str = "") -> str:
        fid = self._uid("Flow")
        self.flows.append(BpmnFlow(fid, source, target, name))
        return fid

    def new_row(self, y_offset: float = 120):
        """Move to a new row for parallel branches."""
        self._y += y_offset
        self._x = 150

    def reset_x(self, x: float = 150):
        """Reset X position for branching."""
        self._x = x

    def to_xml(self) -> str:
        """Generate complete BPMN 2.0 XML."""
        # Register namespaces
        ET.register_namespace("bpmn", BPMN_NS)
        ET.register_namespace("bpmndi", BPMNDI_NS)
        ET.register_namespace("dc", DC_NS)
        ET.register_namespace("di", DI_NS)

        root = ET.Element(
            f"{{{BPMN_NS}}}definitions",
            {
                "id": f"Definitions_{uuid.uuid4().hex[:8]}",
                "targetNamespace": "http://bpmn.io/schema/bpmn",
                "exporter": "DRN-BPMN-Generator",
                "exporterVersion": "1.0",
            },
        )
        process = ET.SubElement(
            root,
            f"{{{BPMN_NS}}}process",
            {"id": self.process_id, "name": self.name, "isExecutable": "false"},
        )
        for elem in self.elements:
            el = ET.SubElement(
                process,
                f"{{{BPMN_NS}}}{elem.elem_type}",
                {"id": elem.id, "name": elem.name},
            )
            for flow in self.flows:
                if flow.target_id == elem.id:
                    ET.SubElement(el, f"{{{BPMN_NS}}}incoming").text = flow.id
                if flow.source_id == elem.id:
                    ET.SubElement(el, f"{{{BPMN_NS}}}outgoing").text = flow.id
        for flow in self.flows:
            attrs = {
                "id": flow.id,
                "sourceRef": flow.source_id,
                "targetRef": flow.target_id,
            }
            if flow.name:
                attrs["name"] = flow.name
            ET.SubElement(process, f"{{{BPMN_NS}}}sequenceFlow", attrs)

        diagram = ET.SubElement(
            root,
            f"{{{BPMNDI_NS}}}BPMNDiagram",
            {"id": f"BPMNDiagram_{uuid.uuid4().hex[:8]}"},
        )
        plane = ET.SubElement(
            diagram,
            f"{{{BPMNDI_NS}}}BPMNPlane",
            {"id": f"BPMNPlane_{uuid.uuid4().hex[:8]}", "bpmnElement": self.process_id},
        )
        for elem in self.elements:
            shape = ET.SubElement(
                plane,
                f"{{{BPMNDI_NS}}}BPMNShape",
                {"id": f"{elem.id}_di", "bpmnElement": elem.id},
            )
            ET.SubElement(
                shape,
                f"{{{DC_NS}}}Bounds",
                {
                    "x": str(elem.x),
                    "y": str(elem.y),
                    "width": str(elem.width),
                    "height": str(elem.height),
                },
            )
        elem_map = {e.id: e for e in self.elements}
        for flow in self.flows:
            edge = ET.SubElement(
                plane,
                f"{{{BPMNDI_NS}}}BPMNEdge",
                {"id": f"{flow.id}_di", "bpmnElement": flow.id},
            )
            src, tgt = elem_map.get(flow.source_id), elem_map.get(flow.target_id)
            if src and tgt:
                ET.SubElement(
                    edge,
                    f"{{{DI_NS}}}waypoint",
                    {"x": str(src.x + src.width), "y": str(src.y + src.height / 2)},
                )
                ET.SubElement(
                    edge,
                    f"{{{DI_NS}}}waypoint",
                    {"x": str(tgt.x), "y": str(tgt.y + tgt.height / 2)},
                )
        return minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(
            indent="  "
        )


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
    bpmn = BpmnXmlBuilder(f"DRN: {title[:50]}")
    start = bpmn.add_start("Dispute Filed")
    file_task = bpmn.add_task("File DRN Case")
    review = bpmn.add_task("Review Filing")
    valid_gw = bpmn.add_gateway("Valid Case?")
    bpmn.add_flow(start, file_task)
    bpmn.add_flow(file_task, review)
    bpmn.add_flow(review, valid_gw)

    if participant_count > 1:
        discuss = bpmn.add_task("Discussion Phase")
        facilitate = bpmn.add_task("Facilitate")
        outcome_gw = bpmn.add_gateway("Resolution?")
        bpmn.add_flow(valid_gw, facilitate, "Yes")
        bpmn.add_flow(facilitate, discuss)
        bpmn.add_flow(discuss, outcome_gw)
        if status_cat == "success":
            end = bpmn.add_end("Resolved")
            bpmn.add_flow(outcome_gw, end, "Agreement")
        elif status_cat == "escalated":
            escalate = bpmn.add_task("Escalate")
            end = bpmn.add_end("Escalated")
            bpmn.add_flow(outcome_gw, escalate, "Complex")
            bpmn.add_flow(escalate, end)
        elif status_cat == "inactive":
            end = bpmn.add_end("Stale")
            bpmn.add_flow(outcome_gw, end, "Abandoned")
        else:
            end = bpmn.add_end("Closed")
            bpmn.add_flow(outcome_gw, end, "No Resolution")
    else:
        if status_cat == "success":
            end = bpmn.add_end("Resolved")
        elif status_cat == "escalated":
            end = bpmn.add_end("Escalated")
        else:
            end = bpmn.add_end("Closed")
        bpmn.add_flow(valid_gw, end, "Yes")

    bpmn.new_row(100)
    bpmn.reset_x(480)
    declined = bpmn.add_end("Declined")
    bpmn.add_flow(valid_gw, declined, "Invalid")

    try:
        bpmn_path.write_text(bpmn.to_xml(), encoding="utf-8")
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
            "        (end " + status_name + ") as end_event\n"
            "        (end Declined) as end_declined\n"
            "\n"
            "start->file_case->review->valid_check\n"
            "valid_check->facilitate: Yes\n"
            "valid_check->end_declined: No\n"
            "facilitate->discuss->resolution_check\n"
            "resolution_check->end_event: " + status_name + "\n"
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
            "        (end " + status_name + ") as end_event\n"
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
        f"{cat_labels.get(cat, cat)} {round(100*n/total)}%"
        for cat, n in remainder
        if n > 0
    )

    has_escalated = cat_counts.get("escalated", 0) > 0
    esc_pct = round(100 * cat_counts.get("escalated", 0) / total)

    # --- BPMN XML ---
    bpmn = BpmnXmlBuilder("Wikipedia DRN Standard Workflow")
    start = bpmn.add_start("Dispute Arises")
    file_t = bpmn.add_task("File DRN Case")
    review_t = bpmn.add_task("Review Filing")
    valid_gw = bpmn.add_gateway("Valid?")
    assess_t = bpmn.add_task("Assess Dispute")
    path_gw = bpmn.add_gateway("Path?")
    mediate_t = bpmn.add_task("Mediate Discussion")
    outcome_gw = bpmn.add_gateway("Outcome?")

    end0 = bpmn.add_end(f"{cat_labels[top2[0][0]]} ({top2_pcts[0]}%)")
    bpmn.add_flow(start, file_t)
    bpmn.add_flow(file_t, review_t)
    bpmn.add_flow(review_t, valid_gw)
    bpmn.add_flow(valid_gw, assess_t, "Yes")
    bpmn.add_flow(assess_t, path_gw)
    bpmn.add_flow(path_gw, mediate_t, "Discussion")
    bpmn.add_flow(mediate_t, outcome_gw)
    bpmn.add_flow(outcome_gw, end0, cat_labels[top2[0][0]])
    bpmn.new_row(100)
    bpmn.reset_x(900)
    end1 = bpmn.add_end(f"{cat_labels[top2[1][0]]} ({top2_pcts[1]}%)")
    bpmn.add_flow(outcome_gw, end1, cat_labels[top2[1][0]])
    bpmn.new_row(100)
    bpmn.reset_x(900)
    end_other = bpmn.add_end(f"Other ({other_pct}%)")
    bpmn.add_flow(outcome_gw, end_other, "Other")

    if has_escalated:
        bpmn.new_row(100)
        bpmn.reset_x(650)
        escalate_t = bpmn.add_task("Escalate to RFC/ArbCom")
        escalated = bpmn.add_end(f"Escalated ({esc_pct}%)")
        bpmn.add_flow(path_gw, escalate_t, "Complex")
        bpmn.add_flow(escalate_t, escalated)
    bpmn.new_row(100)
    bpmn.reset_x(400)
    declined = bpmn.add_end("Declined")
    bpmn.add_flow(valid_gw, declined, "Invalid")
    (output_dir / "drn_aggregate_workflow.bpmn").write_text(
        bpmn.to_xml(), encoding="utf-8"
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
    print(f"\n{'='*60}\nAvailable DRN data files:\n{'='*60}")
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
        f"\n{'='*60}\nCreating aggregate workflow ({len(all_cases)} cases)...\n{'='*60}"
    )
    create_aggregate_bpmn(all_cases, output_dir)

    print(f"\n{'='*60}")
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
