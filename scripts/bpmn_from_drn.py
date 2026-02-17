"""
DRN (Dispute Resolution Noticeboard) to BPMN Model Generator

Dual approach:
1. processpiper for PNG visualization (good visuals, pools/lanes)
2. Direct BPMN 2.0 XML generation for complete .bpmn files

This ensures the .bpmn files contain all elements and work in any BPMN editor.

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
# BPMN 2.0 XML Generator (Complete, works in all editors)
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
        )
        self._x += 80
        return eid

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

        # Process
        process = ET.SubElement(
            root,
            f"{{{BPMN_NS}}}process",
            {"id": self.process_id, "name": self.name, "isExecutable": "false"},
        )

        # Elements
        for elem in self.elements:
            el = ET.SubElement(
                process,
                f"{{{BPMN_NS}}}{elem.elem_type}",
                {"id": elem.id, "name": elem.name},
            )
            # Add incoming/outgoing references
            for flow in self.flows:
                if flow.target_id == elem.id:
                    inc = ET.SubElement(el, f"{{{BPMN_NS}}}incoming")
                    inc.text = flow.id
                if flow.source_id == elem.id:
                    out = ET.SubElement(el, f"{{{BPMN_NS}}}outgoing")
                    out.text = flow.id

        # Sequence flows
        for flow in self.flows:
            attrs = {
                "id": flow.id,
                "sourceRef": flow.source_id,
                "targetRef": flow.target_id,
            }
            if flow.name:
                attrs["name"] = flow.name
            ET.SubElement(process, f"{{{BPMN_NS}}}sequenceFlow", attrs)

        # Diagram (visual layout)
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

        # Shapes
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

        # Edges
        elem_map = {e.id: e for e in self.elements}
        for flow in self.flows:
            edge = ET.SubElement(
                plane,
                f"{{{BPMNDI_NS}}}BPMNEdge",
                {"id": f"{flow.id}_di", "bpmnElement": flow.id},
            )
            src, tgt = elem_map.get(flow.source_id), elem_map.get(flow.target_id)
            if src and tgt:
                # Waypoints
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

        xml_str = ET.tostring(root, encoding="unicode")
        return minidom.parseString(xml_str).toprettyxml(indent="  ")


# =============================================================================
# Status & Event Processing
# =============================================================================

STATUS_MAP = {
    "new": ("New", "active"),
    "open": ("Open", "active"),
    "discussion": ("Discussion", "active"),
    "pending": ("Pending", "active"),
    "in progress": ("In Progress", "active"),
    "stale": ("Stale", "inactive"),
    "resolved": ("Resolved", "success"),
    "closed": ("Closed", "closed"),
    "failed": ("Failed", "failed"),
    "escalated": ("Escalated", "escalated"),
    "rfc": ("To RFC", "escalated"),
    "arbcom": ("To ArbCom", "escalated"),
    "withdrawn": ("Withdrawn", "closed"),
    "declined": ("Declined", "closed"),
}


def load_drn_data(filepath: Path) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_status(status_str: str | None) -> tuple[str, str]:
    if not status_str:
        return ("Unknown", "unknown")
    status_lower = status_str.lower().strip()
    for key, value in STATUS_MAP.items():
        if key in status_lower:
            return value
    return (status_str.title(), "unknown")


def safe_filename(title: str, max_len: int = 40) -> str:
    """Create a safe filename from title."""
    safe = re.sub(r"[^\w\-]", "_", title)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe[:max_len] if safe else "unnamed"


# =============================================================================
# Case BPMN Generation
# =============================================================================


def create_case_bpmn(case: dict, case_index: int, output_dir: Path) -> bool:
    """
    Create both PNG (via processpiper) and BPMN XML (direct) for a case.
    Returns True if successful.
    """
    title = case.get("title", f"Case_{case_index}")
    status_name, status_cat = parse_status(case.get("status"))
    participant_count = case.get("participant_count", 0)

    safe_name = safe_filename(title)
    png_path = output_dir / f"case_{case_index:03d}_{safe_name}.png"
    bpmn_path = output_dir / f"case_{case_index:03d}_{safe_name}.bpmn"

    # === 1. Generate BPMN XML (complete, works in all editors) ===
    bpmn = BpmnXmlBuilder(f"DRN: {title[:50]}")

    # Build the workflow
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

        # Outcomes based on status
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
        # Simple case - no discussion
        if status_cat == "success":
            end = bpmn.add_end("Resolved")
        elif status_cat == "escalated":
            end = bpmn.add_end("Escalated")
        else:
            end = bpmn.add_end("Closed")
        bpmn.add_flow(valid_gw, end, "Yes")

    # Add decline path
    bpmn.new_row(100)
    bpmn.reset_x(480)
    declined = bpmn.add_end("Declined")
    bpmn.add_flow(valid_gw, declined, "Invalid")

    # Write BPMN XML
    try:
        bpmn_path.write_text(bpmn.to_xml(), encoding="utf-8")
    except Exception as e:
        print(f"  ERROR writing BPMN for '{title}': {e}")
        return False

    # === 2. Generate PNG via PiperFlow (better visuals) ===
    piperflow = f"""
