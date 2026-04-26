#!/usr/bin/env python3
"""
arbitration_bpmn_hf.py — Wikipedia ArbCom BPMN Generator (HuggingFace NER)

Uses jtlicardo/bpmn-information-extraction (BERT-based token classifier) to
extract AGENT, TASK, and CONDITION entities from arbitration case text, then
builds BPMN 2.0 XML with swimlanes + PNG diagrams.

Swimlanes
---------
  Involved Parties      — disputing users / requestors
  ArbCom Clerk          — administrative tasks (open, close, notify)
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
  python scripts/arbitration_bpmn_hf.py --output-dir artifacts/bpmn_hf

Requirements
------------
  pip install transformers torch processpiper
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET

# ── Optional deps ─────────────────────────────────────────────────────────────

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

# ── Constants ─────────────────────────────────────────────────────────────────

HF_NER_MODEL = "jtlicardo/bpmn-information-extraction"

LANES = ["Involved Parties", "ArbCom Clerk", "Arbitration Committee", "Administrator"]

ENFORCEMENT_RE = re.compile(
    r"\b(ban(ned)?|block(ed)?|topic.ban|desysop(ped)?|sanction(ed)?|"
    r"restrict(ed)?|prohibit(ed)?|suspend(ed)?|remov(ed)?|revok(ed)?)\b",
    re.IGNORECASE,
)

NS_BPMN = "http://www.omg.org/spec/BPMN/20100524/MODEL"
NS_BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"
NS_DC = "http://www.omg.org/spec/DD/20100524/DC"
NS_DI = "http://www.omg.org/spec/DD/20100524/DI"

POOL_X, POOL_Y = 100, 80
POOL_HEADER_W = 30
LANE_H = 160
TASK_W, TASK_H = 130, 60
GW_W, GW_H = 50, 50
EVT_W, EVT_H = 36, 36
STEP_GAP = 160
FIRST_X = POOL_X + POOL_HEADER_W + 80

# ── Utilities ─────────────────────────────────────────────────────────────────


def _uid(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def safe_filename(title: str, max_len: int = 60) -> str:
    s = re.sub(r"[^\w\-]", "_", title)
    return re.sub(r"_+", "_", s).strip("_")[:max_len] or "unnamed"


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    return [v for v in items if not (v.lower() in seen or seen.add(v.lower()))]


def _lower_sections(sections: dict[str, str]) -> dict[str, str]:
    """Precompute {heading.lower(): text} once per case; avoids re-lowercasing on every lookup."""
    return {k.lower(): v or "" for k, v in sections.items()}


def section_match(key: str, lower_secs: dict[str, str]) -> str:
    """Return text of first section whose lowercased heading contains key (already lowercased)."""
    return next((v for k, v in lower_secs.items() if key in k), "")


def has_section(key: str, lower_secs: dict[str, str]) -> bool:
    return bool(section_match(key, lower_secs).strip())


def needs_enforcement(lower_secs: dict[str, str]) -> bool:
    text = (
        section_match("remedies", lower_secs)
        + " "
        + section_match("final decision", lower_secs)
    )
    return bool(ENFORCEMENT_RE.search(text))


def chunk_text(text: str, max_chars: int = 1400) -> list[str]:
    """Split long text into chunks at paragraph then sentence boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        if len(current) + len(para) + 2 <= max_chars:
            current = (current + "\n\n" + para).strip()
        elif len(para) > max_chars:
            if current:
                chunks.append(current)
            current = ""  # reset before sentence loop to avoid carry-over
            for sent in re.split(r"(?<=[.!?])\s+", para):
                if len(current) + len(sent) + 1 <= max_chars:
                    current = (current + " " + sent).strip()
                else:
                    if current:
                        chunks.append(current)
                    current = sent
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks


# ── Process Specification — single source of truth for diagram shape ──────────


