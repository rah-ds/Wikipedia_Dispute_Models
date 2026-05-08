#!/usr/bin/env python3
"""
gemma4_bpmn.py — BPMN diagram generator for Wikipedia dispute resolution

Supports three venues, each with its own extraction recipe and lane layout:
  • ArbCom (--arb)         — Wikipedia Arbitration Committee cases
  • DRN    (--drn)         — Dispute Resolution Noticeboard cases
  • RFC    (--rfc)         — Request for Comment discussions

Two complementary pipelines in one script:

  (A) Per-case extraction — ingests ONE case from any venue and emits:
        • <case>_case.json   — structured extraction (with a `venue` field)
        • <case>.bpmn        — BPMN 2.0 XML (open in bpmn.io / Camunda)
        • <case>.svg         — vector diagram (no browser needed)
        • <case>.png         — raster diagram (if cairosvg installed)

  (B) Aggregate analysis — ingests a directory of *_case.json files and
      emits ONE corpus-level diagram. Aggregation is per-venue:
        • --aggregate DIR        → arbcom_aggregate_workflow.svg
        • --aggregate-drn DIR    → drn_aggregate_workflow.svg
        • --aggregate-rfc DIR    → rfc_aggregate_workflow.svg
      Each command filters the input directory by the `venue` field, so
      ARB / DRN / RFC JSONs can be mixed in one folder safely.

Hybrid per-case pipeline (same shape across all 3 venues)
---------------------------------------------------------
  Phase 1 (deterministic) — Regex extraction of venue-agnostic facts:
    rule invocations, namespace link distribution. ARB also parses dates,
    parties, vote tallies, section counts, outcome classification.

  Phase 2 (LLM) — Gemma multi-pass extraction:
    • ArbCom — 5 passes (principles, findings, remedies, lifecycle, arbs)
    • DRN    — 3 passes (parties, discussion, closure)
    • RFC    — 3 passes (proposal, votes, closure)

  Phase 3 (assembly) — Venue-specific BPMN builder emits BPMN 2.0 XML with
    DI coordinates. A pure-Python SVG renderer converts the BPMN to SVG
    using the DI coordinates directly (no browser required).

Per-case input modes (choose exactly one)
-----------------------------------------
  --text FILE          Plain-text / wikitext file. Use --text-venue to
                       choose which venue's extraction recipe to apply.
  --arb CASE           Fetch ArbCom case from Wikipedia by title — pulls
                       the main case page plus all subpages (/Evidence,
                       /Workshop, /Proposed_decision, /Enforcement_log,
                       etc.) so the full lifecycle is captured.
  --drn CASE           Fetch a DRN case. Use either a full archive page
                       title ("Wikipedia:Dispute_resolution_noticeboard/
                       Archive_233") or a specific section by anchor
                       ("Archive_233#Talk:Tetris").
  --drn-archive N      Fetch every case section from DRN Archive N at
                       once. ~30 cases per archive.
  --rfc PAGE           Fetch an RFC. Most live on article talk pages as
                       a section ("Talk:Article#RfC_question") and a few
                       in Wikipedia: namespace.
  --json FILE          Pre-scraped ARB JSON (legacy bpmn_from_arb format)
  --batch DIR          Process all *.txt files in a directory.

Aggregate input modes (each builds ONE corpus-level diagram)
------------------------------------------------------------
  --aggregate     DIR  ArbCom corpus from all *_case.json files
  --aggregate-drn DIR  DRN corpus from DRN-tagged *_case.json files
  --aggregate-rfc DIR  RFC corpus from RFC-tagged *_case.json files

  All three are venue-filtered, so dropping ARB / DRN / RFC JSONs in
  one folder and running each command is safe — only the right subset
  is consumed. Aggregate modes do NOT call Gemma; runs in milliseconds.

Model options (ignored in any --aggregate mode)
-----------------------------------------------
  --model-dir DIR      Gemma model path or HuggingFace ID
                       (default: $MODEL_DIR env var, or google/gemma-3-4b-it)
  --quantize MODE      Load with bitsandbytes quantization to reduce VRAM.
                         4bit — ~7 GB VRAM for gemma-3-12b-it
                         8bit — ~14 GB VRAM for gemma-3-12b-it
                       Requires: pip install bitsandbytes
  --max-new-tokens N   Cap on generated tokens per LLM pass (default 2048).
  --no-llm             Skip Gemma — regex-only pipeline.
                       Useful for smoke-testing without a GPU.

Output options
--------------
  --output-dir DIR     Where to save artifact files
                       (default: artifacts/bpmn/gemma4)
  --simple-lanes       Use the 4-lane ARB layout (Requesting Party /
                       Clerk / Arbitrators / Enforcement) instead of the
                       6-lane default. ARB only — DRN and RFC have their
                       own fixed lane layouts.
  --text-venue VENUE   With --text or --batch, which venue's extraction
                       recipe to use. One of: arb, drn, rfc.
                       Default: arb.  (Ignored for --arb / --drn / --rfc
                       which set the venue automatically.)
  --dry-run            Print extracted case JSON to stdout; write no files.

Fetch options (only used with --arb)
------------------------------------
  --no-subpages        Fetch only the main case page (faster, but misses
                       principle/finding/remedy votes which live on the
                       /Proposed_decision subpage).

Batch options (only used with --json / --batch / --drn-archive)
---------------------------------------------------------------
  --max-cases N        Process at most N cases from the input.

Typical workflows
-----------------

  # ArbCom workflow — fetch + aggregate
  python scripts/gemma4_bpmn.py \\
      --arb "Wikipedia:Arbitration/Requests/Case/A Man In Black" \\
      --output-dir artifacts/cases/
  python scripts/gemma4_bpmn.py \\
      --arb "Wikipedia:Arbitration/Requests/Case/Abortion" \\
      --output-dir artifacts/cases/
  python scripts/gemma4_bpmn.py \\
      --aggregate artifacts/cases/ --output-dir artifacts/

  # DRN workflow — entire archive at once + aggregate
  python scripts/gemma4_bpmn.py \\
      --drn-archive 233 --max-cases 5 \\
      --output-dir artifacts/drn/
  python scripts/gemma4_bpmn.py \\
      --aggregate-drn artifacts/drn/ --output-dir artifacts/

  # RFC workflow — specific RFC section + aggregate
  python scripts/gemma4_bpmn.py \\
      --rfc "Talk:Climate_change#RfC_about_lead_section" \\
      --output-dir artifacts/rfc/
  python scripts/gemma4_bpmn.py \\
      --aggregate-rfc artifacts/rfc/ --output-dir artifacts/

More usage examples
-------------------
  # Use the larger 12b model with 4-bit quantization (better extraction)
  python scripts/gemma4_bpmn.py \\
      --arb "Wikipedia:Arbitration/Requests/Case/Abortion" \\
      --model-dir google/gemma-3-12b-it --quantize 4bit

  # Regex-only smoke test (no GPU, no Gemma download)
  python scripts/gemma4_bpmn.py --text case.txt --no-llm

  # Process a saved DRN case from disk
  python scripts/gemma4_bpmn.py --text my_drn_case.txt --text-venue drn

  # Batch-process scraped JSON, cap at 5 cases
  python scripts/gemma4_bpmn.py --json arb_part_1.json --max-cases 5

  Input size is handled automatically — the script reads the model's
  context window AND your GPU's VRAM and sends the largest input that
  fits, falling back to smaller chunks on CUDA OOM. No manual flag
  required.

Output artifacts per case
-------------------------
  artifacts/cases/
    Wikipedia_..._Abortion_case.json   ← structured extraction (always)
    Wikipedia_..._Abortion.bpmn        ← BPMN 2.0 XML (always)
    Wikipedia_..._Abortion.svg         ← vector diagram (always)
    Wikipedia_..._Abortion.png         ← raster (if cairosvg installed)

Output artifacts per aggregate
------------------------------
  artifacts/
    arbcom_aggregate_workflow.svg     ← from --aggregate
    drn_aggregate_workflow.svg        ← from --aggregate-drn
    rfc_aggregate_workflow.svg        ← from --aggregate-rfc
    *.png                             ← raster (if cairosvg installed)

Finding cases to process
------------------------
  ARB cases — listed at https://en.wikipedia.org/wiki/Wikipedia:Arbitration/
              Index/Cases. Pass the full title with the
              "Wikipedia:Arbitration/Requests/Case/" prefix.

  DRN cases — find archive numbers at https://en.wikipedia.org/wiki/
              Wikipedia:Dispute_resolution_noticeboard/Archive_index.
              Use --drn-archive N for batch, or browse a specific
              archive page in your browser to find a case section
              and pass it via --drn "Page#Section_anchor".

  RFCs     — currently-active RFCs are listed at https://en.wikipedia.org/
              wiki/Wikipedia:Requests_for_comment/All. Closed historical
              RFCs are NOT centrally indexed — you'll need to know which
              talk page they lived on. Talk-page archives often contain
              multiple RFCs; pass the section anchor for the specific one.

Requirements
------------
  # Core (needed for any LLM extraction)
  pip install transformers torch accelerate huggingface_hub

  # Gemma license acceptance — visit the model page in a browser and accept:
  #   https://huggingface.co/google/gemma-3-4b-it
  #   (or the model size you chose via --model-dir)
  # Then authenticate once in your shell:
  #   hf auth login   # paste an hf_... token from huggingface.co/settings/tokens

  # Optional extras
  pip install bitsandbytes  # only for --quantize
  pip install pywikibot     # only for --arb / --drn / --drn-archive / --rfc
  pip install cairosvg      # enables .png output alongside .svg (no sudo needed)

  # Optional alternative PNG renderer (higher quality, requires Node.js +
  # Chromium system libraries — if cairosvg is installed this is not
  # necessary):
  #   npm install -g bpmn-to-image

  # Without any PNG renderer, the .bpmn and .svg are still produced —
  # both are viewable in any modern browser or vector editor.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import uuid
from collections import defaultdict
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
        "         (use --no-llm to run the regex-only pipeline)\n"
    )

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MODEL_ID = "google/gemma-3-4b-it"  # ~8 GB; use 12b or 27b for higher quality
DEFAULT_OUTPUT_DIR = Path("artifacts/bpmn/gemma4")
DEFAULT_MAX_NEW_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.2
# Input budget is computed automatically from the model's context window.
# See _compute_char_budget() — no manual --max-input-chars flag needed.

# Conservative overhead assumptions for budget calculation:
CHARS_PER_TOKEN = 3.5  # English tokenizer ratio, erring on the safe side
PROMPT_OVERHEAD_TOKENS = 800  # system + instruction boilerplate per pass

# Extended ARB lanes — more granular than bpmn_from_arb.py's 4 lanes.
# Each lane maps to a real role in the ArbCom process.
ARB_LANES_DETAILED = [
    "Requesting Party",
    "Other Editors",
    "Clerk",
    "Drafting Arbitrators",
    "Full Committee",
    "Enforcement",
]

# The classic 4-lane layout from bpmn_from_arb.py — simpler but less detailed.
ARB_LANES_SIMPLE = ["Requesting Party", "Clerk", "Arbitrators", "Enforcement"]

# DRN lanes — reflects the actual roles in DRN's volunteer-mediated process.
# Source: WP:DRN, WP:DRN/Volunteering. DRN has no formal voting or enforcement;
# the volunteer mediator's role is to facilitate, not adjudicate.
DRN_LANES = [
    "Filing Party",
    "Other Parties",
    "Volunteer Mediator",
    "Closer",  # Often the same person as the mediator, but conceptually distinct
]

# RFC lanes — reflects the open community-discussion model. There is no
# central process role; the closer (uninvolved editor or admin) reads the
# discussion and writes a closing summary determining consensus.
RFC_LANES = [
    "Proposer",
    "Participants",  # Editors who !vote support / oppose / neutral
    "Closer",  # Uninvolved editor / admin who reads consensus
]

# ─────────────────────────────────────────────────────────────────────────────
# Gemma prompts — multi-pass extraction
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert analyst of Wikipedia's arbitration process. You read
    raw ARB case text and extract structured data about principles, findings
    of fact, proposed remedies, motions, votes, and enforcement actions.

    Output ONLY valid JSON. No prose. No markdown fences. No comments.
    Follow the requested schema exactly. If a field is unknown leave it
    as an empty string or empty list.
""")

# Pass 1 — Principles
PROMPT_PRINCIPLES = textwrap.dedent("""\
    Extract every Proposed Principle from the arbitration case below.
    A Principle is a statement of Wikipedia policy the committee relies on
    (e.g. "Neutral point of view", "Edit warring", "Administrator conduct").

    Output JSON:
    {{
      "principles": [
        {{
          "name": "<short title, max 10 words>",
          "summary": "<one-sentence summary of the principle>",
          "policy_refs": ["WP:NPOV", "WP:3RR", ...],
          "support": <int or 0>,
          "oppose": <int or 0>,
          "abstain": <int or 0>,
          "passed": true or false
        }}
      ]
    }}

    --- CASE TEXT ---
    {text}
    --- END ---

    JSON:
""")

# Pass 2 — Findings of fact
PROMPT_FINDINGS = textwrap.dedent("""\
    Extract every Proposed Finding of Fact from the arbitration case below.
    A Finding identifies conduct by a specific editor (e.g.
    "User X engaged in edit warring on article Y").

    Output JSON:
    {{
      "findings": [
        {{
          "name": "<short title, max 10 words>",
          "target_editor": "<username the finding is about, or empty>",
          "conduct": "<what they did — 1 sentence>",
          "evidence_refs": ["<diff or evidence description>", ...],
          "policy_refs": ["WP:...", ...],
          "support": <int or 0>,
          "oppose": <int or 0>,
          "abstain": <int or 0>,
          "passed": true or false
        }}
      ]
    }}

    --- CASE TEXT ---
    {text}
    --- END ---

    JSON:
""")

# Pass 3 — Remedies
PROMPT_REMEDIES = textwrap.dedent("""\
    Extract every Proposed Remedy from the arbitration case below.
    Classify each remedy's type and target, noting whether the remedy
    creates an ongoing state (like a contentious topic designation) or
    a suspended/conditional sanction that can be triggered later.

    Output JSON:
    {{
      "remedies": [
        {{
          "name": "<short title, max 10 words>",
          "target_editor": "<username sanctioned, or empty>",
          "target_article": "<article sanctioned, or empty>",
          "target_topic": "<topic area sanctioned, e.g. 'Arab-Israeli conflict', or empty>",
          "sanction_type": "<short lowercase classification — prefer one of: warning, admonishment, topic_ban, site_ban, block, desysop, probation, revert_restriction, interaction_ban, contentious_topic, discretionary_sanctions, article_protection — but use a new lowercase underscore_separated label if none of these fit>",
          "duration": "<e.g. '1 year', 'indefinite', 'permanent', empty>",
          "scope": "<e.g. 'articles related to X', empty>",
          "suspended": true if the remedy is suspended/conditional (triggerable later at ARCA), else false,
          "ongoing": true if the remedy creates a perpetual ongoing state (contentious topic, indefinite topic ban, discretionary sanctions in an area), else false,
          "support": <int or 0>,
          "oppose": <int or 0>,
          "abstain": <int or 0>,
          "passed": true or false
        }}
      ]
    }}

    --- CASE TEXT ---
    {text}
    --- END ---

    JSON:
""")

# Pass 4 — Enforcement, amendments, appeals — the post-case lifecycle
PROMPT_ENFORCEMENT = textwrap.dedent("""\
    Extract every BEFORE-CASE and AFTER-CASE lifecycle event mentioned in
    the arbitration case text below. Include:
      - Pre-case emergency actions (blocks, bans, or other ArbCom actions
        taken BEFORE the case was formally opened)
      - Enforcement actions (blocks, unblocks, AE reports, topic-ban
        enforcement) that happened AFTER the case closed
      - Amendment requests filed after the case (to modify remedies)
      - Clarification requests (to interpret remedies)
      - Appeals (by the sanctioned editor or on their behalf)
      - Standalone motions passed by ArbCom AFTER the case closed that
        modify this case's remedies (distinct from motions voted on
        DURING the case — those are already in 'remedies')

    For each event extract dates when available. These are LIFECYCLE EVENTS
    we want to track chronologically.

    Output JSON:
    {{
      "pre_case_actions": [
        {{
          "date": "<YYYY-MM-DD or empty>",
          "action": "<block, ban, interim sanction, etc.>",
          "target_editor": "<username, or empty>",
          "reason": "<short reason, or empty>"
        }}
      ],
      "enforcement_actions": [
        {{
          "date": "<YYYY-MM-DD or empty>",
          "action": "<block, unblock, AE report, warning, etc.>",
          "target_editor": "<username, or empty>",
          "admin": "<acting admin, or empty>",
          "outcome": "<upheld, declined, overturned, pending, or empty>"
        }}
      ],
      "amendments": [
        {{
          "date": "<YYYY-MM-DD or empty>",
          "requester": "<username, or empty>",
          "subject": "<which remedy or principle is being amended>",
          "change": "<what change is being proposed>",
          "outcome": "<passed, declined, withdrawn, pending, or empty>"
        }}
      ],
      "clarifications": [
        {{
          "date": "<YYYY-MM-DD or empty>",
          "requester": "<username, or empty>",
          "question": "<what clarification is sought>",
          "outcome": "<clarified, declined, pending, or empty>"
        }}
      ],
      "appeals": [
        {{
          "date": "<YYYY-MM-DD or empty>",
          "requester": "<username, or empty>",
          "subject": "<what's being appealed>",
          "outcome": "<granted, declined, pending, or empty>"
        }}
      ],
      "post_case_motions": [
        {{
          "date": "<YYYY-MM-DD or empty>",
          "motion": "<short description of the standalone motion>",
          "vote": "<e.g. '10-0-1' for support-oppose-abstain, or empty>",
          "outcome": "<passed, failed, withdrawn, or empty>"
        }}
      ]
    }}

    --- CASE TEXT ---
    {text}
    --- END ---

    JSON:
""")

# Pass 5 — Arbitrator identity and roles
PROMPT_ARBITRATORS = textwrap.dedent("""\
    Extract the named arbitrators involved in this case, with their roles.

    Output JSON:
    {{
      "drafting_arbitrators": ["<username>", ...],
      "recused_arbitrators": ["<username>", ...],
      "inactive_arbitrators": ["<username>", ...],
      "trainee_clerks": ["<username>", ...],
      "clerks": ["<username>", ...]
    }}

    --- CASE TEXT ---
    {text}
    --- END ---

    JSON:
""")


# ─────────────────────────────────────────────────────────────────────────────
# DRN-specific prompts (Dispute Resolution Noticeboard — content disputes)
# ─────────────────────────────────────────────────────────────────────────────
#
# DRN cases have a totally different shape from ArbCom cases:
#   - No formal voting; volunteers mediate to consensus
#   - No findings of fact, no remedies, no enforcement
#   - Outcomes are closure types: resolved / failed / closed (unsuitable)
#   - Key data: filing party, other parties, volunteer mediator(s),
#     content question being disputed, closing reason

DRN_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert analyst of Wikipedia's Dispute Resolution Noticeboard
    (DRN) process. You read raw DRN case text and extract structured data
    about the parties, the article(s) being disputed, the volunteer
    mediator's facilitation, and the case closure.

    Output ONLY valid JSON. No prose. No markdown fences. No comments.
    Follow the requested schema exactly. If a field is unknown leave it
    as an empty string or empty list.
""")

DRN_PROMPT_PARTIES = textwrap.dedent("""\
    Extract the parties and dispute subject from this DRN case.
    Output JSON in this exact shape:
    {{
      "filing_party": "<username of editor who opened the case>",
      "other_parties": ["<username>", ...],
      "article_subject": "<article or page being disputed>",
      "talk_page_url": "<url of the talk-page discussion that led here, or empty>",
      "dispute_summary": "<1-2 sentence summary of the content disagreement>",
      "filing_date": "<YYYY-MM-DD if extractable, else free-form>"
    }}

    DRN case text:
    --- START ---
    {text}
    --- END ---

    JSON:
""")

DRN_PROMPT_DISCUSSION = textwrap.dedent("""\
    Extract the moderated-discussion structure from this DRN case.
    Output JSON in this exact shape:
    {{
      "volunteer_mediators": ["<username>", ...],
      "opening_statements": [
        {{"editor": "<username>", "summary": "<1-2 sentence position>"}}
      ],
      "discussion_phases": [
        "<short label for each phase the mediator framed, e.g. 'first opening statements', 'discuss source X', 'compromise text proposal'>"
      ],
      "compromise_proposed": true if any compromise text or solution was floated,
      "compromise_accepted": true if all parties agreed to the compromise,
      "off_topic_warnings": <integer count of times the mediator warned about conduct/off-topic>,
      "policies_discussed": ["WP:NPOV", "WP:RS", ...]
    }}

    DRN case text:
    --- START ---
    {text}
    --- END ---

    JSON:
""")

DRN_PROMPT_CLOSURE = textwrap.dedent("""\
    Extract the closure / outcome of this DRN case.
    Output JSON in this exact shape:
    {{
      "closure_type": "<one of: resolved | failed | closed-unsuitable | withdrawn | bot-archived | premature | unknown>",
      "closer": "<username, or empty>",
      "closure_reason": "<the reason given in the archive top template, or empty>",
      "closure_date": "<YYYY-MM-DD if extractable, else free-form>",
      "next_venue_recommended": "<RFC | Mediation | ANI | None | (other), if the closer recommended escalation>",
      "duration_days": <integer if extractable, else 0>
    }}

    Closure conventions used at DRN:
      - resolved: parties reached agreement
      - failed: process attempted but stalled or one party refused to engage
      - closed-unsuitable: case was outside DRN scope from the start
      - withdrawn: filer pulled the request
      - bot-archived: 14 days elapsed with no progress, EarwigBot auto-closed
      - premature: insufficient prior talk-page discussion

    DRN case text:
    --- START ---
    {text}
    --- END ---

    JSON:
