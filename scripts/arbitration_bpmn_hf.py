#!/usr/bin/env python3
"""
arbitration_bpmn_hf.py — Wikipedia ArbCom BPMN Generator (HuggingFace NER)

Uses jtlicardo/bpmn-information-extraction (BERT-based token classifier) to
extract AGENT, TASK, and CONDITION entities from arbitration case text, then
builds BPMN 2.0 XML with swimlanes + PNG diagrams.

Swimlanes
---------
  Involved Parties     — disputing users / requestors
  ArbCom Clerk         — administrative tasks (open, close, notify)
  Arbitration Committee — review, deliberation, findings, decision
  Administrator         — enforcement of remedies / sanctions

Modes
-----
  Specific case   — BPMN for one named case (interactive prompt or --case flag)
  Aggregate model — generalised flow from all cases (--aggregate flag)

Usage
-----
  python scripts/arbitration_bpmn_hf.py
  python scripts/arbitration_bpmn_hf.py --case "Wikipedia:Requests_for_arbitration/-Ril-"
  python scripts/arbitration_bpmn_hf.py --aggregate
  python scripts/arbitration_bpmn_hf.py --aggregate --sample 50
  python scripts/arbitration_bpmn_hf.py --output-dir artifacts/bpmn/arb

Requirements
------------
  pip install transformers torch processpiper
  (torch not strictly required; transformers will use CPU by default)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET

# ─────────────────────────────────────────────────────────────────────────────
# Optional deps — graceful fallbacks so the script still works without them
# ─────────────────────────────────────────────────────────────────────────────

try:
    from transformers import pipeline as hf_pipeline

    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False
    print(
        "WARNING: 'transformers' not installed.\n"
        "         Run: pip install transformers torch\n"
        "         NER extraction is disabled; rule-based flow only.\n"
    )

try:
    from processpiper.text2diagram import render as render_piperflow

    PIPERFLOW_AVAILABLE = True
except ImportError:
    PIPERFLOW_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

HF_NER_MODEL = "jtlicardo/bpmn-information-extraction"

# Swimlane order (top → bottom in the diagram)
LANES = [
    "Involved Parties",
    "ArbCom Clerk",
    "Arbitration Committee",
    "Administrator",
]

# Which lane "owns" each section heading (partial-match keys)
SECTION_LANE: dict[str, str] = {
    "Case Opened": "ArbCom Clerk",
    "Case Closed": "ArbCom Clerk",
    "Involved Parties": "Involved Parties",
    "Statement by": "Involved Parties",
    "Confirmation that all parties": "Involved Parties",
    "Confirmation that other steps": "Involved Parties",
    "Requests for comment": "Arbitration Committee",
    "Preliminary decisions": "Arbitration Committee",
    "Findings of Fact": "Arbitration Committee",
    "Final decision": "Arbitration Committee",
    "Remedies": "Arbitration Committee",
    "Enforcement": "Administrator",
}

# Keywords that indicate active remedies / enforcement
ENFORCEMENT_KEYWORDS = re.compile(
    r"\b(ban(ned)?|block(ed)?|topic.ban|desysop(ped)?|sanction(ed)?|"
    r"restrict(ed)?|prohibit(ed)?|suspend(ed)?|remov(ed)?|revok(ed)?)\b",
    re.IGNORECASE,
)

# BPMN 2.0 XML namespaces
NS_BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
NS_BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
NS_DC = "http://www.omg.org/spec/DD/20100524/DC"
NS_DI = "http://www.omg.org/spec/DD/20100524/DI"

# Swimlane / diagram layout
POOL_X = 100
POOL_Y = 80
POOL_HEADER_W = 30  # width of the pool label strip on the left
LANE_H = 160  # vertical height of each lane
TASK_W = 130
TASK_H = 60
GW_W = 50
GW_H = 50
EVT_W = 36
EVT_H = 36
STEP_GAP = 160  # horizontal gap between element centres
FIRST_X = POOL_X + POOL_HEADER_W + 80  # x-coord of first element

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────


def _uid(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def safe_filename(title: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\-]", "_", title)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:max_len] if s else "unnamed"


def section_matches(key: str, sections: dict) -> str:
    """Return text of first section whose heading contains *key* (case-insensitive)."""
    key_lo = key.lower()
    for heading, text in sections.items():
        if key_lo in heading.lower():
            return text or ""
    return ""


def has_section(key: str, sections: dict) -> bool:
    return bool(section_matches(key, sections).strip())


def needs_enforcement(sections: dict) -> bool:
    """True if Remedies / Final decision text implies active sanctions."""
    text = (
        section_matches("Remedies", sections)
        + " "
        + section_matches("Final decision", sections)
    )
    return bool(ENFORCEMENT_KEYWORDS.search(text))


def chunk_text(text: str, max_chars: int = 1400) -> list[str]:
    """Split long text into chunks at paragraph boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 <= max_chars:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            if len(para) > max_chars:
                # Fall back to sentence splitting
                for sent in re.split(r"(?<=[.!?])\s+", para):
                    if len(current) + len(sent) + 1 <= max_chars:
                        current = (current + " " + sent).strip()
                    else:
                        if current:
                            chunks.append(current)
                        current = sent
            else:
                current = para
    if current:
        chunks.append(current)
    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# HuggingFace NER Extractor