@dataclass
class ProcessSpec:
    """
    Captures all decisions about process shape in one place.
    Both build_bpmn() and build_piperflow() consume this object exclusively —
    the conditional logic lives here, not scattered across parallel builders.
    """

    title: str
    has_rfc: bool
    has_prelim: bool
    has_fof: bool
    has_enforce: bool
    is_aggregate: bool = False
    enforce_label: str = "Enforce Remedies / Sanctions"
    # Aggregate-only percentage annotations (0 for specific cases)
    rfc_pct: int = 0
    prelim_pct: int = 0
    fof_pct: int = 0
    enforcement_pct: int = 0
    total_cases: int = 0
    sample_cases: int = 0

    def annotated(self, base: str, pct: int) -> str:
        """Append '(N% of cases)' annotation for aggregate specs only."""
        return f"{base} ({pct}% of cases)" if self.is_aggregate and pct else base


def spec_from_case(
    title: str, sections: dict[str, str], ner: dict[str, list[str]]
) -> ProcessSpec:
    """Build ProcessSpec for a specific arbitration case."""
    ls = _lower_sections(sections)
    enforce_label = next(
        (t for t in ner.get("TASK", []) if ENFORCEMENT_RE.search(t)),
        "Enforce Remedies / Sanctions",
    )[:50]
    return ProcessSpec(
        title=title,
        has_rfc=has_section("requests for comment", ls),
        has_prelim=has_section("preliminary decisions", ls),
        has_fof=has_section("findings of fact", ls),
        has_enforce=needs_enforcement(ls) or has_section("enforcement", ls),
        enforce_label=enforce_label,
    )


def spec_from_aggregate(
    section_counts: Counter, total: int, enforcement_pct: int, sample: int
) -> ProcessSpec:
    """Build ProcessSpec for the generalised aggregate model."""

    def pct(key: str) -> int:
        return round(section_counts.get(key, 0) * 100 / max(total, 1))

    rfc_pct = pct("Requests for comment")
    prelim_pct = pct("Preliminary decisions")
    return ProcessSpec(
        title="Wikipedia ArbCom — Standard Arbitration Process",
        has_rfc=rfc_pct > 20,
        has_prelim=prelim_pct > 30,
        has_fof=True,  # always shown in aggregate
        has_enforce=True,
        is_aggregate=True,
        rfc_pct=rfc_pct,
        prelim_pct=prelim_pct,
        fof_pct=pct("Findings of Fact"),
        enforcement_pct=enforcement_pct,
        total_cases=total,
        sample_cases=sample,
    )


# ── NER Extractor ─────────────────────────────────────────────────────────────


class NERExtractor:
    """
    Wraps jtlicardo/bpmn-information-extraction (BERT token classifier).
    Labels: AGENT, TASK, TASK_INFO, PROCESS_INFO, CONDITION
    """

    _LABELS = ("AGENT", "TASK", "TASK_INFO", "PROCESS_INFO", "CONDITION")

    def __init__(self, model_name: str = HF_NER_MODEL, load_model: bool = True):
        self._pipe = None
        if not load_model or not HF_AVAILABLE:
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
                if label in results and len(word) > 2:
                    results[label].append(word)
        return {k: _dedup(v) for k, v in results.items()}

    def extract_sections(
        self, sections: dict[str, str], keys: list[str]
    ) -> dict[str, list[str]]:
        """Extract NER from multiple sections (partial-key matched) and merge."""
        ls = _lower_sections(sections)
        merged: dict[str, list[str]] = {lbl: [] for lbl in self._LABELS}
        for key in keys:
            for lbl, vals in self.extract(section_match(key.lower(), ls)).items():
                merged[lbl].extend(vals)
        return {k: _dedup(v) for k, v in merged.items()}


# ── BPMN 2.0 XML Builder ──────────────────────────────────────────────────────


