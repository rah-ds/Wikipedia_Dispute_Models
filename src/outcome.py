"""
Outcome parser for Wikipedia ArbCom proposed-decision pages.

Extracts structured data from raw wikitext of /Proposed decision (or
/Final decision) pages, including:
  - Principles, findings of fact, and remedies
  - Per-item vote tallies (Support / Oppose / Abstain)
  - Per-item voter lists
  - Case-level outcome status (passed / failed)

The wikitext conventions used by the Arbitration Committee are
semi-structured:

    ==Proposed findings of fact==
    ===Locus of dispute===
    1) Descriptive text …

    :Support:
    :# Comment [[User:Alice|Alice]] …
    :# [[User:Bob|Bob]] …

    :Oppose:
    :#

    :Abstain:
    :#

This parser operates on raw section text using regex heuristics.
It does NOT require mwparserfromhell (keeping dependencies light),
though it could be extended to use it for richer template parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Top-level sections we recognise (case-insensitive matching)
_SECTION_KINDS = {
    "proposed principles": "principle",
    "principles": "principle",
    "proposed findings of fact": "finding",
    "findings of fact": "finding",
    "proposed remedies": "remedy",
    "remedies": "remedy",
    "proposed enforcement": "enforcement",
    "enforcement": "enforcement",
}

#: Regex to extract usernames from vote lines
#: Matches [[User:Name|…]] or [[User talk:Name|…]]
_VOTER_RE = re.compile(r"\[\[User(?:\s+talk)?:([^\]|/]+)", re.IGNORECASE)

#: Section heading regex (levels 2–4)
_HEADING_RE = re.compile(r"^(={2,4})\s*(.+?)\s*\1\s*$", re.MULTILINE)

#: Vote-category labels on ArbCom pages
_VOTE_LABELS = {"support", "oppose", "abstain"}

#: Template-style vote detection for pre-2012 pages
#: Matches {{support}}, {{Support}}, {{oppose}}, {{abstain}} etc. on list lines
_TEMPLATE_VOTE_RE = re.compile(
    r"^[*#:]+\s*\{\{(support|oppose|abstain)[^}]*\}\}",
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class VoteTally:
    """Vote counts and voter lists for a single proposal item."""

    support: int = 0
    oppose: int = 0
    abstain: int = 0
    support_voters: list[str] = field(default_factory=list)
    oppose_voters: list[str] = field(default_factory=list)
    abstain_voters: list[str] = field(default_factory=list)

    @property
    def net_support(self) -> int:
        """Support minus oppose (ArbCom's passing metric)."""
        return self.support - self.oppose

    @property
    def passed(self) -> bool:
        """
        An item passes with ≥ 4 net support votes.
        (Standard ArbCom threshold.)
        """
        return self.net_support >= 4

    @property
    def total_votes(self) -> int:
        return self.support + self.oppose + self.abstain


@dataclass
class ProposalItem:
    """A single principle, finding, remedy, or enforcement provision."""

    kind: str  # "principle" | "finding" | "remedy" | "enforcement"
    number: str  # e.g. "1", "6.1", "14.3"
    title: str  # section heading text
    body: str  # raw wikitext of the proposal body (before votes)
    votes: VoteTally = field(default_factory=VoteTally)

    @property
    def passed(self) -> bool:
        return self.votes.passed


@dataclass
class DecisionOutcome:
    """
    Structured summary of an entire proposed / final decision page.
    """

    items: list[ProposalItem] = field(default_factory=list)

    # --- Convenience accessors ---

    @property
    def principles(self) -> list[ProposalItem]:
        return [i for i in self.items if i.kind == "principle"]

    @property
    def findings(self) -> list[ProposalItem]:
        return [i for i in self.items if i.kind == "finding"]

    @property
    def remedies(self) -> list[ProposalItem]:
        return [i for i in self.items if i.kind == "remedy"]

    @property
    def enforcement(self) -> list[ProposalItem]:
        return [i for i in self.items if i.kind == "enforcement"]

    @property
    def passed_items(self) -> list[ProposalItem]:
        return [i for i in self.items if i.passed]

    @property
    def failed_items(self) -> list[ProposalItem]:
        return [i for i in self.items if not i.passed]

    # --- Aggregate metrics ---

    @property
    def total_items(self) -> int:
        return len(self.items)

    @property
    def total_passed(self) -> int:
        return len(self.passed_items)

    @property
    def total_failed(self) -> int:
        return len(self.failed_items)

    @property
    def pass_rate(self) -> float:
        return self.total_passed / self.total_items if self.total_items else 0.0

    @property
    def all_voters(self) -> set[str]:
        """Unique set of all editors who voted on any item."""
        voters: set[str] = set()
        for item in self.items:
            voters.update(item.votes.support_voters)
            voters.update(item.votes.oppose_voters)
            voters.update(item.votes.abstain_voters)
        return voters

    @property
    def arbitrator_count(self) -> int:
        return len(self.all_voters)

    def to_summary_dict(self) -> dict:
        """Flat dict for merging into a case-level DataFrame row."""
        return {
            "outcome_total_items": self.total_items,
            "outcome_principles": len(self.principles),
            "outcome_findings": len(self.findings),
            "outcome_remedies": len(self.remedies),
            "outcome_enforcement": len(self.enforcement),
            "outcome_passed": self.total_passed,
            "outcome_failed": self.total_failed,
            "outcome_pass_rate": round(self.pass_rate, 3),
            "outcome_arbitrator_count": self.arbitrator_count,
            "outcome_remedies_passed": len([r for r in self.remedies if r.passed]),
            "outcome_findings_passed": len([f for f in self.findings if f.passed]),
        }


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _extract_voters(text: str) -> list[str]:
    """
    Pull unique usernames from a block of vote lines.

    Each vote line starts with ``:#`` and may contain a
    ``[[User:Name|…]]`` link.  Empty ``:#`` lines are ignored.
    """
    voters: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        # Vote lines start with :# (with possible leading colons)
        if not re.match(r":+#", stripped):
            continue
        # Skip empty vote slots like ":#\n" or ":#  "
        content_after_hash = re.sub(r"^:+#\s*", "", stripped)
        if not content_after_hash:
            continue
        # Extract usernames from this line
        for match in _VOTER_RE.finditer(stripped):
            username = match.group(1).strip()
            if username and username not in seen:
                voters.append(username)
                seen.add(username)
    return voters


def _split_headings(wikitext: str) -> list[tuple[int, str, int, int]]:
    """
    Find all section headings and return (level, title, start, end) tuples.

    level: 2 for ==, 3 for ===, 4 for ====
    start: char offset of the heading line
    end:   char offset of the next heading (or end of string)
    """
    matches = list(_HEADING_RE.finditer(wikitext))
    result = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        title = m.group(2).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(wikitext)
        result.append((level, title, start, end))
    return result


def _detect_item_kind(title: str, active_kind: str) -> str:
    """Map a heading title to an item kind, or inherit from parent."""
    lower = title.lower().strip()
    return _SECTION_KINDS.get(lower, active_kind)


def _extract_number(title: str, body: str) -> str:
    """
    Try to extract the proposal number from the body text.

    ArbCom items typically start with e.g. "1) …" or "6.1) …".
    Falls back to the title itself.
    """
    # Look for "N)" or "N.M)" at start of body
    m = re.search(r"^\s*(\d+(?:\.\d+)?)\)", body)
    if m:
        return m.group(1)
    # Look for number in the heading title  e.g. "====Finding 6.1===="
    m = re.search(r"(\d+(?:\.\d+)?)", title)
    if m:
        return m.group(1)
    return title


def _parse_votes_from_section(section_text: str) -> VoteTally:
    """
    Given the text of a single proposal item section, find the
    Support / Oppose / Abstain blocks and tally votes.

    Handles two historical vote formats:
    - Post-2012 colon format:  ``:Support:`` / ``:Oppose:`` labels
    - Pre-2012 template format: ``{{support}}``, ``{{oppose}}``, ``{{abstain}}``
      on bullet/hash lines (``* {{support}} [[User:...]]``)
    """
    tally = VoteTally()

    # --- Format 1: colon-style blocks (post-2012) ---
    vote_block_re = re.compile(
        r"^:+(Support|Oppose|Abstain)\s*:", re.IGNORECASE | re.MULTILINE
    )
    splits = list(vote_block_re.finditer(section_text))

    for i, m in enumerate(splits):
        category = m.group(1).lower()
        block_start = m.end()
        block_end = splits[i + 1].start() if i + 1 < len(splits) else len(section_text)
        block_text = section_text[block_start:block_end]
        voters = _extract_voters(block_text)

        if category == "support":
            tally.support = len(voters)
            tally.support_voters = voters
        elif category == "oppose":
            tally.oppose = len(voters)
            tally.oppose_voters = voters
        elif category == "abstain":
            tally.abstain = len(voters)
            tally.abstain_voters = voters

    # --- Format 2: template-style lines (pre-2012 fallback) ---
    if tally.total_votes == 0:
        support_voters: list[str] = []
        oppose_voters: list[str] = []
        abstain_voters: list[str] = []
        seen: set[str] = set()

        for m in _TEMPLATE_VOTE_RE.finditer(section_text):
            category = m.group(1).lower()
            line = section_text[m.start() : section_text.find("\n", m.start())]
            for vm in _VOTER_RE.finditer(line):
                username = vm.group(1).strip()
                if username and username not in seen:
                    seen.add(username)
                    if category == "support":
                        support_voters.append(username)
                    elif category == "oppose":
                        oppose_voters.append(username)
                    elif category == "abstain":
                        abstain_voters.append(username)

        if support_voters or oppose_voters or abstain_voters:
            tally.support = len(support_voters)
            tally.support_voters = support_voters
            tally.oppose = len(oppose_voters)
            tally.oppose_voters = oppose_voters
            tally.abstain = len(abstain_voters)
            tally.abstain_voters = abstain_voters

    return tally


def parse_decision(wikitext: str) -> DecisionOutcome:
    """
    Parse the raw wikitext of a /Proposed decision or /Final decision
    page into a :class:`DecisionOutcome`.

    Parameters
    ----------
    wikitext : str
        Full raw wikitext of the page.

    Returns
    -------
    DecisionOutcome
        Structured summary with all proposal items and votes.
    """
    outcome = DecisionOutcome()
    headings = _split_headings(wikitext)

    if not headings:
        return outcome

    # Track the current "kind" (principle/finding/remedy/enforcement)
    # as we descend through headings.
    active_kind = ""

    for level, title, start, end in headings:
        section_text = wikitext[start:end]

        # Level-2 headings define the top-level grouping
        if level == 2:
            active_kind = _detect_item_kind(title, active_kind)
            continue

        # Level 3-4 headings are individual proposal items
        if level in (3, 4) and active_kind:
            # Skip certain meta-sections
            lower_title = title.lower()
            if any(
                skip in lower_title
                for skip in (
                    "discussion by arbitrators",
                    "motion to close",
                    "implementation notes",
                    "template",
                    "proposed motions",
                    "proposed temporary injunctions",
                    "general",
                )
            ):
                continue

            # The body is from the heading to the first :Support: / :Oppose:
            vote_marker = re.search(
                r"^:+(?:Support|Oppose|Abstain)\s*:",
                section_text,
                re.IGNORECASE | re.MULTILINE,
            )
            body_end = vote_marker.start() if vote_marker else len(section_text)
            # Skip the heading line itself
            heading_end = section_text.index("\n") + 1 if "\n" in section_text else 0
            body = section_text[heading_end:body_end].strip()

            number = _extract_number(title, body)
            votes = _parse_votes_from_section(section_text)

            # Include all proposal items regardless of vote count.
            # Pre-2012 pages used different vote formats; dropping zero-vote
            # items caused findings and principles to be silently omitted.
            outcome.items.append(
                ProposalItem(
                    kind=active_kind,
                    number=number,
                    title=title,
                    body=body[:500],  # truncate for storage
                    votes=votes,
                )
            )

    return outcome