# ─────────────────────────────────────────────────────────────────────────────


class NERExtractor:
    """
    Wraps jtlicardo/bpmn-information-extraction (BERT token classifier).

    Output labels
    -------------
    AGENT        — person / role performing an action
    TASK         — specific activity or process step
    TASK_INFO    — qualifying detail about a task
    PROCESS_INFO — process-level context
    CONDITION    — conditional branch trigger
    """

    _LABELS = ("AGENT", "TASK", "TASK_INFO", "PROCESS_INFO", "CONDITION")

    def __init__(self, model_name: str = HF_NER_MODEL):
        self._pipe = None
        if not HF_AVAILABLE:
            return
        print(f"  Loading HuggingFace model: {model_name}")
        print("  (First run downloads ~400 MB — subsequent runs use local cache)")
        try:
            self._pipe = hf_pipeline(
                "token-classification",
                model=model_name,
                aggregation_strategy="simple",
            )
            print("  Model ready.\n")
        except Exception as exc:
            print(f"  WARNING: Could not load model ({exc}). Rule-based flow only.\n")

    def extract(self, text: str) -> dict[str, list[str]]:
        """Return {label: [entity, ...]} for the given text."""
        results: dict[str, list[str]] = {lbl: [] for lbl in self._LABELS}
        if not self._pipe or not text.strip():
            return results

        for chunk in chunk_text(text):
            try:
                raw = self._pipe(chunk, truncation=True, max_length=512)
            except Exception:
                continue
            for ent in raw:
                label = re.sub(
                    r"^[BI]-",
                    "",
                    ent.get("entity_group", ent.get("entity", "")).upper(),
                )
                word = ent.get("word", "").strip()
                if label in results and word and len(word) > 2:
                    results[label].append(word)

        # Deduplicate preserving order
        for key in results:
            seen: set[str] = set()
            deduped = []
            for v in results[key]:
                if v.lower() not in seen:
                    seen.add(v.lower())
                    deduped.append(v)
            results[key] = deduped
        return results

    def extract_sections(
        self, sections: dict[str, str], keys: list[str]
    ) -> dict[str, list[str]]:
        """Extract from multiple sections and merge."""
        merged: dict[str, list[str]] = {lbl: [] for lbl in self._LABELS}
        for key in keys:
            text = section_matches(key, sections)
            if text:
                for lbl, vals in self.extract(text).items():
                    merged[lbl].extend(vals)
        # Final dedup
        for key in merged:
            seen: set[str] = set()
            deduped = []
            for v in merged[key]:
                if v.lower() not in seen:
                    seen.add(v.lower())
                    deduped.append(v)
            merged[key] = deduped
        return merged


# ─────────────────────────────────────────────────────────────────────────────
# Swimlane BPMN 2.0 XML Builder
# ─────────────────────────────────────────────────────────────────────────────


