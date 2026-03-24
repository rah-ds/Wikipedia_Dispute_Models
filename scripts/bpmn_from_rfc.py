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
from pathlib import Path

from processpiper.text2diagram import render as render_piperflow


# ---------------------------------------------------------------------------
# BPMN 2.0 XML Builder (zero-dependency, stdlib only)
# ---------------------------------------------------------------------------


class BpmnXmlBuilder:
    EVENT_SIZE = 36
    GATEWAY_SIZE = 50
    NODE_W = 120
    NODE_H = 60
    X_STEP = 180
    Y_CENTER = 200

    def __init__(self, name: str):
        self.name = name
        self.process_id = "Process_" + self._uid()
        self.nodes: list[dict] = []
        self.flows: list[tuple] = []
        self._x = 80

    def add_start(self, label: str) -> str:
        nid = "StartEvent_" + self._uid()
        self.nodes.append(
            {
                "id": nid,
                "type": "startEvent",
                "label": label,
                "x": self._x,
                "y": self.Y_CENTER,
                "w": self.EVENT_SIZE,
                "h": self.EVENT_SIZE,
            }
        )
        self._x += self.X_STEP
        return nid

    def add_end(self, label: str, x_off: int = 0, y_off: int = 0) -> str:
        nid = "EndEvent_" + self._uid()
        self.nodes.append(
            {
                "id": nid,
                "type": "endEvent",
                "label": label,
                "x": self._x + x_off,
                "y": self.Y_CENTER + y_off,
                "w": self.EVENT_SIZE,
                "h": self.EVENT_SIZE,
            }
        )
        return nid

    def add_task(
        self, label: str, task_type: str = "userTask", x_off: int = 0, y_off: int = 0
    ) -> str:
        nid = "Task_" + self._uid()
        self.nodes.append(
            {
                "id": nid,
                "type": task_type,
                "label": label,
                "x": self._x + x_off,
                "y": self.Y_CENTER - self.NODE_H // 2 + y_off,
                "w": self.NODE_W,
                "h": self.NODE_H,
            }
        )
        self._x += self.X_STEP
        return nid

    def add_gateway(self, label: str, x_off: int = 0, y_off: int = 0) -> str:
        nid = "Gateway_" + self._uid()
        self.nodes.append(
            {
                "id": nid,
                "type": "exclusiveGateway",
                "label": label,
                "x": self._x + x_off,
                "y": self.Y_CENTER - self.GATEWAY_SIZE // 2 + y_off,
                "w": self.GATEWAY_SIZE,
                "h": self.GATEWAY_SIZE,
            }
        )
        self._x += self.X_STEP
        return nid

    def connect(self, src: str, tgt: str, label: str | None = None) -> str:
        fid = "Flow_" + self._uid()
        self.flows.append((fid, src, tgt, label))
        return fid

    @staticmethod
    def _esc(text: str) -> str:
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    @staticmethod
    def _uid() -> str:
        return uuid.uuid4().hex[:8]

    def to_xml(self) -> str:
        ind = "  "
        nodes_xml, shapes_xml, edges_xml = [], [], []
        for n in self.nodes:
            nid, ntype, lbl = n["id"], n["type"], self._esc(n["label"])
            if ntype in ("startEvent", "endEvent"):
                nodes_xml.append(f'{ind*2}<{ntype} id="{nid}" name="{lbl}"/>')
            elif ntype == "exclusiveGateway":
                nodes_xml.append(
                    f'{ind*2}<exclusiveGateway id="{nid}" name="{lbl}" gatewayDirection="Diverging"/>'
                )
            else:
                nodes_xml.append(f'{ind*2}<{ntype} id="{nid}" name="{lbl}"/>')
            shapes_xml.append(
                f'{ind*2}<bpmndi:BPMNShape id="{nid}_di" bpmnElement="{nid}">\n'
                f'{ind*3}<dc:Bounds x="{n["x"]}" y="{n["y"]}" width="{n["w"]}" height="{n["h"]}"/>\n'
                f'{ind*3}<bpmndi:BPMNLabel/>\n'
                f'{ind*2}</bpmndi:BPMNShape>'
            )
        for fid, src, tgt, lbl in self.flows:
            name_attr = f' name="{self._esc(lbl)}"' if lbl else ""
            nodes_xml.append(
                f'{ind*2}<sequenceFlow id="{fid}" sourceRef="{src}" targetRef="{tgt}"{name_attr}/>'
            )
            edges_xml.append(
                f'{ind*2}<bpmndi:BPMNEdge id="{fid}_di" bpmnElement="{fid}">\n'
                f"{ind*3}<bpmndi:BPMNLabel/>\n"
                f"{ind*2}</bpmndi:BPMNEdge>"
            )
        nl = "\n"
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="http://www.omg.org/spec/BPMN/20100524/MODEL"
             xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
             xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
             xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
             xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
             targetNamespace="http://bpmn.io/schema/bpmn"
             id="Definitions_{self._uid()}">
  <process id="{self.process_id}" name="{self._esc(self.name)}" isExecutable="false">
{nl.join(nodes_xml)}
  </process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="{self.process_id}">
{nl.join(shapes_xml)}
{nl.join(edges_xml)}
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</definitions>
"""


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

    b = BpmnXmlBuilder("RFC: " + parsed["title"][:60])
    start = b.add_start("RFC Filed")
    submit = b.add_task("Submission - " + filed_date, "userTask")
    review = b.add_task("Submission Review", "serviceTask")
    gw_valid = b.add_gateway("Valid RFC?")
    inv_end = b.add_end("Marked Invalid", y_off=-160)
    b.connect(gw_valid, inv_end, "No - Invalid")

    if has_disc:
        facilitate = b.add_task("Assess and Facilitate", "userTask")
        discuss = b.add_task(disc_label[:60], "userTask")
        gw_out = b.add_gateway("Outcome?")
        b.connect(gw_valid, facilitate, "Yes")
        b.connect(facilitate, discuss)
        b.connect(discuss, gw_out)
    else:
        gw_out = b.add_gateway("Outcome?")
        b.connect(gw_valid, gw_out, "Yes")

    end_main = b.add_end(outcome)
    b.connect(gw_out, end_main, outcome)
    b.connect(start, submit)
    b.connect(submit, review)
    b.connect(review, gw_valid)

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

    b = BpmnXmlBuilder("RFC Standard Workflow (Aggregate)")
    start = b.add_start("RFC Filed")
    submit = b.add_task("RFC Submission", "userTask")
    screen = b.add_task("Categorise and Screen", "serviceTask")
    gw_valid = b.add_gateway("Valid RFC?")
    inv_end = b.add_end("Invalid - Closed", y_off=-160)
    assess = b.add_task("Assess RFC", "userTask")
    discuss = b.add_task("Discussion Period", "userTask")
    closer = b.add_task("Closer Reviews Outcome", "userTask")
    gw_out = b.add_gateway("Resolution Outcome?")

    b.connect(start, submit)
    b.connect(submit, screen)
    b.connect(screen, gw_valid)
    b.connect(gw_valid, inv_end, "No - Invalid")
    b.connect(gw_valid, assess, "Yes - Valid")
    b.connect(assess, discuss)
    b.connect(discuss, closer)
    b.connect(closer, gw_out)

    y_off = 0
    for i, (o, _) in enumerate(top2):
        end = b.add_end(o + " (" + str(top2_pcts[i]) + "%)", y_off=y_off)
        b.connect(gw_out, end, o)
        y_off += 100
    end_other = b.add_end(
        "Other (" + str(other_pct) + "%): " + (other_detail or "none"), y_off=y_off
    )
    b.connect(gw_out, end_other, "Other")

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
