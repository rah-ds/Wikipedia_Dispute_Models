"""Arbitration case outcome parsing.

This module extracts case outcomes, remedies, and sanctions from
arbitration case wikitext.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import mwparserfromhell


@dataclass
class Sanction:
    """A sanction or remedy from an arbitration case."""

    sanction_type: str  # topic_ban, interaction_ban, block, warning, etc.
    target_user: str
    description: str
    duration: Optional[str] = None
    scope: Optional[str] = None  # Topic area if topic ban
    is_indefinite: bool = False
    raw_text: str = ""


@dataclass
class CaseOutcome:
    """Parsed outcome of an arbitration case."""

    status: str  # open, pending, closed, appealed
    decision_date: Optional[str] = None
    remedies: list[Sanction] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    principles: list[str] = field(default_factory=list)
    case_closed: bool = False
    has_active_remedies: bool = False


# Templates indicating case status
STATUS_TEMPLATES = {
    "open": [
        "arbcom open tasks",
        "arbcom-open",
        "arbitration case open",
        "ac open",
    ],
    "closed": [
        "arbcom closed tasks",
        "arbcom-closed",
        "arbitration case closed",
        "ac closed",
        "arbcom case closed",
    ],
    "pending": [
        "arbcom pending",
        "arbitration case pending",
        "ac pending",
    ],
}

# Text patterns for case status (used when templates not found)
# These match actual Wikipedia formatting like '''Case Closed'''
STATUS_TEXT_PATTERNS = {
    "closed": [
        r"'''Case Closed'''",
        r"<big>'''Case Closed'''",
        r"Case Closed on",
        r"case closed on",
        r"\|status\s*=\s*closed",
        r"status\s*=\s*closed",
    ],
    "open": [
        r"'''Case Opened'''",
        r"<big>'''Case Opened'''",
        r"Case Opened on",
        r"case opened on",
        r"\|status\s*=\s*open",
        r"status\s*=\s*open",
    ],
}

# Sanction template patterns
SANCTION_PATTERNS = {
    "topic_ban": [
        r"\{\{topic\s*ban\|([^}]+)\}\}",
        r"\{\{tban\|([^}]+)\}\}",
        r"\{\{TBAN\|([^}]+)\}\}",
    ],
    "interaction_ban": [
        r"\{\{interaction\s*ban\|([^}]+)\}\}",
        r"\{\{iban\|([^}]+)\}\}",
        r"\{\{IBAN\|([^}]+)\}\}",
    ],
    "community_ban": [
        r"\{\{community\s*ban\|([^}]+)\}\}",
        r"\{\{cban\|([^}]+)\}\}",
        r"\{\{banned\s*user\|([^}]+)\}\}",
    ],
    "block": [
        r"\{\{blocked\|([^}]+)\}\}",
        r"\{\{checkuserblock\|([^}]+)\}\}",
    ],
    "restriction": [
        r"\{\{editing\s*restriction\|([^}]+)\}\}",
        r"\{\{1rr\|([^}]+)\}\}",
        r"\{\{0rr\|([^}]+)\}\}",
    ],
    "warning": [
        r"\{\{final\s*warning\|([^}]+)\}\}",
        r"\{\{arb\s*warning\|([^}]+)\}\}",
    ],
}


def parse_case_status(content: str) -> str:
    """
    Determine case status from main case page content.

    Args:
        content: Raw wikitext of case main page

    Returns:
        Status string: "open", "closed", "pending", or "unknown"
    """
    content_lower = content.lower()

    # Check for status templates
    for status, templates in STATUS_TEMPLATES.items():
        for template in templates:
            if template in content_lower:
                return status

    # Check text patterns (e.g., '''Case Closed''' in bold)
    for status, patterns in STATUS_TEXT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return status

    # Fallback: look for status indicators in text
    if "this case is closed" in content_lower:
        return "closed"
    if "this case is open" in content_lower:
        return "open"
    if "case closed" in content_lower:
        return "closed"
    if "case opened" in content_lower:
        return "open"
    if "awaiting" in content_lower and "decision" in content_lower:
        return "pending"

    return "unknown"


def extract_sanctions_from_text(content: str) -> list[Sanction]:
    """
    Extract sanctions from wikitext using template patterns.

    Args:
        content: Raw wikitext containing sanction templates

    Returns:
        List of Sanction objects
    """
    sanctions = []

    for sanction_type, patterns in SANCTION_PATTERNS.items():
        for pattern in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                raw_params = match.group(1)
                params = [p.strip() for p in raw_params.split("|")]

                sanction = Sanction(
                    sanction_type=sanction_type,
                    target_user=params[0] if params else "",
                    description=f"{sanction_type}: {raw_params}",
                    raw_text=match.group(0),
                )

                # Parse duration if present
                for param in params[1:]:
                    if "=" in param:
                        key, value = param.split("=", 1)
                        if key.lower() in ("duration", "time", "length"):
                            sanction.duration = value
                        elif key.lower() in ("scope", "topic", "area"):
                            sanction.scope = value
                    elif param.lower() in ("indef", "indefinite", "permanent"):
                        sanction.is_indefinite = True

                sanctions.append(sanction)

    return sanctions


def parse_remedies_page(content: str) -> list[Sanction]:
    """
    Parse the /Remedies subpage for formal sanctions.

    Args:
        content: Raw wikitext of /Remedies subpage

    Returns:
        List of Sanction objects
    """
    # First, try to extract sanctions directly from templates
    sanctions = extract_sanctions_from_text(content)

    # If found, return them
    if sanctions:
        return sanctions

    # Otherwise, try section-based parsing
    try:
        wikicode = mwparserfromhell.parse(content)

        # Look for sections that typically contain remedies
        remedy_sections = []
        current_section = None
        current_content = []

        for node in wikicode.nodes:
            if isinstance(node, mwparserfromhell.nodes.Heading):
                if current_section and current_content:
                    remedy_sections.append(
                        {
                            "title": current_section,
                            "content": "".join(str(n) for n in current_content),
                        }
                    )
                current_section = str(node.title).strip()
                current_content = []
            elif current_section is not None:
                current_content.append(node)

        # Don't forget the last section
        if current_section and current_content:
            remedy_sections.append(
                {
                    "title": current_section,
                    "content": "".join(str(n) for n in current_content),
                }
            )

        # Extract sanctions from each section
        for section in remedy_sections:
            section_title = section["title"].lower()

            # Skip non-remedy sections
            if any(
                skip in section_title
                for skip in ["discussion", "comment", "note", "archive"]
            ):
                continue

            # Extract sanctions from section content
            section_sanctions = extract_sanctions_from_text(section["content"])

            # If no template-based sanctions, try to extract from numbered lists
            if not section_sanctions:
                section_sanctions = _extract_list_sanctions(
                    section["title"], section["content"]
                )

            sanctions.extend(section_sanctions)

    except Exception:
        # Fall back to simple pattern matching
        sanctions = extract_sanctions_from_text(content)

    return sanctions


def _extract_list_sanctions(section_title: str, content: str) -> list[Sanction]:
    """
    Extract sanctions from numbered or bulleted lists.

    Many remedies pages use prose or lists rather than templates.
    """
    sanctions = []

    # Look for user mentions in list items
    list_pattern = r"(?:^|\n)\s*(?:\*|\#|\d+\.)\s*(.+?)(?=\n|$)"
    matches = re.findall(list_pattern, content)

    for item in matches:
        # Check if this looks like a sanction (mentions a user and action)
        user_match = re.search(r"\[\[User:([^\]|]+)", item, re.IGNORECASE)
        if not user_match:
            continue

        username = user_match.group(1).strip()

        # Determine sanction type from keywords
        item_lower = item.lower()
        sanction_type = "other"

        if "topic ban" in item_lower or "tban" in item_lower:
            sanction_type = "topic_ban"
        elif "interaction ban" in item_lower or "iban" in item_lower:
            sanction_type = "interaction_ban"
        elif "block" in item_lower:
            sanction_type = "block"
        elif "warning" in item_lower:
            sanction_type = "warning"
        elif "restriction" in item_lower or "1rr" in item_lower or "0rr" in item_lower:
            sanction_type = "restriction"
        elif "ban" in item_lower:
            sanction_type = "community_ban"

        # Only add if it looks like a sanction
        if sanction_type != "other" or any(
            kw in item_lower
            for kw in ["sanction", "remedy", "prohibited", "required", "must"]
        ):
            sanction = Sanction(
                sanction_type=sanction_type,
                target_user=username,
                description=item.strip()[:200],
                raw_text=item.strip(),
                is_indefinite="indefinite" in item_lower or "indef" in item_lower,
            )
            sanctions.append(sanction)

    return sanctions


def parse_findings(content: str) -> list[str]:
    """
    Extract findings of fact from case content.

    Args:
        content: Raw wikitext (typically from main page or /Proposed decision)

    Returns:
        List of finding summaries
    """
    findings = []

    try:
        wikicode = mwparserfromhell.parse(content)

        in_findings = False
        for node in wikicode.nodes:
            if isinstance(node, mwparserfromhell.nodes.Heading):
                title = str(node.title).strip().lower()
                in_findings = "finding" in title or "fact" in title

            elif in_findings and isinstance(node, mwparserfromhell.nodes.Text):
                text = str(node).strip()
                # Look for numbered findings
                if re.match(r"^\d+\.", text):
                    findings.append(text[:500])

    except Exception:
        pass

    return findings


def parse_principles(content: str) -> list[str]:
    """
    Extract principles from case content.

    Args:
        content: Raw wikitext (typically from main page or /Proposed decision)

    Returns:
        List of principle summaries
    """
    principles = []

    try:
        wikicode = mwparserfromhell.parse(content)

        in_principles = False
        for node in wikicode.nodes:
            if isinstance(node, mwparserfromhell.nodes.Heading):
                title = str(node.title).strip().lower()
                in_principles = "principle" in title

            elif in_principles and isinstance(node, mwparserfromhell.nodes.Text):
                text = str(node).strip()
                if re.match(r"^\d+\.", text):
                    principles.append(text[:500])

    except Exception:
        pass

    return principles


def parse_case_outcome(case_pages: dict) -> CaseOutcome:
    """
    Parse complete case outcome from all case pages.

    Args:
        case_pages: Dictionary with page contents keyed by subpage name
            Expected keys: "main", "evidence", "workshop",
                          "proposed_decision", "remedies"

    Returns:
        CaseOutcome with status, remedies, findings, principles
    """
    outcome = CaseOutcome(status="unknown")

    # Parse status from main page
    main_content = case_pages.get("main", {}).get("content", "")
    if main_content:
        outcome.status = parse_case_status(main_content)
        outcome.case_closed = outcome.status == "closed"

    # Parse remedies
    remedies_content = case_pages.get("remedies", {}).get("content", "")
    if remedies_content:
        outcome.remedies = parse_remedies_page(remedies_content)
        outcome.has_active_remedies = len(outcome.remedies) > 0

    # Also check proposed decision for sanctions
    proposed_content = case_pages.get("proposed_decision", {}).get("content", "")
    if proposed_content and not outcome.remedies:
        outcome.remedies = parse_remedies_page(proposed_content)

    # Parse findings and principles
    for page_key in ["main", "proposed_decision"]:
        content = case_pages.get(page_key, {}).get("content", "")
        if content:
            if not outcome.findings:
                outcome.findings = parse_findings(content)
            if not outcome.principles:
                outcome.principles = parse_principles(content)

    return outcome


def sanctions_to_dict(sanctions: list[Sanction]) -> list[dict]:
    """Convert list of Sanction objects to serializable dicts."""
    return [
        {
            "sanction_type": s.sanction_type,
            "target_user": s.target_user,
            "description": s.description,
            "duration": s.duration,
            "scope": s.scope,
            "is_indefinite": s.is_indefinite,
        }
        for s in sanctions
    ]


def outcome_to_dict(outcome: CaseOutcome) -> dict:
    """Convert CaseOutcome to serializable dict."""
    return {
        "status": outcome.status,
        "decision_date": outcome.decision_date,
        "case_closed": outcome.case_closed,
        "has_active_remedies": outcome.has_active_remedies,
        "remedies": sanctions_to_dict(outcome.remedies),
        "findings": outcome.findings,
        "principles": outcome.principles,
        "remedy_count": len(outcome.remedies),
        "finding_count": len(outcome.findings),
        "principle_count": len(outcome.principles),
    }
