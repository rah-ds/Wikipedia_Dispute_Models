"""
ARB (Arbitration) to BPMN Model Generator
==========================================

Reads Wikipedia Arbitration case data from JSON and generates:
  - Polished PNG diagrams via processpiper (swimlane layout, BLUEMOUNTAIN theme)
  - Complete BPMN 2.0 XML files (viewable in bpmn.io / Camunda Modeler)

Install: pip install processpiper

Usage:
    python bpmn_from_arb.py
    python bpmn_from_arb.py --input data/raw/arb/
    python bpmn_from_arb.py --input arb_part_1.json --max-cases 10 --output artifacts/bpmn/arb

View output:
    PNG  -- open directly in any image viewer
    BPMN -- drag & drop at https://demo.bpmn.io
            or use Camunda Modeler: https://camunda.com/download/modeler/
"""

from __future__ import annotations

import argparse
import json
import re
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET

import processpiper.lane as _pp_lane
from processpiper.text2diagram import render as _render_piperflow_raw
from processpiper.constants import Configs as _PiperConfigs

_PiperConfigs.LANE_SHAPE_RIGHT_MARGIN = 150  # was 30
_PiperConfigs.SURFACE_RIGHT_MARGIN = 80  # was 20


_orig_lane_set_draw_position = _pp_lane.Lane.set_draw_position


def _patched_lane_set_draw_position(self, *args, **kwargs):
    """Wrapper that adds LANE_SHAPE_RIGHT_MARGIN to computed width."""
    result = _orig_lane_set_draw_position(self, *args, **kwargs)
    self.width += _PiperConfigs.LANE_SHAPE_RIGHT_MARGIN
    return result


_pp_lane.Lane.set_draw_position = _patched_lane_set_draw_position
# ── End fix ────────────────────────────────────────────────────


def _add_right_padding(png_path: str, pad: int = 80) -> None:
    """
    Always add `pad` px of blank space on the right side of the PNG.
    processpiper's swimlane grey stripes make edge-detection unreliable,
    so we unconditionally extend the canvas.
    """
    try:
        from PIL import Image

        img = Image.open(png_path)
        w, h = img.size
        bg = img.getpixel((2, 2))  # outer margin colour
        new_img = Image.new(img.mode, (w + pad, h), bg)
        new_img.paste(img, (0, 0))
        new_img.save(png_path, dpi=(1200, 1200), optimize=False)
    except Exception:
        pass


def render_piperflow(dsl: str, output_file: str) -> None:
    """Render PiperFlow DSL to PNG with right-margin safety."""
    _render_piperflow_raw(dsl, output_file=output_file)
    _add_right_padding(output_file)


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

ARB_LANES = ["Requesting Party", "Clerk", "Arbitrators", "Enforcement"]


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
        # (eid, label, elem_type, lane_name, step)
        self._elements: list[tuple[str, str, str, str, int]] = []
        # (fid, source_id, target_id, label)
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
                "exporter": "ARB-BPMN-Generator",
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


# ---------------------------------------------------------------------------
# ARB Data Parsing
# ---------------------------------------------------------------------------