class SwimlaneBpmnBuilder:
    """
    Constructs a BPMN 2.0 XML document with a Collaboration (pool) whose
    process contains horizontally-oriented swimlanes (lanes).

    Elements are positioned automatically: each call to add_* increments a
    global step counter that controls the x-coordinate; the lane assignment
    determines the y-coordinate.
    """

    def __init__(self, process_name: str, lanes: list[str] = LANES):
        self.process_name = process_name
        self.lanes = lanes
        self._lane_ids = {name: _uid("Lane") for name in lanes}
        self._collab_id = _uid("Collab")
        self._part_id = _uid("Participant")
        self._proc_id = _uid("Process")

        # (eid, label, elem_type, lane_name, step)
        self._elements: list[tuple[str, str, str, str, int]] = []
        # (fid, source_id, target_id, label)
        self._flows: list[tuple[str, str, str, str]] = []
        self._step = 0

    # ── element adders ───────────────────────────────────────────────────────

    def _add(self, label: str, etype: str, lane: str) -> str:
        eid = _uid(etype.replace("Event", "Evt").replace("Gateway", "GW")[:6])
        self._elements.append((eid, label, etype, lane, self._step))
        self._step += 1
        return eid

    def start(self, label: str, lane: str = "Involved Parties") -> str:
        return self._add(label, "startEvent", lane)

    def end(self, label: str, lane: str = "Administrator") -> str:
        return self._add(label, "endEvent", lane)

    def task(self, label: str, lane: str, user: bool = False) -> str:
        etype = "userTask" if user else "task"
        return self._add(label, etype, lane)

    def gateway(self, label: str, lane: str, exclusive: bool = True) -> str:
        etype = "exclusiveGateway" if exclusive else "parallelGateway"
        return self._add(label, etype, lane)

    def flow(self, src: str, tgt: str, label: str = "") -> str:
        fid = _uid("Flow")
        self._flows.append((fid, src, tgt, label))
        return fid

    # ── layout helpers ───────────────────────────────────────────────────────

    def _bounds(self, etype: str, lane: str, step: int) -> tuple[int, int, int, int]:
        """Return (x, y, width, height) for an element."""
        lane_idx = self.lanes.index(lane)
        lane_top = POOL_Y + lane_idx * LANE_H
        cx = FIRST_X + step * STEP_GAP

        if etype in ("startEvent", "endEvent"):
            w, h = EVT_W, EVT_H
        elif "Gateway" in etype:
            w, h = GW_W, GW_H
        else:
            w, h = TASK_W, TASK_H

        y = lane_top + (LANE_H - h) // 2
        return cx, y, w, h

    # ── XML serialisation ────────────────────────────────────────────────────

    def to_xml(self) -> str:
        for prefix, uri in (
            ("bpmn", NS_BPMN),
            ("bpmndi", NS_BPMNDI),
            ("dc", NS_DC),
            ("di", NS_DI),
        ):
            ET.register_namespace(prefix, uri)

        root = ET.Element(
            f"{{{NS_BPMN}}}definitions",
            {
                "id": _uid("Defs"),
                "targetNamespace": "http://bpmn.io/schema/bpmn",
                "exporter": "ArbCom-BPMN-HF",
                "exporterVersion": "2.0",
            },
        )

        # ── Collaboration ────────────────────────────────────────────────────
        collab = ET.SubElement(
            root, f"{{{NS_BPMN}}}collaboration", {"id": self._collab_id}
        )
        ET.SubElement(
            collab,
            f"{{{NS_BPMN}}}participant",
            {
                "id": self._part_id,
                "name": self.process_name,
                "processRef": self._proc_id,
            },
        )

        # ── Process ──────────────────────────────────────────────────────────
        process = ET.SubElement(
            root,
            f"{{{NS_BPMN}}}process",
            {"id": self._proc_id, "isExecutable": "false"},
        )

        # LaneSet with flowNodeRefs
        lane_set = ET.SubElement(process, f"{{{NS_BPMN}}}laneSet", {"id": _uid("LS")})
        for lane_name in self.lanes:
            lane_el = ET.SubElement(
                lane_set,
                f"{{{NS_BPMN}}}lane",
                {"id": self._lane_ids[lane_name], "name": lane_name},
            )
            for eid, _lbl, _et, elane, _step in self._elements:
                if elane == lane_name:
                    ET.SubElement(lane_el, f"{{{NS_BPMN}}}flowNodeRef").text = eid

        # Build incoming/outgoing lookup
        incoming: dict[str, list[str]] = defaultdict(list)
        outgoing: dict[str, list[str]] = defaultdict(list)
        for fid, src, tgt, _lbl in self._flows:
            outgoing[src].append(fid)
            incoming[tgt].append(fid)

        # Flow nodes
        for eid, label, etype, _lane, _step in self._elements:
            el = ET.SubElement(
                process, f"{{{NS_BPMN}}}{etype}", {"id": eid, "name": label}
            )
            for fid in incoming.get(eid, []):
                ET.SubElement(el, f"{{{NS_BPMN}}}incoming").text = fid
            for fid in outgoing.get(eid, []):
                ET.SubElement(el, f"{{{NS_BPMN}}}outgoing").text = fid

        # Sequence flows
        for fid, src, tgt, label in self._flows:
            attrs: dict[str, str] = {"id": fid, "sourceRef": src, "targetRef": tgt}
            if label:
                attrs["name"] = label
            ET.SubElement(process, f"{{{NS_BPMN}}}sequenceFlow", attrs)

        # ── Diagram ──────────────────────────────────────────────────────────
        max_step = max((e[4] for e in self._elements), default=0)
        pool_w = FIRST_X - POOL_X + (max_step + 1) * STEP_GAP + 80
        pool_h = LANE_H * len(self.lanes)

        diagram = ET.SubElement(
            root, f"{{{NS_BPMNDI}}}BPMNDiagram", {"id": _uid("Diag")}
        )
        plane = ET.SubElement(
            diagram,
            f"{{{NS_BPMNDI}}}BPMNPlane",
            {"id": _uid("Plane"), "bpmnElement": self._collab_id},
        )

        # Pool shape
        ps = ET.SubElement(
            plane,
            f"{{{NS_BPMNDI}}}BPMNShape",
            {
                "id": f"{self._part_id}_di",
                "bpmnElement": self._part_id,
                "isHorizontal": "true",
            },
        )
        ET.SubElement(
            ps,
            f"{{{NS_DC}}}Bounds",
            {
                "x": str(POOL_X),
                "y": str(POOL_Y),
                "width": str(pool_w),
                "height": str(pool_h),
            },
        )

        # Lane shapes
        for i, lane_name in enumerate(self.lanes):
            lid = self._lane_ids[lane_name]
            ls = ET.SubElement(
                plane,
                f"{{{NS_BPMNDI}}}BPMNShape",
                {"id": f"{lid}_di", "bpmnElement": lid, "isHorizontal": "true"},
            )
            ET.SubElement(
                ls,
                f"{{{NS_DC}}}Bounds",
                {
                    "x": str(POOL_X + POOL_HEADER_W),
                    "y": str(POOL_Y + i * LANE_H),
                    "width": str(pool_w - POOL_HEADER_W),
                    "height": str(LANE_H),
                },
            )

        # Element shapes
        bounds_cache: dict[str, tuple[int, int, int, int]] = {}
        for eid, label, etype, lane, step in self._elements:
            x, y, w, h = self._bounds(etype, lane, step)
            bounds_cache[eid] = (x, y, w, h)
            shape = ET.SubElement(
                plane,
                f"{{{NS_BPMNDI}}}BPMNShape",
                {"id": f"{eid}_di", "bpmnElement": eid},
            )
            ET.SubElement(
                shape,
                f"{{{NS_DC}}}Bounds",
                {
                    "x": str(x),
                    "y": str(y),
                    "width": str(w),
                    "height": str(h),
                },
            )
            # Explicit label bounds for events / gateways
            if etype in ("startEvent", "endEvent") or "Gateway" in etype:
                lbl_el = ET.SubElement(shape, f"{{{NS_BPMNDI}}}BPMNLabel")
                ET.SubElement(
                    lbl_el,
                    f"{{{NS_DC}}}Bounds",
                    {
                        "x": str(x - 10),
                        "y": str(y + h + 4),
                        "width": str(w + 20),
                        "height": str(40),
                    },
                )

        # Sequence flow edges
        for fid, src, tgt, label in self._flows:
            edge = ET.SubElement(
                plane,
                f"{{{NS_BPMNDI}}}BPMNEdge",
                {"id": f"{fid}_di", "bpmnElement": fid},
            )
            if label:
                le = ET.SubElement(edge, f"{{{NS_BPMNDI}}}BPMNLabel")
                sx, sy, sw, sh = bounds_cache.get(src, (0, 0, 0, 0))
                tx, ty, tw, th = bounds_cache.get(tgt, (0, 0, 0, 0))
                ET.SubElement(
                    le,
                    f"{{{NS_DC}}}Bounds",
                    {
                        "x": str((sx + sw / 2 + tx + tw / 2) / 2 - 20),
                        "y": str((sy + sh / 2 + ty + th / 2) / 2 - 10),
                        "width": "60",
                        "height": "20",
                    },
                )

            sx, sy, sw, sh = bounds_cache.get(src, (0, 0, 0, 0))
            tx, ty, tw, th = bounds_cache.get(tgt, (0, 0, 0, 0))
            # waypoints: right-centre of source → left-centre of target
            ET.SubElement(
                edge,
                f"{{{NS_DI}}}waypoint",
                {
                    "x": str(sx + sw),
                    "y": str(sy + sh / 2),
                },
            )
            ET.SubElement(
                edge,
                f"{{{NS_DI}}}waypoint",
                {
                    "x": str(tx),
                    "y": str(ty + th / 2),
                },
            )

        xml_str = ET.tostring(root, encoding="unicode")
        return minidom.parseString(xml_str).toprettyxml(indent="  ")


