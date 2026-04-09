#!/usr/bin/env python3
"""
gemma4_bpmn.py — BPMN generator for Wikipedia dispute text using Gemma 4

Loads a local Gemma 4 checkpoint, prompts it to extract process structure
from Wikipedia dispute-resolution text (ARB, DRN, RFC, ANI), then builds
BPMN 2.0 XML with swimlanes.  Optionally renders PNG diagrams.

Two-phase approach
------------------
  Phase 1 — Gemma 4 extracts structured process JSON (actors, tasks, flows,
             gateways) from raw dispute text.  JSON is more reliable than
             asking the model to emit raw XML.
  Phase 2 — BpmnXmlBuilder turns the JSON into valid BPMN 2.0 XML, following
             the same pattern used in arbitration_bpmn_hf.py.

Modes
-----
  --text FILE      Process a single plain-text dispute document
  --arb  CASE      Fetch an arbitration case from Wikipedia and process it
  --batch DIR      Process all *.txt files in a directory
  --dry-run        Print the extracted JSON without writing BPMN files

Usage
-----
  python scripts/gemma4_bpmn.py --text my_dispute.txt
  python scripts/gemma4_bpmn.py --arb "Wikipedia:Requests_for_arbitration/-Ril-"
  python scripts/gemma4_bpmn.py --batch data/raw/drn/ --output-dir artifacts/bpmn/gemma4
  python scripts/gemma4_bpmn.py --text my_dispute.txt --dry-run
  python scripts/gemma4_bpmn.py --text my_dispute.txt --quantize 4bit

Requirements
------------
  pip install transformers torch accelerate bitsandbytes huggingface_hub
  (bitsandbytes only needed for --quantize)

Environment
-----------
  HF_TOKEN=hf_YOUR_TOKEN_HERE   (only needed if loading from Hub directly)
  MODEL_DIR=/path/to/local/weights  (or pass --model-dir)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import uuid
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET

# ─────────────────────────────────────────────────────────────────────────────
# Optional heavy deps — graceful fallback keeps the script importable
# ─────────────────────────────────────────────────────────────────────────────

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    print(
        "WARNING: 'transformers' or 'torch' not installed.\n"
        "         Run: pip install transformers torch accelerate\n"
    )

try:
    from processpiper.text2diagram import render as render_piperflow  # type: ignore[import-untyped]  # noqa: F401

    PIPERFLOW_AVAILABLE = True
except ImportError:
    PIPERFLOW_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# TODO: confirm model ID once Gemma 4 is available on HuggingFace Hub
DEFAULT_MODEL_ID = "google/gemma-4-9b-it"
DEFAULT_OUTPUT_DIR = Path("artifacts/bpmn/gemma4")
DEFAULT_MAX_NEW_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.2  # low temp → more deterministic JSON

# Swimlane defaults for Wikipedia dispute venues
LANE_PRESETS: dict[str, list[str]] = {
    "arb": [
        "Involved Parties",
        "ArbCom Clerk",
        "Arbitration Committee",
        "Administrator",
    ],
    "drn": ["Complainant", "Respondent", "DRN Volunteer", "Administrator"],
    "rfc": ["Proposer", "Participants", "Closer"],
    "ani": ["Reporter", "Reported Editor", "Administrator"],
    "generic": ["Initiator", "Participant", "Mediator", "Administrator"],
}

# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert business process analyst specializing in Wikipedia's
    dispute-resolution system.  Your task is to read Wikipedia dispute text
    and extract a structured process model suitable for BPMN 2.0 diagrams.

    Output ONLY valid JSON — no prose, no markdown fences, no comments.
    Follow the schema exactly.
""")