def _load_single_json(filepath: Path) -> list[dict]:
    """Load ARB cases from a single JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("cases", "arb", "arbitration", "data"):
            if key in data and isinstance(data[key], list):
                return data[key]
        for v in data.values():
            if isinstance(v, list):
                return v
    return []


def load_arb_data(source: str | Path | list[Path]) -> list[dict]:
    """
    Load ARB cases from one file, multiple files, or a directory.

    Accepts:
      - A single JSON file path
      - A list of JSON file paths  (merged together)
      - A directory               (all *.json inside are merged)
    """
    if isinstance(source, list):
        all_cases: list[dict] = []
        seen_titles: set[str] = set()
        for fp in source:
            cases = _load_single_json(fp)
            for c in cases:
                title = c.get("title", "")
                if title not in seen_titles:
                    seen_titles.add(title)
                    all_cases.append(c)
            print(f"  Loaded {len(cases)} cases from {fp.name}")
        return all_cases

    source = Path(source)
    if source.is_dir():
        json_files = sorted(source.glob("*.json"))
        if not json_files:
            return []
        return load_arb_data(json_files)

    return _load_single_json(source)


def _extract_date(text: str, pattern: str) -> str | None:
    """Extract a date string near a label like 'Case Opened'."""
    m = re.search(pattern, text, re.I | re.DOTALL)
    if not m:
        return None
    raw = m.group(1).strip()
    iso = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if iso:
        return iso.group(1)
    for fmt in [r"(\d{1,2}\s+\w+\s+\d{4})", r"(\w+\s+\d{1,2},?\s+\d{4})", r"(\d{4})"]:
        d = re.search(fmt, raw)
        if d:
            return d.group(1)
    return raw[:40] if raw else None


def _count_accept_votes(content: str) -> tuple[int, int, int]:
    """Parse arbitrator votes. Returns (accept, decline, recuse)."""
    vote_summary = re.search(
        r"Arbitrators['\u2019]?\s*opinions?\s*on\s*hearing.*?" r"\((\d+)/(\d+)/(\d+)",
        content,
        re.I,
    )
    if vote_summary:
        return (
            int(vote_summary.group(1)),
            int(vote_summary.group(2)),
            int(vote_summary.group(3)),
        )
    prelim_section = re.search(
        r"(?:Preliminary decision|Arbitrators['\u2019]?\s*opinion)"
        r"(.*?)(?:=\s*(?:Final|Temporary)|\Z)",
        content,
        re.I | re.DOTALL,
    )
    if not prelim_section:
        return (0, 0, 0)
    section = prelim_section.group(1)
    return (
        len(re.findall(r"\bAccept\b", section, re.I)),
        len(re.findall(r"\bDecline\b", section, re.I)),
        len(re.findall(r"\bRecuse\b", section, re.I)),
    )


def _extract_involved_parties(content: str) -> list[str]:
    """Extract named parties from the Involved parties / Parties section."""
    section = None
    for pattern in [
        r"==\s*Involved\s*parties\s*==(.*?)(?:\n==|\Z)",
        r"==\s*Parties\s*==(.*?)(?:\n==|\Z)",
    ]:
        section = re.search(pattern, content, re.I | re.DOTALL)
        if section:
            break
    text = section.group(1) if section else content[:2000]

    users = re.findall(r"\[\[User:([^\]|]+)", text, re.I)
    users += re.findall(r"\{\{User5?\|([^}|]+)", text, re.I)
    users += re.findall(r"\{\{Userlinks?\|([^}|]+)", text, re.I)

    seen: set[str] = set()
    result: list[str] = []
    for u in users:
        u_clean = u.strip()
        if u_clean.lower() not in seen and not u_clean.startswith(
            ("Special:", "User talk:")
        ):
            seen.add(u_clean.lower())
            result.append(u_clean)
    return result


def _extract_remedies(content: str) -> list[str]:
    """Extract remedy names from the Remedies section."""
    remedies: list[str] = []
    remedy_section = re.search(
        r"==+\s*(?:Proposed\s+)?Remedies\s*==+"
        r"(.*?)(?:\n==+\s*(?:Proposed\s+)?(?:Enforcement|Clerk)|$)",
        content,
        re.I | re.DOTALL,
    )
    if not remedy_section:
        return remedies
    text = remedy_section.group(1)

    headers = re.findall(r"===+\s*(.+?)\s*===+", text)
    skip_kw = {"enforcement", "log of blocks", "clerk"}
    for h in headers:
        clean = re.sub(r"\[\[.*?\||\]\]|\{\{.*?\}\}", "", h).strip()
        if clean and len(clean) > 2 and clean.lower() not in skip_kw:
            remedies.append(clean)

    if not remedies:
        numbered = re.findall(r"(?:^|\n)\s*\d+(?:\.\d+)?\)\s*(.+?)(?:\n|$)", text)
        for item in numbered:
            clean = re.sub(r"\[\[.*?\||\]\]|\{\{.*?\}\}", "", item).strip()
            if clean and len(clean) > 2:
                remedies.append(clean[:80])
    return remedies


def _classify_outcome(content: str, remedies: list[str]) -> str:
    """Classify case outcome."""
    has_final = bool(re.search(r"=\s*Final\s+decision\s*=", content, re.I))
    if not has_final:
        if re.search(r"\bDecline[d]?\b", content[:3000], re.I):
            return "Declined"
        return "Closed - No Decision"
    if not remedies:
        return "Closed - No Decision"
    remedy_text = " ".join(remedies).lower()
    heavy = [
        "ban",
        "block",
        "probation",
        "parole",
        "desysop",
        "restrict",
        "revert",
        "topic ban",
        "indefinite",
    ]
    if any(kw in remedy_text for kw in heavy):
        return "Remedies Imposed"
    if "admonish" in remedy_text or "warn" in remedy_text:
        return "Admonishment Only"
    return "Remedies Imposed"


def _extract_principles_count(content: str) -> int:
    section = re.search(
        r"==+\s*(?:Proposed\s+)?Principles\s*==+"
        r"(.*?)(?:\n==+\s*(?:Proposed\s+)?(?:Findings|Remedies)|\Z)",
        content,
        re.I | re.DOTALL,
    )
    if not section:
        return 0
    return len(re.findall(r"\n===+[^=\n]+===+", section.group(1)))


def _extract_findings_count(content: str) -> int:
    section = re.search(
        r"==+\s*(?:Proposed\s+)?Findings\s*(?:of\s*[Ff]act)?\s*==+"
        r"(.*?)(?:\n==+\s*(?:Proposed\s+)?Remedies|\Z)",
        content,
        re.I | re.DOTALL,
    )
    if not section:
        return 0
    return len(re.findall(r"\n===+[^=\n]+===+", section.group(1)))


def parse_arb_case(case: dict) -> dict:
    """Extract structured BPMN-relevant fields from a raw ARB case entry."""
    content = case.get("content", "")
    title_raw = case.get("title", "")
    short_title = re.sub(
        r"^(?:Wikipedia:)?(?:Requests?\s+for\s+arbitration"
        r"|Arbitration/Requests/Case)/",
        "",
        title_raw,
        flags=re.I,
    ).strip()

    opened = _extract_date(content, r"Case\s+Opened.*?on\s+(.+?)(?:\n|<)")
    closed = _extract_date(content, r"Case\s+Closed.*?on\s+(.+?)(?:\n|<)")
    parties = _extract_involved_parties(content)
    accept_n, decline_n, recuse_n = _count_accept_votes(content)
    principles_count = _extract_principles_count(content)
    findings_count = _extract_findings_count(content)
    remedies = _extract_remedies(content)
    has_injunction = bool(
        re.search(r"Temporary\s+injunction(?!\s*\(none\))", content, re.I)
        and not re.search(r"Temporary\s+injunction\s*\(none\)", content, re.I)
    )
    outcome = _classify_outcome(content, remedies)
    revisions = case.get("revisions", [])
    editors = set(r.get("user", "") for r in revisions)
    user_mentions = re.findall(r"\[\[User:([^\]|]+)", content, re.I)

    return {
        "title": short_title,
        "url": case.get("url", ""),
        "opened_date": opened,
        "closed_date": closed,
        "parties": parties,
        "party_count": len(parties),
        "accept_votes": accept_n,
        "decline_votes": decline_n,
        "recuse_votes": recuse_n,
        "has_injunction": has_injunction,
        "principles_count": principles_count,
        "findings_count": findings_count,
        "remedies": remedies,
        "remedy_count": len(remedies),
        "outcome": outcome,
        "revision_count": len(revisions),
        "editor_count": len(editors),
        "discussion_turns": len(user_mentions),
    }


def safe_filename(title: str, max_len: int = 45) -> str:
    safe = re.sub(r"[^\w\-]", "_", title)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe[:max_len] if safe else "unnamed"


# ---------------------------------------------------------------------------
# PiperFlow helpers  (processpiper swimlane diagrams - BLUEMOUNTAIN theme)
# ---------------------------------------------------------------------------


def _clean_piper(text: str) -> str:
    """Strip characters that break the PiperFlow parser."""
    return text.replace('"', "").replace("'", "").replace(":", " -").replace("//", " ")


def _piperflow_case(parsed: dict) -> str:
    """
    Build a PiperFlow DSL string for one ARB case.

    Swimlanes:
        Lane: Requesting Party     -- start, submit request
        Pool: ArbCom Process
            Lane: Clerk            -- screen, accept/decline gateway
            Lane: Arbitrators      -- evidence, workshop, proposed decision, final
            Lane: Enforcement      -- monitoring, outcome
    NOTE: Do NOT use // in PiperFlow strings -- the parser treats them as
          Python integer division and raises a SyntaxError.
          Use @label to annotate named end events instead.
    """
    title = _clean_piper(parsed["title"][:48])
    outcome = _clean_piper(parsed["outcome"])
    votes = (
        str(parsed["accept_votes"])
        + "A-"
        + str(parsed["decline_votes"])
        + "D-"
        + str(parsed["recuse_votes"])
        + "R"
    )
    filed = _clean_piper(parsed["opened_date"] or "unknown date")
    party_count = parsed["party_count"]
    remedy_count = parsed["remedy_count"]

    footer_parts = [
        "Parties - " + str(party_count),
        "Votes - " + votes,
        "Remedies - " + str(remedy_count),
    ]
    if parsed["has_injunction"]:
        footer_parts.append("Injunction - Yes")
    footer = " | ".join(footer_parts)

    # Build the flow - with or without injunction step
    if parsed["has_injunction"]:
        injunction_def = "        [Temporary Injunction Issued] as injunction\n"
        flow_chain = (
            "evidence->workshop->injunction->proposed->final->enforce->end_main"
        )
    else:
        injunction_def = ""
        flow_chain = "evidence->workshop->proposed->final->enforce->end_main"

    return (
        "title: ARB - " + title + "\n"
        "colourtheme: BLUEMOUNTAIN\n"
        "\n"
        "lane: Requesting Party\n"
        "    (start) as start\n"
        "    [Submit Arbitration Request - " + filed + "] as submit\n"
        "\n"
        "pool: ArbCom Process\n"
        "    lane: Clerk\n"
        "        [Screen Request] as screen\n"
        "        <Accepted?> as accept_gw\n"
        "        (end Declined) as end_declined\n"
        "\n"
        "    lane: Arbitrators\n"
        "        [Evidence Phase - " + str(party_count) + " parties] as evidence\n"
        "        [Workshop - Draft Decision] as workshop\n"
        + injunction_def
        + "        [Proposed Decision Vote - "
        + votes
        + "] as proposed\n"
        "        [Final Decision Published] as final\n"
        "\n"
        "    lane: Enforcement\n"
        "        [Enforcement and Monitoring] as enforce\n"
        "        (end " + outcome + ") as end_main\n"
        "\n"
        "start->submit->screen->accept_gw\n"
        "accept_gw->evidence: Accepted\n"
        "accept_gw->end_declined: Declined\n" + flow_chain + "\n"
        "end_main@label: " + outcome + "\n"
        "end_declined@label: Declined\n"
        "\n"
        "footer: " + footer + "\n"
    )


def _piperflow_aggregate(all_parsed: list[dict]) -> str:
    """
    Build a PiperFlow DSL string for the aggregate ARB workflow.

    Shows top 2 outcomes individually; groups the rest as Other so
    percentages always sum to 100% (processpiper limit: 1 incoming + 3 outgoing
    per gateway node).
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
    if len(top2_pcts) >= 2:
        top2_pcts[-1] = 100 - other_pct - sum(top2_pcts[:-1])

    other_detail = ", ".join(
        _clean_piper(o) + " " + str(round(100 * n / total)) + "%"
        for o, n in remainder
        if n > 0
    )

    avg_parties = sum(p["party_count"] for p in all_parsed) / max(total, 1)
    avg_remedies = sum(p["remedy_count"] for p in all_parsed) / max(total, 1)
    injunction_n = sum(1 for p in all_parsed if p["has_injunction"])

    end0_lbl = "end " + _clean_piper(top2[0][0]) + " " + str(top2_pcts[0]) + "%"
    end1_lbl = (
        "end " + _clean_piper(top2[1][0]) + " " + str(top2_pcts[1]) + "%"
        if len(top2) > 1
        else "end Other 0%"
    )
    other_lbl = "end Other " + str(other_pct) + "%"

    lines = [
        "title: ArbCom Standard Workflow - Aggregate " + str(total) + " cases",
        "colourtheme: BLUEMOUNTAIN",
        "",
        "lane: Requesting Party",
        "    (start) as start",
        "    [Submit Arbitration Request] as submit",
        "",
        "pool: ArbCom Process",
        "    lane: Clerk",
        "        [Screen and Categorise Request] as screen",
        "        <Accepted by ArbCom?> as accept_gw",
        "        (end Declined - Rejected) as end_declined",
        "",
        "    lane: Arbitrators",
        "        [Evidence Phase - Parties and Witnesses] as evidence",
        "        [Workshop - Draft Principles, Findings, Remedies] as workshop",
        "        [Proposed Decision Voting] as proposed",
        "        [Final Decision Published] as final",
        "",
        "    lane: Enforcement",
        "        [Enforcement and Monitoring] as enforce",
        "        <Case Outcome?> as outcome_gw",
        "        (" + end0_lbl + ") as end0",
        "        (" + end1_lbl + ") as end1",
        "        (" + other_lbl + ") as end_other",
        "",
        "start->submit->screen->accept_gw",
        "accept_gw->evidence: Accepted",
        "accept_gw->end_declined: Declined",
        "evidence->workshop->proposed->final->enforce->outcome_gw",
        "outcome_gw->end0: " + _clean_piper(top2[0][0]),
        "outcome_gw->end1: " + (_clean_piper(top2[1][0]) if len(top2) > 1 else "Other"),
        "outcome_gw->end_other: Other",
        "",
        "footer: Avg parties - "
        + f"{avg_parties:.1f}"
        + " | Avg remedies - "
        + f"{avg_remedies:.1f}"
        + " | Injunctions - "
        + str(injunction_n)
        + " | Other includes - "
        + (other_detail or "none"),
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Diagram creation functions
# ---------------------------------------------------------------------------


def _safe_label(text: str, max_len: int = 45) -> str:
    return text[:max_len] + "\u2026" if len(text) > max_len else text


def create_arb_case_bpmn(
    parsed: dict, case_idx: int, output_dir: Path
) -> tuple[Path, Path | None]:
    """Generate PNG + BPMN XML for one ARB case. Returns (bpmn_path, png_path)."""
    slug = safe_filename(parsed["title"])
    stem = f"arb_{case_idx:04d}_{slug}"
    bpmn_path = output_dir / f"{stem}.bpmn"
    png_path = output_dir / f"{stem}.png"

    # PNG via processpiper
    png_out = None
    try:
        render_piperflow(_piperflow_case(parsed), output_file=str(png_path))
        png_out = png_path
    except Exception as e:
        print(f"    WARNING: PNG failed for case {case_idx}: {e}")

    # BPMN XML
    outcome = parsed["outcome"]
    filed = parsed["opened_date"] or "unknown date"
    votes = (  # noqa: F841
        str(parsed["accept_votes"])
        + "A/"
        + str(parsed["decline_votes"])
        + "D/"
        + str(parsed["recuse_votes"])
        + "R"
    )

    b = SwimlaneBpmnBuilder("ARB Case: " + parsed["title"][:60], ARB_LANES)
    start = b.start("Request Filed", "Requesting Party")
    submit = b.task("Submission - " + filed, "Requesting Party", user=True)
    review = b.task("Preliminary Review (ArbCom Votes)", "Clerk", user=True)
    gw_accept = b.gateway("Accepted?", "Clerk")
    declined_end = b.end("Declined", "Clerk")

    evidence = b.task("Evidence Phase", "Arbitrators", user=True)
    workshop = b.task("Workshop (Draft Decision)", "Arbitrators", user=True)
    proposed = b.task("Proposed Decision Voting", "Arbitrators", user=True)

    if parsed["has_injunction"]:
        injunction = b.task("Temporary Injunction", "Arbitrators")

    final = b.task("Final Decision Published", "Arbitrators")
    enforce = b.task("Enforcement", "Enforcement", user=True)
    gw_out = b.gateway("Outcome?", "Enforcement")

    b.flow(start, submit)
    b.flow(submit, review)
    b.flow(review, gw_accept)
    b.flow(gw_accept, declined_end, "No - Declined")
    b.flow(gw_accept, evidence, "Yes - Accepted")
    b.flow(evidence, workshop)
    b.flow(workshop, proposed)

    if parsed["has_injunction"]:
        b.flow(proposed, injunction)
        b.flow(injunction, final)
    else:
        b.flow(proposed, final)

    b.flow(final, enforce)
    b.flow(enforce, gw_out)

    end_main = b.end(outcome, "Enforcement")
    b.flow(gw_out, end_main, outcome)

    for remedy in parsed["remedies"][:4]:
        r_end = b.end(_safe_label(remedy, 35), "Enforcement")
        b.flow(gw_out, r_end, _safe_label(remedy, 25))

    bpmn_path.write_text(b.to_xml(), encoding="utf-8")
    return bpmn_path, png_out


def create_aggregate_arb_bpmn(
    all_parsed: list[dict], output_dir: Path
) -> tuple[Path, Path | None]:
    """Generate aggregate PNG + BPMN XML. Returns (bpmn_path, png_path)."""
    bpmn_path = output_dir / "arb_aggregate_workflow.bpmn"
    png_path = output_dir / "arb_aggregate_workflow.png"

    # PNG via processpiper
    png_out = None
    try:
        render_piperflow(_piperflow_aggregate(all_parsed), output_file=str(png_path))
        png_out = png_path
    except Exception as e:
        print(f"  WARNING: Aggregate PNG failed: {e}")

    # BPMN XML - same top2 + Other grouping
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
    if len(top2_pcts) >= 2:
        top2_pcts[-1] = 100 - other_pct - sum(top2_pcts[:-1])

    other_detail = ", ".join(
        o + " " + str(round(100 * n / total)) + "%" for o, n in remainder if n > 0
    )

    b = SwimlaneBpmnBuilder("ArbCom Standard Workflow (Aggregate)", ARB_LANES)
    start = b.start("Request Filed", "Requesting Party")
    submit = b.task("Submit Arbitration Request", "Requesting Party", user=True)
    screen = b.task("Screen and Categorise", "Clerk")
    gw_valid = b.gateway("Accepted by ArbCom?", "Clerk")
    declined = b.end("Declined / Rejected", "Clerk")
    evidence = b.task("Evidence Phase", "Arbitrators", user=True)
    workshop = b.task("Workshop (Draft Decision)", "Arbitrators", user=True)
    proposed = b.task("Proposed Decision Voting", "Arbitrators", user=True)
    final = b.task("Final Decision Published", "Arbitrators")
    enforce = b.task("Enforcement & Monitoring", "Enforcement", user=True)
    gw_out = b.gateway("Case Outcome?", "Enforcement")

    b.flow(start, submit)
    b.flow(submit, screen)
    b.flow(screen, gw_valid)
    b.flow(gw_valid, declined, "No - Declined")
    b.flow(gw_valid, evidence, "Yes - Accepted")
    b.flow(evidence, workshop)
    b.flow(workshop, proposed)
    b.flow(proposed, final)
    b.flow(final, enforce)
    b.flow(enforce, gw_out)

    for i, (o, _) in enumerate(top2):
        end = b.end(o + " (" + str(top2_pcts[i]) + "%)", "Enforcement")
        b.flow(gw_out, end, o)
    end_other = b.end(
        "Other (" + str(other_pct) + "%): " + (other_detail or "none"), "Enforcement"
    )
    b.flow(gw_out, end_other, "Other")

    bpmn_path.write_text(b.to_xml(), encoding="utf-8")

    # Print summary
    avg_parties = sum(p["party_count"] for p in all_parsed) / max(total, 1)
    avg_remedies = sum(p["remedy_count"] for p in all_parsed) / max(total, 1)
    injunction_n = sum(1 for p in all_parsed if p["has_injunction"])
    remedy_counter: Counter[str] = Counter()
    for p in all_parsed:
        remedy_counter.update(p["remedies"])

    print(f"\n{'=' * 60}")
    print(f"AGGREGATE SUMMARY - {total} ARB cases")
    print(f"{'=' * 60}")
    print(f"  Avg parties per case:  {avg_parties:.1f}")
    print(f"  Avg remedies per case: {avg_remedies:.1f}")
    print(f"  Cases with injunction: {injunction_n}")
    print("\n  Outcome distribution:")
    for o, n in sorted(outcome_counts.items(), key=lambda x: -x[1]):
        bar = "X" * (n // max(1, total // 40))
        print(f"    {o:<30} {n:>4}  ({round(100 * n / total)}%)  {bar}")
    print("\n  Top remedy types:")
    for r, n in remedy_counter.most_common(10):
        print(f"    {_safe_label(r, 40):<42} {n:>4}")
    print()

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
                    f"  Out of range: {sorted(invalid)}. "
                    f"Enter numbers between 1 and {total}."
                )
                continue

            indices = sorted(selected)
            print(
                f"  Selected {len(indices)} case(s): "
                f"{indices[:5]}{'...' if len(indices) > 5 else ''}"
            )
            return indices

        except ValueError:
            print("  Invalid input. Use: all | 10 | 100,200,305 | 1-50")


def select_input_file(data_dir: Path) -> Path | list[Path] | None:
    """
    Let user pick which JSON file(s) to process.

    Returns a single Path, a list of Paths (user chose 'all'), or None.
    """
    json_files = sorted(data_dir.glob("*.json"))
    for sub in ("arb", "arbitration", "raw", "raw/arb", "raw/arbitration"):
        sub_dir = data_dir / sub
        if sub_dir.is_dir():
            json_files.extend(sorted(sub_dir.glob("*.json")))
    seen: set[str] = set()
    unique: list[Path] = []
    for f in json_files:
        rp = str(f.resolve())
        if rp not in seen:
            seen.add(rp)
            unique.append(f)
    json_files = unique

    if not json_files:
        return None
    if len(json_files) == 1:
        return json_files[0]

    print("\nAvailable ARB data files:")
    print("=" * 60)
    total_kb = 0
    for i, f in enumerate(json_files, 1):
        size_kb = f.stat().st_size / 1024
        total_kb += size_kb
        print(f"  [{i}] {f.name}  ({size_kb:.0f} KB)")
    print(f"  [A] *** ALL FILES COMBINED ***  ({total_kb:.0f} KB total)")

    choice = input("\nSelect file number, or A for all [default: A]: ").strip().lower()
    if choice in ("a", "all", ""):
        print(f"\n  -> Merging all {len(json_files)} files...")
        return json_files
    try:
        idx = int(choice) - 1
        return json_files[max(0, min(idx, len(json_files) - 1))]
    except ValueError:
        print(f"  -> Merging all {len(json_files)} files...")
        return json_files


def main():
    parser = argparse.ArgumentParser(
        description="Generate BPMN + PNG models from Wikipedia "
        "Arbitration (ARB) case data."
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        default=None,
        help="Path to ARB JSON file or directory. "
        "If omitted, searches ./data/raw/arb/ and "
        "./data/raw/arbitration/",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output directory. Default: ./artifacts/bpmn/arb/",
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

    project_root = Path(__file__).resolve().parent.parent
    cwd = Path.cwd()
    if args.input:
        input_source = Path(args.input)
        if input_source.is_dir():
            json_files = sorted(input_source.glob("*.json"))
            if not json_files:
                print(f"No JSON files found in {input_source}")
                return
            input_source = json_files
    else:
        # Search multiple candidate directories
        data_dir = None
        candidates = []
        for root in dict.fromkeys([project_root, cwd]):
            for dirname in ("arb", "arbitration"):
                candidates.append(root / "data" / "raw" / dirname)
            candidates.append(root / "data" / "raw")
            candidates.append(root / "data")
            candidates.append(root)
        for candidate in candidates:
            if candidate.is_dir() and list(candidate.glob("*.json")):
                data_dir = candidate
                break
        if data_dir is None:
            data_dir = cwd
        input_source = select_input_file(data_dir)
        if not input_source:
            searched = "\n  ".join(str(c) for c in candidates[:6])
            print(f"No JSON files found. Searched:\n  {searched}")
            print("\nUse --input to specify a file or directory.")
            return

    if args.output:
        output_dir = Path(args.output)
    else:
        # Prefer project_root if it has an artifacts dir, else use CWD
        if (project_root / "artifacts").exists():
            output_dir = project_root / "artifacts" / "bpmn" / "arb"
        else:
            output_dir = cwd / "artifacts" / "bpmn" / "arb"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print("ARB -> BPMN + PNG Generator")
    print(f"{'=' * 60}")
    if isinstance(input_source, list):
        print(f"Input : {len(input_source)} JSON file(s)")
    else:
        print(f"Input : {input_source}")
    print(f"Output: {output_dir}")
    print(f"{'=' * 60}")

    raw_cases = load_arb_data(input_source)
    print(f"\nLoaded {len(raw_cases)} raw ARB cases.")

    all_parsed = [parse_arb_case(c) for c in raw_cases]

    # Show outcome distribution
    print("\nOutcome distribution:")
    outcome_counts: dict[str, int] = {}
    for p in all_parsed:
        outcome_counts[p["outcome"]] = outcome_counts.get(p["outcome"], 0) + 1
    for outcome, count in sorted(outcome_counts.items(), key=lambda x: -x[1]):
        bar = "X" * (count // max(1, len(all_parsed) // 40))
        print(f"  {outcome:<30} {count:>4}  {bar}")

    # Aggregate diagram
    agg_bpmn = agg_png = None
    if not args.no_aggregate:
        print("\nGenerating aggregate workflow...")
        agg_bpmn, agg_png = create_aggregate_arb_bpmn(all_parsed, output_dir)
        print(f"  + {agg_bpmn.name}")
        if agg_png:
            print(f"  + {agg_png.name}")

    # List available cases for selection
    print(f"\nParsed {len(all_parsed)} cases:")
    for i, p in enumerate(all_parsed, 1):
        votes = (
            str(p["accept_votes"])
            + "A/"
            + str(p["decline_votes"])
            + "D/"
            + str(p["recuse_votes"])
            + "R"
        )
        print(
            f"  [{i:>4}] {p['title'][:55]:<57}  "
            f"votes={votes}  remedies={p['remedy_count']}"
        )

    # Individual case diagrams
    if args.max_cases is not None:
        selected_indices = list(range(1, min(args.max_cases, len(all_parsed)) + 1))
    else:
        selected_indices = get_user_case_selection(len(all_parsed))

    print(f"\nGenerating {len(selected_indices)} individual diagram(s)...\n")
    bpmn_files: list[Path] = []
    png_files: list[Path] = []

    for i, idx in enumerate(selected_indices, start=1):
        parsed = all_parsed[idx - 1]
        bpmn_p, png_p = create_arb_case_bpmn(parsed, i, output_dir)
        bpmn_files.append(bpmn_p)
        if png_p:
            png_files.append(png_p)
        label = "PNG + BPMN" if png_p else "BPMN only"
        votes = (
            str(parsed["accept_votes"])
            + "A/"
            + str(parsed["decline_votes"])
            + "D/"
            + str(parsed["recuse_votes"])
            + "R"
        )
        print(
            f"  [{i:>4}/{len(selected_indices)}] "
            f"{bpmn_p.stem[:50]:<52}  "
            f"votes={votes}  "
            f"remedies={parsed['remedy_count']}  {label}"
        )

    total_bpmn = len(bpmn_files) + (1 if agg_bpmn else 0)
    total_png = len(png_files) + (1 if agg_png else 0)

    print(f"\n{'=' * 60}")
    print("Done!")
    print(f"  Individual diagrams : {len(selected_indices)} of {len(all_parsed)} cases")
    print(f"  Aggregate           : full dataset ({len(all_parsed)} cases)")
    print(f"  BPMN files : {total_bpmn}")
    print(f"  PNG files  : {total_png}")
    print(f"  Output dir : {output_dir}")
    print("\nTo view:")
    print("  PNG  -- open any .png directly")
    print("  BPMN -- drag & drop at https://demo.bpmn.io")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