# ─────────────────────────────────────────────────────────────────────────────
# PNG generation via PiperFlow (processpiper)
# ─────────────────────────────────────────────────────────────────────────────


def _piperflow_case(
    title: str,
    sections: dict[str, str],
    ner: dict[str, list[str]],
) -> str:
    """Build piperflow DSL string for a specific case."""

    has_prelim = has_section("Preliminary decisions", sections)
    has_fof = has_section("Findings of Fact", sections)
    has_rfc = has_section("Requests for comment", sections)
    has_enforce = needs_enforcement(sections) or has_section("Enforcement", sections)

    # Remedy label from NER tasks (first matching task, or default)
    remedy_tasks = ner.get("TASK", [])
    remedy_label = next(
        (t for t in remedy_tasks if ENFORCEMENT_KEYWORDS.search(t)),
        "Enforce Remedies",
    )[:40]

    # ── Lane: Involved Parties ───────────────────────────────────────────────
    parties_elems = [
        "        (start) as start",
        "        [File Arbitration Request] as file_req",
        "        [Submit Statements & Evidence] as submit",
    ]
    if has_rfc:
        parties_elems.append("        [Respond to RFC] as rfc_respond")

    # ── Lane: ArbCom Clerk — open + close in one lane (no duplicates) ────────
    clerk_elems = [
        "        [Open Case & Notify Parties] as open_case",
        "        (end) as end_closed",
    ]

    # ── Lane: Arbitration Committee ──────────────────────────────────────────
    arbcom_elems = ["        [Review Submissions] as review"]
    if has_rfc:
        arbcom_elems.append("        [Issue Request for Comment] as rfc_issue")
    if has_prelim:
        arbcom_elems.append("        [Issue Preliminary Decisions] as prelim")
    arbcom_elems.append("        [Deliberate & Workshop] as deliberate")
    if has_fof:
        arbcom_elems.append("        [Compile Findings of Fact] as fof")
    arbcom_elems += [
        "        [Vote on Final Decision] as vote",
        "        [Publish Final Decision] as final_dec",
        "        <Remedies Required?> as remedy_gw",
    ]

    # ── Lane: Administrator ──────────────────────────────────────────────────
    admin_elems = []
    if has_enforce:
        admin_elems += [
            f"        [{remedy_label}] as enforce",
            "        (end) as end_enforced",
        ]

    # ── Assemble pool ────────────────────────────────────────────────────────
    lines = (
        [
            f"title: {title[:60]}",
            "colourtheme: BLUEMOUNTAIN",
            "",
            "pool: Wikipedia Arbitration Process",
            "    lane: Involved Parties",
        ]
        + parties_elems
        + [
            "    lane: ArbCom Clerk",
        ]
        + clerk_elems
        + [
            "    lane: Arbitration Committee",
        ]
        + arbcom_elems
    )

    if admin_elems:
        lines += ["    lane: Administrator"] + admin_elems

    lines.append("")  # blank line ends the pool block

    # ── Flow connections ─────────────────────────────────────────────────────
    lines.append("start->file_req->open_case->submit->review")

    if has_rfc:
        lines.append("review->rfc_issue->rfc_respond->deliberate")
    elif has_prelim:
        lines.append("review->prelim->deliberate")
    else:
        lines.append("review->deliberate")

    if has_fof:
        lines.append("deliberate->fof->vote->final_dec->remedy_gw")
    else:
        lines.append("deliberate->vote->final_dec->remedy_gw")

    if has_enforce:
        lines += ["remedy_gw->enforce: Yes", "enforce->end_enforced"]
    lines.append("remedy_gw->end_closed: No")

    lines.append(f"\nfooter: ArbCom case: {title[:50]}")

    return "\n".join(lines)