EXTRACTION_PROMPT_TEMPLATE = textwrap.dedent("""\
    Analyse the following Wikipedia dispute-resolution text and extract a
    BPMN process model as JSON.

    Venue type hint: {venue}
    Expected swimlanes (use these names exactly): {lanes}

    Output a single JSON object with this schema:
    {{
      "process_name": "<short descriptive name>",
      "lanes": [
        {{
          "id": "lane_<snake_case_name>",
          "name": "<Lane Name>",
          "elements": [
            {{
              "id": "elem_<unique_id>",
              "type": "startEvent | endEvent | task | exclusiveGateway | parallelGateway",
              "name": "<short label>",
              "outgoing": ["<target_elem_id>", ...]
            }}
          ]
        }}
      ]
    }}

    Rules:
    - Every process must have exactly one startEvent and at least one endEvent.
    - Gateway names must be yes/no questions or conditions (e.g. "Case accepted?").
    - Task names must be short verb phrases (≤ 6 words).
    - outgoing lists connect elements across lanes using the target element's id.
    - Use only IDs defined within this JSON — no dangling references.

    --- DISPUTE TEXT ---
    {text}
    --- END TEXT ---

    JSON:
""")

# ─────────────────────────────────────────────────────────────────────────────
# Model loader
# ─────────────────────────────────────────────────────────────────────────────


class Gemma4Loader:
    """Load Gemma 4 with optional quantization; handle CPU fallback."""

    def __init__(
        self,
        model_dir: str | Path,
        quantize: str | None = None,
    ) -> None:
        if not TRANSFORMERS_AVAILABLE:
            raise RuntimeError("transformers not installed — cannot load model")

        model_path = str(model_dir)
        device_map = "auto"

        bnb_config = None
        if quantize == "4bit":
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
        elif quantize == "8bit":
            bnb_config = BitsAndBytesConfig(load_in_8bit=True)

        print(f"Loading tokenizer from {model_path} ...")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)

        print(
            f"Loading model (quantize={quantize or 'none'}, device_map={device_map}) ..."
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            device_map=device_map,
            torch_dtype=torch.float16,
            quantization_config=bnb_config,
        )
        self.model.eval()
        print("Model loaded.\n")

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        """Run greedy / low-temp generation; return the new tokens only."""
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        with torch.no_grad():
            output_ids = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        new_tokens = output_ids[0][inputs["input_ids"].shape[1] :]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True)


# ─────────────────────────────────────────────────────────────────────────────
# Extraction — LLM → process JSON
# ─────────────────────────────────────────────────────────────────────────────


def build_prompt(text: str, venue: str, lanes: list[str]) -> str:
    """Construct the full chat-formatted prompt for Gemma 4 (instruction format)."""
    user_content = EXTRACTION_PROMPT_TEMPLATE.format(
        venue=venue,
        lanes=", ".join(lanes),
        text=text[:4000],  # truncate to keep within context window
    )
    # Gemma 4 instruction format — TODO: verify exact template once model is public
    # Typical Google instruct format: <start_of_turn>user\n...<end_of_turn>\n<start_of_turn>model
    return (
        f"<start_of_turn>system\n{SYSTEM_PROMPT}<end_of_turn>\n"
        f"<start_of_turn>user\n{user_content}<end_of_turn>\n"
        f"<start_of_turn>model\n"
    )