""")


# ─────────────────────────────────────────────────────────────────────────────
# RFC-specific prompts (Request for Comment — community consensus on a question)
# ─────────────────────────────────────────────────────────────────────────────
#
# RFCs are open community discussions with structured !votes:
#   - Proposer asks a yes/no/multi-option question
#   - Editors !vote Support / Oppose / Neutral with rationales
#   - 30-day default duration (auto-handled by Legobot)
#   - Uninvolved editor or admin reads the discussion and writes a
#     closing summary stating consensus
#
# RFC outcomes are nuanced — closers often write rough consensus / no
# consensus / strong consensus determinations rather than a binary count.

RFC_SYSTEM_PROMPT = textwrap.dedent("""\
    You are an expert analyst of Wikipedia's Request for Comment (RFC)
    process. You read raw RFC discussion text (proposer's question,
    !votes, threaded discussion, closer's summary) and extract structured
    data about the proposal, the participation, and the outcome.

    Output ONLY valid JSON. No prose. No markdown fences. No comments.
    Follow the requested schema exactly. If a field is unknown leave it
    as an empty string or empty list.
""")

RFC_PROMPT_PROPOSAL = textwrap.dedent("""\
    Extract the proposal that opened this RFC.
    Output JSON in this exact shape:
    {{
      "proposer": "<username>",
      "rfc_id": "<the RFC id assigned by Legobot, e.g. '2A1B3C4', or empty>",
      "page": "<page or article on which the RFC sits>",
      "proposal_question": "<the exact question the proposer asked, paraphrased to one sentence>",
      "proposal_options": ["<option label>", ...],
      "rfc_categories": ["<category tag the proposer chose, e.g. 'policy', 'biography', 'science'>", ...],
      "open_date": "<YYYY-MM-DD if extractable, else free-form>",
      "policies_invoked": ["WP:NPOV", "WP:RS", ...]
    }}

    RFC text:
    --- START ---
    {text}
    --- END ---

    JSON:
""")

RFC_PROMPT_VOTES = textwrap.dedent("""\
    Extract the !votes and discussion structure from this RFC.
    Output JSON in this exact shape:
    {{
      "support_count": <integer>,
      "oppose_count": <integer>,
      "neutral_count": <integer>,
      "alternative_count": <integer of editors who proposed an alternative>,
      "support_voters": ["<username>", ...],
      "oppose_voters": ["<username>", ...],
      "key_arguments_for": ["<short summary>", ...],
      "key_arguments_against": ["<short summary>", ...],
      "uninvolved_voters": <integer of clearly-uninvolved editors who weighed in>,
      "involved_voters": <integer of editors clearly involved with the underlying topic>
    }}

    Treat any line starting with bolded "Support", "Oppose", or "Neutral"
    (or *'''Support''' / *'''Oppose''' wikitext) as a !vote. The numeric
    counts must reflect what actually appears in the text, not assumptions.

    RFC text:
    --- START ---
    {text}
    --- END ---

    JSON:
""")

RFC_PROMPT_CLOSURE = textwrap.dedent("""\
    Extract the closing of this RFC.
    Output JSON in this exact shape:
    {{
      "closer": "<username, or empty>",
      "closer_is_admin": true if the closer is identified as an admin / sysop,
      "consensus_finding": "<one of: strong-consensus-support | rough-consensus-support | no-consensus | rough-consensus-oppose | strong-consensus-oppose | withdrawn | speedy-close | unknown>",
      "closing_summary": "<2-3 sentence paraphrase of the closer's reasoning>",
      "close_date": "<YYYY-MM-DD if extractable, else free-form>",
      "duration_days": <integer if extractable, else 0>,
      "appealed": true if the close was challenged at Wikipedia:Administrators' noticeboard or similar,
      "next_actions": "<what the closer instructed should happen, e.g. 'implement the change', 'no action', 'discuss further'>"
    }}

    RFC text:
    --- START ---
    {text}
    --- END ---

    JSON:
""")


# ─────────────────────────────────────────────────────────────────────────────
# Venue registry — single source of truth for ARB / DRN / RFC differences.
# Adding a new venue = adding one entry to this dict.
# ─────────────────────────────────────────────────────────────────────────────
#
# Each entry pairs the venue's identity (label, lane layout) with its
# extraction recipe (system prompt + ordered list of pass prompts). The
# regex extractors are venue-agnostic (rule invocations, namespaces,
# etc.) so they're not in here.

VENUES = {
    "arb": {
        "label": "ArbCom",
        "lanes_detailed": ARB_LANES_DETAILED,
        "lanes_simple": ARB_LANES_SIMPLE,
        "url_prefix": "Wikipedia:Arbitration/Requests/Case/",
        "system_prompt": SYSTEM_PROMPT,
        "passes": [
            ("principles", "PROMPT_PRINCIPLES"),
            ("findings", "PROMPT_FINDINGS"),
            ("remedies", "PROMPT_REMEDIES"),
            ("lifecycle", "PROMPT_LIFECYCLE"),
            ("arbitrators", "PROMPT_ARBITRATORS"),
        ],
    },
    "drn": {
        "label": "DRN",
        "lanes_detailed": DRN_LANES,
        "lanes_simple": DRN_LANES,  # DRN has no "simple" variant
        "url_prefix": "Wikipedia:Dispute_resolution_noticeboard",
        "system_prompt": DRN_SYSTEM_PROMPT,
        "passes": [
            ("parties", "DRN_PROMPT_PARTIES"),
            ("discussion", "DRN_PROMPT_DISCUSSION"),
            ("closure", "DRN_PROMPT_CLOSURE"),
        ],
    },
    "rfc": {
        "label": "RFC",
        "lanes_detailed": RFC_LANES,
        "lanes_simple": RFC_LANES,
        "url_prefix": "Wikipedia:Requests_for_comment/",  # may also be talk-page based
        "system_prompt": RFC_SYSTEM_PROMPT,
        "passes": [
            ("proposal", "RFC_PROMPT_PROPOSAL"),
            ("votes", "RFC_PROMPT_VOTES"),
            ("closure", "RFC_PROMPT_CLOSURE"),
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic regex parsers  (ported from bpmn_from_arb.py, plus venue-
# agnostic helpers for rule invocations and namespace links)
# ─────────────────────────────────────────────────────────────────────────────


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


def _count_accept_votes(content: str) -> tuple[int, int, int, int]:
    """Parse arbitrator votes. Returns (accept, decline, recuse, abstain)."""
    vote_summary = re.search(
        r"Arbitrators['\u2019]?\s*opinions?\s*on\s*hearing.*?\((\d+)/(\d+)/(\d+)",
        content,
        re.I,
    )
    if vote_summary:
        # Older vote format: accept/decline/recuse only
        abstain_from_summary = re.search(
            r"Arbitrators['\u2019]?\s*opinions?\s*on\s*hearing.*?"
            r"\(\d+/\d+/\d+/(\d+)",
            content,
            re.I,
        )
        abstain = int(abstain_from_summary.group(1)) if abstain_from_summary else 0
        return (
            int(vote_summary.group(1)),
            int(vote_summary.group(2)),
            int(vote_summary.group(3)),
            abstain,
        )
    prelim_section = re.search(
        r"(?:Preliminary decision|Arbitrators['\u2019]?\s*opinion)"
        r"(.*?)(?:=\s*(?:Final|Temporary)|\Z)",
        content,
        re.I | re.DOTALL,
    )
    if not prelim_section:
        return (0, 0, 0, 0)
    section = prelim_section.group(1)
    return (
        len(re.findall(r"\bAccept\b", section, re.I)),
        len(re.findall(r"\bDecline\b", section, re.I)),
        len(re.findall(r"\bRecuse\b", section, re.I)),
        len(re.findall(r"\bAbstain\b", section, re.I)),
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


def _extract_section(content: str, section_re: str) -> str:
    """Return the text of a section, or empty string."""
    m = re.search(section_re, content, re.I | re.DOTALL)
    return m.group(1) if m else ""


def _extract_remedies_raw(content: str) -> list[str]:
    """Extract remedy names from the Remedies section (regex baseline)."""
    remedies: list[str] = []
    text = _extract_section(
        content,
        r"==+\s*(?:Proposed\s+)?Remedies\s*==+"
        r"(.*?)(?:\n==+\s*(?:Proposed\s+)?(?:Enforcement|Clerk)|$)",
    )
    if not text:
        return remedies
    headers = re.findall(r"===+\s*(.+?)\s*===+", text)
    skip_kw = {"enforcement", "log of blocks", "clerk"}
    for h in headers:
        clean = re.sub(r"\[\[.*?\||\]\]|\{\{.*?\}\}", "", h).strip()
        if clean and len(clean) > 2 and clean.lower() not in skip_kw:
            remedies.append(clean)
    return remedies


def _extract_principles_raw(content: str) -> list[str]:
    """Extract principle names from the Principles section (regex baseline)."""
    text = _extract_section(
        content,
        r"==+\s*(?:Proposed\s+)?Principles\s*==+"
        r"(.*?)(?:\n==+\s*(?:Proposed\s+)?(?:Findings|Remedies)|\Z)",
    )
    if not text:
        return []
    return [
        re.sub(r"\[\[.*?\||\]\]|\{\{.*?\}\}", "", h).strip()
        for h in re.findall(r"===+\s*(.+?)\s*===+", text)
    ]


def _extract_findings_raw(content: str) -> list[str]:
    """Extract finding names from the Findings section (regex baseline)."""
    text = _extract_section(
        content,
        r"==+\s*(?:Proposed\s+)?Findings\s*(?:of\s*[Ff]act)?\s*==+"
        r"(.*?)(?:\n==+\s*(?:Proposed\s+)?Remedies|\Z)",
    )
    if not text:
        return []
    return [
        re.sub(r"\[\[.*?\||\]\]|\{\{.*?\}\}", "", h).strip()
        for h in re.findall(r"===+\s*(.+?)\s*===+", text)
    ]


# Keyword hints for outcome classification. NOT a gatekeeper — these are
# substrings checked (case-insensitive) against remedy text to label an
# overall case outcome. Add keywords as new sanction patterns emerge.
HEAVY_SANCTION_KEYWORDS: set[str] = {
    "ban",
    "block",
    "probation",
    "parole",
    "desysop",
    "restrict",
    "revert",
    "topic ban",
    "indefinite",
}
LIGHT_SANCTION_KEYWORDS: set[str] = {
    "admonish",
    "warn",
}


def _classify_outcome(content: str, remedies: list[str]) -> str:
    """Classify case outcome using keyword heuristics.

    Returns one of: 'Declined', 'Closed - No Decision', 'Remedies Imposed',
    or 'Admonishment Only'. Heavy sanction keywords (bans, blocks, etc.)
    beat light ones; empty remedy lists go to 'Closed - No Decision'.
    """
    has_final = bool(re.search(r"=\s*Final\s+decision\s*=", content, re.I))
    if not has_final:
        if re.search(r"\bDecline[d]?\b", content[:3000], re.I):
            return "Declined"
        return "Closed - No Decision"
    if not remedies:
        return "Closed - No Decision"
    remedy_text = " ".join(remedies).lower()
    if any(kw in remedy_text for kw in HEAVY_SANCTION_KEYWORDS):
        return "Remedies Imposed"
    if any(kw in remedy_text for kw in LIGHT_SANCTION_KEYWORDS):
        return "Admonishment Only"
    return "Remedies Imposed"


# Case-type detection rules. Each entry maps a case_type label to a list of
# keyword groups; matching is case-insensitive. A case matches a type if
# ANY keyword group matches (with all its conjunctive parts present).
# First match wins, so order matters. Default is 'conduct'.
#
# Example: to add a new case type, append a new entry:
#     "unblock_request": [["unblock", "appeal"]]
CASE_TYPE_RULES: list[tuple[str, list[list[str]]]] = [
    ("appeal", [["appeal"], ["appeal of"]]),
    ("desysop", [["desysop"], ["removal of permissions"], ["admin tools"]]),
    ("access_approval", [["checkuser", "access"], ["oversight", "access"]]),
    ("procedural", [["banning policy"]]),
]


def _detect_case_type(title: str, content: str) -> str:
    """Classify the type of ArbCom request — conduct, appeal, desysop, etc.

    Matches keywords from CASE_TYPE_RULES against the title and the first
    ~3K chars of content. First match wins; default is 'conduct'.
    """
    haystack = ((title or "") + " " + (content or "")[:3000]).lower()
    for case_type, keyword_groups in CASE_TYPE_RULES:
        for group in keyword_groups:
            if all(kw in haystack for kw in group):
                return case_type
    return "conduct"


# Phrase markers suggesting a case was handled privately (off-wiki).
# Module-level set — extend to catch new wording patterns as they emerge.
PRIVATE_CASE_MARKERS: set[str] = {
    "case was conducted privately",
    "conducted via private",
    "heard privately",
    "resolved privately",
    "private case",
}


def _detect_private_case(title: str, content: str) -> bool:
    """Detect if this is a private case (no public case page, or announcement-only).

    Returns True if title contains 'private', content is very short (<600 chars
    suggests announcement-only), or any PRIVATE_CASE_MARKERS phrase appears.
    """
    if "private" in (title or "").lower():
        return True
    if not content or len(content.strip()) < 600:
        return True
    c = content.lower()
    for marker in PRIVATE_CASE_MARKERS:
        if marker in c:
            return True
    return False


def _extract_drafting_arbitrators(content: str) -> list[str]:
    """Extract names of drafting arbitrators from a case page."""
    # Common patterns: "drafting arbitrators will be X, Y, and Z"
    #                  "Drafters: X, Y, Z"
    #                  "drafter(s): X and Y"
    names: list[str] = []
    patterns = [
        r"drafting\s+arbitrators?\s+(?:will\s+be|are|:)\s*([^.\n]+?)(?:\.|\n)",
        r"drafters?\s*[:—-]\s*([^.\n]+?)(?:\.|\n)",
        r"drafted\s+by\s+([^.\n]+?)(?:\.|\n)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, content, re.I):
            chunk = m.group(1)
            # Split on commas, 'and', '&'
            for name in re.split(r",|\band\b|&", chunk):
                name = name.strip(" []|").split("(")[0].strip()
                if name and 2 <= len(name) <= 40 and name.lower() not in names:
                    names.append(name)
    return names[:10]


# Words that look like capitalized names but aren't — used to filter
# false positives in _extract_recused_arbitrators. Extend as needed.
_NAME_STOPWORDS: set[str] = {
    "I",
    "You",
    "We",
    "They",
    "He",
    "She",
    "It",
    "While",
    "If",
    "When",
    "As",
    "Since",
    "Because",
    "Although",
    "This",
    "That",
    "These",
    "Those",
    "The",
    "A",
    "An",
    "Note",
    "Also",
    "However",
    "Additionally",
    "Further",
    "Moreover",
    "My",
    "Our",
    "Their",
    "His",
    "Her",
    "Me",
    "Us",
    "Them",
    "Him",
    "Arbitrator",
    "Arbitrators",
    "Admin",
    "Administrator",
    "Clerk",
    "User",
    "Editor",
    "Editors",
}


def _extract_recused_arbitrators(content: str) -> list[str]:
    """Extract names of arbitrators who recused themselves.

    Uses two signal patterns:
      1. An explicit "Recused: X, Y, Z" header line.
      2. Inline "Username recused" or "Username has recused" — but only
         matches a SINGLE word (no whitespace) or a two-word alpha phrase
         to avoid slurping "I am", "While Jclemens is", etc.

    Filters _NAME_STOPWORDS to drop common sentence-starters and pronouns.
    """
    names: list[str] = []

    def _accept(candidate: str) -> bool:
        candidate = candidate.strip(" []|.,;:")
        if not candidate:
            return False
        if len(candidate) > 40 or len(candidate) < 2:
            return False
        if candidate in _NAME_STOPWORDS:
            return False
        # Username-like token: either a single capitalized word, or two
        # tokens where the first looks like a name (e.g. "Worm That Turned")
        # Reject anything with lowercase "is", "am", "was" etc. as a token
        tokens = candidate.split()
        if len(tokens) > 4:  # too long to be a username
            return False
        if any(t.lower() in {"is", "am", "was", "will", "has", "have"} for t in tokens):
            return False
        if candidate.lower() in {n.lower() for n in names}:
            return False
        return True

    # Pattern 1: inline mentions. Require the captured name to be either:
    #   - a single non-whitespace username (up to 30 chars), OR
    #   - multi-word but ≤ 3 words of all-alphabetic tokens
    # The negative lookbehind avoids matching inside words.
    inline_pattern = re.compile(
        r"(?<![A-Za-z])([A-Z][A-Za-z0-9_\-.]{1,29}(?:\s+[A-Z][A-Za-z0-9_\-.]{1,29}){0,2})"
        r"\s+(?:has\s+)?recused?\b",
    )
    for m in inline_pattern.finditer(content):
        candidate = m.group(1).strip()
        if _accept(candidate):
            names.append(candidate)

    # Pattern 2: explicit header
    m = re.search(r"Recused\s*[:—-]\s*([^.\n]+?)(?:\.|\n)", content, re.I)
    if m:
        for raw in re.split(r",|\band\b|&", m.group(1)):
            candidate = raw.strip(" []|").split("(")[0].strip()
            if _accept(candidate):
                names.append(candidate)

    return names[:10]


def _extract_pre_case_actions(content: str) -> list[dict]:
    """Scan for emergency ArbCom actions taken before the case opened."""
    actions: list[dict] = []
    # Patterns: "was already banned", "pre-case", "emergency block"
    for m in re.finditer(
        r"(?:pre-?case|prior\s+to\s+the\s+case|already\s+banned|"
        r"emergency\s+(?:block|ban|desysop))"
        r"[^.\n]{0,150}",
        content,
        re.I,
    ):
        snippet = m.group(0).strip()[:180]
        if snippet:
            actions.append(
                {"date": "", "action": snippet, "target_editor": "", "reason": ""}
            )
    return actions[:5]


# ─────────────────────────────────────────────────────────────────────────────
# Rule-invocation tracking (policy refs + namespace-aware link analysis)
# ─────────────────────────────────────────────────────────────────────────────

# Classification hints — NOT gatekeepers. Any WP:X shortcut encountered is
# extracted regardless of whether it appears here. These sets only control
# the `type` tag attached to each rule in the output JSON. New or obscure
# shortcuts get classified as "other" automatically — they are still
# counted, still summarized, still visible in the top_rules list.
#
# Source for the initial lists:
#   https://en.wikipedia.org/wiki/Wikipedia:List_of_policies_and_guidelines
# These can be edited, extended, or loaded from an external JSON file
# without affecting what the extractor detects — only how it labels things.

CORE_POLICIES: set[str] = {
    "NPOV",
    "V",
    "NOR",
    "BLP",
    "COPYVIO",
    "CIVIL",
    "NPA",
    "HA",
    "NLT",
    "VANDAL",
    "EDITWAR",
    "3RR",
    "CONSENSUS",
    "OUTING",
    "HARASS",
    "ADMIN",
    "INVOLVED",
    "DELETION",
    "NOT",
    "NOTHERE",
    "SOCK",
    "NAC",
    "ARBPOL",
    "ACDS",
    "AEBLOCK",
    "BANPOL",
    "BLOCKP",
    "CTOP",
    "ARBECR",
}
GUIDELINES: set[str] = {
    "RS",
    "CITE",
    "N",
    "GNG",
    "OR",
    "SYNTH",
    "UNDUE",
    "FRINGE",
    "MEDRS",
    "BRD",
    "DR",
    "COI",
    "PAID",
    "SPA",
    "CANVAS",
    "BATTLEGROUND",
    "AGF",
    "DE",
    "TE",
    "OWN",
    "IDHT",
    "GAME",
    "DIVA",
    "CIR",
    "COMPETENCE",
    "ARBCOM",
    "RFC",
    "CONLEVEL",
}
ESSAYS: set[str] = {
    "BOOMERANG",
    "SNOW",
    "IAR",
    "COMMON",
    "CRYSTAL",
    "BITE",
    "DICK",
    "RANDY",
    "NOTAFORUM",
    "POINT",
    "LAWYER",
}

# Namespace name → human-readable meaning. NOT a gatekeeper — namespaces
# detected in source text that are NOT in this dict are still tracked;
# they get a generic meaning string ("(unclassified namespace)") rather
# than being dropped. Add entries here to give new namespaces semantic
# descriptions in the output.
NAMESPACE_MEANINGS: dict[str, str] = {
    "User": "editor conduct — personal user page evidence",
    "User_talk": "editor conduct — user-talk-page discussions",
    "Talk": "article talk — content discussion evidence",
    "Wikipedia": "policy / guideline / process reference",
    "Wikipedia_talk": "policy / guideline / process discussion",
    "File": "file / image content evidence",
    "File_talk": "file / image content discussion",
    "Template": "template-usage evidence",
    "Template_talk": "template-usage discussion",
    "Category": "category / taxonomy evidence",
    "Category_talk": "category / taxonomy discussion",
    "Help": "help / documentation reference",
    "Help_talk": "help / documentation discussion",
    "Special": "special-page / log evidence",
    "Portal": "portal evidence",
    "Portal_talk": "portal discussion",
    "Draft": "draft-namespace evidence",
    "Draft_talk": "draft-namespace discussion",
    "MediaWiki": "software interface reference",
    "MediaWiki_talk": "software interface discussion",
    "Module": "Lua module evidence",
    "Module_talk": "Lua module discussion",
    "Book": "book-namespace evidence",
    "Book_talk": "book-namespace discussion",
    "TimedText": "caption / subtitle evidence",
    "Main": "article content evidence",
}


def _classify_rule(ref: str) -> str:
    """Classify a policy shortcut as 'policy', 'guideline', 'essay', or 'other'."""
    # Strip WP: prefix, uppercase for matching
    key = ref.upper().replace("WP:", "").replace("WIKIPEDIA:", "").strip()
    if key in CORE_POLICIES:
        return "policy"
    if key in GUIDELINES:
        return "guideline"
    if key in ESSAYS:
        return "essay"
    return "other"


def _extract_rule_invocations(content: str) -> dict:
    """
    Scan the case text for rule/policy invocations. Returns a structured
    summary with per-rule counts, namespace-aware link stats, and
    per-section distribution.

    DESIGN: this function does NOT gate extraction on any known list. It
    discovers every WP:X shortcut and every [[Namespace:...]] link by
    pattern, then classifies using optional hints. New, recent, or obscure
    rules are detected and reported even if they aren't in our hint sets.
    """
    # Match WP: / Wikipedia: shortcuts in three common forms. Accepts any
    # uppercase shortcut of 2-21 chars — classification happens later and
    # doesn't filter anything out.
    shortcut_patterns = [
        r"\[\[(?:WP|Wikipedia):([A-Z][A-Z0-9_/-]*)(?:[|\]])",
        r"\{\{(?:policy|guideline|essay)\s*\|\s*([A-Z][A-Z0-9_/-]*)\s*[|}]",
        r"(?<![A-Za-z0-9])WP:([A-Z][A-Z0-9]{1,20})\b",
    ]
    counts: dict[str, int] = {}
    for pat in shortcut_patterns:
        for m in re.finditer(pat, content):
            key = "WP:" + m.group(1).upper()
            counts[key] = counts.get(key, 0) + 1

    # ── Namespace-aware link detection (discovery-based) ────────────────────
    # Instead of locking to a fixed list, we discover every capitalized
    # namespace prefix that appears in [[Foo:Bar]] or [[Foo talk:Bar]]
    # style links. Unknown namespaces still get tracked — they just fall
    # back to a generic meaning string later.
    #
    # NOTE: "WP" and "Wikipedia" links are counted separately in the rule
    # invocations above, so we skip them here to avoid double-counting.
    namespace_counts: dict[str, int] = {}
    ns_generic_pattern = re.compile(r"\[\[([A-Z][A-Za-z]+(?:[ _][A-Za-z]+)?):[^\]|]+")
    for m in ns_generic_pattern.finditer(content):
        ns = m.group(1).replace(" ", "_")
        # Skip WP / Wikipedia namespaces — those are counted as rule invocations
        if ns in ("WP", "Wikipedia", "Wikipedia_talk"):
            continue
        if len(ns) <= 30 and ns[0].isupper():
            namespace_counts[ns] = namespace_counts.get(ns, 0) + 1

    # Links with no namespace prefix are article-space (Main)
    total_links = len(re.findall(r"\[\[[^\]]+\]\]", content))
    prefixed_links = sum(namespace_counts.values())
    article_links = max(total_links - prefixed_links, 0)
    if article_links:
        namespace_counts["Main"] = article_links

    # ── Per-section distribution ────────────────────────────────────────────
    # Which section was each rule FIRST invoked in?
    first_section: dict[str, str] = {}
    section_markers = [
        ("Evidence", r"==\s*Evidence\s*=="),
        ("Workshop", r"==\s*Workshop|==\s*Proposed\s+"),
        ("Proposed_decision", r"==\s*(?:Proposed\s+)?(?:Principles|Findings|Remedies)"),
        ("Final_decision", r"=\s*Final\s+decision\s*="),
    ]
    section_spans: list[tuple[str, int]] = []
    for name, marker in section_markers:
        m = re.search(marker, content, re.I)
        if m:
            section_spans.append((name, m.start()))
    section_spans.sort(key=lambda x: x[1])

    def _which_section(offset: int) -> str:
        current = "Preamble"
        for name, start in section_spans:
            if offset >= start:
                current = name
            else:
                break
        return current

    for pat in shortcut_patterns:
        for m in re.finditer(pat, content):
            key = "WP:" + m.group(1).upper()
            if key not in first_section:
                first_section[key] = _which_section(m.start())

    # ── Build the result ────────────────────────────────────────────────────
    top_rules: list[dict] = []
    for ref, count in sorted(counts.items(), key=lambda x: -x[1]):
        top_rules.append(
            {
                "ref": ref,
                "count": count,
                "type": _classify_rule(ref),
                "first_section": first_section.get(ref, ""),
            }
        )

    type_counts = {"policy": 0, "guideline": 0, "essay": 0, "other": 0}
    for r in top_rules:
        type_counts[r["type"]] += r["count"]

    # Namespace summary — look up meaning, fall back to generic label for
    # any namespace not in NAMESPACE_MEANINGS. No namespace gets silently
    # dropped.
    namespaces: list[dict] = []
    for ns, n in sorted(namespace_counts.items(), key=lambda x: -x[1]):
        namespaces.append(
            {
                "namespace": ns,
                "count": n,
                "meaning": NAMESPACE_MEANINGS.get(ns, "(unclassified namespace)"),
            }
        )

    return {
        "total_invocations": sum(counts.values()),
        "unique_rules": len(counts),
        "by_type": type_counts,
        "top_rules": top_rules,  # full list, sorted by count
        "namespace_links": namespaces,  # namespaces sorted by link count
    }


def parse_arb_case_deterministic(content: str, title: str = "") -> dict:
    """
    Extract structured BPMN-relevant fields from raw ARB case text using
    only regex (no LLM). Mirrors parse_arb_case from bpmn_from_arb.py but
    adds case-type detection, private-case detection, arbitrator role
    identification, pre-case actions, and the "4 net votes" accept rule.
    """
    short_title = re.sub(
        r"^(?:Wikipedia:)?(?:Requests?\s+for\s+arbitration"
        r"|Arbitration/Requests/Case)/",
        "",
        title,
        flags=re.I,
    ).strip()

    opened = _extract_date(content, r"Case\s+Opened.*?on\s+(.+?)(?:\n|<)")
    closed = _extract_date(content, r"Case\s+Closed.*?on\s+(.+?)(?:\n|<)")
    parties = _extract_involved_parties(content)
    accept_n, decline_n, recuse_n, abstain_n = _count_accept_votes(content)
    principles_raw = _extract_principles_raw(content)
    findings_raw = _extract_findings_raw(content)
    remedies_raw = _extract_remedies_raw(content)
    has_injunction = bool(
        re.search(r"Temporary\s+injunction(?!\s*\(none\))", content, re.I)
        and not re.search(r"Temporary\s+injunction\s*\(none\)", content, re.I)
    )
    outcome = _classify_outcome(content, remedies_raw)
    case_type = _detect_case_type(title, content)
    is_private = _detect_private_case(title, content)
    drafting_arbs = _extract_drafting_arbitrators(content)
    recused_arbs = _extract_recused_arbitrators(content)
    pre_case_actions = _extract_pre_case_actions(content)
    rule_invocations = _extract_rule_invocations(content)

    # "4 net votes OR majority" accept rule per Wikipedia:Arbitration/Requests/Case/Header
    net_votes = accept_n - decline_n
    has_majority = accept_n > (decline_n + recuse_n)
    accepted_by_rule = net_votes >= 4 or has_majority

    # Build a Wikipedia URL for the case so BPMN documentation can link back
    case_url = ""
    if title:
        url_title = title.replace(" ", "_")
        case_url = f"https://en.wikipedia.org/wiki/{url_title}"

    return {
        "title": short_title or title,
        "case_url": case_url,
        "case_type": case_type,
        "is_private": is_private,
        "opened_date": opened,
        "closed_date": closed,
        "parties": parties,
        "accept_votes": accept_n,
        "decline_votes": decline_n,
        "recuse_votes": recuse_n,
        "abstain_votes": abstain_n,
        "net_votes": net_votes,
        "accepted_by_rule": accepted_by_rule,
        "has_injunction": has_injunction,
        "drafting_arbitrators": drafting_arbs,
        "recused_arbitrators": recused_arbs,
        "pre_case_actions": pre_case_actions,
        "rule_invocations": rule_invocations,
        "principles_raw": principles_raw,
        "findings_raw": findings_raw,
        "remedies_raw": remedies_raw,
        "outcome": outcome,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Swimlane BPMN 2.0 XML Builder  (ported from bpmn_from_arb.py)
# ─────────────────────────────────────────────────────────────────────────────

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
_STEP_GAP = 170
_FIRST_X = _POOL_X + _POOL_HEADER_W + 80


class SwimlaneBpmnBuilder:
    """
    Build BPMN 2.0 XML with a collaboration pool containing swimlanes.
    Supports documentation blocks on elements for rich per-node metadata.
    """

    def __init__(self, process_name: str, lanes: list[str]):
        self.process_name = process_name
        self.lanes = lanes
        self._lane_ids = {name: "Lane_" + uuid.uuid4().hex[:8] for name in lanes}
        self._collab_id = "Collab_" + uuid.uuid4().hex[:8]
        self._part_id = "Participant_" + uuid.uuid4().hex[:8]
        self._proc_id = "Process_" + uuid.uuid4().hex[:8]
        # (eid, label, elem_type, lane_name, step, documentation)
        self._elements: list[tuple[str, str, str, str, int, str]] = []
        # (fid, source_id, target_id, label)
        self._flows: list[tuple[str, str, str, str]] = []
        # Per-lane step counters so elements don't overlap horizontally
        self._lane_steps: dict[str, int] = {lane: 0 for lane in lanes}
        # Global step for cross-lane ordering
        self._global_step = 0
        # Track which elements carry a loop marker (ongoing / never-ending)
        self._loop_elements: set[str] = set()

    def _add(self, label: str, etype: str, lane: str, documentation: str = "") -> str:
        if lane not in self._lane_ids:
            raise ValueError(f"Unknown lane: {lane!r}. Lanes: {self.lanes}")
        eid = (
            etype[:6].replace("Event", "Evt").replace("Gatew", "GW_")
            + "_"
            + uuid.uuid4().hex[:8]
        )
        self._elements.append(
            (eid, label, etype, lane, self._global_step, documentation)
        )
        self._global_step += 1
        self._lane_steps[lane] = self._lane_steps.get(lane, 0) + 1
        return eid

    def start(self, label: str, lane: str, doc: str = "") -> str:
        return self._add(label, "startEvent", lane, doc)

    def end(self, label: str, lane: str, doc: str = "") -> str:
        return self._add(label, "endEvent", lane, doc)

    def task(
        self,
        label: str,
        lane: str,
        user: bool = False,
        doc: str = "",
        loop: bool = False,
    ) -> str:
        """Add a task. Set loop=True to mark an ongoing/never-ending task
        (renders as a loop marker in bpmn.io, i.e. the ↻ symbol)."""
        eid = self._add(label, "userTask" if user else "task", lane, doc)
        if loop:
            self._loop_elements.add(eid)
        return eid

    def gateway(
        self, label: str, lane: str, exclusive: bool = True, doc: str = ""
    ) -> str:
        return self._add(
            label,
            "exclusiveGateway" if exclusive else "parallelGateway",
            lane,
            doc,
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
                "exporter": "Gemma4-ARB-BPMN-Generator",
                "exporterVersion": "3.0",
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
            process,
            f"{{{_NS_BPMN}}}laneSet",
            {"id": "LS_" + uuid.uuid4().hex[:8]},
        )
        for lane_name in self.lanes:
            lane_el = ET.SubElement(
                lane_set,
                f"{{{_NS_BPMN}}}lane",
                {"id": self._lane_ids[lane_name], "name": lane_name},
            )
            for eid, _lbl, _et, elane, _step, _doc in self._elements:
                if elane == lane_name:
                    ET.SubElement(lane_el, f"{{{_NS_BPMN}}}flowNodeRef").text = eid

        incoming: dict[str, list[str]] = defaultdict(list)
        outgoing: dict[str, list[str]] = defaultdict(list)
        for fid, src, tgt, _lbl in self._flows:
            outgoing[src].append(fid)
            incoming[tgt].append(fid)

        for eid, label, etype, _lane, _step, doc in self._elements:
            el = ET.SubElement(
                process, f"{{{_NS_BPMN}}}{etype}", {"id": eid, "name": label}
            )
            if doc:
                d = ET.SubElement(el, f"{{{_NS_BPMN}}}documentation")
                d.text = doc
            # Loop marker for ongoing/never-ending tasks (BPMN standardLoopCharacteristics
            # renders as the ↻ loop symbol in bpmn.io / Camunda Modeler)
            if eid in self._loop_elements and etype in ("task", "userTask"):
                ET.SubElement(el, f"{{{_NS_BPMN}}}standardLoopCharacteristics")
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
            root,
            f"{{{_NS_BPMNDI}}}BPMNDiagram",
            {"id": "Diag_" + uuid.uuid4().hex[:8]},
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
        for eid, _label, etype, lane, step, _doc in self._elements:
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
                {"x": str(x), "y": str(y), "width": str(w), "height": str(h)},
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

        # Pre-count outgoing edges per source so we can vertically stagger
        # the label of each fan-out branch. Without staggering, all branch
        # labels of "gateway → N end events" land at the same Y because
        # their midpoints share the same Y.
        outgoing_counts: dict[str, int] = {}
        for _fid, src, _tgt, _lbl in self._flows:
            outgoing_counts[src] = outgoing_counts.get(src, 0) + 1
        # Per-source running index, incremented as we emit each edge from that source
        outgoing_seen: dict[str, int] = {}

        for fid, src, tgt, label in self._flows:
            edge = ET.SubElement(
                plane,
                f"{{{_NS_BPMNDI}}}BPMNEdge",
                {"id": fid + "_di", "bpmnElement": fid},
            )
            sx, sy, sw, sh = bounds_cache.get(src, (0, 0, 0, 0))
            tx, ty, tw, th = bounds_cache.get(tgt, (0, 0, 0, 0))
            if label:
                le = ET.SubElement(edge, f"{{{_NS_BPMNDI}}}BPMNLabel")
                # Default label position: midpoint of source and target
                base_x = (sx + sw / 2 + tx + tw / 2) / 2 - 20
                base_y = (sy + sh / 2 + ty + th / 2) / 2 - 10
                # If this source fans out to multiple edges, stagger this
                # label vertically by 18px per sibling so they don't stack.
                # The center of the stack stays at base_y.
                n_out = outgoing_counts.get(src, 1)
                if n_out > 1:
                    idx = outgoing_seen.get(src, 0)
                    outgoing_seen[src] = idx + 1
                    stagger = (idx - (n_out - 1) / 2) * 18
                    base_y += stagger
                ET.SubElement(
                    le,
                    f"{{{_NS_DC}}}Bounds",
                    {
                        "x": str(int(base_x)),
                        "y": str(int(base_y)),
                        "width": "60",
                        "height": "20",
                    },
                )
            ET.SubElement(
                edge,
                f"{{{_NS_DI}}}waypoint",
                {"x": str(sx + sw), "y": str(int(sy + sh / 2))},
            )
            ET.SubElement(
                edge,
                f"{{{_NS_DI}}}waypoint",
                {"x": str(tx), "y": str(int(ty + th / 2))},
            )

        xml_str = ET.tostring(root, encoding="unicode")
        return minidom.parseString(xml_str).toprettyxml(indent="  ")


# ─────────────────────────────────────────────────────────────────────────────
# Gemma loader
# ─────────────────────────────────────────────────────────────────────────────


class Gemma4Loader:
    """Load Gemma with optional quantization; handle CPU fallback."""

    def __init__(self, model_dir: str | Path, quantize: str | None = None) -> None:
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
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        except Exception as exc:
            self._raise_friendly_load_error(model_path, exc)

        print(
            f"Loading model (quantize={quantize or 'none'}, device_map={device_map}) ..."
        )
        # bfloat16 > float16 for inference stability, especially when
        # device_map="auto" spills parts of the model to CPU/disk. With
        # float16, offloaded layers can produce inf/nan in probabilities
        # during sampling → CUDA assertion crash.
        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        try:
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                device_map=device_map,
                dtype=dtype,
                quantization_config=bnb_config,
            )
        except TypeError:
            # Older transformers versions use torch_dtype= instead of dtype=
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                device_map=device_map,
                torch_dtype=dtype,
                quantization_config=bnb_config,
            )
        except Exception as exc:
            self._raise_friendly_load_error(model_path, exc)
        self.model.eval()

        # Detect offloading — if part of the model is on CPU/disk, warn the
        # user and recommend 4-bit quantization.
        device_types = set()
        try:
            for p in self.model.parameters():
                device_types.add(p.device.type)
        except Exception:
            pass
        if "meta" in device_types or ("cpu" in device_types and "cuda" in device_types):
            print(
                "\n" + "!" * 72 + "\n"
                "WARNING: model is split across GPU and CPU/disk.\n"
                "This MAY cause 'inf/nan' sampling errors mid-generation.\n"
                "\n"
                "If you hit a CUDA assert during generate(), rerun with:\n"
                "    --quantize 4bit\n"
                "or try a smaller model like google/gemma-3-4b-it.\n" + "!" * 72 + "\n"
            )

        print("Model loaded.\n")

    @staticmethod
    def _raise_friendly_load_error(model_path: str, exc: Exception) -> None:
        """Turn opaque HF errors into a clear, actionable message."""
        msg = str(exc)
        is_auth_error = any(
            s in msg
            for s in (
                "401",
                "Unauthorized",
                "RepositoryNotFoundError",
                "not a valid model identifier",
                "gated",
            )
        )
        if is_auth_error:
            sys.stderr.write(
                "\n" + "=" * 72 + "\n"
                f"ERROR: Could not load '{model_path}'.\n"
                "\n"
                "Gemma models are GATED on HuggingFace — you must:\n"
                "  1. Visit the model page in a browser and accept the license:\n"
                f"     https://huggingface.co/{model_path}\n"
                "  2. Create an access token at https://huggingface.co/settings/tokens\n"
                "  3. Authenticate in this shell:   hf auth login\n"
                "     (or export HF_TOKEN=hf_xxx   before running the script)\n"
                "\n"
                "Valid Gemma 3 instruction-tuned model IDs:\n"
                "  google/gemma-3-1b-it   (smallest, ~2 GB, text-only,  32K ctx)\n"
                "  google/gemma-3-4b-it   (~8 GB, multimodal,          128K ctx)  [default]\n"
                "  google/gemma-3-12b-it  (~24 GB, multimodal,         128K ctx)\n"
                "  google/gemma-3-27b-it  (~54 GB, multimodal,         128K ctx)\n"
                "\n"
                "NOTE: 'google/gemma-3-9b-it' does NOT exist.\n"
                "\n"
                "Alternatives that don't require HF gating acceptance:\n"
                "  mistralai/Mistral-7B-Instruct-v0.3\n"
                "  Qwen/Qwen2.5-7B-Instruct   (gate-free, similar quality)\n"
                "\n"
                "To skip the LLM entirely and use the regex-only pipeline:\n"
                "  python scripts/gemma4_bpmn_revised.py --no-llm  [other args]\n"
                + "=" * 72
                + "\n"
            )
            sys.exit(1)
        # Non-auth error — re-raise to preserve the original trace
        raise exc

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> str:
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        # Build a kwargs dict so we can fall back to greedy if sampling crashes
        gen_kwargs = {
            **inputs,
            "max_new_tokens": max_new_tokens,
            "pad_token_id": self.tokenizer.eos_token_id,
        }
        if temperature > 0:
            gen_kwargs.update(
                do_sample=True,
                temperature=temperature,
                top_p=0.95,  # top_p filter catches most inf/nan before multinomial
            )
        else:
            gen_kwargs["do_sample"] = False

        with torch.no_grad():
            try:
                output_ids = self.model.generate(**gen_kwargs)
            except RuntimeError as exc:
                # A CUDA assertion or inf/nan during sampling — retry greedy.
                # Greedy uses argmax so it can't hit the multinomial assertion.
                if (
                    "inf" in str(exc).lower()
                    or "nan" in str(exc).lower()
                    or "device-side assert" in str(exc).lower()
                    or "multinomial" in str(exc).lower()
                ):
                    print(
                        "  [generate] sampling produced inf/nan — "
                        "retrying with greedy decoding"
                    )
                    gen_kwargs["do_sample"] = False
                    gen_kwargs.pop("temperature", None)
                    gen_kwargs.pop("top_p", None)
                    # Clear any leftover GPU error state before retrying
                    if torch.cuda.is_available():
                        torch.cuda.synchronize()
                    output_ids = self.model.generate(**gen_kwargs)
                else:
                    raise
        new_tokens = output_ids[0][inputs["input_ids"].shape[1] :]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True)


def _build_chat_prompt(system: str, user: str) -> str:
    """Gemma-style instruction prompt. Compatible with Gemma 2 / 3 / 4."""
    return (
        f"<start_of_turn>system\n{system}<end_of_turn>\n"
        f"<start_of_turn>user\n{user}<end_of_turn>\n"
        f"<start_of_turn>model\n"
    )


def _extract_json(raw: str) -> dict:
    """Pull the first valid JSON object out of the model's raw output."""
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
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


def _compute_char_budget(
    loader: Gemma4Loader | None,
    max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
) -> int:
    """
    Determine how many input characters we can feed per LLM pass.

    Two-sided budget:
      1. Model context window (declared max sequence length).
      2. Hardware-practical sequence length derived from available VRAM.

    The attention mask for sequence length N is roughly O(N²) in memory.
    A model's *declared* 128K context doesn't mean your 8 GB GPU can
    process 128K tokens in one pass — the attention matrices alone would
    dwarf the weights. We take the MIN of both ceilings so the pass
    actually runs instead of OOM'ing mid-generate.

    If no loader is provided (no-llm mode), returns a large sentinel.
    """
    if loader is None:
        return 10_000_000

    # ── 1) Model's declared context window ──────────────────────────────────
    max_ctx_tokens: int | None = None
    mml = getattr(loader.tokenizer, "model_max_length", None)
    if isinstance(mml, int) and 1024 <= mml <= 2_000_000:
        max_ctx_tokens = mml
    if max_ctx_tokens is None:
        cfg = getattr(loader.model, "config", None)
        candidate_attrs = (
            "max_position_embeddings",
            "n_positions",
            "seq_length",
            "max_sequence_length",
            "sliding_window",
        )
        for attr in candidate_attrs:
            val = getattr(cfg, attr, None) if cfg else None
            if isinstance(val, int) and 1024 <= val <= 2_000_000:
                max_ctx_tokens = val
                break
        if max_ctx_tokens is None and cfg is not None:
            text_cfg = getattr(cfg, "text_config", None)
            if text_cfg is not None:
                for attr in candidate_attrs:
                    val = getattr(text_cfg, attr, None)
                    if isinstance(val, int) and 1024 <= val <= 2_000_000:
                        max_ctx_tokens = val
                        break
    if max_ctx_tokens is None:
        max_ctx_tokens = 8192
        print("  [budget] no declared context window; assuming 8192 tokens")

    # ── 2) Hardware-practical sequence length ───────────────────────────────
    hw_seq_tokens = max_ctx_tokens  # default: trust the model
    if torch.cuda.is_available():
        try:
            # Use device 0's total memory as the ceiling, minus what's already
            # reserved by model weights. This is approximate but conservative.
            device = torch.cuda.current_device()
            total_vram = torch.cuda.get_device_properties(device).total_memory
            reserved = torch.cuda.memory_reserved(device)
            free_vram = max(total_vram - reserved, 512 * 1024 * 1024)

            # Attention memory scales roughly as:
            #   n_layers * n_heads * seq_len² * bytes_per_element
            # For Gemma 3 4b: ~26 layers, ~16 heads, bf16 (2 bytes).
            # This simplification bundles all the per-token overhead into a
            # single coefficient. Empirically ~600 bytes/token² for Gemma 3
            # family with sliding-window attention, headroom included.
            # seq_len = sqrt(free_vram / 600)
            import math

            practical_seq = int(math.sqrt(free_vram / 600))
            # Floor/ceiling to keep us in a sane range
            practical_seq = max(2048, min(practical_seq, max_ctx_tokens))
            hw_seq_tokens = practical_seq

            free_gb = free_vram / (1024**3)
            total_gb = total_vram / (1024**3)
            print(
                f"  [budget] GPU: {free_gb:.1f} GB free / {total_gb:.1f} GB total "
                f"→ practical seq length: {hw_seq_tokens:,} tokens"
            )
        except Exception as exc:
            print(f"  [budget] could not probe VRAM ({exc}); using declared ctx")

    # Take the tighter of the two limits
    effective_ctx = min(max_ctx_tokens, hw_seq_tokens)
    usable_tokens = effective_ctx - max_new_tokens - PROMPT_OVERHEAD_TOKENS
    usable_tokens = max(usable_tokens, 1024)
    budget_chars = int(usable_tokens * CHARS_PER_TOKEN)

    print(
        f"  [budget] model ctx: {max_ctx_tokens:,} | "
        f"hw-practical: {hw_seq_tokens:,} | "
        f"effective: {effective_ctx:,} tokens → "
        f"{budget_chars:,} input chars/pass "
        f"(reserving {max_new_tokens:,} output + {PROMPT_OVERHEAD_TOKENS} overhead)"
    )
    return budget_chars


def _run_pass(
    loader: Gemma4Loader,
    prompt_tmpl: str,
    text: str,
    max_input_chars: int,
    label: str,
    max_retries: int = 2,
) -> dict:
    """Run a single extraction pass with retries.

    Automatically uses min(len(text), max_input_chars) — so when the
    document is shorter than the model's window, we don't pad or
    artificially cap it, which keeps runtime down.

    On CUDA OOM, halves the input length and retries up to 3 times.
    This usually recovers because the attention mask scales as O(N²)
    in input length, so halving N uses ~25% of the previous memory.
    """
    effective_cap = min(len(text), max_input_chars)
    if effective_cap < len(text):
        print(
            f"    [{label}] truncating {len(text):,} → {effective_cap:,} chars "
            f"to fit model context"
        )
    else:
        print(f"    [{label}] sending full {len(text):,} chars")

    oom_shrinks_remaining = 3
    while True:
        user_msg = prompt_tmpl.format(text=text[:effective_cap])
        full_prompt = _build_chat_prompt(SYSTEM_PROMPT, user_msg)
        try:
            for attempt in range(1, max_retries + 1):
                raw = loader.generate(full_prompt)
                try:
                    return _extract_json(raw)
                except (ValueError, json.JSONDecodeError) as exc:
                    print(
                        f"    [{label}] attempt {attempt}/{max_retries} "
                        f"parse error: {exc}"
                    )
                    if attempt == max_retries:
                        print(
                            f"    [{label}] giving up parsing — "
                            "using empty result for this pass"
                        )
                        return {}
            return {}
        except torch.cuda.OutOfMemoryError:
            if oom_shrinks_remaining <= 0:
                print(
                    f"    [{label}] CUDA OOM and cannot shrink further — "
                    "returning empty result for this pass"
                )
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                return {}
            oom_shrinks_remaining -= 1
            new_cap = max(effective_cap // 2, 1500)
            print(
                f"    [{label}] CUDA OOM — halving input "
                f"{effective_cap:,} → {new_cap:,} chars and retrying "
                f"({oom_shrinks_remaining} shrinks remaining)"
            )
            effective_cap = new_cap
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            if new_cap == 1500:
                # Hit the floor — don't loop forever
                oom_shrinks_remaining = 0


# ─────────────────────────────────────────────────────────────────────────────
# Full multi-pass extraction
# ─────────────────────────────────────────────────────────────────────────────


def extract_detailed_case(
    loader: Gemma4Loader | None,
    content: str,
    title: str,
    max_input_chars: int,
) -> dict:
    """
    Build a rich case record combining deterministic regex + multi-pass LLM.
    When loader is None, falls back to regex-only output.
    """
    base = parse_arb_case_deterministic(content, title)

    if loader is None:
        print("  [no-llm] skipping Gemma passes")
        # Synthesize minimal LLM-style output from regex names
        base["principles"] = [
            {
                "name": n,
                "summary": "",
                "policy_refs": [],
                "support": 0,
                "oppose": 0,
                "abstain": 0,
                "passed": True,
            }
            for n in base["principles_raw"]
        ]
        base["findings"] = [
            {
                "name": n,
                "target_editor": "",
                "conduct": "",
                "evidence_refs": [],
                "policy_refs": [],
                "support": 0,
                "oppose": 0,
                "abstain": 0,
                "passed": True,
            }
            for n in base["findings_raw"]
        ]
        base["remedies"] = [
            {
                "name": n,
                "target_editor": "",
                "target_article": "",
                "target_topic": "",
                "sanction_type": "other",
                "duration": "",
                "scope": "",
                "suspended": False,
                "ongoing": "contentious topic" in (n or "").lower()
                or "indefinite" in (n or "").lower()
                or "discretionary sanctions" in (n or "").lower(),
                "support": 0,
                "oppose": 0,
                "abstain": 0,
                "passed": True,
            }
            for n in base["remedies_raw"]
        ]
        base["enforcement_actions"] = []
        base["amendments"] = []
        base["clarifications"] = []
        base["appeals"] = []
        base["post_case_motions"] = []
        # Pre-case actions already populated from regex; ensure fields exist
        base.setdefault("pre_case_actions", [])
        # Keep drafting/recused lists from regex
        base.setdefault("drafting_arbitrators", [])
        base.setdefault("recused_arbitrators", [])
        base.setdefault("inactive_arbitrators", [])
        base.setdefault("trainee_clerks", [])
        base.setdefault("clerks", [])
        return base

    print("  [gemma] pass 1/5 — principles")
    p1 = _run_pass(loader, PROMPT_PRINCIPLES, content, max_input_chars, "principles")
    print("  [gemma] pass 2/5 — findings of fact")
    p2 = _run_pass(loader, PROMPT_FINDINGS, content, max_input_chars, "findings")
    print("  [gemma] pass 3/5 — remedies")
    p3 = _run_pass(loader, PROMPT_REMEDIES, content, max_input_chars, "remedies")
    print("  [gemma] pass 4/5 — pre/post-case lifecycle")
    p4 = _run_pass(loader, PROMPT_ENFORCEMENT, content, max_input_chars, "lifecycle")
    print("  [gemma] pass 5/5 — arbitrator identity and roles")
    p5 = _run_pass(loader, PROMPT_ARBITRATORS, content, max_input_chars, "arbitrators")

    base["principles"] = p1.get("principles", [])
    base["findings"] = p2.get("findings", [])
    base["remedies"] = p3.get("remedies", [])
    # Prefer LLM-extracted pre-case actions, fall back to regex list
    llm_pre = p4.get("pre_case_actions", [])
    if llm_pre:
        base["pre_case_actions"] = llm_pre
    base["enforcement_actions"] = p4.get("enforcement_actions", [])
    base["amendments"] = p4.get("amendments", [])
    base["clarifications"] = p4.get("clarifications", [])
    base["appeals"] = p4.get("appeals", [])
    base["post_case_motions"] = p4.get("post_case_motions", [])
    # Merge arbitrator lists: union regex + LLM
    for key in (
        "drafting_arbitrators",
        "recused_arbitrators",
        "inactive_arbitrators",
        "trainee_clerks",
        "clerks",
    ):
        llm_list = p5.get(key, []) or []
        regex_list = base.get(key, []) or []
        merged: list[str] = []
        seen = set()
        for name in regex_list + llm_list:
            k = (name or "").strip().lower()
            if k and k not in seen:
                seen.add(k)
                merged.append(name.strip())
        base[key] = merged

    # Fall back to regex-extracted names if LLM returned nothing for a section
    if not base["principles"] and base["principles_raw"]:
        base["principles"] = [
            {
                "name": n,
                "summary": "(regex fallback)",
                "policy_refs": [],
                "support": 0,
                "oppose": 0,
                "abstain": 0,
                "passed": True,
            }
            for n in base["principles_raw"]
        ]
    if not base["findings"] and base["findings_raw"]:
        base["findings"] = [
            {
                "name": n,
                "target_editor": "",
                "conduct": "(regex fallback)",
                "evidence_refs": [],
                "policy_refs": [],
                "support": 0,
                "oppose": 0,
                "abstain": 0,
                "passed": True,
            }
            for n in base["findings_raw"]
        ]
    if not base["remedies"] and base["remedies_raw"]:
        base["remedies"] = [
            {
                "name": n,
                "target_editor": "",
                "target_article": "",
                "target_topic": "",
                "sanction_type": "other",
                "duration": "",
                "scope": "(regex fallback)",
                "suspended": False,
                "ongoing": "contentious topic" in (n or "").lower()
                or "indefinite" in (n or "").lower()
                or "discretionary sanctions" in (n or "").lower(),
                "support": 0,
                "oppose": 0,
                "abstain": 0,
                "passed": True,
            }
            for n in base["remedies_raw"]
        ]
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Detailed BPMN construction — maximize branches
# ─────────────────────────────────────────────────────────────────────────────


def _truncate(s: str, n: int = 40) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "\u2026"


def _votes_str(item: dict) -> str:
    """Render support/oppose/abstain tally as a compact suffix."""
    s = item.get("support", 0) or 0
    o = item.get("oppose", 0) or 0
    a = item.get("abstain", 0) or 0
    if s or o or a:
        if a:
            return f" ({s}S-{o}O-{a}Ab)"
        return f" ({s}S-{o}O)"
    return ""


# Heuristic hints for detecting ongoing ("perpetual") remedies when Gemma
# didn't flag them explicitly. NOT exhaustive — the primary signal is the
# `ongoing` field set by the LLM. These are fallback substrings matched
# case-insensitively against remedy names / durations. Add new keywords as
# Wikipedia adopts new standing-remedy patterns.
ONGOING_REMEDY_NAME_HINTS: set[str] = {
    "contentious topic",
    "discretionary sanction",
    "general sanction",
    "1rr",
    "ecp restriction",
    "extended confirmed",
}
ONGOING_REMEDY_DURATION_HINTS: set[str] = {
    "indefinite",
    "permanent",
    "perpetual",
}
# Sanction types that by definition create ongoing states.
ONGOING_SANCTION_TYPES: set[str] = {
    "contentious_topic",
    "discretionary_sanctions",
}


def _is_ongoing_remedy(rem: dict) -> bool:
    """Detect if a remedy creates an ongoing, never-ending state.

    Primary signal: the LLM-set `ongoing` flag. Fallback: heuristic
    keyword matching against name / duration / sanction_type using the
    module-level ONGOING_* hint sets. Both the LLM and the heuristic
    classify based on semantics — new unknown patterns will show ongoing=False
    but can be caught if their name or duration matches the hint sets.
    """
    if rem.get("ongoing"):
        return True
    stype = (rem.get("sanction_type") or "").lower()
    name = (rem.get("name") or "").lower()
    duration = (rem.get("duration") or "").lower()
    if stype in ONGOING_SANCTION_TYPES:
        return True
    if any(kw in name for kw in ONGOING_REMEDY_NAME_HINTS):
        return True
    if any(kw in duration for kw in ONGOING_REMEDY_DURATION_HINTS):
        return True
    return False


def _remedy_target_label(rem: dict) -> str:
    """Pick the most descriptive target for a remedy — editor, article, or topic."""
    t = rem.get("target_editor") or ""
    if t:
        return f"[{t}]"
    a = rem.get("target_article") or ""
    if a:
        return f"[article: {_truncate(a, 25)}]"
    topic = rem.get("target_topic") or ""
    if topic:
        return f"[topic: {_truncate(topic, 25)}]"
    return ""


def _build_appeal_or_desysop_bpmn(
    case: dict, lanes: list[str], b: SwimlaneBpmnBuilder
) -> str:
    """Shorter flow for appeal-style or desysop requests — no workshop,
    usually a direct committee vote."""
    committee_lane = "Full Committee" if "Full Committee" in lanes else "Arbitrators"
    ctype = case.get("case_type", "conduct")
    start = b.start(f"{ctype.capitalize()} Request Filed", "Requesting Party")
    submit = b.task(
        f"Submit {ctype.capitalize()} Request",
        "Requesting Party",
        user=True,
        doc=case.get("case_url") or "",
    )
    review = b.task("Committee Review", committee_lane, user=True)
    gw = b.gateway(f"{ctype.capitalize()} Granted?", committee_lane)
    granted = b.end(
        f"{ctype.capitalize()} Granted", committee_lane, doc=case.get("outcome", "")
    )
    declined = b.end(f"{ctype.capitalize()} Declined", committee_lane)
    b.flow(start, submit)
    b.flow(submit, review)
    b.flow(review, gw)
    b.flow(gw, granted, "Yes")
    b.flow(gw, declined, "No")
    return b.to_xml()


def _build_private_case_bpmn(
    case: dict, lanes: list[str], b: SwimlaneBpmnBuilder
) -> str:
    """Minimal flow for private cases — committee announces outcome only."""
    committee_lane = "Full Committee" if "Full Committee" in lanes else "Arbitrators"
    start = b.start("Private Matter Raised", "Requesting Party")
    private_handling = b.task(
        "Private Case Handling (off-wiki)",
        committee_lane,
        user=True,
        doc=(
            "This case was handled privately. Details not published. "
            + (case.get("case_url") or "")
        ),
    )
    announce = b.task("Announce Outcome at Noticeboard", committee_lane)
    end = b.end(
        case.get("outcome", "Outcome Announced"),
        "Enforcement",
        doc=f"Closed: {case.get('closed_date', 'unknown')}",
    )
    b.flow(start, private_handling)
    b.flow(private_handling, announce)
    b.flow(announce, end)
    return b.to_xml()


def build_detailed_bpmn(case: dict, use_detailed_lanes: bool = True) -> str:
    """
    Convert a rich case record to BPMN XML with MANY branches.

    Each proposed principle, finding, and remedy becomes its own task +
    exclusive gateway (passed? yes/no), which is what drives the branch
    count high. Motions that didn't pass terminate in 'Rejected' end events.

    Handles:
      - Private cases (minimal flow, #1)
      - Standalone post-case motions (separate from in-case motions, #2)
      - Pre-case emergency actions (upstream phase, #3)
      - Non-conduct case types — appeal / desysop / access (#4)
      - Named drafting & recused arbitrators (#5)
      - "4 net votes" accept rule (#6)
      - Abstention counts in vote labels (#7)
      - Article/topic targets on remedies (#8)
      - Suspended remedies (dual-end branch, #9)
      - Ongoing remedies as loop-marked tasks (#10)
    """
    lanes = ARB_LANES_DETAILED if use_detailed_lanes else ARB_LANES_SIMPLE
    drafting_lane = "Drafting Arbitrators" if use_detailed_lanes else "Arbitrators"
    committee_lane = "Full Committee" if use_detailed_lanes else "Arbitrators"
    other_lane = "Other Editors" if use_detailed_lanes else "Requesting Party"

    title = case.get("title", "ARB Case")[:60]
    b = SwimlaneBpmnBuilder(f"ARB Case: {title}", lanes)

    # ── Item #1: Private case — skip the full pipeline ──────────────────────
    if case.get("is_private"):
        return _build_private_case_bpmn(case, lanes, b)

    # ── Item #4: Non-conduct case types use a shorter flow ──────────────────
    case_type = case.get("case_type", "conduct")
    if case_type in ("appeal", "desysop", "access_approval"):
        return _build_appeal_or_desysop_bpmn(case, lanes, b)

    case_url = case.get("case_url", "")

    # Build a compact rule-invocation summary for the start event doc
    ri = case.get("rule_invocations", {}) or {}
    ri_doc_parts = []
    total_inv = ri.get("total_invocations", 0)
    unique = ri.get("unique_rules", 0)
    if total_inv:
        by_type = ri.get("by_type", {})
        ri_doc_parts.append(
            f"Rule invocations: {total_inv} total across {unique} unique rules "
            f"(policies={by_type.get('policy', 0)}, "
            f"guidelines={by_type.get('guideline', 0)}, "
            f"essays={by_type.get('essay', 0)}, "
            f"other={by_type.get('other', 0)})"
        )
        top5 = ri.get("top_rules", [])[:5]
        if top5:
            top5_str = ", ".join(f"{r['ref']}×{r['count']}" for r in top5)
            ri_doc_parts.append(f"Top rules: {top5_str}")
        ns_links = ri.get("namespace_links", [])[:5]
        if ns_links:
            ns_str = ", ".join(f"{n['namespace']}×{n['count']}" for n in ns_links)
            ri_doc_parts.append(f"Namespace links: {ns_str}")
    start_doc = "  ".join(ri_doc_parts) if ri_doc_parts else ""

    # ── Item #3: Pre-case emergency actions (if any) ────────────────────────
    start = b.start("Dispute Unresolved", "Requesting Party", doc=start_doc)
    prev = start
    for idx, pa in enumerate(case.get("pre_case_actions", [])[:4], start=1):
        date = pa.get("date") or ""
        action_label = _truncate(pa.get("action", f"Pre-case Action {idx}"), 40)
        target = pa.get("target_editor") or ""
        label = f"Pre-case: {action_label}"
        if target:
            label += f" → {target}"
        if date:
            label += f" — {date}"
        pre_task = b.task(
            label, "Enforcement", user=True, doc=f"Reason: {pa.get('reason', '')}"
        )
        b.flow(prev, pre_task)
        prev = pre_task

    # ── Phase 1: Filing & screening ─────────────────────────────────────────
    opened = case.get("opened_date") or "unknown"
    submit = b.task(
        f"File Arbitration Request ({opened})",
        "Requesting Party",
        user=True,
        doc=(
            f"Parties: {', '.join(case.get('parties', [])[:8])}  Case URL: {case_url}"
        ),
    )
    b.flow(prev, submit)

    statements = b.task(
        "Statements by Other Parties",
        other_lane,
        user=True,
        doc=f"{len(case.get('parties', []))} parties named",
    )

    screen = b.task("Clerk Screens Request", "Clerk", user=True)

    # Item #6: net-votes accept rule + Item #7: abstain in label
    accept_n = case.get("accept_votes", 0)
    decline_n = case.get("decline_votes", 0)
    recuse_n = case.get("recuse_votes", 0)
    abstain_n = case.get("abstain_votes", 0)
    net = accept_n - decline_n
    vote_str = f"{accept_n}A/{decline_n}D/{recuse_n}R"
    if abstain_n:
        vote_str += f"/{abstain_n}Ab"
    vote_str += f" net={net:+d}"

    gw_accept = b.gateway(
        f"Case Accepted? ({vote_str})",
        "Clerk",
        doc="Accept rule: 4 net votes OR majority of active arbitrators.",
    )
    end_declined = b.end("Case Declined", "Clerk")

    b.flow(submit, statements)
    b.flow(statements, screen)
    b.flow(screen, gw_accept)

    # Use the server-computed accepted_by_rule field (correct "4 net votes" rule)
    accepted = case.get("accepted_by_rule")
    if accepted is None:
        accepted = net >= 4 or accept_n > (decline_n + recuse_n)

    if not accepted and case.get("outcome") == "Declined":
        b.flow(gw_accept, end_declined, "No")
        return b.to_xml()
    b.flow(gw_accept, end_declined, "No - Declined")

    # ── Phase 2: Temporary injunction (optional branch) ─────────────────────
    prev = b.task("Open Case & Begin Evidence Phase", "Clerk", user=True)
    b.flow(gw_accept, prev, "Yes - Accepted")

    if case.get("has_injunction"):
        inj_task = b.task("Propose Temporary Injunction", drafting_lane, user=True)
        gw_inj = b.gateway("Injunction Passed?", committee_lane)
        inj_enforced = b.task("Enforce Temporary Injunction", "Enforcement", user=True)
        inj_rejected = b.end("Injunction Rejected", committee_lane)
        b.flow(prev, inj_task)
        b.flow(inj_task, gw_inj)
        b.flow(gw_inj, inj_enforced, "Yes")
        b.flow(gw_inj, inj_rejected, "No")
        prev = inj_enforced

    # ── Phase 3: Evidence ───────────────────────────────────────────────────
    evidence = b.task(
        "Evidence Phase",
        drafting_lane,
        user=True,
        doc=f"Parties present evidence — {len(case.get('parties', []))} parties",
    )
    b.flow(prev, evidence)

    # Item #5: name the drafting arbitrators & recused arbs in workshop doc
    drafters = case.get("drafting_arbitrators", []) or []
    recused = case.get("recused_arbitrators", []) or []
    inactive = case.get("inactive_arbitrators", []) or []
    workshop_doc_parts = []
    if drafters:
        workshop_doc_parts.append("Drafting arbitrators: " + ", ".join(drafters[:6]))
    if recused:
        workshop_doc_parts.append("Recused: " + ", ".join(recused[:6]))
    if inactive:
        workshop_doc_parts.append("Inactive: " + ", ".join(inactive[:6]))

    workshop = b.task(
        "Workshop — Draft Principles, Findings, Remedies",
        drafting_lane,
        user=True,
        doc="  ".join(workshop_doc_parts) if workshop_doc_parts else "",
    )
    b.flow(evidence, workshop)
    prev = workshop

    # ── Phase 4: Vote on each Principle (many gateways) ─────────────────────
    principles = case.get("principles", [])
    prev_label = ""
    if principles:
        pv_entry = b.task("Proposed Decision: Principles", committee_lane)
        b.flow(prev, pv_entry)
        last_pass_node = pv_entry
        for idx, princ in enumerate(principles[:12], start=1):
            name = _truncate(princ.get("name", f"Principle {idx}"), 45)
            # Short version for gateway/end labels (limited space)
            short_name = _truncate(princ.get("name", f"Principle {idx}"), 28)
            task = b.task(
                f"Vote on Principle: {name}{_votes_str(princ)}",
                committee_lane,
                user=True,
                doc=(
                    (princ.get("summary") or "")
                    + (
                        "  Policies: " + ", ".join(princ.get("policy_refs") or [])
                        if princ.get("policy_refs")
                        else ""
                    )
                ),
            )
            gw = b.gateway(f"{short_name} passed?", committee_lane)
            rej = b.end(f"{short_name}: rejected", committee_lane, doc=name)
            b.flow(last_pass_node, task)
            b.flow(task, gw)
            b.flow(gw, rej, "No")
            last_pass_node = gw
        prev = last_pass_node
        prev_label = "Yes"

    # ── Phase 5: Vote on each Finding of Fact ───────────────────────────────
    findings = case.get("findings", [])
    if findings:
        fv_entry = b.task("Proposed Decision: Findings of Fact", committee_lane)
        b.flow(prev, fv_entry, prev_label)
        last_pass_node = fv_entry
        for idx, find in enumerate(findings[:12], start=1):
            name = _truncate(find.get("name", f"Finding {idx}"), 45)
            short_name = _truncate(find.get("name", f"Finding {idx}"), 28)
            target = find.get("target_editor") or ""
            label = f"Vote on Finding: {name}" + (f" [{target}]" if target else "")
            doc = (
                (find.get("conduct") or "")
                + (
                    "  Evidence: " + "; ".join((find.get("evidence_refs") or [])[:3])
                    if find.get("evidence_refs")
                    else ""
                )
                + (
                    "  Policies: " + ", ".join(find.get("policy_refs") or [])
                    if find.get("policy_refs")
                    else ""
                )
            )
            task = b.task(
                label + _votes_str(find),
                committee_lane,
                user=True,
                doc=doc,
            )
            gw = b.gateway(f"{short_name} passed?", committee_lane)
            rej = b.end(f"{short_name}: rejected", committee_lane, doc=name)
            b.flow(last_pass_node, task, "Yes" if last_pass_node is fv_entry else "")
            b.flow(task, gw)
            b.flow(gw, rej, "No")
            last_pass_node = gw
        prev = last_pass_node
        prev_label = "Yes"

    # ── Phase 6: Vote on each Remedy (items #8, #9, #10) ────────────────────
    remedies = case.get("remedies", [])
    if remedies:
        rv_entry = b.task("Proposed Decision: Remedies", committee_lane)
        b.flow(prev, rv_entry, prev_label)
        last_pass_node = rv_entry
        for idx, rem in enumerate(remedies[:12], start=1):
            name = _truncate(rem.get("name", f"Remedy {idx}"), 45)
            short_name = _truncate(rem.get("name", f"Remedy {idx}"), 28)
            target_label = _remedy_target_label(rem)  # #8
            stype = rem.get("sanction_type") or ""
            dur = rem.get("duration") or ""
            suspended = bool(rem.get("suspended"))
            ongoing = _is_ongoing_remedy(rem)  # #10

            label = f"Vote on Remedy: {name}"
            if target_label:
                label += f" {target_label}"

            doc_parts = []
            if stype:
                doc_parts.append(f"Type: {stype}")
            if dur:
                doc_parts.append(f"Duration: {dur}")
            if rem.get("scope"):
                doc_parts.append(f"Scope: {rem['scope']}")
            if suspended:
                doc_parts.append("SUSPENDED — can be triggered later via ARCA")
            if ongoing:
                doc_parts.append(
                    "ONGOING — perpetual state; see case page for live log"
                )
            if case_url:
                doc_parts.append(f"Case: {case_url}")

            task = b.task(
                label + _votes_str(rem),
                committee_lane,
                user=True,
                doc="  ".join(doc_parts),
                loop=ongoing,  # #10: loop marker for never-ending remedies
            )
            gw = b.gateway(f"{short_name} passed?", committee_lane)
            rej = b.end(f"{short_name}: rejected", committee_lane, doc=name)
            b.flow(last_pass_node, task, "Yes" if last_pass_node is rv_entry else "")
            b.flow(task, gw)
            b.flow(gw, rej, "No")

            # #9 Suspended: add a second "Yes" branch showing the suspended state
            # which can later be triggered at ARCA
            if suspended:
                sus_end = b.end(
                    f"{short_name}: suspended (ARCA-triggerable)",
                    committee_lane,
                    doc="Remedy held in reserve; activated only on later motion.",
                )
                b.flow(gw, sus_end, "Yes — suspended")
                active_gw = b.gateway(f"{short_name} active?", committee_lane)
                b.flow(gw, active_gw, "Yes — active")
                last_pass_node = active_gw
            else:
                last_pass_node = gw
        prev = last_pass_node
        prev_label = "Yes"

    # ── Phase 7: Final decision ─────────────────────────────────────────────
    final = b.task(
        "Final Decision Published",
        committee_lane,
        doc=f"Closed: {case.get('closed_date', 'unknown')}  URL: {case_url}",
    )
    b.flow(prev, final, prev_label)

    enforce = b.task("Enforcement & Monitoring", "Enforcement", user=True)
    b.flow(final, enforce)

    # ── Phase 8: Enforcement actions (each = a branch) ──────────────────────
    actions = case.get("enforcement_actions", [])
    prev = enforce
    prev_label = ""
    for idx, act in enumerate(actions[:8], start=1):
        date = act.get("date") or ""
        atxt = _truncate(act.get("action", f"Action {idx}"), 35)
        target = act.get("target_editor") or ""
        admin = act.get("admin") or ""
        label = f"AE: {atxt}"
        if target:
            label += f" → {target}"
        if date:
            label += f" — {date}"
        doc = f"Admin: {admin}  Outcome: {act.get('outcome', '')}"
        a_task = b.task(label, "Enforcement", user=True, doc=doc)
        a_gw = b.gateway(f"Action {idx} Upheld?", "Enforcement")
        a_overturned = b.end(f"Action {idx} Overturned", "Enforcement")
        b.flow(prev, a_task, prev_label)
        b.flow(a_task, a_gw)
        b.flow(a_gw, a_overturned, "No")
        prev = a_gw
        prev_label = "Yes"

    # ── Phase 9: Appeals ────────────────────────────────────────────────────
    appeals = case.get("appeals", [])
    for idx, app in enumerate(appeals[:5], start=1):
        subj = _truncate(app.get("subject", f"Appeal {idx}"), 35)
        req = app.get("requester") or ""
        date = app.get("date") or ""
        label = f"Appeal: {subj}"
        if req:
            label += f" (by {req})"
        if date:
            label += f" — {date}"
        ap_task = b.task(
            label, committee_lane, user=True, doc=f"Outcome: {app.get('outcome', '')}"
        )
        ap_gw = b.gateway(f"Appeal {idx} Granted?", committee_lane)
        ap_granted = b.end(f"Appeal {idx} Granted", committee_lane)
        b.flow(prev, ap_task, prev_label)
        b.flow(ap_task, ap_gw)
        b.flow(ap_gw, ap_granted, "Yes")
        prev = ap_gw
        prev_label = "No"

    # ── Phase 9b: Amendments ────────────────────────────────────────────────
    amendments = case.get("amendments", [])
    for idx, am in enumerate(amendments[:5], start=1):
        subj = _truncate(am.get("subject", f"Amendment {idx}"), 30)
        req = am.get("requester") or ""
        date = am.get("date") or ""
        change = _truncate(am.get("change", ""), 40)
        label = f"Amendment: {subj}"
        if date:
            label += f" — {date}"
        doc_parts = []
        if req:
            doc_parts.append(f"Requester: {req}")
        if change:
            doc_parts.append(f"Change: {change}")
        doc_parts.append(f"Outcome: {am.get('outcome', '')}")
        am_task = b.task(label, committee_lane, user=True, doc="  ".join(doc_parts))
        short_subj = _truncate(am.get("subject", f"Amendment {idx}"), 24)
        am_gw = b.gateway(f"Amend: {short_subj} passed?", committee_lane)
        am_rejected = b.end(f"Amend: {short_subj} declined", committee_lane)
        b.flow(prev, am_task, prev_label)
        b.flow(am_task, am_gw)
        b.flow(am_gw, am_rejected, "No")
        prev = am_gw
        prev_label = "Yes"

    # ── Phase 9c: Clarifications ────────────────────────────────────────────
    clarifications = case.get("clarifications", [])
    for idx, cl in enumerate(clarifications[:5], start=1):
        question = _truncate(cl.get("question", f"Clarification {idx}"), 35)
        req = cl.get("requester") or ""
        date = cl.get("date") or ""
        label = f"Clarification: {question}"
        if date:
            label += f" — {date}"
        doc = f"Requester: {req}  Outcome: {cl.get('outcome', '')}"
        cl_task = b.task(label, committee_lane, user=True, doc=doc)
        cl_gw = b.gateway(f"Clarification {idx} Given?", committee_lane)
        cl_declined = b.end(f"Clarification {idx} Declined", committee_lane)
        b.flow(prev, cl_task, prev_label)
        b.flow(cl_task, cl_gw)
        b.flow(cl_gw, cl_declined, "No")
        prev = cl_gw
        prev_label = "Yes"

    # ── Phase 9d: Standalone post-case motions (Item #2) ────────────────────
    # These are motions passed by ArbCom AFTER the case closed, distinct
    # from votes on remedies that happened during the case.
    post_motions = case.get("post_case_motions", [])
    for idx, mo in enumerate(post_motions[:5], start=1):
        desc = _truncate(mo.get("motion", f"Post-case Motion {idx}"), 40)
        date = mo.get("date") or ""
        vote = mo.get("vote") or ""
        label = f"Post-case Motion: {desc}"
        if date:
            label += f" — {date}"
        doc_parts = []
        if vote:
            doc_parts.append(f"Vote: {vote}")
        doc_parts.append(f"Outcome: {mo.get('outcome', '')}")
        mo_task = b.task(label, committee_lane, user=True, doc="  ".join(doc_parts))
        mo_gw = b.gateway(f"Post-case Motion {idx} Passed?", committee_lane)
        mo_failed = b.end(f"Post-case Motion {idx} Failed", committee_lane)
        b.flow(prev, mo_task, prev_label)
        b.flow(mo_task, mo_gw)
        b.flow(mo_gw, mo_failed, "No")
        prev = mo_gw
        prev_label = "Yes"

    # ── Phase 10: Terminal outcome ──────────────────────────────────────────
    outcome = case.get("outcome", "Case Closed")
    end_main = b.end(
        outcome,
        "Enforcement",
        doc=(f"Closed: {case.get('closed_date', 'unknown')}  URL: {case_url}"),
    )
    b.flow(prev, end_main, prev_label)

    return b.to_xml()


# ─────────────────────────────────────────────────────────────────────────────
# Wikipedia fetching & per-document pipeline
# ─────────────────────────────────────────────────────────────────────────────


def safe_filename(title: str, max_len: int = 60) -> str:
    safe = re.sub(r"[^\w\-]", "_", title)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe[:max_len] if safe else "unnamed"


# Subpages we try to fetch in addition to the main case page. Order matters —
# these get concatenated and fed to the regex + Gemma extractors as one body.
ARB_SUBPAGE_SUFFIXES = [
    "Evidence",
    "Workshop",
    "Proposed_decision",  # THE critical one — has the actual votes
    "Proposed decision",  # Some older cases use space instead of underscore
    "Enforcement_log",
    "Enforcement log",
    "Motion",
    "Motions",
    "Amendments",
]


def fetch_arb_case_full(case_title: str, include_subpages: bool = True) -> str:
    """
    Fetch a Wikipedia ARB case plus its standard subpages, concatenated
    with section markers so the regex parsers can still identify sections.

    Returns the combined wikitext. Missing subpages are skipped silently.
    """
    try:
        import pywikibot  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "pywikibot not installed. Run: pip install pywikibot"
        ) from exc

    site = pywikibot.Site("en", "wikipedia")
    parts: list[str] = []

    # Main case page
    print(f"  [fetch] main: {case_title}")
    try:
        main_page = pywikibot.Page(site, case_title)
        main_text = main_page.text
        if main_text:
            parts.append("\n\n<!-- ========== MAIN CASE PAGE ========== -->\n")
            parts.append(main_text)
            print(f"          ({len(main_text):,} chars)")
        else:
            print("          (empty)")
    except Exception as exc:
        print(f"          ERROR: {exc}")

    if not include_subpages:
        return "".join(parts)

    # Subpages
    tried: set[str] = set()
    for suffix in ARB_SUBPAGE_SUFFIXES:
        subpage_title = f"{case_title}/{suffix}"
        # Avoid duplicates after space/underscore normalisation
        normalized = subpage_title.replace(" ", "_")
        if normalized in tried:
            continue
        tried.add(normalized)

        try:
            sub_page = pywikibot.Page(site, subpage_title)
            if not sub_page.exists():
                continue
            sub_text = sub_page.text
            if not sub_text or len(sub_text) < 50:
                continue
            print(f"  [fetch] subpage: /{suffix} ({len(sub_text):,} chars)")
            parts.append(f"\n\n<!-- ========== SUBPAGE: {suffix} ========== -->\n")
            parts.append(sub_text)
        except Exception as exc:
            # Subpages commonly don't exist — only warn on unexpected errors
            if "does not exist" not in str(exc).lower():
                print(f"  [fetch] subpage /{suffix}: {exc}")

    combined = "".join(parts)
    print(f"  [fetch] combined lifecycle text: {len(combined):,} chars")
    return combined


# ─────────────────────────────────────────────────────────────────────────────
# DRN fetcher — single case by title, OR all cases in one archive
# ─────────────────────────────────────────────────────────────────────────────


def fetch_drn_case(case_title: str) -> str:
    """Fetch a single DRN case from Wikipedia.

    DRN cases are normally sections within a numbered archive page (e.g.
    'Wikipedia:Dispute_resolution_noticeboard/Archive_233#Section_Name').
    The caller can pass either the full URL with anchor or just the
    archive page title — in which case all sections are returned.
    """
    try:
        import pywikibot  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "pywikibot not installed. Run: pip install pywikibot"
        ) from exc

    # Split off any "#anchor" or "#section-id" — pywikibot fetches the
    # whole page, then we slice out the section if a fragment was given.
    if "#" in case_title:
        page_title, anchor = case_title.split("#", 1)
        anchor = anchor.replace("_", " ")
    else:
        page_title, anchor = case_title, None

    site = pywikibot.Site("en", "wikipedia")
    print(f"  [fetch] DRN page: {page_title}")
    try:
        page = pywikibot.Page(site, page_title)
        full_text = page.text
        if not full_text:
            print("          (empty)")
            return ""
    except Exception as exc:
        print(f"          ERROR: {exc}")
        return ""

    if not anchor:
        print(f"  [fetch] full page ({len(full_text):,} chars) — all sections")
        return full_text

    # Slice out the section matching the anchor (case-insensitive).
    # MediaWiki sections are headed by "== Title ==" — we find the matching
    # heading and return content up to the next heading at the same level.
    import re as _re

    pattern = _re.compile(r"(==+\s*" + _re.escape(anchor) + r"\s*==+)", _re.I)
    m = pattern.search(full_text)
    if not m:
        print(f"          WARNING: section '{anchor}' not found; returning full page")
        return full_text
    section_start = m.start()
    # Find next heading of same or higher level after this one
    level = m.group(1).count("=") // 2
    # Look for next heading of this level or shallower
    next_heading = _re.compile(rf"\n=={{1,{level}}}[^=].*?=={{1,{level}}}\s*\n")
    rest = full_text[m.end() :]
    nm = next_heading.search(rest)
    section = (
        full_text[section_start : m.end() + nm.start()]
        if nm
        else full_text[section_start:]
    )
    print(f"  [fetch] section '{anchor}' ({len(section):,} chars)")
    return section