title: DRN: {title[:40]}
colourtheme: BLUEMOUNTAIN

lane: Filer
    (start) as start
    [File Case] as file_case
    {"[Participate in Discussion] as discuss" if participant_count > 1 else ""}

pool: DRN Process
    lane: Volunteer/Admin
        [Review Filing] as review
        <Valid Case?> as valid_check
        {"[Facilitate Discussion] as facilitate" if participant_count > 1 else ""}
        {"<Resolution Possible?> as resolution_check" if participant_count > 1 else ""}
        (end) as end_event

start->file_case->review->valid_check
{"valid_check->facilitate: Yes" if participant_count > 1 else "valid_check->end_event: Yes"}
{"facilitate->discuss->resolution_check" if participant_count > 1 else ""}
{"resolution_check->end_event: " + status_name if participant_count > 1 else ""}

footer: Status: {status_name} | Participants: {participant_count}
"""

    try:
        render_piperflow(piperflow, output_file=str(png_path))
    except Exception as e:
        print(f"  WARNING: PNG generation failed for '{title}': {e}")
        # Continue - BPMN was created successfully

    print(f"  [{case_index:03d}] {safe_name}: PNG + BPMN ✓")
    return True


# =============================================================================
# Aggregate Workflow
# =============================================================================


def create_aggregate_bpmn(cases: list[dict], output_dir: Path) -> None:
    """Create standard DRN workflow with statistics."""

    outcomes = defaultdict(int)
    for case in cases:
        _, cat = parse_status(case.get("status"))
        outcomes[cat] += 1
    total = sum(outcomes.values()) or 1

    # BPMN XML
    bpmn = BpmnXmlBuilder("Wikipedia DRN Standard Workflow")

    start = bpmn.add_start("Dispute Arises")
    file_t = bpmn.add_task("File DRN Case")
    review_t = bpmn.add_task("Review Filing")
    valid_gw = bpmn.add_gateway("Valid?")
    assess_t = bpmn.add_task("Assess Dispute")
    path_gw = bpmn.add_gateway("Path?")
    mediate_t = bpmn.add_task("Mediate Discussion")
    outcome_gw = bpmn.add_gateway("Outcome?")

    resolved_pct = outcomes["success"] * 100 // total
    closed_pct = outcomes["closed"] * 100 // total
    escalated_pct = outcomes["escalated"] * 100 // total

    resolved = bpmn.add_end(f"Resolved ({resolved_pct}%)")

    bpmn.add_flow(start, file_t)
    bpmn.add_flow(file_t, review_t)
    bpmn.add_flow(review_t, valid_gw)
    bpmn.add_flow(valid_gw, assess_t, "Yes")
    bpmn.add_flow(assess_t, path_gw)
    bpmn.add_flow(path_gw, mediate_t, "Discussion")
    bpmn.add_flow(mediate_t, outcome_gw)
    bpmn.add_flow(outcome_gw, resolved, "Agreement")

    # Branch: Closed
    bpmn.new_row(100)
    bpmn.reset_x(900)
    closed = bpmn.add_end(f"Closed ({closed_pct}%)")
    bpmn.add_flow(outcome_gw, closed, "No Resolution")

    # Branch: Escalated
    bpmn.new_row(100)
    bpmn.reset_x(650)
    escalate_t = bpmn.add_task("Escalate to RFC/ArbCom")
    escalated = bpmn.add_end(f"Escalated ({escalated_pct}%)")
    bpmn.add_flow(path_gw, escalate_t, "Complex")
    bpmn.add_flow(escalate_t, escalated)

    # Branch: Declined
    bpmn.new_row(100)
    bpmn.reset_x(400)
    declined = bpmn.add_end("Declined")
    bpmn.add_flow(valid_gw, declined, "Invalid")

    bpmn_path = output_dir / "drn_aggregate_workflow.bpmn"
    bpmn_path.write_text(bpmn.to_xml(), encoding="utf-8")

    # PNG via PiperFlow
    piperflow = f"""
title: Wikipedia DRN Standard Workflow
colourtheme: BLUEMOUNTAIN

lane: Disputing Parties
    (start) as start
    [Identify Dispute] as identify
    [File DRN Case] as file
    [Discuss with Other Party] as discuss

pool: Dispute Resolution Noticeboard
    lane: DRN Volunteer
        [Review Filing] as review
        <Valid Filing?> as valid_check
        [Assess Dispute] as assess
        <Resolution Path?> as path_check
        [Mediate Discussion] as mediate
        <Outcome?> as outcome_check
        (end) as resolved //Resolved ({resolved_pct}%)
        (end) as closed //Closed ({closed_pct}%)
    lane: Admin/Escalation
        [Escalate to RFC/ArbCom] as escalate
        (end) as escalated //Escalated ({escalated_pct}%)
        (end) as declined //Declined