def _piperflow_aggregate(
    section_counts: dict[str, int],
    total: int,
    enforcement_pct: int,
    sample: int,
) -> str:
    """Build piperflow DSL for the generalised aggregate model."""

    def pct(section: str) -> int:
        return round(section_counts.get(section, 0) * 100 / max(total, 1))

    has_rfc_common = pct("Requests for comment") > 20
    has_prelim_common = pct("Preliminary decisions") > 30

    lines = [
        "title: Wikipedia ArbCom — Generalised Arbitration Process",
        "colourtheme: BLUEMOUNTAIN",
        "",
        "pool: Wikipedia Arbitration Process",
        "    lane: Involved Parties",
        "        (start) as start",
        "        [File Arbitration Request] as file_req",
        "        [Submit Statements & Evidence] as submit",
        "    lane: ArbCom Clerk",
        "        [Open Case & Notify Parties] as open_case",
        "        [Close Case] as close_case",
        "        (end) as end_admin",
        "    lane: Arbitration Committee",
        "        [Review Submissions] as review",
    ]

    if has_prelim_common:
        lines += [
            f"        [Issue Preliminary Decisions ({pct('Preliminary decisions')}%)] as prelim"
        ]

    if has_rfc_common:
        lines += [
            f"        [Issue Request for Comment ({pct('Requests for comment')}%)] as rfc_issue"
        ]

    lines += [
        "        [Deliberate & Workshop] as deliberate",
        f"        [Compile Findings of Fact ({pct('Findings of Fact')}%)] as fof",
        "        [Vote on Final Decision] as vote",
        "        [Publish Final Decision] as final_dec",
        "        <Remedies Imposed?> as remedy_gw",
        "    lane: Administrator",
        f"        [Enforce Remedies / Sanctions ({enforcement_pct}%)] as enforce",
        "        (end) as end_enforced",
        "",
    ]

    lines += ["start->file_req->open_case->submit->review"]

    if has_prelim_common and has_rfc_common:
        lines += ["review->prelim->rfc_issue->deliberate"]
    elif has_prelim_common:
        lines += ["review->prelim->deliberate"]
    elif has_rfc_common:
        lines += ["review->rfc_issue->deliberate"]
    else:
        lines += ["review->deliberate"]

    lines += [
        "deliberate->fof->vote->final_dec->remedy_gw",
        f"remedy_gw->enforce: Yes ({enforcement_pct}%)",
        "enforce->end_enforced",
        f"remedy_gw->close_case: No ({100 - enforcement_pct}%)",
        "close_case->end_admin",
    ]

    lines += [
        f"\nfooter: Derived from {sample} of {total} ArbCom cases",
    ]

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# BPMN flow construction — case-specific
# ─────────────────────────────────────────────────────────────────────────────