def fetch_drn_archive(archive_number: int | str) -> list[tuple[str, str]]:
    """Fetch every case section from one DRN archive page.

    Returns a list of (section_title, section_wikitext) tuples — one per
    case in the archive. Useful for batch DRN extraction since each archive
    contains ~30 cases.
    """
    try:
        import pywikibot  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "pywikibot not installed. Run: pip install pywikibot"
        ) from exc

    page_title = f"Wikipedia:Dispute_resolution_noticeboard/Archive_{archive_number}"
    site = pywikibot.Site("en", "wikipedia")
    print(f"  [fetch] DRN archive: {page_title}")
    try:
        page = pywikibot.Page(site, page_title)
        full_text = page.text
    except Exception as exc:
        print(f"          ERROR: {exc}")
        return []
    if not full_text:
        print("          (empty)")
        return []

    # Split on level-2 headings (== Title ==) — each is one DRN case.
    import re as _re

    sections: list[tuple[str, str]] = []
    pattern = _re.compile(r"\n==\s*([^=\n]+?)\s*==\s*\n")
    matches = list(pattern.finditer(full_text))
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        body = full_text[start:end]
        if len(body) < 200:  # skip tiny non-case sections (TOC, header, etc.)
            continue
        sections.append((title, body))
    print(f"  [fetch] found {len(sections)} cases in archive {archive_number}")
    return sections