start->identify->file->review->valid_check
valid_check->assess: Yes
valid_check->declined: No
assess->path_check
path_check->mediate: Discussion
path_check->escalate: Complex
mediate->discuss->outcome_check
outcome_check->resolved: Agreement
outcome_check->closed: No Resolution
escalate->escalated

footer: Statistics from {len(cases)} DRN cases
"""

    png_path = output_dir / "drn_aggregate_workflow.png"
    try:
        render_piperflow(piperflow, output_file=str(png_path))
        print("  Aggregate workflow: PNG + BPMN ✓")
    except Exception as e:
        print(f"  Aggregate PNG failed: {e}, BPMN created ✓")


# =============================================================================
# Main
# =============================================================================


def get_user_file_selection(files: list[Path]) -> list[Path]:
    """Prompt user to select which files to process."""
    print(f"\n{'=' * 60}")
    print("Available DRN data files:")
    print("=" * 60)

    for i, f in enumerate(files, 1):
        print(f"  [{i}] {f.name}")

    print("\nWhich files should be processed?")
    print("  Options: Enter numbers separated by commas (e.g., 1,3)")
    print("           Enter a range (e.g., 1-3)")
    print("           Enter 'all' for all files")
    print("  [Default: all]\n")

    while True:
        user_input = (
            input(f"Select files (1-{len(files)}, range, or 'all'): ").strip().lower()
        )

        if user_input == "" or user_input == "all":
            return files

        try:
            selected_indices = set()

            # Parse input (handles "1,2,3" and "1-3" and "1,3-5")
            for part in user_input.split(","):
                part = part.strip()
                if "-" in part:
                    start, end = part.split("-")
                    selected_indices.update(range(int(start), int(end) + 1))
                else:
                    selected_indices.add(int(part))

            # Validate indices
            if all(1 <= i <= len(files) for i in selected_indices):
                selected = [files[i - 1] for i in sorted(selected_indices)]
                return selected
            else:
                print(f"  Please enter numbers between 1 and {len(files)}")
        except ValueError:
            print("  Invalid input. Use numbers, ranges (1-3), or 'all'")


def get_user_case_count(total_cases: int) -> int:
    """Prompt user to select how many cases to process."""
    print("\nHow many cases should BPMN models be created for?")
    print(f"  Options: 1 to {total_cases}, or 'all' for all cases")
    print("  [Default: all]\n")

    while True:
        try:
            user_input = (
                input(f"Enter number (1-{total_cases}) or 'all': ").strip().lower()
            )

            if user_input == "" or user_input == "all":
                return total_cases

            count = int(user_input)
            if 1 <= count <= total_cases:
                return count
            else:
                print(f"  Please enter a number between 1 and {total_cases}")
        except ValueError:
            print(f"  Invalid input. Enter a number (1-{total_cases}) or 'all'")


def main():
    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data" / "raw" / "drn"
    output_dir = project_root / "artifacts" / "bpmn"
    output_dir.mkdir(parents=True, exist_ok=True)

    drn_files = sorted(data_dir.glob("*.json"))

    if not drn_files:
        print(f"No JSON files found in {data_dir}")
        return

    # Let user select which files to process
    selected_files = get_user_file_selection(drn_files)
    print(f"\nSelected {len(selected_files)} file(s) for processing.")

    all_cases = []
    case_index = 0

    for drn_file in selected_files:
        print(f"\n{'=' * 60}")
        print(f"Processing: {drn_file.name}")
        print("=" * 60)

        data = load_drn_data(drn_file)
        cases = data.get("parsed_cases", [])
        revisions = data.get("revisions", [])

        print(f"Found {len(cases)} cases, {len(revisions)} revisions")

        # Ask user how many cases to process
        cases_to_process = get_user_case_count(len(cases))
        print(f"\nGenerating BPMN for {cases_to_process} case(s)...\n")

        # Process selected number of cases
        for case in cases[:cases_to_process]:
            case_index += 1
            create_case_bpmn(case, case_index, output_dir)
            all_cases.append(case)

    # Aggregate workflow
    if all_cases:
        print(f"\n{'=' * 60}")
        print("Creating aggregate workflow...")
        print("=" * 60)
        create_aggregate_bpmn(all_cases, output_dir)

    print(f"\n{'=' * 60}")
    print(f"✓ COMPLETE: {len(all_cases)} cases processed")
    print(f"✓ Output directory: {output_dir}")
    print(
        f"✓ Files created: {len(list(output_dir.glob('*.bpmn')))} BPMN, {len(list(output_dir.glob('*.png')))} PNG"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