def build_case_bpmn(
    title: str,
    sections: dict[str, str],
    ner: dict[str, list[str]],
) -> SwimlaneBpmnBuilder:
    """Build a SwimlaneBpmnBuilder for one arbitration case."""

    b = SwimlaneBpmnBuilder(f"ArbCom: {title[:60]}")

    has_prelim = has_section("Preliminary decisions", sections)
    has_fof = has_section("Findings of Fact", sections)
    has_rfc = has_section("Requests for comment", sections)
    has_enforce = needs_enforcement(sections) or has_section("Enforcement", sections)

    # ── Base flow ────────────────────────────────────────────────────────────
    start = b.start("Dispute Arises", "Involved Parties")
    file_req = b.task("File Arbitration Request", "Involved Parties", user=True)
    open_case = b.task("Open Case & Notify Parties", "ArbCom Clerk")
    submit = b.task("Submit Statements & Evidence", "Involved Parties", user=True)
    review = b.task("Review Submissions", "Arbitration Committee")

    # ── Optional: RFC ────────────────────────────────────────────────────────
    if has_rfc:
        rfc_issue = b.task("Issue Request for Comment", "Arbitration Committee")
        rfc_resp = b.task("Respond to External Comment", "Involved Parties", user=True)

    # ── Optional: preliminary decisions ─────────────────────────────────────
    if has_prelim:
        prelim = b.task("Issue Preliminary Decisions", "Arbitration Committee")

    # ── Core deliberation ────────────────────────────────────────────────────
    deliberate = b.task("Deliberate & Workshop", "Arbitration Committee")

    if has_fof:
        fof = b.task("Compile Findings of Fact", "Arbitration Committee")

    vote = b.task("Vote on Final Decision", "Arbitration Committee")
    final_dec = b.task("Publish Final Decision", "Arbitration Committee")
    close_admin = b.task("Close Case (Administrative)", "ArbCom Clerk")

    # ── Enforcement gateway ──────────────────────────────────────────────────
    remedy_gw = b.gateway("Remedies\nRequired?", "Arbitration Committee")

    # remedy label from NER (e.g. "blocked", "topic-banned")
    remedy_tasks = ner.get("TASK", [])
    enforce_label = next(
        (t for t in remedy_tasks if ENFORCEMENT_KEYWORDS.search(t)),
        "Enforce Remedies / Sanctions",
    )[:50]

    if has_enforce:
        enforce = b.task(enforce_label, "Administrator")
        end_yes = b.end("Case Resolved", "Administrator")
    end_no = b.end("Case Closed", "ArbCom Clerk")

    # ── Sequence flows ────────────────────────────────────────────────────────
    b.flow(start, file_req)
    b.flow(file_req, open_case)
    b.flow(open_case, submit)
    b.flow(submit, review)

    prev = review
    if has_rfc:
        b.flow(prev, rfc_issue)
        b.flow(rfc_issue, rfc_resp)
        prev = rfc_resp
    if has_prelim:
        b.flow(prev, prelim)
        prev = prelim
    b.flow(prev, deliberate)
    prev = deliberate

    if has_fof:
        b.flow(prev, fof)
        prev = fof

    b.flow(prev, vote)
    b.flow(vote, final_dec)
    b.flow(final_dec, close_admin)
    b.flow(close_admin, remedy_gw)

    if has_enforce:
        b.flow(remedy_gw, enforce, "Yes")
        b.flow(enforce, end_yes)
    b.flow(remedy_gw, end_no, "No")

    return b


# ─────────────────────────────────────────────────────────────────────────────
# BPMN flow construction — aggregate
# ─────────────────────────────────────────────────────────────────────────────


def build_aggregate_bpmn(
    section_counts: dict[str, int],
    total: int,
    enforcement_pct: int,
    sample: int,
) -> SwimlaneBpmnBuilder:
    """Build the generalised BPMN showing all common process paths."""

    def pct(section: str) -> int:
        return round(section_counts.get(section, 0) * 100 / max(total, 1))

    b = SwimlaneBpmnBuilder("Wikipedia ArbCom — Standard Arbitration Process")

    start = b.start("Dispute Arises", "Involved Parties")
    file_req = b.task("File Arbitration Request", "Involved Parties", user=True)
    open_case = b.task("Open Case & Notify Parties", "ArbCom Clerk")
    submit = b.task("Submit Statements & Evidence", "Involved Parties", user=True)
    review = b.task("Review Submissions", "Arbitration Committee")

    # Optional RFC
    if pct("Requests for comment") > 20:
        rfc = b.task(
            f"Issue RFC ({pct('Requests for comment')}% of cases)",
            "Arbitration Committee",
        )

    # Optional preliminary decisions
    if pct("Preliminary decisions") > 30:
        prelim = b.task(
            f"Preliminary Decisions ({pct('Preliminary decisions')}% of cases)",
            "Arbitration Committee",
        )

    deliberate = b.task("Deliberate & Workshop", "Arbitration Committee")
    fof = b.task(
        f"Compile Findings of Fact ({pct('Findings of Fact')}% of cases)",
        "Arbitration Committee",
    )
    vote = b.task("Vote on Final Decision", "Arbitration Committee")
    final_dec = b.task("Publish Final Decision", "Arbitration Committee")
    close_case = b.task("Close Case", "ArbCom Clerk")
    remedy_gw = b.gateway("Sanctions\nImposed?", "Arbitration Committee")
    enforce = b.task(
        f"Enforce Remedies / Sanctions ({enforcement_pct}% of cases)",
        "Administrator",
    )
    end_yes = b.end("Sanctions Applied", "Administrator")
    end_no = b.end("Case Closed (No Sanctions)", "ArbCom Clerk")

    # Flows
    b.flow(start, file_req)
    b.flow(file_req, open_case)
    b.flow(open_case, submit)
    b.flow(submit, review)

    prev = review
    if pct("Requests for comment") > 20:
        b.flow(prev, rfc)
        prev = rfc
    if pct("Preliminary decisions") > 30:
        b.flow(prev, prelim)
        prev = prelim
    b.flow(prev, deliberate)
    b.flow(deliberate, fof)
    b.flow(fof, vote)
    b.flow(vote, final_dec)
    b.flow(final_dec, close_case)
    b.flow(close_case, remedy_gw)
    b.flow(remedy_gw, enforce, f"Yes ({enforcement_pct}%)")
    b.flow(enforce, end_yes)
    b.flow(remedy_gw, end_no, f"No ({100 - enforcement_pct}%)")

    return b