# ─────────────────────────────────────────────────────────────────────────────
# RFC fetcher — RFCs live on talk pages or in Wikipedia: namespace
# ─────────────────────────────────────────────────────────────────────────────


def fetch_rfc(rfc_title: str) -> str:
    """Fetch an RFC from Wikipedia.

    RFCs typically live as sections of a talk page (Talk:Article#RfC_title)
    or as standalone pages under Wikipedia:Requests_for_comment/.
    Both forms are handled — anchor-based slicing works the same as DRN.
    """
    return fetch_drn_case(rfc_title)  # logic is identical: page + optional #anchor


# ─────────────────────────────────────────────────────────────────────────────
# Venue-aware Gemma extraction — runs the appropriate prompt set per venue
# ─────────────────────────────────────────────────────────────────────────────


def _get_prompt_by_name(name: str) -> str:
    """Resolve a prompt constant name to its actual string at runtime.

    The venue registry stores prompt names as strings (rather than the
    objects themselves) so the registry can be defined before the prompts
    in module-load order. This indirection is harmless — module globals
    are stable by the time any extract function runs.
    """
    return globals()[name]


def extract_venue_case(
    loader: Gemma4Loader | None,
    text: str,
    title: str,
    venue: str,
    max_input_chars: int,
) -> dict:
    """Generic per-case extractor for any venue in the VENUES registry.

    Always runs the deterministic regex pass first (rule invocations,
    namespace links — venue-agnostic), then runs the LLM passes named in
    the venue's recipe and merges the results. Each pass's JSON is stored
    under its label key in the case dict, so callers can reach into e.g.
    `case["closure"]` for DRN closures.
    """
    venue_cfg = VENUES.get(venue)
    if not venue_cfg:
        raise ValueError(f"Unknown venue: {venue!r}; expected one of {list(VENUES)}")

    # Deterministic universals (rule invocations + namespaces) — these run
    # for every venue regardless of LLM availability.
    rule_invocations = _extract_rule_invocations(text)
    case: dict = {
        "title": title,
        "venue": venue,
        "venue_label": venue_cfg["label"],
        "rule_invocations": rule_invocations,
    }

    if loader is None:
        # No-LLM mode: return only the deterministic data. The diagram
        # builder handles missing fields gracefully.
        return case

    # Venue-specific multi-pass extraction
    print(f"[{title}] Extracting {venue_cfg['label']} case structure ...")
    for i, (pass_label, prompt_name) in enumerate(venue_cfg["passes"], start=1):
        print(f"  [gemma] pass {i}/{len(venue_cfg['passes'])} — {pass_label}")
        prompt = _get_prompt_by_name(prompt_name)
        # Use the venue's system prompt instead of the global ARB one
        try:
            result = _run_pass_with_system(
                loader,
                venue_cfg["system_prompt"],
                prompt,
                text,
                max_input_chars,
                pass_label,
            )
        except Exception as exc:
            print(f"    [{pass_label}] failed: {exc}")
            result = {}
        # Merge top-level fields directly when the result is a dict; nest
        # under the pass label otherwise.
        if isinstance(result, dict):
            for k, v in result.items():
                if k not in case:  # don't clobber title/venue/etc.
                    case[k] = v
            # Also keep a copy under the pass label for traceability
            case[f"_{pass_label}_pass"] = result
    return case