class SwimlaneBpmnBuilder:
    """Builds a BPMN 2.0 XML document with horizontally-oriented swimlanes."""

    def __init__(self, process_name: str, lanes: list[str] = LANES):
        self.process_name = process_name
        self.lanes = lanes
        self._lane_index = {name: i for i, name in enumerate(lanes)}  # O(1) lookup
        self._lane_ids = {name: _uid("Lane") for name in lanes}
        self._collab_id = _uid("Collab")
        self._part_id = _uid("Participant")
        self._proc_id = _uid("Process")
        self._elements: list[
            tuple[str, str, str, str, int]
        ] = []  # (eid, label, etype, lane, step)
        self._flows: list[tuple[str, str, str, str]] = []  # (fid, src, tgt, label)
        self._step = 0

    def _add(self, label: str, etype: str, lane: str) -> str:
        eid = _uid(etype.replace("Event", "Evt").replace("Gateway", "GW")[:6])
        self._elements.append((eid, label, etype, lane, self._step))
        self._step += 1
        return eid

    def start(self, label: str, lane: str = "Involved Parties") -> str:
        return self._add(label, "startEvent", lane)

    def end(self, label: str, lane: str = "ArbCom Clerk") -> str:
        return self._add(label, "endEvent", lane)

    def task(self, label: str, lane: str, user: bool = False) -> str:
        return self._add(label, "userTask" if user else "task", lane)

    def gateway(self, label: str, lane: str, exclusive: bool = True) -> str:
        return self._add(
            label, "exclusiveGateway" if exclusive else "parallelGateway", lane
        )

    def flow(self, src: str, tgt: str, label: str = "") -> str:
        fid = _uid("Flow")
        self._flows.append((fid, src, tgt, label))
        return fid

    def _bounds(self, etype: str, lane: str, step: int) -> tuple[int, int, int, int]:
        lane_top = POOL_Y + self._lane_index[lane] * LANE_H  # O(1) dict lookup
        cx = FIRST_X + step * STEP_GAP
        if etype in ("startEvent", "endEvent"):
            w, h = EVT_W, EVT_H
        elif "Gateway" in etype:
            w, h = GW_W, GW_H
        else:
            w, h = TASK_W, TASK_H
        return cx, lane_top + (LANE_H - h) // 2, w, h

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

        process = ET.SubElement(
            root,
            f"{{{NS_BPMN}}}process",
            {
                "id": self._proc_id,
                "isExecutable": "false",
            },
        )

        lane_set = ET.SubElement(process, f"{{{NS_BPMN}}}laneSet", {"id": _uid("LS")})
        for lane_name in self.lanes:
            lane_el = ET.SubElement(
                lane_set,
                f"{{{NS_BPMN}}}lane",
                {
                    "id": self._lane_ids[lane_name],
                    "name": lane_name,
                },
            )
            for eid, _, _, elane, _ in self._elements:
                if elane == lane_name:
                    ET.SubElement(lane_el, f"{{{NS_BPMN}}}flowNodeRef").text = eid

        incoming: dict[str, list[str]] = defaultdict(list)
        outgoing: dict[str, list[str]] = defaultdict(list)
        for fid, src, tgt, _ in self._flows:
            outgoing[src].append(fid)
            incoming[tgt].append(fid)

        for eid, label, etype, _, _ in self._elements:
            el = ET.SubElement(
                process, f"{{{NS_BPMN}}}{etype}", {"id": eid, "name": label}
            )
            for fid in incoming.get(eid, []):
                ET.SubElement(el, f"{{{NS_BPMN}}}incoming").text = fid
            for fid in outgoing.get(eid, []):
                ET.SubElement(el, f"{{{NS_BPMN}}}outgoing").text = fid

        for fid, src, tgt, label in self._flows:
            attrs: dict[str, str] = {"id": fid, "sourceRef": src, "targetRef": tgt}
            if label:
                attrs["name"] = label
            ET.SubElement(process, f"{{{NS_BPMN}}}sequenceFlow", attrs)

        max_step = max((e[4] for e in self._elements), default=0)
        pool_w = FIRST_X - POOL_X + (max_step + 1) * STEP_GAP + 80
        pool_h = LANE_H * len(self.lanes)

        diagram = ET.SubElement(
            root, f"{{{NS_BPMNDI}}}BPMNDiagram", {"id": _uid("Diag")}
        )
        plane = ET.SubElement(
            diagram,
            f"{{{NS_BPMNDI}}}BPMNPlane",
            {
                "id": _uid("Plane"),
                "bpmnElement": self._collab_id,
            },
        )

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

        for i, lane_name in enumerate(self.lanes):
            lid = self._lane_ids[lane_name]
            ls_el = ET.SubElement(
                plane,
                f"{{{NS_BPMNDI}}}BPMNShape",
                {
                    "id": f"{lid}_di",
                    "bpmnElement": lid,
                    "isHorizontal": "true",
                },
            )
            ET.SubElement(
                ls_el,
                f"{{{NS_DC}}}Bounds",
                {
                    "x": str(POOL_X + POOL_HEADER_W),
                    "y": str(POOL_Y + i * LANE_H),
                    "width": str(pool_w - POOL_HEADER_W),
                    "height": str(LANE_H),
                },
            )

        bounds_cache: dict[str, tuple[int, int, int, int]] = {}
        for eid, label, etype, lane, step in self._elements:
            x, y, w, h = self._bounds(etype, lane, step)
            bounds_cache[eid] = (x, y, w, h)
            shape = ET.SubElement(
                plane,
                f"{{{NS_BPMNDI}}}BPMNShape",
                {
                    "id": f"{eid}_di",
                    "bpmnElement": eid,
                },
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
            if etype in ("startEvent", "endEvent") or "Gateway" in etype:
                lbl_el = ET.SubElement(shape, f"{{{NS_BPMNDI}}}BPMNLabel")
                ET.SubElement(
                    lbl_el,
                    f"{{{NS_DC}}}Bounds",
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
                f"{{{NS_BPMNDI}}}BPMNEdge",
                {
                    "id": f"{fid}_di",
                    "bpmnElement": fid,
                },
            )
            sx, sy, sw, sh = bounds_cache.get(src, (0, 0, 0, 0))
            tx, ty, tw, th = bounds_cache.get(tgt, (0, 0, 0, 0))
            if label:
                le = ET.SubElement(edge, f"{{{NS_BPMNDI}}}BPMNLabel")
                ET.SubElement(
                    le,
                    f"{{{NS_DC}}}Bounds",
                    {
                        "x": str(int((sx + sw / 2 + tx + tw / 2) / 2) - 20),
                        "y": str(int((sy + sh / 2 + ty + th / 2) / 2) - 10),
                        "width": "60",
                        "height": "20",
                    },
                )
            ET.SubElement(
                edge,
                f"{{{NS_DI}}}waypoint",
                {"x": str(sx + sw), "y": str(int(sy + sh / 2))},
            )
            ET.SubElement(
                edge, f"{{{NS_DI}}}waypoint", {"x": str(tx), "y": str(int(ty + th / 2))}
            )

        return minidom.parseString(ET.tostring(root, encoding="unicode")).toprettyxml(
            indent="  "
        )


# ── Diagram builders — both consume ProcessSpec ───────────────────────────────


def build_bpmn(spec: ProcessSpec) -> SwimlaneBpmnBuilder:
    """
    Construct BPMN XML builder from a ProcessSpec.
    This is the authoritative representation of process logic.
    build_piperflow() must mirror any changes made here.
    """
    lanes = LANES if spec.has_enforce else LANES[:-1]
    b = SwimlaneBpmnBuilder(f"ArbCom: {spec.title[:60]}", lanes)

    start = b.start("Dispute Arises", "Involved Parties")
    file_req = b.task("File Arbitration Request", "Involved Parties", user=True)
    open_case = b.task("Open Case & Notify Parties", "ArbCom Clerk")
    submit = b.task("Submit Statements & Evidence", "Involved Parties", user=True)
    review = b.task("Review Submissions", "Arbitration Committee")

    prelim = rfc_issue = rfc_resp = fof = None

    if spec.has_prelim:
        prelim = b.task(
            spec.annotated("Issue Preliminary Decisions", spec.prelim_pct),
            "Arbitration Committee",
        )
    if spec.has_rfc:
        rfc_issue = b.task(
            spec.annotated("Issue Request for Comment", spec.rfc_pct),
            "Arbitration Committee",
        )
        if not spec.is_aggregate:
            rfc_resp = b.task(
                "Respond to External Comment", "Involved Parties", user=True
            )

    deliberate = b.task("Deliberate & Workshop", "Arbitration Committee")

    if spec.has_fof:
        fof = b.task(
            spec.annotated("Compile Findings of Fact", spec.fof_pct),
            "Arbitration Committee",
        )

    vote = b.task("Vote on Final Decision", "Arbitration Committee")
    final_dec = b.task("Publish Final Decision", "Arbitration Committee")
    remedy_gw = b.gateway("Sanctions\nImposed?", "Arbitration Committee")

    enforce = end_yes = None
    if spec.has_enforce:
        enforce = b.task(
            spec.annotated(spec.enforce_label, spec.enforcement_pct), "Administrator"
        )
        end_yes = b.end("Sanctions Applied", "Administrator")
    close_case = b.task("Close Case", "ArbCom Clerk")
    end_no = b.end("Case Closed", "ArbCom Clerk")

    b.flow(start, file_req)
    b.flow(file_req, open_case)
    b.flow(open_case, submit)
    b.flow(submit, review)

    prev = review
    if prelim:
        b.flow(prev, prelim)
        prev = prelim
    if rfc_issue:
        b.flow(prev, rfc_issue)
        prev = rfc_resp if rfc_resp else rfc_issue
    b.flow(prev, deliberate)
    prev = deliberate
    if fof:
        b.flow(prev, fof)
        prev = fof
    b.flow(prev, vote)
    b.flow(vote, final_dec)
    b.flow(final_dec, remedy_gw)

    yes_lbl = f"Yes ({spec.enforcement_pct}%)" if spec.is_aggregate else "Yes"
    no_lbl = f"No ({100 - spec.enforcement_pct}%)" if spec.is_aggregate else "No"
    if enforce:
        b.flow(remedy_gw, enforce, yes_lbl)
        b.flow(enforce, end_yes)
    b.flow(remedy_gw, close_case, no_lbl)
    b.flow(close_case, end_no)

    return b


def build_piperflow(spec: ProcessSpec) -> str:
    """
    Build processpiper DSL string from a ProcessSpec.
    Mirrors build_bpmn() — if you change process logic in one, update the other.
    """
    parties = [
        "        (start) as start",
        "        [File Arbitration Request] as file_req",
        "        [Submit Statements & Evidence] as submit",
    ]
    if spec.has_rfc and not spec.is_aggregate:
        parties.append("        [Respond to RFC] as rfc_respond")

    clerk = [
        "        [Open Case & Notify Parties] as open_case",
        "        [Close Case] as close_case",
        "        (end) as end_closed",
    ]

    arbcom = ["        [Review Submissions] as review"]
    if spec.has_prelim:
        arbcom.append(
            f"        [{spec.annotated('Issue Preliminary Decisions', spec.prelim_pct)}] as prelim"
        )
    if spec.has_rfc:
        arbcom.append(
            f"        [{spec.annotated('Issue Request for Comment', spec.rfc_pct)}] as rfc_issue"
        )
    arbcom.append("        [Deliberate & Workshop] as deliberate")
    if spec.has_fof:
        arbcom.append(
            f"        [{spec.annotated('Compile Findings of Fact', spec.fof_pct)}] as fof"
        )
    arbcom += [
        "        [Vote on Final Decision] as vote",
        "        [Publish Final Decision] as final_dec",
        "        <Sanctions Imposed?> as remedy_gw",
    ]

    admin = []
    if spec.has_enforce:
        admin += [
            f"        [{spec.annotated(spec.enforce_label, spec.enforcement_pct)[:40]}] as enforce",
            "        (end) as end_enforced",
        ]

    lines = [
        f"title: {spec.title[:60]}",
        "colourtheme: BLUEMOUNTAIN",
        "",
        "pool: Wikipedia Arbitration Process",
        "    lane: Involved Parties",
        *parties,
        "    lane: ArbCom Clerk",
        *clerk,
        "    lane: Arbitration Committee",
        *arbcom,
    ]
    if admin:
        lines += ["    lane: Administrator", *admin]
    lines.append("")

    # Build main flow chain — mirrors the sequence flows in build_bpmn()
    chain = ["review"]
    if spec.has_prelim:
        chain.append("prelim")
    if spec.has_rfc:
        chain.append("rfc_issue")
        if not spec.is_aggregate:
            chain.append("rfc_respond")
    chain.append("deliberate")
    if spec.has_fof:
        chain.append("fof")
    chain += ["vote", "final_dec", "remedy_gw"]

    lines.append("start->file_req->open_case->submit->" + "->".join(chain))

    yes_lbl = f": Yes ({spec.enforcement_pct}%)" if spec.is_aggregate else ": Yes"
    no_lbl = f": No ({100 - spec.enforcement_pct}%)" if spec.is_aggregate else ": No"
    if spec.has_enforce:
        lines += [f"remedy_gw->enforce{yes_lbl}", "enforce->end_enforced"]
    lines += [f"remedy_gw->close_case{no_lbl}", "close_case->end_closed"]

    footer = (
        f"Derived from {spec.sample_cases} of {spec.total_cases} ArbCom cases"
        if spec.is_aggregate
        else f"ArbCom case: {spec.title[:50]}"
    )
    lines.append(f"\nfooter: {footer}")
    return "\n".join(lines)


# ── File / case selection ─────────────────────────────────────────────────────


def select_data_file(data_dir: Path) -> Path:
    candidates = sorted(data_dir.glob("clean_arbitration_cases*.json"))
    if not candidates:
        sys.exit(f"ERROR: No 'clean_arbitration_cases*.json' files found in {data_dir}")
    print(f"\n{'=' * 60}\nAvailable arbitration case files:\n{'=' * 60}")
    for i, p in enumerate(candidates, 1):
        print(f"  [{i}] {p.name}  ({p.stat().st_size // 1024} KB)")
    if len(candidates) == 1:
        print(f"\n  Auto-selecting: {candidates[0].name}")
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
    print(f"\n{'=' * 60}\nFound {len(cases)} arbitration cases.\n{'=' * 60}")
    print("Search by title fragment or enter case number. Type 'list' to show all.\n")
    while True:
        raw = input("Case name / number: ").strip()
        if not raw:
            continue
        if raw.lower() == "list":
            for i, c in enumerate(cases, 1):
                print(f"  [{i:4d}] {c.get('title', '?')}")
            continue
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(cases):
                return cases[idx]
            print(f"  Enter a number between 1 and {len(cases)}.")
            continue
        except ValueError:
            pass
        matches = [c for c in cases if raw.lower() in c.get("title", "").lower()]
        if not matches:
            print(f"  No cases matching '{raw}'.")
        elif len(matches) == 1:
            print(f"  Found: {matches[0]['title']}")
            return matches[0]
        else:
            print(f"  {len(matches)} matches:")
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


# ── Shared output writer ──────────────────────────────────────────────────────


def _write_outputs(
    spec: ProcessSpec, stem: str, output_dir: Path, dashboard_dir: Path | None = None
) -> None:
    bpmn_path = output_dir / f"{stem}.bpmn"
    bpmn_path.write_text(build_bpmn(spec).to_xml(), encoding="utf-8")
    print(f"  BPMN XML → {bpmn_path}")

    if PIPERFLOW_AVAILABLE:
        png_path = output_dir / f"{stem}.png"
        try:
            render_piperflow(build_piperflow(spec), output_file=str(png_path))
            print(f"  PNG      → {png_path}")
            if dashboard_dir:
                import shutil

                dashboard_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(png_path, dashboard_dir / f"{stem}.png")
                print(f"  PNG   ↗  → {dashboard_dir / f'{stem}.png'}")
        except Exception as exc:
            print(f"  PNG generation failed: {exc}")
    else:
        print("  PNG skipped (processpiper not installed).")


# ── Run modes ─────────────────────────────────────────────────────────────────


def run_specific_case(
    cases: list[dict],
    case_title: str | None,
    ner: NERExtractor,
    output_dir: Path,
    dashboard_dir: Path | None = None,
) -> None:
    if case_title:
        matches = [c for c in cases if case_title.lower() in c.get("title", "").lower()]
        if not matches:
            sys.exit(f"ERROR: No case matching '{case_title}'")
        case = matches[0]
        if len(matches) > 1:
            print(f"WARNING: {len(matches)} matches; using first: {case['title']}")
    else:
        case = select_case(cases)

    title = case.get("title", "Unnamed")
    sections = case.get("sections", {}) or {}
    print(f"\n{'=' * 60}\nGenerating BPMN for: {title}\n{'=' * 60}")

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
    for lbl, limit in (("AGENT", 6), ("TASK", 6), ("CONDITION", 4)):
        if ner_result.get(lbl):
            print(f"  {lbl:12s}: {ner_result[lbl][:limit]}")

    spec = spec_from_case(title, sections, ner_result)
    _write_outputs(spec, f"arb_{safe_filename(title)}", output_dir, dashboard_dir)
    print("\nDone. Open the .bpmn file in Camunda Modeler or bpmn.io to view.")


def run_aggregate(
    cases: list[dict],
    sample: int | None,
    ner: NERExtractor,
    output_dir: Path,
    dashboard_dir: Path | None = None,
) -> None:
    working = random.sample(cases, sample) if sample and sample < len(cases) else cases
    print(
        f"\n{'=' * 60}\nBuilding aggregate BPMN from {len(working)} of {len(cases)} cases...\n{'=' * 60}"
    )

    section_counts: Counter = Counter()
    enforcement_count = 0
    for case in working:
        secs = case.get("sections", {}) or {}
        ls = _lower_sections(secs)
        for heading, text in secs.items():
            if text and text.strip():
                section_counts[heading] += 1
        if needs_enforcement(ls):
            enforcement_count += 1

    total = len(working)
    enforcement_pct = round(enforcement_count * 100 / max(total, 1))

    print("\nSection frequencies:")
    for sec, count in sorted(section_counts.items(), key=lambda x: -x[1])[:12]:
        print(f"  {count:4d}/{total}  ({count * 100 // total:3d}%)  {sec}")
    print(
        f"  Cases with active enforcement: {enforcement_count}/{total} ({enforcement_pct}%)"
    )

    spec = spec_from_aggregate(section_counts, total, enforcement_pct, len(working))
    _write_outputs(spec, "arb_aggregate_workflow", output_dir, dashboard_dir)
    print("\nDone. Open the .bpmn file in Camunda Modeler or bpmn.io to view.")


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate BPMN diagrams from Wikipedia ArbCom cases using HuggingFace NER.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--case", metavar="TITLE", help="Title fragment of the case to model."
    )
    mode.add_argument(
        "--aggregate",
        action="store_true",
        help="Build a generalised model from all cases.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        metavar="N",
        help="For --aggregate: random sample of N cases (default: all).",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/bpmn/arb",
        help="Directory for .bpmn and .png output (default: artifacts/bpmn/arb).",
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
    output_dir = project_root / args.output_dir
    dashboard_dir = project_root / "dashboard" / "public" / "bpmn" / "arbitration"
    output_dir.mkdir(parents=True, exist_ok=True)

    data_file = select_data_file(project_root / "data" / "processed")
    print(f"\nLoading {data_file.name}...")
    with open(data_file, encoding="utf-8") as fh:
        cases = json.load(fh)
    print(f"Loaded {len(cases)} cases.")

    ner = NERExtractor(load_model=not args.no_ner)

    if args.aggregate:
        run_aggregate(cases, args.sample, ner, output_dir, dashboard_dir)
    elif args.case:
        run_specific_case(cases, args.case, ner, output_dir, dashboard_dir)
    else:
        print(
            f"\n{'=' * 60}\nWhat would you like to generate?\n  [1] BPMN for a specific case\n  [2] Generalised aggregate BPMN"
        )
        choice = input("Choice [1/2, default 1]: ").strip()
        if choice == "2":
            raw = input("Sample how many cases? (Enter for all): ").strip()
            run_aggregate(
                cases,
                int(raw) if raw.isdigit() else None,
                ner,
                output_dir,
                dashboard_dir,
            )
        else:
            run_specific_case(cases, None, ner, output_dir, dashboard_dir)


if __name__ == "__main__":
    main()