# ─────────────────────────────────────────────────────────────────────────────
# File / case selection helpers
# ─────────────────────────────────────────────────────────────────────────────


def select_data_file(data_dir: Path) -> Path:
    """Let the user pick from clean_arbitration_cases*.json files."""
    candidates = sorted(data_dir.glob("clean_arbitration_cases*.json"))
    if not candidates:
        sys.exit(f"ERROR: No 'clean_arbitration_cases*.json' files found in {data_dir}")

    print(f"\n{'=' * 60}")
    print("Available arbitration case files:")
    print("=" * 60)
    for i, p in enumerate(candidates, 1):
        size_kb = p.stat().st_size // 1024
        print(f"  [{i}] {p.name}  ({size_kb} KB)")

    if len(candidates) == 1:
        print(f"\n  Auto-selecting only file: {candidates[0].name}")
        return candidates[0]

    while True:
        raw = input(f"\nSelect file [1–{len(candidates)}] (default 1): ").strip()
        if raw == "":
            return candidates[0]
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
        except ValueError:
            pass
        print(f"  Enter a number between 1 and {len(candidates)}.")


def select_case(cases: list[dict]) -> dict:
    """Interactively pick one case from the list by search or index."""
    print(f"\n{'=' * 60}")
    print(f"Found {len(cases)} arbitration cases.")
    print("=" * 60)
    print("Search by title fragment (e.g. 'Ril') or enter case number.")
    print("Type 'list' to show all titles (may be long).\n")

    while True:
        raw = input("Case name / number: ").strip()
        if not raw:
            continue

        if raw.lower() == "list":
            for i, c in enumerate(cases, 1):
                print(f"  [{i:4d}] {c.get('title', '?')}")
            continue

        # Try numeric
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(cases):
                return cases[idx]
            print(f"  Enter a number between 1 and {len(cases)}.")
            continue
        except ValueError:
            pass

        # Search by fragment
        matches = [c for c in cases if raw.lower() in c.get("title", "").lower()]
        if not matches:
            print(f"  No cases matching '{raw}'. Try a different fragment.")
        elif len(matches) == 1:
            print(f"  Found: {matches[0]['title']}")
            return matches[0]
        else:
            print(f"  Multiple matches ({len(matches)}):")
            for i, m in enumerate(matches[:20], 1):
                print(f"    [{i}] {m.get('title', '?')}")
            while True:
                choice = input("  Pick number (or blank to search again): ").strip()
                if not choice:
                    break
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(matches):
                        return matches[idx]
                except ValueError:
                    pass


# ─────────────────────────────────────────────────────────────────────────────
# Main entry points
# ─────────────────────────────────────────────────────────────────────────────


def run_specific_case(
    cases: list[dict],
    case_title: str | None,
    ner: NERExtractor,
    output_dir: Path,
) -> None:
    # Pick case
    if case_title:
        matches = [c for c in cases if case_title.lower() in c.get("title", "").lower()]
        if not matches:
            sys.exit(f"ERROR: No case matching '{case_title}'")
        case = matches[0]
        if len(matches) > 1:
            print(
                f"WARNING: {len(matches)} cases match '{case_title}'; using first: {case['title']}"
            )
    else:
        case = select_case(cases)

    title = case.get("title", "Unnamed")
    sections = case.get("sections", {}) or {}

    print(f"\n{'=' * 60}")
    print(f"Generating BPMN for: {title}")
    print(
        f"Sections present:    {[k for k in sections if (sections.get(k) or '').strip()]}"
    )
    print("=" * 60)

    # Run NER on key sections
    print("\nRunning NER extraction...")
    ner_result = ner.extract_sections(
        sections,
        [
            "Statement by",
            "Findings of Fact",
            "Remedies",
            "Final decision",
            "Preliminary decisions",
        ],
    )
    if ner_result.get("AGENT"):
        print(f"  Agents found:  {ner_result['AGENT'][:6]}")
    if ner_result.get("TASK"):
        print(f"  Tasks found:   {ner_result['TASK'][:6]}")
    if ner_result.get("CONDITION"):
        print(f"  Conditions:    {ner_result['CONDITION'][:4]}")

    # Build BPMN XML
    bpmn = build_case_bpmn(title, sections, ner_result)
    fname = safe_filename(title)
    bpmn_path = output_dir / f"arb_{fname}.bpmn"
    bpmn_path.write_text(bpmn.to_xml(), encoding="utf-8")
    print(f"\n  BPMN XML → {bpmn_path}")

    # Build PNG
    png_path = output_dir / f"arb_{fname}.png"
    if PIPERFLOW_AVAILABLE:
        try:
            piperflow_src = _piperflow_case(title, sections, ner_result)
            render_piperflow(piperflow_src, output_file=str(png_path))
            print(f"  PNG      → {png_path}")
        except Exception as exc:
            print(f"  PNG generation failed: {exc}")
    else:
        print("  PNG skipped (processpiper not installed).")

    print(f"\nDone. Open {bpmn_path.name} in Camunda Modeler or bpmn.io to view.")