def _run_pass_with_system(
    loader: Gemma4Loader,
    system_prompt: str,
    prompt_tmpl: str,
    text: str,
    max_input_chars: int,
    label: str,
    max_retries: int = 2,
) -> dict:
    """Like _run_pass but takes an explicit system prompt (not the global one)."""
    effective_cap = min(len(text), max_input_chars)
    if effective_cap < len(text):
        print(
            f"    [{label}] truncating {len(text):,} → {effective_cap:,} chars "
            f"to fit model context"
        )
    else:
        print(f"    [{label}] sending full {len(text):,} chars")

    oom_shrinks_remaining = 3
    while True:
        user_msg = prompt_tmpl.format(text=text[:effective_cap])
        full_prompt = _build_chat_prompt(system_prompt, user_msg)
        try:
            for attempt in range(1, max_retries + 1):
                raw = loader.generate(full_prompt)
                try:
                    return _extract_json(raw)
                except (ValueError, json.JSONDecodeError) as exc:
                    print(
                        f"    [{label}] attempt {attempt}/{max_retries} "
                        f"parse error: {exc}"
                    )
                    if attempt == max_retries:
                        return {}
            return {}
        except torch.cuda.OutOfMemoryError:
            if oom_shrinks_remaining <= 0:
                print(f"    [{label}] CUDA OOM — giving up on this pass")
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                return {}
            oom_shrinks_remaining -= 1
            new_cap = max(effective_cap // 2, 1500)
            print(f"    [{label}] CUDA OOM — halving {effective_cap:,} → {new_cap:,}")
            effective_cap = new_cap
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            if new_cap == 1500:
                oom_shrinks_remaining = 0


# ─────────────────────────────────────────────────────────────────────────────
# DRN BPMN builder — simple flow: filing → mediator pickup → moderation → close
# ─────────────────────────────────────────────────────────────────────────────


def build_drn_bpmn(case: dict) -> str:
    """Build a DRN-flavored BPMN diagram from an extracted DRN case dict.

    DRN's process is much simpler than ArbCom — no voting branches, no
    formal remedies. The diagram captures: filing → other-party statements
    → volunteer pickup → moderated discussion phases → closure.
    """
    title = case.get("title", "Untitled")
    b = SwimlaneBpmnBuilder(process_name=title, lanes=DRN_LANES)

    filer = case.get("filing_party", "") or "Filing Party"
    parties = case.get("other_parties", []) or []
    article = case.get("article_subject", "") or ""
    summary = case.get("dispute_summary", "") or ""

    start = b.start(
        "Content Dispute Identified", "Filing Party", doc=summary or article
    )

    # Filing
    file_task = b.task(
        f"File DRN: {filer}" + (f" re: {article}" if article else ""),
        "Filing Party",
        user=True,
        doc=summary,
    )
    b.flow(start, file_task)
    prev = file_task
    prev_label = ""

    # Other-party statements
    if parties:
        statements = b.task(
            f"Opening statements from {len(parties)} other parties",
            "Other Parties",
            user=True,
            doc=", ".join(parties[:10]),
        )
        b.flow(prev, statements)
        prev = statements

    # Volunteer pickup decision
    mediators = case.get("volunteer_mediators", []) or []
    pickup_gw = b.gateway("Volunteer picks up case?", "Volunteer Mediator")
    no_volunteer = b.end(
        "Closed: no volunteer", "Closer", doc="14-day archival without pickup"
    )
    b.flow(prev, pickup_gw)
    b.flow(pickup_gw, no_volunteer, "No")

    pickup = b.task(
        f"Volunteer mediation: {', '.join(mediators) if mediators else '(unnamed)'}",
        "Volunteer Mediator",
        user=True,
    )
    b.flow(pickup_gw, pickup, "Yes")

    # Discussion phases — each phase becomes its own task in sequence
    phases = case.get("discussion_phases", []) or []
    last = pickup
    for i, phase in enumerate(phases[:6], start=1):
        phase_task = b.task(
            f"Phase {i}: {phase[:50]}",
            "Volunteer Mediator",
            user=True,
        )
        b.flow(last, phase_task)
        last = phase_task

    # Compromise gateway
    compromise_proposed = case.get("compromise_proposed")
    compromise_accepted = case.get("compromise_accepted")
    if compromise_proposed:
        comp_task = b.task(
            "Compromise proposal floated", "Volunteer Mediator", user=True
        )
        b.flow(last, comp_task)
        comp_gw = b.gateway("Parties accept compromise?", "Volunteer Mediator")
        b.flow(comp_task, comp_gw)
        last = comp_gw
        if compromise_accepted:
            prev_label = "Yes"
        else:
            no_accept = b.end(
                "Compromise rejected — case fails",
                "Closer",
                doc="Parties did not accept",
            )
            b.flow(comp_gw, no_accept, "No")
            prev_label = "Yes"  # fall through to closure

    # Closure outcomes
    closure_type = (case.get("closure_type", "") or "unknown").lower()
    closer = case.get("closer", "") or ""
    reason = case.get("closure_reason", "") or ""
    next_venue = case.get("next_venue_recommended", "") or ""

    close_task = b.task(
        f"Closer determines outcome: {closer}" if closer else "Case closed",
        "Closer",
        user=True,
        doc=reason,
    )
    b.flow(last, close_task, prev_label)

    # Outcome end events — one per closure type so the diagram shows the option
    outcome_labels = {
        "resolved": "Resolved (consensus reached)",
        "failed": "Failed (stalled or refused)",
        "closed-unsuitable": "Closed unsuitable (out of scope)",
        "withdrawn": "Withdrawn by filer",
        "bot-archived": "Bot-archived (14d expired)",
        "premature": "Premature (insufficient prior discussion)",
        "unknown": "Closed (reason unknown)",
    }
    final_label = outcome_labels.get(closure_type, f"Closed: {closure_type}")
    final = b.end(final_label, "Closer", doc=reason)
    b.flow(close_task, final)

    # If a next venue was recommended, branch off to a separate end event
    if next_venue and next_venue.lower() not in ("none", ""):
        escalate = b.end(
            f"Escalated to {next_venue}",
            "Closer",
            doc=f"Closer recommended escalation to {next_venue}",
        )
        b.flow(close_task, escalate)

    return b.to_xml()


# ─────────────────────────────────────────────────────────────────────────────
# RFC BPMN builder — proposal → !vote period → closer summary → outcome
# ─────────────────────────────────────────────────────────────────────────────


def build_rfc_bpmn(case: dict) -> str:
    """Build an RFC-flavored BPMN diagram from an extracted RFC case dict.

    RFCs have a well-defined open structure: proposer asks a question,
    community !votes for ~30 days, an uninvolved closer reads consensus
    and writes a closing summary. Outcomes cluster around 4 categories:
    consensus support / consensus oppose / no consensus / withdrawn.
    """
    title = case.get("title", "Untitled")
    b = SwimlaneBpmnBuilder(process_name=title, lanes=RFC_LANES)

    proposer = case.get("proposer", "") or "Proposer"
    question = case.get("proposal_question", "") or ""
    page = case.get("page", "") or ""
    options = case.get("proposal_options", []) or []
    rfc_id = case.get("rfc_id", "") or ""
    open_date = case.get("open_date", "") or ""

    start_doc = "  ".join(
        filter(
            None,
            [
                f"Page: {page}" if page else "",
                f"Question: {question[:200]}" if question else "",
                f"Options: {', '.join(options[:6])}" if options else "",
                f"RFC ID: {rfc_id}" if rfc_id else "",
                f"Opened: {open_date}" if open_date else "",
            ],
        )
    )
    start = b.start("Issue requires community input", "Proposer", doc=start_doc)

    # Proposer formulates the question
    prop_task = b.task(
        f"Open RFC: {proposer}",
        "Proposer",
        user=True,
        doc=question[:300],
    )
    b.flow(start, prop_task)

    # Listing/categorisation step — Legobot tags the RFC by category
    cats = case.get("rfc_categories", []) or []
    listing = b.task(
        f"Listed by Legobot — categories: {', '.join(cats[:4]) if cats else '(none)'}",
        "Proposer",
        doc="Auto-listed in central RFC tables for advertised participation",
    )
    b.flow(prop_task, listing)

    # !Voting period — render the actual !vote distribution
    sup = case.get("support_count", 0) or 0
    opp = case.get("oppose_count", 0) or 0
    neu = case.get("neutral_count", 0) or 0
    alt = case.get("alternative_count", 0) or 0
    sup_voters = case.get("support_voters", []) or []
    opp_voters = case.get("oppose_voters", []) or []
    invo = case.get("involved_voters", 0) or 0
    uninv = case.get("uninvolved_voters", 0) or 0

    args_for = case.get("key_arguments_for", []) or []
    args_against = case.get("key_arguments_against", []) or []

    vote_task = b.task(
        f"Community discussion ({sup}S / {opp}O / {neu}N"
        + (f" / {alt}Alt" if alt else "")
        + ")",
        "Participants",
        user=True,
        doc="  ".join(
            filter(
                None,
                [
                    f"Support voters: {', '.join(sup_voters[:8])}"
                    if sup_voters
                    else "",
                    f"Oppose voters: {', '.join(opp_voters[:8])}" if opp_voters else "",
                    f"Top arguments for: {' | '.join(args_for[:3])}"
                    if args_for
                    else "",
                    f"Top arguments against: {' | '.join(args_against[:3])}"
                    if args_against
                    else "",
                    f"Involved/uninvolved breakdown: {invo} involved / {uninv} uninvolved",
                ],
            )
        ),
    )
    b.flow(listing, vote_task)

    # 30-day timer / Legobot delisting — implicit but worth showing
    timer = b.task(
        "30-day discussion period (Legobot delists)",
        "Participants",
        doc="Default RFC duration; can be extended for ongoing discussion",
    )
    b.flow(vote_task, timer)

    # Closer reads consensus
    closer = case.get("closer", "") or ""
    closer_is_admin = bool(case.get("closer_is_admin"))
    consensus = (case.get("consensus_finding", "") or "unknown").lower()
    summary = case.get("closing_summary", "") or ""
    next_actions = case.get("next_actions", "") or ""
    close_date = case.get("close_date", "") or ""
    appealed = bool(case.get("appealed"))

    close_task = b.task(
        f"Closer summary: {closer}" + (" (admin)" if closer_is_admin else ""),
        "Closer",
        user=True,
        doc="  ".join(
            filter(
                None,
                [
                    f"Closed: {close_date}" if close_date else "",
                    f"Summary: {summary[:300]}" if summary else "",
                    f"Next: {next_actions}" if next_actions else "",
                    "APPEALED at AN/ANI" if appealed else "",
                ],
            )
        ),
    )
    b.flow(timer, close_task)

    # Consensus gateway → branch by outcome.
    #
    # Each possible consensus outcome becomes its own end event. The renderer
    # is responsible for laying these out so labels don't collide; the
    # builder just declares the topology (one branch per possible outcome).
    # The gateway's documentation carries the legend for the short flow
    # codes so the diagram is self-explanatory.
    gateway_legend = (
        "Branch codes:  "
        "SS = strong consensus support  •  "
        "RS = rough consensus support  •  "
        "NC = no consensus  •  "
        "RO = rough consensus oppose  •  "
        "SO = strong consensus oppose  •  "
        "W = withdrawn  •  "
        "SC = speedy close  •  "
        "U = unknown"
    )
    consensus_gw = b.gateway("Consensus finding?", "Closer", doc=gateway_legend)
    b.flow(close_task, consensus_gw)

    consensus_labels = {
        "strong-consensus-support": "Strong consensus to SUPPORT — implement",
        "rough-consensus-support": "Rough consensus to support — implement with caveats",
        "no-consensus": "No consensus — status quo / no change",
        "rough-consensus-oppose": "Rough consensus to OPPOSE — do not implement",
        "strong-consensus-oppose": "Strong consensus to OPPOSE — proposal rejected",
        "withdrawn": "Withdrawn by proposer",
        "speedy-close": "Speedy-closed (snowball/bad faith/duplicate)",
        "unknown": "Outcome unclear",
    }
    # Short codes used as flow labels on the arrows. The full descriptive
    # text lives on each end event below the circle, so the diagram is
    # readable without redundancy. Each code maps 1:1 to its end-event row.
    consensus_codes = {
        "strong-consensus-support": "SS",
        "rough-consensus-support": "RS",
        "no-consensus": "NC",
        "rough-consensus-oppose": "RO",
        "strong-consensus-oppose": "SO",
        "withdrawn": "W",
        "speedy-close": "SC",
        "unknown": "U",
    }
    matched = consensus if consensus in consensus_labels else "unknown"
    # Emit all branches; the actual outcome gets a ★ prefix and the closer's
    # summary as documentation. Other branches are tagged as not-reached so
    # the renderer can dim them or otherwise distinguish them. The flow
    # labels use short two-letter codes (SS/RS/NC/RO/SO/W/SC/U) rather than
    # repeating the end-event name on the arrow.
    for label_key, label_text in consensus_labels.items():
        if label_key == matched:
            end_node = b.end(f"★ {label_text}", "Closer", doc=summary)
        else:
            end_node = b.end(
                label_text, "Closer", doc="Possible outcome — not the one reached."
            )
        b.flow(consensus_gw, end_node, consensus_codes[label_key])

    # Appeal branch — if the close was challenged, show that as an additional
    # downstream node (which would loop back into another venue's process)
    if appealed:
        appeal_end = b.end(
            "Close appealed at AN/ANI",
            "Closer",
            doc="Closer's determination challenged in another venue",
        )
        b.flow(close_task, appeal_end)

    return b.to_xml()


def process_document(
    loader: Gemma4Loader | None,
    text: str,
    title: str,
    output_dir: Path,
    max_input_chars: int,
    detailed_lanes: bool,
    dry_run: bool,
    venue: str = "arb",
) -> None:
    """Per-case pipeline: extract → save JSON → build BPMN → render SVG/PNG.

    Dispatches on `venue` to choose between ArbCom, DRN, and RFC pipelines.
    Each venue has its own extractor (ArbCom uses the rich `extract_detailed_case`
    with regex+LLM merge; DRN/RFC use the generic `extract_venue_case`) and
    its own BPMN builder.
    """
    stem = f"arb_gemma_{safe_filename(title)}"

    if venue == "arb":
        # ArbCom — full hybrid extraction with all the per-section regex parsing
        print(f"\n[{stem}] Extracting detailed ArbCom case structure ...")
        case = extract_detailed_case(loader, text, title, max_input_chars)

        remedies = case.get("remedies", [])
        n_suspended = sum(1 for r in remedies if r.get("suspended"))
        n_ongoing = sum(1 for r in remedies if _is_ongoing_remedy(r))
        n_gateways = (
            1
            + (1 if case.get("has_injunction") else 0)
            + len(case.get("principles", []))
            + len(case.get("findings", []))
            + len(remedies)
            + n_suspended
            + len(case.get("enforcement_actions", []))
            + len(case.get("appeals", []))
            + len(case.get("amendments", []))
            + len(case.get("clarifications", []))
            + len(case.get("post_case_motions", []))
        )
        print(
            f"[{stem}] Built rich lifecycle model:\n"
            f"         type={case.get('case_type', 'conduct')}, "
            f"private={case.get('is_private', False)}, "
            f"pre-case actions={len(case.get('pre_case_actions', []))}\n"
            f"         principles={len(case.get('principles', []))}, "
            f"findings={len(case.get('findings', []))}, "
            f"remedies={len(remedies)} "
            f"(suspended={n_suspended}, ongoing={n_ongoing})\n"
            f"         AE actions={len(case.get('enforcement_actions', []))}, "
            f"appeals={len(case.get('appeals', []))}, "
            f"amendments={len(case.get('amendments', []))}, "
            f"clarifications={len(case.get('clarifications', []))}, "
            f"post-case motions={len(case.get('post_case_motions', []))}\n"
            f"         drafters={len(case.get('drafting_arbitrators', []))}, "
            f"recused={len(case.get('recused_arbitrators', []))}\n"
            f"         rule invocations: {case.get('rule_invocations', {}).get('total_invocations', 0)} "
            f"total, {case.get('rule_invocations', {}).get('unique_rules', 0)} unique "
            f"(top: {', '.join(r['ref'] for r in case.get('rule_invocations', {}).get('top_rules', [])[:3]) or 'none'})\n"
            f"         → ~{n_gateways} gateway branches"
        )
    else:
        # DRN / RFC — generic venue-aware extraction
        case = extract_venue_case(loader, text, title, venue, max_input_chars)
        ri = case.get("rule_invocations", {})
        if venue == "drn":
            phases = case.get("discussion_phases", []) or []
            print(
                f"[{stem}] Built DRN case model:\n"
                f"         filer={case.get('filing_party', '?')}, "
                f"others={len(case.get('other_parties', []) or [])}, "
                f"mediators={len(case.get('volunteer_mediators', []) or [])}\n"
                f"         phases={len(phases)}, "
                f"compromise_proposed={case.get('compromise_proposed', False)}, "
                f"compromise_accepted={case.get('compromise_accepted', False)}\n"
                f"         closure={case.get('closure_type', 'unknown')}, "
                f"escalation={case.get('next_venue_recommended', 'none')}\n"
                f"         rule invocations: {ri.get('total_invocations', 0)} total"
            )
        elif venue == "rfc":
            print(
                f"[{stem}] Built RFC case model:\n"
                f"         proposer={case.get('proposer', '?')}, "
                f"page={case.get('page', '?')}\n"
                f"         votes: {case.get('support_count', 0)}S / "
                f"{case.get('oppose_count', 0)}O / "
                f"{case.get('neutral_count', 0)}N / "
                f"{case.get('alternative_count', 0)}Alt\n"
                f"         consensus={case.get('consensus_finding', 'unknown')}, "
                f"closer={case.get('closer', '?')}, "
                f"appealed={case.get('appealed', False)}\n"
                f"         rule invocations: {ri.get('total_invocations', 0)} total"
            )

    if dry_run:
        print(json.dumps(case, indent=2, default=str))
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}_case.json"
    json_path.write_text(json.dumps(case, indent=2, default=str))
    print(f"[{stem}] Saved case JSON → {json_path}")

    # Build the BPMN appropriate to the venue
    if venue == "arb":
        xml = build_detailed_bpmn(case, use_detailed_lanes=detailed_lanes)
    elif venue == "drn":
        xml = build_drn_bpmn(case)
    elif venue == "rfc":
        xml = build_rfc_bpmn(case)
    else:
        raise ValueError(f"Unknown venue: {venue!r}")

    bpmn_path = output_dir / f"{stem}.bpmn"
    bpmn_path.write_text(xml, encoding="utf-8")
    print(f"[{stem}] Saved BPMN XML  → {bpmn_path}")

    # Render the BPMN to visual formats (always SVG, optionally PNG).
    svg_path = output_dir / f"{stem}.svg"
    png_path = output_dir / f"{stem}.png"
    if render_bpmn_to_svg(bpmn_path, svg_path, case=case):
        print(f"[{stem}] Saved SVG      → {svg_path}")
    if render_bpmn_to_png(bpmn_path, png_path, svg_path=svg_path):
        print(f"[{stem}] Saved PNG      → {png_path}")