def extract_json(raw: str) -> dict:
    """Pull the first valid JSON object out of the model's raw output."""
    # Strip markdown fences if model adds them despite instructions
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)

    # Find outermost braces
    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object found in model output")
    depth = 0
    for i, ch in enumerate(raw[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(raw[start : i + 1])
    raise ValueError("Unmatched braces in model output")


def extract_process(
    loader: Gemma4Loader,
    text: str,
    venue: str,
    lanes: list[str],
    max_retries: int = 2,
) -> dict:
    """Prompt the model and parse the JSON; retry on parse failure."""
    prompt = build_prompt(text, venue, lanes)
    for attempt in range(1, max_retries + 1):
        raw = loader.generate(prompt)
        try:
            data = extract_json(raw)
            _validate_process_json(data)
            return data
        except (ValueError, KeyError) as exc:
            print(f"  Attempt {attempt}/{max_retries} — parse error: {exc}")
            if attempt == max_retries:
                raise RuntimeError(
                    f"Model did not return valid process JSON after {max_retries} attempts"
                ) from exc
    raise RuntimeError("unreachable")


def _validate_process_json(data: dict) -> None:
    """Raise KeyError / ValueError if required fields are missing."""
    if "lanes" not in data or not isinstance(data["lanes"], list):
        raise KeyError("Missing 'lanes' array")
    for lane in data["lanes"]:
        for key in ("id", "name", "elements"):
            if key not in lane:
                raise KeyError(f"Lane missing '{key}'")
    # Check at least one startEvent exists
    all_types = [
        el["type"] for lane in data["lanes"] for el in lane.get("elements", [])
    ]
    if "startEvent" not in all_types:
        raise ValueError("No startEvent found in extracted process")


# ─────────────────────────────────────────────────────────────────────────────
# BPMN XML builder  (mirrors the pattern from arbitration_bpmn_hf.py)
# ─────────────────────────────────────────────────────────────────────────────

NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
NS_DI = "http://www.omg.org/spec/BPMN/20100524/DI"
NS_DC = "http://www.omg.org/spec/DD/20100524/DC"
NS_BPMNDI = "http://www.omg.org/spec/BPMN/20100524/DI"

ET.register_namespace("", NS)
ET.register_namespace("bpmndi", NS_BPMNDI)
ET.register_namespace("dc", NS_DC)
ET.register_namespace("di", NS_DI)


class BpmnXmlBuilder:
    """Convert extracted process JSON → BPMN 2.0 XML string."""

    ELEM_W = 120
    ELEM_H = 60
    LANE_H = 160
    LANE_W = 900
    X_START = 80
    X_STEP = 160

    def __init__(self, process_data: dict) -> None:
        self.data = process_data
        self.proc_id = "proc_" + uuid.uuid4().hex[:8]

    def build(self) -> str:
        root = ET.Element(
            f"{{{NS}}}definitions",
            {
                "id": "definitions_" + uuid.uuid4().hex[:6],
                "targetNamespace": "http://bpmn.io/schema/bpmn",
            },
        )

        process = ET.SubElement(
            root,
            f"{{{NS}}}process",
            {
                "id": self.proc_id,
                "name": self.data.get("process_name", "Dispute Process"),
                "isExecutable": "false",
            },
        )

        collab_id = "collab_" + uuid.uuid4().hex[:6]
        collab = ET.SubElement(root, f"{{{NS}}}collaboration", {"id": collab_id})
        _ = ET.SubElement(
            collab,
            f"{{{NS}}}participant",
            {
                "id": "participant_main",
                "name": self.data.get("process_name", "Dispute Process"),
                "processRef": self.proc_id,
            },
        )

        # Build swimlanes
        lane_set = ET.SubElement(
            process, f"{{{NS}}}laneSet", {"id": "laneset_" + uuid.uuid4().hex[:6]}
        )

        all_elem_ids: set[str] = set()
        elem_lane_y: dict[str, int] = {}  # elem_id → y centre
        elem_x: dict[str, int] = {}  # elem_id → x centre

        for lane_idx, lane in enumerate(self.data["lanes"]):
            lane_node = ET.SubElement(
                lane_set,
                f"{{{NS}}}lane",
                {
                    "id": lane["id"],
                    "name": lane["name"],
                },
            )
            y_centre = lane_idx * self.LANE_H + self.LANE_H // 2

            for elem_idx, elem in enumerate(lane["elements"]):
                eid = elem["id"]
                all_elem_ids.add(eid)
                elem_lane_y[eid] = y_centre
                elem_x[eid] = self.X_START + elem_idx * self.X_STEP
                ET.SubElement(lane_node, f"{{{NS}}}flowNodeRef").text = eid

        # Emit flow elements and sequence flows
        flow_edges: list[tuple[str, str]] = []
        for lane in self.data["lanes"]:
            for elem in lane["elements"]:
                eid = elem["id"]
                etype = elem.get("type", "task")
                name = elem.get("name", "")

                tag = {
                    "startEvent": f"{{{NS}}}startEvent",
                    "endEvent": f"{{{NS}}}endEvent",
                    "task": f"{{{NS}}}task",
                    "exclusiveGateway": f"{{{NS}}}exclusiveGateway",
                    "parallelGateway": f"{{{NS}}}parallelGateway",
                }.get(etype, f"{{{NS}}}task")

                el_node = ET.SubElement(process, tag, {"id": eid, "name": name})

                for target_id in elem.get("outgoing", []):
                    if target_id not in all_elem_ids:
                        continue  # skip dangling refs
                    flow_id = f"flow_{eid}_{target_id}"
                    ET.SubElement(
                        process,
                        f"{{{NS}}}sequenceFlow",
                        {
                            "id": flow_id,
                            "sourceRef": eid,
                            "targetRef": target_id,
                        },
                    )
                    ET.SubElement(el_node, f"{{{NS}}}outgoing").text = flow_id
                    flow_edges.append((eid, target_id))

        # BPMN DI (diagram interchange)
        diagram = ET.SubElement(
            root, f"{{{NS_BPMNDI}}}BPMNDiagram", {"id": "diagram_1"}
        )
        plane = ET.SubElement(
            diagram,
            f"{{{NS_BPMNDI}}}BPMNPlane",
            {
                "id": "plane_1",
                "bpmnElement": collab_id,
            },
        )

        # Participant shape
        total_h = len(self.data["lanes"]) * self.LANE_H
        self._shape(
            plane,
            "participant_main",
            20,
            20,
            self.LANE_W + 100,
            total_h,
            is_horizontal=True,
        )

        # Lane shapes
        for lane_idx, lane in enumerate(self.data["lanes"]):
            self._shape(
                plane,
                lane["id"],
                60,
                20 + lane_idx * self.LANE_H,
                self.LANE_W + 60,
                self.LANE_H,
            )

        # Element shapes
        for lane_idx, lane in enumerate(self.data["lanes"]):
            for elem_idx, elem in enumerate(lane["elements"]):
                eid = elem["id"]
                x = 100 + self.X_START + elem_idx * self.X_STEP
                y = 20 + lane_idx * self.LANE_H + (self.LANE_H - self.ELEM_H) // 2
                self._shape(plane, eid, x, y, self.ELEM_W, self.ELEM_H)

        # Edge waypoints
        for src, tgt in flow_edges:
            flow_id = f"flow_{src}_{tgt}"
            edge = ET.SubElement(
                plane,
                f"{{{NS_BPMNDI}}}BPMNEdge",
                {
                    "id": f"edge_{flow_id}",
                    "bpmnElement": flow_id,
                },
            )
            # Simple straight-line waypoints
            for eid in (src, tgt):
                lane_idx = next(
                    i
                    for i, ln in enumerate(self.data["lanes"])
                    if any(e["id"] == eid for e in ln["elements"])
                )
                elem_idx = next(
                    i
                    for i, e in enumerate(self.data["lanes"][lane_idx]["elements"])
                    if e["id"] == eid
                )
                wx = 100 + self.X_START + elem_idx * self.X_STEP + self.ELEM_W // 2
                wy = 20 + lane_idx * self.LANE_H + self.LANE_H // 2
                ET.SubElement(
                    edge, f"{{{NS_DC}}}waypoint", {"x": str(wx), "y": str(wy)}
                )

        raw_xml = ET.tostring(root, encoding="unicode")
        return minidom.parseString(raw_xml).toprettyxml(indent="  ")

    def _shape(
        self,
        parent: ET.Element,
        elem_id: str,
        x: int,
        y: int,
        w: int,
        h: int,
        is_horizontal: bool = False,
    ) -> None:
        attrs: dict[str, str] = {"id": f"shape_{elem_id}", "bpmnElement": elem_id}
        if is_horizontal:
            attrs["isHorizontal"] = "true"
        shape = ET.SubElement(parent, f"{{{NS_BPMNDI}}}BPMNShape", attrs)
        ET.SubElement(
            shape,
            f"{{{NS_DC}}}Bounds",
            {"x": str(x), "y": str(y), "width": str(w), "height": str(h)},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Per-document pipeline
# ─────────────────────────────────────────────────────────────────────────────


def process_document(
    loader: Gemma4Loader,
    text: str,
    stem: str,
    venue: str,
    output_dir: Path,
    dry_run: bool,
) -> None:
    lanes = LANE_PRESETS.get(venue, LANE_PRESETS["generic"])
    print(f"[{stem}] Extracting process structure (venue={venue}) ...")

    proc_data = extract_process(loader, text, venue, lanes)

    if dry_run:
        print(json.dumps(proc_data, indent=2))
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    # Save raw JSON
    json_path = output_dir / f"{stem}_process.json"
    json_path.write_text(json.dumps(proc_data, indent=2))
    print(f"[{stem}] Saved process JSON → {json_path}")

    # Build and save BPMN XML
    builder = BpmnXmlBuilder(proc_data)
    xml_str = builder.build()
    bpmn_path = output_dir / f"{stem}.bpmn"
    bpmn_path.write_text(xml_str, encoding="utf-8")
    print(f"[{stem}] Saved BPMN XML     → {bpmn_path}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate BPMN diagrams from Wikipedia dispute text via Gemma 4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--text", metavar="FILE", help="Path to a plain-text dispute document"
    )
    src.add_argument(
        "--arb",
        metavar="CASE",
        help="Wikipedia ARB case title (fetches from Wikipedia API)",
    )
    src.add_argument(
        "--batch",
        metavar="DIR",
        help="Process all *.txt files in DIR",
    )

    p.add_argument(
        "--model-dir",
        default=None,
        metavar="DIR",
        help=(
            "Path to downloaded Gemma 4 weights.  "
            "Falls back to MODEL_DIR env var, then "
            + DEFAULT_MODEL_ID
            + " (Hub download)"
        ),
    )
    p.add_argument(
        "--venue",
        default="generic",
        choices=list(LANE_PRESETS.keys()),
        help="Dispute venue — determines default swimlane names (default: generic)",
    )
    p.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        metavar="DIR",
        help=f"Output directory for .bpmn and .json files (default: {DEFAULT_OUTPUT_DIR})",
    )
    p.add_argument(
        "--quantize",
        choices=["4bit", "8bit"],
        default=None,
        help="Load model with bitsandbytes quantization (reduces VRAM)",
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_NEW_TOKENS,
        help=f"Max new tokens for generation (default: {DEFAULT_MAX_NEW_TOKENS})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print extracted JSON to stdout; do not write BPMN files",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if not TRANSFORMERS_AVAILABLE:
        print("ERROR: transformers/torch not installed.  Aborting.")
        sys.exit(1)

    # Resolve model path
    model_dir = (
        args.model_dir
        or os.environ.get("MODEL_DIR")  # set in SLURM script
        or DEFAULT_MODEL_ID  # HuggingFace Hub fallback
    )
    loader = Gemma4Loader(model_dir=model_dir, quantize=args.quantize)
    output_dir = Path(args.output_dir)

    if args.text:
        text = Path(args.text).read_text(encoding="utf-8")
        stem = Path(args.text).stem
        process_document(loader, text, stem, args.venue, output_dir, args.dry_run)

    elif args.arb:
        # Lazy import — pywikibot is a project dep but may not be set up locally
        try:
            import pywikibot  # type: ignore[import-untyped]

            site = pywikibot.Site("en", "wikipedia")
            page = pywikibot.Page(site, args.arb)
            text = page.text
        except Exception as exc:
            print(f"ERROR fetching '{args.arb}' from Wikipedia: {exc}")
            sys.exit(1)
        stem = re.sub(r"[^\w]+", "_", args.arb)[:60]
        process_document(loader, text, stem, "arb", output_dir, args.dry_run)

    elif args.batch:
        batch_dir = Path(args.batch)
        txt_files = sorted(batch_dir.glob("*.txt"))
        if not txt_files:
            print(f"No *.txt files found in {batch_dir}")
            sys.exit(1)
        print(f"Batch: {len(txt_files)} files in {batch_dir}\n")
        for f in txt_files:
            text = f.read_text(encoding="utf-8")
            process_document(loader, text, f.stem, args.venue, output_dir, args.dry_run)


if __name__ == "__main__":
    main()