def run_aggregate(
    cases: list[dict],
    sample: int | None,
    ner: NERExtractor,
    output_dir: Path,
) -> None:
    working = cases if not sample else cases[:sample]

    print(f"\n{'=' * 60}")
    print(f"Building aggregate BPMN from {len(working)} of {len(cases)} cases...")
    print("=" * 60)

    # Count section occurrences
    section_counts: Counter = Counter()
    enforcement_count = 0
    for case in working:
        secs = case.get("sections", {}) or {}
        for heading, text in secs.items():
            if text and text.strip():
                section_counts[heading] += 1
        if needs_enforcement(secs):
            enforcement_count += 1

    total = len(working)
    enforcement_pct = round(enforcement_count * 100 / max(total, 1))

    print("\nSection frequencies:")
    for sec, count in sorted(section_counts.items(), key=lambda x: -x[1])[:12]:
        print(f"  {count:4d}/{total}  ({count * 100 // total:3d}%)  {sec}")
    print(
        f"  Cases with active enforcement: {enforcement_count}/{total} ({enforcement_pct}%)"
    )

    # Build BPMN XML
    bpmn = build_aggregate_bpmn(section_counts, total, enforcement_pct, len(working))
    bpmn_path = output_dir / "arb_aggregate_workflow.bpmn"
    bpmn_path.write_text(bpmn.to_xml(), encoding="utf-8")
    print(f"\n  BPMN XML → {bpmn_path}")

    # Build PNG
    png_path = output_dir / "arb_aggregate_workflow.png"
    if PIPERFLOW_AVAILABLE:
        try:
            piperflow_src = _piperflow_aggregate(
                section_counts, total, enforcement_pct, len(working)
            )
            render_piperflow(piperflow_src, output_file=str(png_path))
            print(f"  PNG      → {png_path}")
        except Exception as exc:
            print(f"  PNG generation failed: {exc}")
    else:
        print("  PNG skipped (processpiper not installed).")

    print(f"\nDone. Open {bpmn_path.name} in Camunda Modeler or bpmn.io to view.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate BPMN diagrams from Wikipedia ArbCom cases using HuggingFace NER.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--case",
        metavar="TITLE",
        help="Title fragment of the case to model (interactive if omitted).",
    )
    mode.add_argument(
        "--aggregate",
        action="store_true",
        help="Build a generalised model from all (or --sample N) cases.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        metavar="N",
        help="For --aggregate: use only the first N cases (default: all).",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/bpmn/arb",
        help="Directory to write .bpmn and .png files (default: artifacts/bpmn/arb).",
    )
    parser.add_argument(
        "--no-ner",
        action="store_true",
        help="Skip HuggingFace NER (faster; rule-based flow only).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    project_root = Path(__file__).parent.parent
    data_dir = project_root / "data" / "processed"
    output_dir = project_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Load data ────────────────────────────────────────────────────────────
    data_file = select_data_file(data_dir)
    print(f"\nLoading {data_file.name}...")
    with open(data_file, encoding="utf-8") as fh:
        cases = json.load(fh)
    print(f"Loaded {len(cases)} cases.")

    # ── Initialise NER ───────────────────────────────────────────────────────
    ner = NERExtractor() if not args.no_ner else NERExtractor.__new__(NERExtractor)
    if args.no_ner:
        ner._pipe = None  # noqa: SLF001

    # ── Dispatch ─────────────────────────────────────────────────────────────
    if args.aggregate:
        run_aggregate(cases, args.sample, ner, output_dir)
    elif args.case:
        run_specific_case(cases, args.case, ner, output_dir)
    else:
        # Interactive: ask user what they want
        print(f"\n{'=' * 60}")
        print("What would you like to generate?")
        print("  [1] BPMN for a specific arbitration case")
        print("  [2] Generalised aggregate BPMN (all cases)")
        choice = input("Choice [1/2, default 1]: ").strip()
        if choice == "2":
            sample_raw = input("Sample how many cases? (Enter for all): ").strip()
            sample = int(sample_raw) if sample_raw.isdigit() else None
            run_aggregate(cases, sample, ner, output_dir)
        else:
            run_specific_case(cases, None, ner, output_dir)


if __name__ == "__main__":
    main()