# ─────────────────────────────────────────────────────────────────────────────
# SVG renderer — pure Python, no browser or system library dependency
# ─────────────────────────────────────────────────────────────────────────────

# Styling constants for the SVG output. Tweak colors/fonts here — the SVG
# is generated from the .bpmn DI coordinates, so layout geometry is
# already decided by SwimlaneBpmnBuilder; this module only decides visuals.
_SVG_STYLE = {
    "lane_fill": "#ffffff",
    "lane_stroke": "#999999",
    "lane_label_fill": "#f3f3f3",
    "task_fill": "#fdf6e3",
    "task_stroke": "#586e75",
    "user_task_fill": "#eee8d5",
    "gateway_fill": "#fff8dc",
    "gateway_stroke": "#b58900",
    "event_start_fill": "#b4f2a1",
    "event_start_stroke": "#2aa198",
    "event_end_fill": "#f4a8a8",
    "event_end_stroke": "#dc322f",
    "flow_stroke": "#657b83",
    "flow_label_fill": "#073642",
    "text_fill": "#073642",
    "font_family": "Helvetica, Arial, sans-serif",
    "font_size": "11",
    "label_font_size": "9",
    "lane_font_size": "13",
}


def render_bpmn_to_svg(
    bpmn_path: Path,
    svg_path: Path,
    case: dict | None = None,
) -> bool:
    """Convert a BPMN 2.0 XML file to a standalone SVG using only stdlib.

    Walks the BPMN DI (diagram interchange) coordinates that our builder
    already produced, and emits equivalent SVG primitives: rounded rects
    for tasks, diamonds for gateways, circles for events, and polylines
    with labels for flows. No browser, no Chromium, no system libraries.

    Optional `case` parameter: when the full extracted case JSON is passed
    in, the SVG grows a 3-column stats footer (element counts, all
    invoked rules, all namespace links) matching the aggregate view. Without
    `case`, the SVG falls back to a smaller header panel derived from the
    BPMN's start-event <documentation>.

    Returns True on success, False on any parse/render error (the caller
    is expected to continue gracefully).
    """
    from xml.etree import ElementTree as ET

    ns = {
        "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
        "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
        "dc": "http://www.omg.org/spec/DD/20100524/DC",
        "di": "http://www.omg.org/spec/DD/20100524/DI",
    }

    try:
        tree = ET.parse(bpmn_path)
        root = tree.getroot()
    except Exception as exc:
        print(f"  [svg] could not parse BPMN: {exc}")
        return False

    # ── Index every element by id → (kind, name, is_user_task, has_loop) ────
    # This lets us style each DI shape correctly when we encounter its
    # reference. "kind" is the local tag name (task, exclusiveGateway, etc.)
    elements: dict[str, dict] = {}

    def _local(tag: str) -> str:
        return tag.split("}", 1)[1] if "}" in tag else tag

    for proc in root.iter("{%s}process" % ns["bpmn"]):
        for child in proc.iter():
            cid = child.get("id")
            if not cid:
                continue
            kind = _local(child.tag)
            if kind in {
                "task",
                "userTask",
                "manualTask",
                "serviceTask",
                "startEvent",
                "endEvent",
                "intermediateCatchEvent",
                "intermediateThrowEvent",
                "exclusiveGateway",
                "inclusiveGateway",
                "parallelGateway",
                "eventBasedGateway",
                "sequenceFlow",
            }:
                doc_el = child.find("bpmn:documentation", ns)
                doc_text = ""
                if doc_el is not None and doc_el.text:
                    doc_text = doc_el.text.strip()
                elements[cid] = {
                    "kind": kind,
                    "name": child.get("name", "") or "",
                    "user_task": kind == "userTask",
                    "has_loop": bool(
                        child.find("bpmn:standardLoopCharacteristics", ns) is not None
                    ),
                    "doc": doc_text,
                }

    # ── Collect shapes (rects for tasks, etc.) and their bounds ─────────────
    shapes: list[dict] = []
    for shape in root.iter("{%s}BPMNShape" % ns["bpmndi"]):
        ref = shape.get("bpmnElement")
        bounds = shape.find("dc:Bounds", ns)
        if ref is None or bounds is None:
            continue
        try:
            x, y = float(bounds.get("x")), float(bounds.get("y"))
            w, h = float(bounds.get("width")), float(bounds.get("height"))
        except (TypeError, ValueError):
            continue
        meta = elements.get(
            ref, {"kind": "lane", "name": "", "user_task": False, "has_loop": False}
        )
        # Participant and Lane elements aren't in `elements` — detect by DI ref
        if ref.startswith("Participant_"):
            meta = {**meta, "kind": "participant"}
        elif ref.startswith("Lane_"):
            # look up lane name from the bpmn:process laneSet
            for lane in root.iter("{%s}lane" % ns["bpmn"]):
                if lane.get("id") == ref:
                    meta = {
                        "kind": "lane",
                        "name": lane.get("name", "") or "",
                        "user_task": False,
                        "has_loop": False,
                    }
                    break
        shapes.append({"x": x, "y": y, "w": w, "h": h, "ref": ref, **meta})

    # ── Collect edges ───────────────────────────────────────────────────────
    # First, build a map of sequenceFlow id → (sourceRef, targetRef) so we
    # can identify which edges share a source (gateway fan-outs).
    flow_endpoints: dict[str, tuple[str, str]] = {}
    for sf in root.iter("{%s}sequenceFlow" % ns["bpmn"]):
        sf_id = sf.get("id")
        src = sf.get("sourceRef", "") or ""
        tgt = sf.get("targetRef", "") or ""
        if sf_id:
            flow_endpoints[sf_id] = (src, tgt)

    edges: list[dict] = []
    for edge in root.iter("{%s}BPMNEdge" % ns["bpmndi"]):
        ref = edge.get("bpmnElement")
        waypoints = []
        for wp in edge.findall("di:waypoint", ns):
            try:
                waypoints.append((float(wp.get("x")), float(wp.get("y"))))
            except (TypeError, ValueError):
                pass
        if len(waypoints) < 2:
            continue
        # Optional edge label
        label = elements.get(ref, {}).get("name", "") or ""
        label_bounds = edge.find("bpmndi:BPMNLabel/dc:Bounds", ns)
        lx = ly = None
        if label_bounds is not None:
            try:
                lx = float(label_bounds.get("x"))
                ly = float(label_bounds.get("y"))
            except (TypeError, ValueError):
                pass
        src, tgt = flow_endpoints.get(ref, ("", ""))
        edges.append(
            {
                "ref": ref,
                "waypoints": waypoints,
                "label": label,
                "lx": lx,
                "ly": ly,
                "src": src,
                "tgt": tgt,
            }
        )

    # ── Extract case-level metadata from the BPMN ──────────────────────────
    # We build a header panel showing the case title, the rule-invocation
    # summary (which is attached as <documentation> to the start event),
    # and some quick flow stats so the SVG is self-documenting and doesn't
    # require opening the .bpmn in a modeler to see the invocation data.
    case_title = ""
    start_event_doc = ""
    for participant in root.iter("{%s}participant" % ns["bpmn"]):
        case_title = participant.get("name", "") or ""
        break
    # Find the first startEvent and pull its documentation
    for se in root.iter("{%s}startEvent" % ns["bpmn"]):
        se_id = se.get("id")
        if se_id and se_id in elements:
            start_event_doc = elements[se_id].get("doc", "")
        break

    # Count elements for the quick-stats line
    n_tasks = sum(
        1
        for s in shapes
        if s["kind"] in ("task", "userTask", "manualTask", "serviceTask")
    )
    n_gateways = sum(1 for s in shapes if s["kind"].endswith("Gateway"))
    n_end_events = sum(
        1 for s in shapes if s["kind"].endswith("Event") and "end" in s["kind"].lower()
    )
    n_loops = sum(1 for s in shapes if s.get("has_loop"))
    n_lanes = sum(1 for s in shapes if s["kind"] == "lane")

    # ── Compute canvas bounds with a bit of margin ──────────────────────────
    if not shapes and not edges:
        print("  [svg] BPMN contained no shapes or edges")
        return False
    xs = [s["x"] for s in shapes] + [p[0] for e in edges for p in e["waypoints"]]
    ys = [s["y"] for s in shapes] + [p[1] for e in edges for p in e["waypoints"]]
    x2s = [s["x"] + s["w"] for s in shapes] + [
        p[0] for e in edges for p in e["waypoints"]
    ]
    y2s = [s["y"] + s["h"] for s in shapes] + [
        p[1] for e in edges for p in e["waypoints"]
    ]
    margin = 40

    # Layout decision: if we have the full case dict, we emit a brief title
    # header at top and a 3-column stats footer at the bottom. Without the
    # case dict, we fall back to a wider header panel that embeds the rule
    # summary (pulled from the start event's documentation).
    has_full_case = bool(case)
    header_h = 70 if has_full_case else (130 if start_event_doc or case_title else 0)
    footer_h = _compute_case_footer_height(case) if has_full_case else 0

    min_x = min(xs) - margin
    min_y = min(ys) - margin - header_h
    max_x = max(x2s) + margin
    max_y = max(y2s) + margin + footer_h
    width, height = max_x - min_x, max_y - min_y

    # ── Emit the SVG ────────────────────────────────────────────────────────
    style = _SVG_STYLE
    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="{min_x} {min_y} {width} {height}" '
        f'width="{int(width)}" height="{int(height)}" '
        f'font-family="{style["font_family"]}">'
    )
    # Arrowhead marker used by all edges
    out.append(
        "<defs>"
        f'<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{style["flow_stroke"]}"/>'
        "</marker>"
        "</defs>"
    )

    # ── Header info panel ──────────────────────────────────────────────────
    if header_h:
        hx = min_x + 10
        hy = min_y + 10
        hw = width - 20
        hh = header_h - 20
        out.append(
            f'<rect x="{hx}" y="{hy}" width="{hw}" height="{hh}" '
            f'fill="{style["lane_label_fill"]}" '
            f'stroke="{style["lane_stroke"]}" rx="4" ry="4"/>'
        )
        # Title
        if case_title:
            out.append(
                f'<text x="{hx + 15}" y="{hy + 24}" font-size="16" '
                f'font-weight="bold" fill="{style["text_fill"]}">'
                f"{_xml_escape(case_title)}</text>"
            )
        # Quick stats
        stats_line = (
            f"{n_lanes} lanes · {n_tasks} tasks · {n_gateways} gateways · "
            f"{n_end_events} end events · {n_loops} ongoing (↻)"
        )
        out.append(
            f'<text x="{hx + 15}" y="{hy + 44}" font-size="11" '
            f'fill="{style["text_fill"]}">{_xml_escape(stats_line)}</text>'
        )
        # When we don't have the full case dict, embed the start-event doc
        # (rule/namespace summary) directly in the header panel. With case
        # data, this info lives in the richer bottom footer instead.
        if not has_full_case and start_event_doc:
            doc_lines = [ln.strip() for ln in start_event_doc.split("  ") if ln.strip()]
            for i, line in enumerate(doc_lines[:4]):
                out.append(
                    f'<text x="{hx + 15}" y="{hy + 66 + i * 15}" '
                    f'font-size="11" fill="{style["text_fill"]}" '
                    f'font-family="monospace">'
                    f"• {_xml_escape(line[:200])}</text>"
                )

    # Draw participants and lanes first (background)
    for shape in shapes:
        if shape["kind"] not in ("participant", "lane"):
            continue
        x, y, w, h = shape["x"], shape["y"], shape["w"], shape["h"]
        fill = style["lane_fill"]
        stroke = style["lane_stroke"]
        out.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
        )
        # Lane label on a vertical strip at the left edge
        if shape["kind"] == "lane" and shape.get("name"):
            label_w = 28
            out.append(
                f'<rect x="{x}" y="{y}" width="{label_w}" height="{h}" '
                f'fill="{style["lane_label_fill"]}" stroke="{stroke}"/>'
            )
            cx = x + label_w / 2
            cy = y + h / 2
            lane_name = _xml_escape(shape["name"])
            out.append(
                f'<text x="{cx}" y="{cy}" font-size="{style["lane_font_size"]}" '
                f'fill="{style["text_fill"]}" text-anchor="middle" '
                f'transform="rotate(-90 {cx} {cy})">{lane_name}</text>'
            )

    # Pre-compute, for each source node, the list of outgoing edges in
    # render order. We use the edge's index within that list to vertically
    # stagger labels on a fan-out (one gateway → many end events). Without
    # this stagger, every polyline goes through ~the same first leg before
    # fanning to its target, so all labels land at the same screen location.
    out_edges_by_source: dict[str, list[int]] = {}
    for i, edge in enumerate(edges):
        out_edges_by_source.setdefault(edge["src"], []).append(i)

    # Draw edges next (so they render beneath node foregrounds)
    for i, edge in enumerate(edges):
        pts = " ".join(f"{x},{y}" for x, y in edge["waypoints"])
        out.append(
            f'<polyline points="{pts}" fill="none" '
            f'stroke="{style["flow_stroke"]}" stroke-width="1.5" '
            'marker-end="url(#arrow)"/>'
        )
        if edge["label"]:
            lx = edge["lx"]
            ly = edge["ly"]
            if lx is None or ly is None:
                # Anchor the label very close to the source exit point. For
                # single-outflow edges (e.g. task → gateway) 25% along is
                # plenty. For fan-outs (gateway → N end events), all the
                # outgoing polylines start from the same point and travel
                # through nearly the same first segment before splitting,
                # so 25% of each polyline lands at the same screen spot.
                # We anchor at the source itself and stagger siblings
                # vertically to keep them distinct.
                wp = edge["waypoints"]
                siblings = out_edges_by_source.get(edge["src"], [edge])
                # Index within the source's outgoing fan
                try:
                    sibling_idx = siblings.index(i)
                except ValueError:
                    sibling_idx = 0
                n_siblings = len(siblings)

                if len(wp) >= 2:
                    p1 = wp[0]
                    p2 = wp[1]
                    # 8% along the first leg — well clear of any target
                    base_lx = p1[0] + (p2[0] - p1[0]) * 0.08
                    base_ly = p1[1] + (p2[1] - p1[1]) * 0.08
                else:
                    base_lx, base_ly = wp[0]

                # Vertical stagger when the source fans to >1 children.
                # Each sibling label gets 14px of vertical separation, which
                # is roughly one line of label-font-size text.
                if n_siblings > 1:
                    stagger_offset = (sibling_idx - (n_siblings - 1) / 2) * 14
                    ly = base_ly + stagger_offset - 4
                else:
                    ly = base_ly - 4
                lx = base_lx
            label = _xml_escape(edge["label"][:40])
            # White stroke halo behind the text so it remains readable when
            # polylines pass through it — important when fan-out labels
            # cluster near the gateway and the fan polylines criss-cross
            # behind them.
            out.append(
                f'<text x="{lx}" y="{ly}" font-size="{style["label_font_size"]}" '
                f'fill="{style["flow_label_fill"]}" '
                f'paint-order="stroke" stroke="{style["lane_fill"]}" '
                f'stroke-width="3">{label}</text>'
            )

    # Draw nodes (tasks, gateways, events) on top
    for shape in shapes:
        if shape["kind"] in ("participant", "lane"):
            continue
        x, y, w, h = shape["x"], shape["y"], shape["w"], shape["h"]
        kind = shape["kind"]
        # Keep `name` raw here — each use site below escapes once. Pre-escaping
        # and then passing to _wrap_text_svg (which also escapes) would
        # double-escape entities (&amp; → &amp;amp;).
        name = shape.get("name", "") or ""
        cx, cy = x + w / 2, y + h / 2

        if kind in ("task", "userTask", "manualTask", "serviceTask"):
            fill = style["user_task_fill"] if kind == "userTask" else style["task_fill"]
            out.append(
                f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" ry="6" '
                f'fill="{fill}" stroke="{style["task_stroke"]}" stroke-width="1.5"/>'
            )
            if shape.get("has_loop"):
                # BPMN loop marker: ↻ in the bottom-center of the task
                out.append(
                    f'<text x="{cx}" y="{y + h - 4}" '
                    f'font-size="14" text-anchor="middle" '
                    f'fill="{style["task_stroke"]}">↻</text>'
                )
            out.append(_wrap_text_svg(name, cx, cy, w - 12, style))

        elif kind.endswith("Gateway"):
            # Diamond: 4-point polygon around the shape center
            points = (
                f"{x + w / 2},{y} "
                f"{x + w},{y + h / 2} "
                f"{x + w / 2},{y + h} "
                f"{x},{y + h / 2}"
            )
            out.append(
                f'<polygon points="{points}" '
                f'fill="{style["gateway_fill"]}" '
                f'stroke="{style["gateway_stroke"]}" stroke-width="1.5"/>'
            )
            # × mark for exclusive gateways
            if kind == "exclusiveGateway":
                out.append(
                    f'<text x="{cx}" y="{cy + 5}" font-size="16" '
                    f'text-anchor="middle" fill="{style["gateway_stroke"]}" '
                    'font-weight="bold">×</text>'
                )
            # Label below the gateway
            if name:
                out.append(
                    f'<text x="{cx}" y="{y + h + 14}" '
                    f'font-size="{style["font_size"]}" text-anchor="middle" '
                    f'fill="{style["text_fill"]}">{_xml_escape(name)}</text>'
                )

        elif kind.endswith("Event"):
            radius = min(w, h) / 2
            is_end = "end" in kind.lower()
            fill = style["event_end_fill"] if is_end else style["event_start_fill"]
            stroke = (
                style["event_end_stroke"] if is_end else style["event_start_stroke"]
            )
            stroke_w = 3 if is_end else 2  # thick border = end per BPMN spec
            out.append(
                f'<circle cx="{cx}" cy="{cy}" r="{radius}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}"/>'
            )
            # Wrapped label below the event. Without wrapping, long end-event
            # names like "Strong consensus to SUPPORT — implement" extend
            # past the column width (170 px) and overflow into adjacent
            # event labels. Wrap to ~22 chars per line; allow up to 4 lines.
            if name:
                # Centre the label block under the circle. _wrap_text_svg
                # centers around (cx, cy) by default, but for events we want
                # the text BELOW the circle, so push cy down by radius + half
                # the expected text block height.
                approx_lines = min(max(1, len(name) // 22 + 1), 4)
                label_cy = y + h + 7 + (approx_lines * 13) / 2
                out.append(_wrap_text_svg(name, cx, label_cy, _STEP_GAP - 20, style))

    # ── 3-column stats footer (only when a case dict was supplied) ──────────
    if has_full_case and footer_h:
        fy = max_y - footer_h + 10
        fx = min_x + 10
        fw = width - 20
        fh = footer_h - 20
        out.extend(_build_case_footer_svg(case, fx, fy, fw, fh, style))

    out.append("</svg>")

    try:
        svg_path.write_text("\n".join(out), encoding="utf-8")
        return True
    except OSError as exc:
        print(f"  [svg] could not write: {exc}")
        return False


def _xml_escape(s: str) -> str:
    """Escape &, <, >, ", ' for safe SVG text content."""
    return (
        (s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _wrap_text_svg(
    text: str,
    cx: float,
    cy: float,
    max_width: float,
    style: dict,
) -> str:
    """Emit SVG <text> with crude word-wrapping to fit a box width.

    Uses ~6 px/char as an average glyph width — good enough for the small
    labels on BPMN shapes. Wraps onto up to 4 lines; truncates with '…'
    if the text overflows.
    """
    if not text:
        return ""
    chars_per_line = max(int(max_width / 6), 8)
    words = text.split()
    lines: list[str] = []
    buf = ""
    for w in words:
        candidate = f"{buf} {w}".strip()
        if len(candidate) <= chars_per_line:
            buf = candidate
        else:
            if buf:
                lines.append(buf)
            if len(w) > chars_per_line:
                # Break very long single words
                lines.append(w[: chars_per_line - 1] + "…")
                buf = ""
            else:
                buf = w
        if len(lines) >= 4:
            break
    if buf and len(lines) < 4:
        lines.append(buf)
    if len(lines) == 4 and words:
        # If we cut off, mark the last line
        lines[-1] = lines[-1][: chars_per_line - 1] + "…"

    line_h = 13
    total_h = line_h * len(lines)
    start_y = cy - total_h / 2 + line_h * 0.75
    parts = [
        f'<text font-size="{style["font_size"]}" text-anchor="middle" '
        f'fill="{style["text_fill"]}">'
    ]
    for i, line in enumerate(lines):
        parts.append(
            f'<tspan x="{cx}" y="{start_y + i * line_h}">{_xml_escape(line)}</tspan>'
        )
    parts.append("</text>")
    return "".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Per-case rich footer — 3-column panel showing element counts, all invoked
# rules, and all namespace links for ONE case. Visual match to the aggregate
# footer so single-case and corpus diagrams share a consistent look.
# ─────────────────────────────────────────────────────────────────────────────


def _compute_case_footer_height(case: dict | None) -> int:
    """Size the footer to fit the longest of the 3 columns without truncation.

    The footer always has 3 columns (elements, rules, namespaces). Height is
    driven by the longest column so everything fits on-screen. Conservative
    padding ensures the rule type breakdown sub-heading and legend don't
    overflow.
    """
    if not case:
        return 0
    ri = case.get("rule_invocations", {}) or {}
    n_rules = len(ri.get("top_rules", []) or [])
    n_ns = len(ri.get("namespace_links", []) or [])
    # Column 1 always has ~11 fixed lines of element counts.
    lines_per_col = max(11, n_rules + 2, n_ns + 1)
    row_px = 13
    return 60 + lines_per_col * row_px + 40  # title + body + padding


def _build_case_footer_svg(
    case: dict,
    fx: float,
    fy: float,
    fw: float,
    fh: float,
    style: dict,
) -> list[str]:
    """Emit a 3-column stats footer for a single case.

    Columns:
      1. Element counts  — parties, principles, findings, remedies, amendments,
         appeals, enforcement actions, clarifications, post-case motions,
         injunctions, pre-case actions.
      2. Rule invocations — total count + type breakdown + full list of
         every invoked rule (not just top 5) with counts.
      3. Namespace links — every namespace encountered with its link count
         and percentage share. Users/Main/Talk dominance is the top-level
         signal for case character (conduct vs content).
    """
    out: list[str] = []
    out.append(
        f'<rect x="{fx}" y="{fy}" width="{fw}" height="{fh}" '
        f'fill="{style["lane_label_fill"]}" '
        f'stroke="{style["lane_stroke"]}" rx="4" ry="4"/>'
    )

    col_w = (fw - 40) / 3
    col1_x = fx + 14
    col2_x = col1_x + col_w
    col3_x = col2_x + col_w
    hy = fy + 22
    body_font = 11
    body_line_h = 13

    def _heading(x: float, text: str) -> None:
        out.append(
            f'<text x="{x}" y="{hy}" font-size="13" font-weight="bold" '
            f'fill="{style["text_fill"]}">{_xml_escape(text)}</text>'
        )

    def _row(
        x: float, y: float, text: str, bold: bool = False, size: int = body_font
    ) -> None:
        weight = ' font-weight="bold"' if bold else ""
        out.append(
            f'<text x="{x}" y="{y}" font-size="{size}"{weight} '
            f'font-family="monospace" fill="{style["text_fill"]}">'
            f"{_xml_escape(text)}</text>"
        )

    # ── Column 1: element counts ────────────────────────────────────────────
    _heading(col1_x, "Case element counts")

    # Build element-count rows with consistent label width so numbers align
    # regardless of label length.
    def _fmt(label: str, value: object) -> str:
        return f"{label + ':':<24} {value}"

    lines1 = [
        _fmt("Parties", len(case.get("parties", []) or [])),
        _fmt("Principles", len(case.get("principles", []) or [])),
        _fmt("Findings of fact", len(case.get("findings", []) or [])),
        _fmt("Remedies", len(case.get("remedies", []) or [])),
        _fmt("Amendments", len(case.get("amendments", []) or [])),
        _fmt("Appeals", len(case.get("appeals", []) or [])),
        _fmt("Enforcement actions", len(case.get("enforcement_actions", []) or [])),
        _fmt("Clarifications", len(case.get("clarifications", []) or [])),
        _fmt("Post-case motions", len(case.get("post_case_motions", []) or [])),
        _fmt("Pre-case actions", len(case.get("pre_case_actions", []) or [])),
        _fmt("Injunction issued", "yes" if case.get("has_injunction") else "no"),
        _fmt("Drafting arbitrators", len(case.get("drafting_arbitrators", []) or [])),
        _fmt("Recused arbitrators", len(case.get("recused_arbitrators", []) or [])),
        _fmt("Case outcome", case.get("outcome", "Unknown")),
    ]
    # Vote summary is a separate block, visually offset
    ab = case.get("accept_votes", 0) or 0
    dec = case.get("decline_votes", 0) or 0
    rec = case.get("recuse_votes", 0) or 0
    abs_v = case.get("abstain_votes", 0) or 0
    net = case.get("net_votes", 0) or 0
    lines1.append(f"Accept votes:  {ab}A / {dec}D / {rec}R / {abs_v}Ab (net={net:+})")
    for i, line in enumerate(lines1):
        _row(col1_x, hy + 20 + i * body_line_h, line)

    # ── Column 2: all invoked rules ─────────────────────────────────────────
    ri = case.get("rule_invocations", {}) or {}
    total_inv = ri.get("total_invocations", 0)
    n_unique = ri.get("unique_rules", 0)
    _heading(col2_x, f"Invoked rules ({total_inv:,} total, {n_unique} unique)")
    # Type breakdown sub-line
    bt = ri.get("by_type", {}) or {}
    by_type_str = (
        f"policies: {bt.get('policy', 0)}, "
        f"guidelines: {bt.get('guideline', 0)}, "
        f"essays: {bt.get('essay', 0)}, "
        f"other: {bt.get('other', 0)}"
    )
    out.append(
        f'<text x="{col2_x}" y="{hy + 16}" font-size="10" '
        f'fill="{style["text_fill"]}" font-style="italic">'
        f"{_xml_escape(by_type_str)}</text>"
    )
    rules = ri.get("top_rules", []) or []
    for i, r in enumerate(rules):
        ref = r.get("ref", "?")
        cnt = r.get("count", 0)
        rtype = r.get("type", "other")
        # Abbreviate type to a single char in monospace column
        t_abbrev = {"policy": "P", "guideline": "G", "essay": "E", "other": "·"}.get(
            rtype, "?"
        )
        line = f"{t_abbrev} {ref:<22} × {cnt}"
        _row(col2_x, hy + 32 + i * body_line_h, line[:40])

    # If no rules detected, show a placeholder
    if not rules:
        _row(col2_x, hy + 32, "(no rule invocations detected)")

    # ── Column 3: namespace distribution ────────────────────────────────────
    _heading(col3_x, "Evidence namespaces")
    ns_list = ri.get("namespace_links", []) or []
    ns_total = sum(n.get("count", 0) for n in ns_list) or 1
    for i, n_ in enumerate(ns_list):
        name = n_.get("namespace", "?")
        count = n_.get("count", 0)
        pct = count / ns_total * 100
        line = f"{name:<16} {count:>5,} ({pct:4.1f}%)"
        _row(col3_x, hy + 20 + i * body_line_h, line[:36])
    if not ns_list:
        _row(col3_x, hy + 20, "(no namespace links detected)")
    else:
        # Legend at the bottom of the namespace column
        legend_y = hy + 20 + (len(ns_list) + 1) * body_line_h
        out.append(
            f'<text x="{col3_x}" y="{legend_y}" font-size="9" '
            f'fill="{style["text_fill"]}" font-style="italic">'
            f"User/User_talk ⇒ conduct; Main/Talk ⇒ content dispute</text>"
        )

    return out


def render_bpmn_to_png(
    bpmn_path: Path,
    png_path: Path,
    svg_path: Path | None = None,
) -> bool:
    """
    Render a BPMN 2.0 XML file to PNG using whatever renderer is available.

    Tries, in order:
      1. `bpmn-to-image` CLI (Node.js + Chromium via Puppeteer).
      2. `npx bpmn-to-image` (on-demand).
      3. `cairosvg` (pure Python, if svg_path is provided and file exists).

    Returns True on success, False otherwise. Never raises. If all three
    fail, the .svg is still available as a viewable artifact.
    """
    if getattr(render_bpmn_to_png, "_disabled", False):
        return False

    import shutil
    import subprocess

    cli = shutil.which("bpmn-to-image")
    npx = shutil.which("npx")
    renderer_found = bool(cli or npx)
    renderer_failed = False

    def _show_error(label: str, exc: Exception) -> None:
        """Print a truncated but useful error so the user can diagnose."""
        if isinstance(exc, subprocess.CalledProcessError):
            stderr_snippet = ""
            if exc.stderr:
                text = (
                    exc.stderr.decode("utf-8", errors="replace")
                    if isinstance(exc.stderr, bytes)
                    else exc.stderr
                )
                stderr_snippet = text.strip()[-800:]
            print(f"  [png] {label} exited with status {exc.returncode}")
            if stderr_snippet:
                print(f"  [png] stderr:\n{stderr_snippet}")
        else:
            print(f"  [png] {label}: {exc}")

    # Path 1: bpmn-to-image CLI
    if cli:
        try:
            subprocess.run(
                [cli, f"{bpmn_path}:{png_path}"],
                check=True,
                capture_output=True,
                timeout=120,
            )
            if png_path.exists():
                return True
            renderer_failed = True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            _show_error("bpmn-to-image", exc)
            renderer_failed = True

    # Path 2: npx on demand — skip if CLI already failed (same underlying code)
    if npx and not renderer_failed:
        try:
            subprocess.run(
                [npx, "-y", "bpmn-to-image", f"{bpmn_path}:{png_path}"],
                check=True,
                capture_output=True,
                timeout=180,
            )
            if png_path.exists():
                return True
            renderer_failed = True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            _show_error("npx bpmn-to-image", exc)
            renderer_failed = True

    # Path 3: cairosvg — convert our SVG to PNG. Pure Python with a
    # small native dep (cairo); doesn't need Chromium.
    if svg_path is not None and svg_path.exists():
        try:
            import cairosvg  # type: ignore
        except ImportError:
            if renderer_found:
                # Chromium failed; tell user about the cairosvg alternative.
                print(
                    "  [png] BPMN-to-image renderer crashed, and cairosvg is\n"
                    "        not installed as a fallback. Two options:\n"
                    "          (a) pip install cairosvg   # pure Python, no sudo\n"
                    "          (b) sudo apt install libnspr4 libnss3  # fix Chromium\n"
                    "        The .svg file is saved regardless and works in any\n"
                    "        browser, image viewer, or vector editor."
                )
                render_bpmn_to_png._disabled = True  # type: ignore[attr-defined]
            else:
                # Nothing installed — cairosvg is the simplest path.
                print(
                    "  [png] No PNG renderer available.\n"
                    "        For quick setup (no sudo):\n"
                    "            pip install cairosvg\n"
                    "        The .svg file is already saved and is fully\n"
                    "        viewable in any browser or vector editor."
                )
                render_bpmn_to_png._disabled = True  # type: ignore[attr-defined]
            return False
        try:
            # Render at 2x scale for nicer quality on screen
            cairosvg.svg2png(
                url=str(svg_path),
                write_to=str(png_path),
                output_width=None,
                scale=2.0,
            )
            if png_path.exists():
                return True
        except Exception as exc:
            print(f"  [png] cairosvg conversion failed: {exc}")

    if not renderer_found and (svg_path is None or not svg_path.exists()):
        # Hit if SVG rendering also failed.
        print(
            "  [png] No BPMN renderer found — skipping PNG generation.\n"
            "        Install either:  pip install cairosvg\n"
            "                     or: npm install -g bpmn-to-image"
        )
        render_bpmn_to_png._disabled = True  # type: ignore[attr-defined]
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Aggregate workflow — ingest N _case.json files → one corpus-level SVG
# ─────────────────────────────────────────────────────────────────────────────


def _load_aggregate_cases(agg_dir: Path) -> list[dict]:
    """Load every *_case.json in the directory as a list of case dicts.

    Skips malformed files with a warning — a corpus of 485 cases shouldn't
    fail wholesale if one file got corrupted.
    """
    cases: list[dict] = []
    for p in sorted(agg_dir.glob("*_case.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                cases.append(json.load(f))
        except Exception as exc:
            print(f"  [agg] skipping {p.name}: {exc}")
    return cases


def _aggregate_metrics(cases: list[dict]) -> dict:
    """Compute all corpus-level metrics from the per-case JSON files.

    Everything needed by the aggregate SVG flows through this single dict.
    Adding a new metric is a matter of extending this function and
    referencing the new key in _build_aggregate_svg.
    """
    from collections import Counter

    n = len(cases)
    if n == 0:
        return {}

    # ── Outcome distribution ────────────────────────────────────────────────
    outcomes = Counter(c.get("outcome", "Unknown") or "Unknown" for c in cases)
    outcome_pct = {k: (v / n * 100.0) for k, v in outcomes.items()}

    # ── Case-type distribution ──────────────────────────────────────────────
    case_types = Counter(c.get("case_type", "conduct") or "conduct" for c in cases)
    private_count = sum(1 for c in cases if c.get("is_private"))

    # ── Element averages ────────────────────────────────────────────────────
    def _avg(key: str) -> float:
        vals = [len(c.get(key, []) or []) for c in cases]
        return sum(vals) / n if n else 0.0

    avg_parties = _avg("parties")
    avg_principles = _avg("principles")
    avg_findings = _avg("findings")
    avg_remedies = _avg("remedies")
    avg_amendments = _avg("amendments")
    avg_appeals = _avg("appeals")
    avg_enforcement = _avg("enforcement_actions")
    avg_clarifications = _avg("clarifications")
    avg_postcase = _avg("post_case_motions")
    injunction_count = sum(1 for c in cases if c.get("has_injunction"))
    pre_case_count = sum(1 for c in cases if c.get("pre_case_actions"))

    # ── Aggregate rule invocations across the corpus ────────────────────────
    rule_totals: Counter = Counter()
    rule_type_counts: Counter = Counter()
    namespace_totals: Counter = Counter()
    total_invocations = 0
    for c in cases:
        ri = c.get("rule_invocations", {}) or {}
        total_invocations += ri.get("total_invocations", 0)
        for r in ri.get("top_rules", []) or []:
            rule_totals[r.get("ref", "?")] += r.get("count", 0)
            rule_type_counts[r.get("type", "other")] += r.get("count", 0)
        for ns in ri.get("namespace_links", []) or []:
            namespace_totals[ns.get("namespace", "?")] += ns.get("count", 0)
    top_rules = rule_totals.most_common(15)
    top_namespaces = namespace_totals.most_common(10)

    # ── Vote behaviour averages ─────────────────────────────────────────────
    accept_votes = [c.get("accept_votes", 0) or 0 for c in cases]
    decline_votes = [c.get("decline_votes", 0) or 0 for c in cases]
    avg_accept = sum(accept_votes) / n if n else 0.0
    avg_decline = sum(decline_votes) / n if n else 0.0

    # ── Drafter / recused arbitrator averages ───────────────────────────────
    avg_drafters = _avg("drafting_arbitrators")
    avg_recused = _avg("recused_arbitrators")

    return {
        "n_cases": n,
        "outcomes": outcomes,
        "outcome_pct": outcome_pct,
        "case_types": case_types,
        "private_count": private_count,
        "avg_parties": avg_parties,
        "avg_principles": avg_principles,
        "avg_findings": avg_findings,
        "avg_remedies": avg_remedies,
        "avg_amendments": avg_amendments,
        "avg_appeals": avg_appeals,
        "avg_enforcement": avg_enforcement,
        "avg_clarifications": avg_clarifications,
        "avg_postcase": avg_postcase,
        "injunction_count": injunction_count,
        "pre_case_count": pre_case_count,
        "total_invocations": total_invocations,
        "rule_type_counts": rule_type_counts,
        "top_rules": top_rules,
        "top_namespaces": top_namespaces,
        "avg_accept_votes": avg_accept,
        "avg_decline_votes": avg_decline,
        "avg_drafters": avg_drafters,
        "avg_recused": avg_recused,
    }


def _build_aggregate_svg(m: dict) -> str:
    """Build a corpus-level SVG process diagram with enriched annotations.

    Structure mirrors the per-case model's overall shape — swimlanes,
    phased flow, decision gateways — but condenses every voting gateway
    down to summary percentages. All computed metrics (outcomes, rule
    invocations, namespaces, case types) render in-diagram as labels,
    annotations on tasks, and a data-dense footer. Pure SVG, no deps.
    """
    style = _SVG_STYLE
    n = m["n_cases"]

    # Canvas & lane geometry
    lane_names = [
        "Requesting Party",
        "Clerk",
        "Drafting Arbitrators",
        "Full Committee",
        "Enforcement",
    ]
    lane_h = 130
    lane_label_w = 30
    top_pad = 70  # title bar
    footer_h = 190  # stats/rules/namespaces
    left_pad = 40

    width = 1800
    lanes_y = top_pad
    total_lane_h = lane_h * len(lane_names)
    height = top_pad + total_lane_h + footer_h

    out: list[str] = []
    out.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" font-family="{style["font_family"]}">'
    )
    out.append(
        "<defs>"
        f'<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{style["flow_stroke"]}"/>'
        "</marker>"
        "</defs>"
    )

    # ── Title bar ───────────────────────────────────────────────────────────
    out.append(
        f'<text x="{left_pad}" y="32" font-size="20" font-weight="bold" '
        f'fill="{style["text_fill"]}">'
        f"ArbCom Aggregate Workflow — {n} cases</text>"
    )
    # Case-type breakdown in subtitle
    types_str = ", ".join(
        f"{k}: {v} ({v / n * 100:.1f}%)" for k, v in m["case_types"].most_common()
    )
    out.append(
        f'<text x="{left_pad}" y="54" font-size="12" '
        f'fill="{style["text_fill"]}">Case types: {types_str}  '
        f"(private: {m['private_count']})</text>"
    )

    # ── Swimlanes ───────────────────────────────────────────────────────────
    for i, name in enumerate(lane_names):
        y = lanes_y + i * lane_h
        out.append(
            f'<rect x="{left_pad}" y="{y}" width="{width - left_pad}" '
            f'height="{lane_h}" fill="{style["lane_fill"]}" '
            f'stroke="{style["lane_stroke"]}"/>'
        )
        out.append(
            f'<rect x="{left_pad}" y="{y}" width="{lane_label_w}" '
            f'height="{lane_h}" fill="{style["lane_label_fill"]}" '
            f'stroke="{style["lane_stroke"]}"/>'
        )
        cx = left_pad + lane_label_w / 2
        cy = y + lane_h / 2
        out.append(
            f'<text x="{cx}" y="{cy}" font-size="{style["lane_font_size"]}" '
            f'fill="{style["text_fill"]}" text-anchor="middle" '
            f'transform="rotate(-90 {cx} {cy})">{_xml_escape(name)}</text>'
        )

    # Lane Y-center helpers
    def lane_cy(idx: int) -> float:
        return lanes_y + idx * lane_h + lane_h / 2

    # ── Build the flow: start → submit → screen → accept? → evidence →
    #    workshop → principles-summary → findings-summary → remedies-summary
    #    → final → enforcement → outcome-gateway → 3 end events ─────────────

    # Coordinate cursor for the main flow
    x = left_pad + 90

    def _task(
        label: str, lane_idx: int, w: int = 150, h: int = 60, annot: str = ""
    ) -> tuple[float, float]:
        """Emit a rounded task rectangle. Returns right-edge anchor for flow."""
        nonlocal x
        cy = lane_cy(lane_idx)
        tx, ty = x, cy - h / 2
        out.append(
            f'<rect x="{tx}" y="{ty}" width="{w}" height="{h}" rx="6" ry="6" '
            f'fill="{style["user_task_fill"]}" stroke="{style["task_stroke"]}" '
            f'stroke-width="1.5"/>'
        )
        out.append(_wrap_text_svg(label, tx + w / 2, cy, w - 10, style))
        if annot:
            out.append(
                f'<text x="{tx + w / 2}" y="{ty + h + 14}" font-size="10" '
                f'text-anchor="middle" fill="{style["text_fill"]}">'
                f"{_xml_escape(annot)}</text>"
            )
        right = (tx + w, cy)
        x = tx + w + 50
        return right

    def _gateway(label: str, lane_idx: int, annot: str = "") -> tuple[float, float]:
        nonlocal x
        cy = lane_cy(lane_idx)
        size = 50
        tx, ty = x, cy - size / 2
        points = (
            f"{tx + size / 2},{ty} {tx + size},{ty + size / 2} "
            f"{tx + size / 2},{ty + size} {tx},{ty + size / 2}"
        )
        out.append(
            f'<polygon points="{points}" fill="{style["gateway_fill"]}" '
            f'stroke="{style["gateway_stroke"]}" stroke-width="1.5"/>'
        )
        out.append(
            f'<text x="{tx + size / 2}" y="{cy + 5}" font-size="16" '
            f'text-anchor="middle" fill="{style["gateway_stroke"]}" '
            f'font-weight="bold">×</text>'
        )
        out.append(
            f'<text x="{tx + size / 2}" y="{ty + size + 14}" font-size="11" '
            f'text-anchor="middle" fill="{style["text_fill"]}">'
            f"{_xml_escape(label)}</text>"
        )
        if annot:
            out.append(
                f'<text x="{tx + size / 2}" y="{ty + size + 28}" font-size="9" '
                f'text-anchor="middle" fill="{style["text_fill"]}">'
                f"{_xml_escape(annot)}</text>"
            )
        right = (tx + size, cy)
        x = tx + size + 50
        return right

    def _event(
        label: str, lane_idx: int, is_end: bool = False, annot: str = ""
    ) -> tuple[float, float]:
        nonlocal x
        cy = lane_cy(lane_idx)
        r = 20
        cx_ = x + r
        fill = style["event_end_fill"] if is_end else style["event_start_fill"]
        stroke = style["event_end_stroke"] if is_end else style["event_start_stroke"]
        stroke_w = 3 if is_end else 2
        out.append(
            f'<circle cx="{cx_}" cy="{cy}" r="{r}" fill="{fill}" '
            f'stroke="{stroke}" stroke-width="{stroke_w}"/>'
        )
        out.append(
            f'<text x="{cx_}" y="{cy + r + 14}" font-size="11" '
            f'text-anchor="middle" fill="{style["text_fill"]}">'
            f"{_xml_escape(label)}</text>"
        )
        if annot:
            out.append(
                f'<text x="{cx_}" y="{cy + r + 28}" font-size="9" '
                f'text-anchor="middle" fill="{style["text_fill"]}">'
                f"{_xml_escape(annot)}</text>"
            )
        x = cx_ + r + 50
        return (cx_ + r, cy)

    def _flow(a: tuple[float, float], b: tuple[float, float], label: str = "") -> None:
        out.append(
            f'<polyline points="{a[0]},{a[1]} {b[0]},{b[1]}" fill="none" '
            f'stroke="{style["flow_stroke"]}" stroke-width="1.5" '
            f'marker-end="url(#arrow)"/>'
        )
        if label:
            mx = (a[0] + b[0]) / 2
            my = (a[1] + b[1]) / 2 - 4
            out.append(
                f'<text x="{mx}" y="{my}" font-size="10" '
                f'fill="{style["flow_label_fill"]}">{_xml_escape(label)}</text>'
            )

    # Flow construction
    start = _event("Case Opened", 0)
    submit = _task(
        "Submit Arbitration Request",
        0,
        annot=f"avg parties: {m['avg_parties']:.1f}",
    )
    _flow(start, submit)

    screen = _task(
        "Clerk Screens Request",
        1,
        annot=f"pre-case emergency actions: {m['pre_case_count']}",
    )
    _flow(submit, screen)

    # Accept gateway
    accept_gw = _gateway(
        "Case Accepted?",
        1,
        annot=f"avg {m['avg_accept_votes']:.1f}A / {m['avg_decline_votes']:.1f}D",
    )
    _flow(screen, accept_gw)

    # Injunction indicator — shown as an annotation on the flow out of accept
    evidence = _task(
        "Evidence Phase",
        2,
        annot=(
            f"injunctions: {m['injunction_count']} of {n} "
            f"({m['injunction_count'] / n * 100:.1f}%)"
        ),
    )
    _flow(accept_gw, evidence, "Yes — accepted")

    workshop = _task(
        "Workshop & Drafting",
        2,
        annot=f"avg drafters: {m['avg_drafters']:.1f}, recused: {m['avg_recused']:.1f}",
    )
    _flow(evidence, workshop)

    # Collapsed principles / findings / remedies — each labeled with averages
    principles = _task(
        "Vote on Principles",
        3,
        annot=f"avg {m['avg_principles']:.1f} principles per case",
    )
    _flow(workshop, principles)

    findings = _task(
        "Vote on Findings",
        3,
        annot=f"avg {m['avg_findings']:.1f} findings per case",
    )
    _flow(principles, findings)

    remedies = _task(
        "Vote on Remedies",
        3,
        annot=f"avg {m['avg_remedies']:.1f} remedies per case",
    )
    _flow(findings, remedies)

    final = _task("Final Decision Published", 3)
    _flow(remedies, final)

    enforce = _task(
        "Enforcement & Amendments",
        4,
        annot=(
            f"avg AE: {m['avg_enforcement']:.1f}, "
            f"appeals: {m['avg_appeals']:.1f}, "
            f"amendments: {m['avg_amendments']:.1f}, "
            f"clarifications: {m['avg_clarifications']:.1f}"
        ),
    )
    _flow(final, enforce)

    # Outcome gateway — one end event per outcome class, with percentages
    outcome_gw = _gateway("Case Outcome?", 4)
    _flow(enforce, outcome_gw)

    # Draw all outcome branches stacked vertically to the right of the gateway
    outcome_items = sorted(m["outcome_pct"].items(), key=lambda kv: -kv[1])
    branch_base_y = lane_cy(4)
    branch_start_x = outcome_gw[0] + 50
    branch_x = branch_start_x
    n_outcomes = len(outcome_items)
    vertical_spread = 100
    for i, (outcome, pct) in enumerate(outcome_items):
        # stack outcomes vertically near the enforcement lane
        offset = (i - (n_outcomes - 1) / 2) * vertical_spread
        cy = branch_base_y + offset
        # branch line from gateway to each end event
        out.append(
            f'<polyline points="{outcome_gw[0]},{outcome_gw[1]} '
            f"{branch_x - 10},{outcome_gw[1]} "
            f"{branch_x - 10},{cy} "
            f'{branch_x + 10},{cy}" fill="none" '
            f'stroke="{style["flow_stroke"]}" stroke-width="1.5" '
            f'marker-end="url(#arrow)"/>'
        )
        # branch label on the horizontal segment
        out.append(
            f'<text x="{outcome_gw[0] + 10}" y="{outcome_gw[1] - 4 + offset * 0.15}" '
            f'font-size="10" fill="{style["flow_label_fill"]}">'
            f"{_xml_escape(outcome)}</text>"
        )
        # end event circle
        r = 22
        cx_ = branch_x + 20 + r
        out.append(
            f'<circle cx="{cx_}" cy="{cy}" r="{r}" '
            f'fill="{style["event_end_fill"]}" '
            f'stroke="{style["event_end_stroke"]}" stroke-width="3"/>'
        )
        out.append(
            f'<text x="{cx_}" y="{cy + r + 14}" font-size="11" '
            f'text-anchor="middle" font-weight="bold" '
            f'fill="{style["text_fill"]}">{pct:.1f}%</text>'
        )
        out.append(
            f'<text x="{cx_}" y="{cy + r + 28}" font-size="10" '
            f'text-anchor="middle" fill="{style["text_fill"]}">'
            f"{_xml_escape(outcome)}</text>"
        )

    # ── Footer: the data-dense corpus metrics ───────────────────────────────
    fy = lanes_y + total_lane_h + 20
    out.append(
        f'<rect x="{left_pad}" y="{fy}" width="{width - left_pad - 20}" '
        f'height="{footer_h - 30}" fill="{style["lane_label_fill"]}" '
        f'stroke="{style["lane_stroke"]}" rx="4" ry="4"/>'
    )
    # Three columns inside the footer
    col_w = (width - left_pad - 40) / 3
    col1_x = left_pad + 12
    col2_x = col1_x + col_w
    col3_x = col2_x + col_w
    hy = fy + 20

    # Column 1: overall element averages + corpus scale
    out.append(
        f'<text x="{col1_x}" y="{hy}" font-size="13" font-weight="bold" '
        f'fill="{style["text_fill"]}">Case element averages</text>'
    )
    lines1 = [
        f"Parties per case:       {m['avg_parties']:.1f}",
        f"Principles per case:    {m['avg_principles']:.1f}",
        f"Findings per case:      {m['avg_findings']:.1f}",
        f"Remedies per case:      {m['avg_remedies']:.1f}",
        f"Amendments per case:    {m['avg_amendments']:.1f}",
        f"Appeals per case:       {m['avg_appeals']:.1f}",
        f"Enforcement actions:    {m['avg_enforcement']:.1f}",
        f"Clarifications:         {m['avg_clarifications']:.1f}",
        f"Post-case motions:      {m['avg_postcase']:.1f}",
        f"Cases with injunctions: {m['injunction_count']} "
        f"({m['injunction_count'] / n * 100:.1f}%)",
    ]
    for i, line in enumerate(lines1):
        out.append(
            f'<text x="{col1_x}" y="{hy + 18 + i * 13}" font-size="11" '
            f'font-family="monospace" fill="{style["text_fill"]}">'
            f"{_xml_escape(line)}</text>"
        )

    # Column 2: top rules invoked across corpus
    out.append(
        f'<text x="{col2_x}" y="{hy}" font-size="13" font-weight="bold" '
        f'fill="{style["text_fill"]}">'
        f"Top rules invoked ({m['total_invocations']:,} total)</text>"
    )
    # Rule-type breakdown
    rt = m["rule_type_counts"]
    rt_str = (
        f"policies: {rt.get('policy', 0):,}, "
        f"guidelines: {rt.get('guideline', 0):,}, "
        f"essays: {rt.get('essay', 0):,}, "
        f"other: {rt.get('other', 0):,}"
    )
    out.append(
        f'<text x="{col2_x}" y="{hy + 16}" font-size="10" '
        f'fill="{style["text_fill"]}">{_xml_escape(rt_str)}</text>'
    )
    for i, (ref, count) in enumerate(m["top_rules"][:12]):
        line = f"{ref:<20} × {count:,}"
        out.append(
            f'<text x="{col2_x}" y="{hy + 34 + i * 13}" font-size="11" '
            f'font-family="monospace" fill="{style["text_fill"]}">'
            f"{_xml_escape(line)}</text>"
        )

    # Column 3: namespace distribution — "where does evidence live?"
    out.append(
        f'<text x="{col3_x}" y="{hy}" font-size="13" font-weight="bold" '
        f'fill="{style["text_fill"]}">Evidence namespaces (link counts)</text>'
    )
    ns_total = sum(n_ for _, n_ in m["top_namespaces"])
    for i, (ns, count) in enumerate(m["top_namespaces"][:10]):
        pct = (count / ns_total * 100) if ns_total else 0.0
        line = f"{ns:<15} {count:>7,} ({pct:4.1f}%)"
        out.append(
            f'<text x="{col3_x}" y="{hy + 18 + i * 13}" font-size="11" '
            f'font-family="monospace" fill="{style["text_fill"]}">'
            f"{_xml_escape(line)}</text>"
        )
    # Quick legend
    out.append(
        f'<text x="{col3_x}" y="{hy + 18 + 11 * 13}" font-size="9" '
        f'fill="{style["text_fill"]}" font-style="italic">'
        f"User/User_talk dominance ⇒ conduct; Main/Talk ⇒ content dispute</text>"
    )

    out.append("</svg>")
    return "\n".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Generate BPMN / SVG / PNG diagrams from Wikipedia dispute "
            "resolution discussions using Gemma + deterministic text "
            "analysis. Supports three venues: ArbCom (--arb), DRN "
            "(--drn / --drn-archive), and RFC (--rfc). Runs in two modes: "
            "per-case extraction (--text/--arb/--drn/--rfc/--json/--batch) "
            "and per-venue corpus aggregation (--aggregate / "
            "--aggregate-drn / --aggregate-rfc)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = p.add_mutually_exclusive_group(required=True)
    # ── Per-case extraction modes ───────────────────────────────────────────
    src.add_argument("--text", metavar="FILE", help="Plain-text / wikitext file")
    src.add_argument("--arb", metavar="CASE", help="Wikipedia ARB case title")
    src.add_argument(
        "--drn",
        metavar="CASE",
        help="Wikipedia DRN case — full page or 'Page#Section' "
        "form, e.g. "
        "'Wikipedia:Dispute_resolution_noticeboard/Archive_233"
        "#Talk:Foo'",
    )
    src.add_argument(
        "--drn-archive",
        metavar="N",
        help="Process every case in DRN Archive N at once. E.g. --drn-archive 233",
    )
    src.add_argument(
        "--rfc",
        metavar="PAGE",
        help="Wikipedia RFC — full page or 'Page#Section' form, "
        "e.g. 'Talk:Article#RfC_about_lead_section'",
    )
    src.add_argument(
        "--json",
        metavar="FILE",
        help="Pre-scraped ARB JSON (bpmn_from_arb format) — "
        "list of {title, content} or {cases: [...]}.",
    )
    src.add_argument(
        "--json-drn",
        metavar="FILE",
        help="Pre-scraped DRN JSON from fetch_drn_archived_cases.py "
        "(shape: {cases: [{title, content, ...}]}). Each "
        "case is processed with the DRN extraction recipe.",
    )
    src.add_argument(
        "--json-rfc",
        metavar="FILE",
        help="Pre-scraped RFC JSON from fetch_rfc.py "
        "(shape: {rfcs: [{title, content, ...}]}). Each "
        "RFC is processed with the RFC extraction recipe.",
    )
    src.add_argument("--batch", metavar="DIR", help="Directory of *.txt files")
    # ── Aggregate modes (one per venue, kept separate per user request) ─────
    src.add_argument(
        "--aggregate",
        metavar="DIR",
        help="ArbCom aggregate: directory of *_case.json files. "
        "Builds ONE ArbCom corpus diagram. Fast.",
    )
    src.add_argument(
        "--aggregate-drn",
        metavar="DIR",
        help="DRN aggregate: directory of DRN *_case.json files. "
        "Builds ONE DRN corpus diagram with closure-type "
        "percentages and top rules.",
    )
    src.add_argument(
        "--aggregate-rfc",
        metavar="DIR",
        help="RFC aggregate: directory of RFC *_case.json files. "
        "Builds ONE RFC corpus diagram with consensus "
        "outcome percentages and !vote distributions.",
    )

    p.add_argument(
        "--model-dir",
        default=None,
        metavar="DIR",
        help=f"Gemma model path or HF ID "
        f"(default: $MODEL_DIR env var or {DEFAULT_MODEL_ID})",
    )
    p.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        metavar="DIR",
        help=f"Output directory for .json / .bpmn / .svg / .png files "
        f"(default: {DEFAULT_OUTPUT_DIR})",
    )
    p.add_argument(
        "--quantize",
        choices=["4bit", "8bit"],
        default=None,
        help="Load model with bitsandbytes quantization to reduce "
        "VRAM. 4bit ~7 GB for 12b model, 8bit ~14 GB. "
        "Requires: pip install bitsandbytes",
    )
    p.add_argument(
        "--max-new-tokens",
        type=int,
        default=DEFAULT_MAX_NEW_TOKENS,
        help=f"Max generated tokens per LLM pass (default: {DEFAULT_MAX_NEW_TOKENS})",
    )
    p.add_argument(
        "--max-cases",
        type=int,
        default=None,
        help="With --json* or --batch / --drn-archive, cap number of cases processed",
    )
    p.add_argument(
        "--filter-titles",
        metavar="SUBSTR",
        action="append",
        default=[],
        help="With any --json* mode, restrict to cases whose "
        "title contains this substring (case-insensitive). "
        "Repeat the flag for multiple substrings: "
        "--filter-titles 'Power electronics' "
        "--filter-titles 'Touhou'. A case is kept if its "
        "title matches ANY of the substrings.",
    )
    p.add_argument(
        "--simple-lanes",
        action="store_true",
        help=f"Use 4-lane layout: {ARB_LANES_SIMPLE}",
    )
    p.add_argument(
        "--no-llm", action="store_true", help="Skip Gemma — regex-only pipeline"
    )
    p.add_argument(
        "--no-subpages",
        action="store_true",
        help="With --arb, fetch only the main case page "
        "(skip /Evidence, /Workshop, /Proposed_decision, etc.)",
    )
    p.add_argument(
        "--text-venue",
        choices=list(VENUES.keys()),
        default="arb",
        help="With --text/--batch, which venue's extraction recipe "
        "to use (default: arb). Only meaningful when paired "
        "with --text or --batch — for --arb / --drn / --rfc "
        "the venue is implied by the flag itself.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print extracted case JSON; don't write files",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    detailed_lanes = not args.simple_lanes

    # ── Aggregate mode: doesn't need Gemma; short-circuit before loading ────
    if args.aggregate:
        _run_aggregate(args.aggregate, output_dir, venue="arb")
        return
    if args.aggregate_drn:
        _run_aggregate(args.aggregate_drn, output_dir, venue="drn")
        return
    if args.aggregate_rfc:
        _run_aggregate(args.aggregate_rfc, output_dir, venue="rfc")
        return

    # Load Gemma (unless disabled)
    loader: Gemma4Loader | None = None
    if not args.no_llm:
        if not TRANSFORMERS_AVAILABLE:
            print("ERROR: transformers not installed. Use --no-llm for regex-only.")
            sys.exit(1)
        model_dir = args.model_dir or os.environ.get("MODEL_DIR") or DEFAULT_MODEL_ID
        loader = Gemma4Loader(model_dir=model_dir, quantize=args.quantize)

    # Auto-compute per-pass input budget from the model's context window.
    # In --no-llm mode this returns a huge sentinel so the regex path sees
    # the full text regardless.
    input_budget = _compute_char_budget(loader, args.max_new_tokens)

    # Dispatch by mode
    if args.text:
        text = Path(args.text).read_text(encoding="utf-8")
        title = Path(args.text).stem
        process_document(
            loader,
            text,
            title,
            output_dir,
            input_budget,
            detailed_lanes,
            args.dry_run,
            venue=args.text_venue,
        )

    elif args.arb:
        try:
            text = fetch_arb_case_full(args.arb, include_subpages=not args.no_subpages)
        except Exception as exc:
            print(f"ERROR fetching '{args.arb}' from Wikipedia: {exc}")
            sys.exit(1)
        if not text.strip():
            print(f"ERROR: no content found for '{args.arb}'")
            sys.exit(1)
        process_document(
            loader,
            text,
            args.arb,
            output_dir,
            input_budget,
            detailed_lanes,
            args.dry_run,
            venue="arb",
        )

    elif args.drn:
        try:
            text = fetch_drn_case(args.drn)
        except Exception as exc:
            print(f"ERROR fetching DRN '{args.drn}': {exc}")
            sys.exit(1)
        if not text.strip():
            print(f"ERROR: no content found for DRN '{args.drn}'")
            sys.exit(1)
        process_document(
            loader,
            text,
            args.drn,
            output_dir,
            input_budget,
            detailed_lanes,
            args.dry_run,
            venue="drn",
        )

    elif args.drn_archive:
        try:
            sections = fetch_drn_archive(args.drn_archive)
        except Exception as exc:
            print(f"ERROR fetching DRN archive {args.drn_archive}: {exc}")
            sys.exit(1)
        if not sections:
            print(f"ERROR: no cases found in DRN archive {args.drn_archive}")
            sys.exit(1)
        if args.max_cases:
            sections = sections[: args.max_cases]
        print(f"Processing {len(sections)} DRN cases from archive {args.drn_archive}\n")
        for section_title, body in sections:
            full_title = (
                f"DRN_archive_{args.drn_archive}_{safe_filename(section_title)}"
            )
            process_document(
                loader,
                body,
                full_title,
                output_dir,
                input_budget,
                detailed_lanes,
                args.dry_run,
                venue="drn",
            )

    elif args.rfc:
        try:
            text = fetch_rfc(args.rfc)
        except Exception as exc:
            print(f"ERROR fetching RFC '{args.rfc}': {exc}")
            sys.exit(1)
        if not text.strip():
            print(f"ERROR: no content found for RFC '{args.rfc}'")
            sys.exit(1)
        process_document(
            loader,
            text,
            args.rfc,
            output_dir,
            input_budget,
            detailed_lanes,
            args.dry_run,
            venue="rfc",
        )

    elif args.json:
        _process_json_corpus(
            args.json,
            loader,
            output_dir,
            input_budget,
            detailed_lanes,
            args.dry_run,
            venue="arb",
            filter_titles=args.filter_titles,
            max_cases=args.max_cases,
            list_keys=("cases",),
        )

    elif args.json_drn:
        _process_json_corpus(
            args.json_drn,
            loader,
            output_dir,
            input_budget,
            detailed_lanes,
            args.dry_run,
            venue="drn",
            filter_titles=args.filter_titles,
            max_cases=args.max_cases,
            list_keys=("cases",),
        )

    elif args.json_rfc:
        _process_json_corpus(
            args.json_rfc,
            loader,
            output_dir,
            input_budget,
            detailed_lanes,
            args.dry_run,
            venue="rfc",
            filter_titles=args.filter_titles,
            max_cases=args.max_cases,
            list_keys=("rfcs", "cases"),  # fetch_rfc.py uses "rfcs"
        )

    elif args.batch:
        batch_dir = Path(args.batch)
        txt_files = sorted(batch_dir.glob("*.txt"))
        if args.max_cases:
            txt_files = txt_files[: args.max_cases]
        if not txt_files:
            print(f"No *.txt files found in {batch_dir}")
            sys.exit(1)
        print(f"Batch: {len(txt_files)} files in {batch_dir}\n")
        for f in txt_files:
            text = f.read_text(encoding="utf-8")
            process_document(
                loader,
                text,
                f.stem,
                output_dir,
                input_budget,
                detailed_lanes,
                args.dry_run,
                venue=args.text_venue,
            )


def _process_json_corpus(
    json_path: str,
    loader: Gemma4Loader | None,
    output_dir: Path,
    input_budget: int,
    detailed_lanes: bool,
    dry_run: bool,
    venue: str,
    filter_titles: list[str],
    max_cases: int | None,
    list_keys: tuple[str, ...],
) -> None:
    """Load a pre-fetched JSON corpus, optionally filter by title substrings,
    cap to max_cases, and process every entry through the right venue's
    pipeline.

    `list_keys` is a tuple of dict keys to try in order when the JSON is a
    dict wrapping the case list (ARB and DRN use 'cases', RFC uses 'rfcs').
    Falls back to treating the entire payload as the case list if it's
    already a list.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        cases = data
    else:
        cases = []
        for k in list_keys:
            if isinstance(data.get(k), list):
                cases = data[k]
                break

    # Title filtering — case-insensitive substring match against any of
    # the filter strings. Empty list means no filtering.
    if filter_titles:
        needles = [s.lower() for s in filter_titles]
        cases = [
            c
            for c in cases
            if any(n in (c.get("title") or "").lower() for n in needles)
        ]
        if not cases:
            print(f"WARNING: no cases matched filter-titles {filter_titles!r}")
            return
        print(f"Filtered to {len(cases)} cases by title substring(s) {filter_titles!r}")

    # Drop records with no content
    before = len(cases)
    cases = [c for c in cases if c.get("content")]
    if len(cases) < before:
        print(f"Skipped {before - len(cases)} records missing content")

    if max_cases:
        cases = cases[:max_cases]

    if not cases:
        print(f"ERROR: no usable cases in {json_path}")
        sys.exit(1)

    print(f"Processing {len(cases)} {VENUES[venue]['label']} cases from {json_path}")
    for c in cases:
        content = c.get("content", "")
        title = c.get("title", "untitled")
        process_document(
            loader,
            content,
            title,
            output_dir,
            input_budget,
            detailed_lanes,
            dry_run,
            venue=venue,
        )


def _run_aggregate(input_dir: str, output_dir: Path, venue: str) -> None:
    """Run aggregate-mode rendering for one venue.

    Reads every *_case.json in input_dir, computes corpus metrics, writes
    SVG + PNG. Currently uses the same _aggregate_metrics + _build_aggregate_svg
    machinery for all venues — venue-specific aggregations would extend this
    by branching on case['venue'] inside those helpers.
    """
    agg_dir = Path(input_dir)
    venue_label = VENUES[venue]["label"].lower()
    out_svg = output_dir / f"{venue_label}_aggregate_workflow.svg"
    out_png = output_dir / f"{venue_label}_aggregate_workflow.png"
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = _load_aggregate_cases(agg_dir)
    if not cases:
        print(f"ERROR: no *_case.json files found in {agg_dir}")
        sys.exit(1)

    # Filter to cases whose venue matches (or whose venue field is missing
    # and we're aggregating ARB — handles legacy ARB JSONs with no venue tag).
    if venue == "arb":
        venue_cases = [c for c in cases if c.get("venue", "arb") == "arb"]
    else:
        venue_cases = [c for c in cases if c.get("venue") == venue]

    if not venue_cases:
        print(
            f"ERROR: no {VENUES[venue]['label']} cases found in {agg_dir} "
            f"(found {len(cases)} cases of other venues). Did you mean a "
            f"different --aggregate flag?"
        )
        sys.exit(1)

    print(
        f"Aggregating {len(venue_cases)} {VENUES[venue]['label']} cases "
        f"from {agg_dir} ..."
    )
    metrics = _aggregate_metrics(venue_cases)
    metrics["venue_label"] = VENUES[venue]["label"]
    svg = _build_aggregate_svg(metrics)
    out_svg.write_text(svg, encoding="utf-8")
    print(f"Saved aggregate SVG → {out_svg}")

    try:
        import cairosvg  # type: ignore

        cairosvg.svg2png(url=str(out_svg), write_to=str(out_png), scale=2.0)
        if out_png.exists():
            print(f"Saved aggregate PNG → {out_png}")
    except ImportError:
        print("  [png] cairosvg not installed; SVG is ready to view.")
    except Exception as exc:
        print(f"  [png] cairosvg failed: {exc}")


if __name__ == "__main__":
    main()
