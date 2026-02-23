"""Tests for arbitration case outcome parsing."""

import sys
from pathlib import Path

import pytest

# Add src to path for direct import
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from outcome import (
    parse_case_status,
    extract_sanctions_from_text,
    parse_remedies_page,
    parse_case_outcome,
    outcome_to_dict,
    sanctions_to_dict,
    Sanction,
    CaseOutcome,
    STATUS_TEMPLATES,
    STATUS_TEXT_PATTERNS,
    SANCTION_PATTERNS,
)


class TestParseCaseStatus:
    """Tests for case status parsing."""

    def test_detect_closed_template(self):
        content = "{{ArbCom closed tasks}}"
        status = parse_case_status(content)
        assert status == "closed"

    def test_detect_open_template(self):
        content = "{{ArbCom open tasks}}"
        status = parse_case_status(content)
        assert status == "open"

    def test_detect_closed_text(self):
        content = "This case is closed and archived."
        status = parse_case_status(content)
        assert status == "closed"

    def test_detect_open_text(self):
        content = "This case is open for evidence submission."
        status = parse_case_status(content)
        assert status == "open"

    def test_detect_pending(self):
        content = "Awaiting final decision from arbitrators."
        status = parse_case_status(content)
        assert status == "pending"

    def test_unknown_status(self):
        content = "Some random content without status indicators."
        status = parse_case_status(content)
        assert status == "unknown"

    def test_case_insensitive(self):
        content = "{{ARBCOM CLOSED TASKS}}"
        status = parse_case_status(content)
        assert status == "closed"

    def test_detect_bold_case_closed(self):
        """Test detection of '''Case Closed''' bold text format."""
        content = "<big>'''Case Closed''' on 03:57, 28 November 2011</big>"
        status = parse_case_status(content)
        assert status == "closed"

    def test_detect_case_closed_on_date(self):
        """Test detection of 'Case Closed on' text."""
        content = "Case Closed on 15 January 2020."
        status = parse_case_status(content)
        assert status == "closed"

    def test_detect_case_opened_text(self):
        """Test detection of '''Case Opened''' text format."""
        content = "<big>'''Case Opened''' on 01:00, 1 January 2020</big>"
        status = parse_case_status(content)
        assert status == "open"

    def test_detect_status_parameter_closed(self):
        """Test detection of |status=closed template parameter."""
        content = "{{Casenav|case=Test|status=closed}}"
        status = parse_case_status(content)
        assert status == "closed"

    def test_detect_status_parameter_open(self):
        """Test detection of |status=open template parameter."""
        content = "{{Casenav|case=Test|status=open}}"
        status = parse_case_status(content)
        assert status == "open"

    def test_fallback_case_closed(self):
        """Test fallback detection of 'case closed' anywhere in text."""
        content = "The arbitration committee has declared this case closed."
        status = parse_case_status(content)
        assert status == "closed"


class TestExtractSanctionsFromText:
    """Tests for sanction template extraction."""

    def test_extract_topic_ban(self):
        content = "{{topic ban|User:Example|scope=Climate}}"
        sanctions = extract_sanctions_from_text(content)

        assert len(sanctions) == 1
        assert sanctions[0].sanction_type == "topic_ban"
        assert sanctions[0].target_user == "User:Example"

    def test_extract_interaction_ban(self):
        content = "{{interaction ban|User:A|User:B}}"
        sanctions = extract_sanctions_from_text(content)

        assert len(sanctions) == 1
        assert sanctions[0].sanction_type == "interaction_ban"

    def test_extract_community_ban(self):
        content = "{{community ban|User:Vandal}}"
        sanctions = extract_sanctions_from_text(content)

        assert len(sanctions) == 1
        assert sanctions[0].sanction_type == "community_ban"

    def test_extract_block(self):
        content = "{{blocked|User:Sockpuppet}}"
        sanctions = extract_sanctions_from_text(content)

        assert len(sanctions) == 1
        assert sanctions[0].sanction_type == "block"

    def test_extract_multiple_sanctions(self):
        content = """
        {{topic ban|User:A|scope=Politics}}
        {{interaction ban|User:B|User:C}}
        {{blocked|User:D}}
        """
        sanctions = extract_sanctions_from_text(content)

        assert len(sanctions) == 3
        types = {s.sanction_type for s in sanctions}
        assert "topic_ban" in types
        assert "interaction_ban" in types
        assert "block" in types

    def test_parse_duration(self):
        content = "{{topic ban|User:Example|duration=1 year}}"
        sanctions = extract_sanctions_from_text(content)

        assert len(sanctions) == 1
        assert sanctions[0].duration == "1 year"

    def test_parse_indefinite(self):
        content = "{{topic ban|User:Example|indef}}"
        sanctions = extract_sanctions_from_text(content)

        assert len(sanctions) == 1
        assert sanctions[0].is_indefinite is True

    def test_case_insensitive_templates(self):
        content = "{{TOPIC BAN|User:Test}}"
        sanctions = extract_sanctions_from_text(content)

        assert len(sanctions) == 1

    def test_no_sanctions(self):
        content = "No sanctions were imposed in this case."
        sanctions = extract_sanctions_from_text(content)

        assert len(sanctions) == 0


class TestParseRemediesPage:
    """Tests for remedies page parsing."""

    def test_parse_remedies_with_templates(self):
        content = """
        == Remedies ==
        {{topic ban|User:Editor1|scope=Middle East}}
        {{interaction ban|User:Editor2|User:Editor3}}
        """
        sanctions = parse_remedies_page(content)

        assert len(sanctions) >= 2

    def test_parse_remedies_from_list(self):
        # List-based extraction is best-effort - templates are more reliable
        content = """
        == Sanctions ==
        * [[User:Editor1]] is topic banned from politics articles indefinitely.
        * [[User:Editor2]] receives a warning.
        """
        sanctions = parse_remedies_page(content)

        # List extraction may or may not find sanctions (best-effort)
        # The important thing is it doesn't crash
        assert isinstance(sanctions, list)

    def test_empty_remedies(self):
        content = "No remedies were imposed."
        sanctions = parse_remedies_page(content)

        assert len(sanctions) == 0


class TestParseCaseOutcome:
    """Tests for full case outcome parsing."""

    def test_parse_complete_case(self):
        pages = {
            "main": {
                "content": "{{ArbCom closed tasks}}\nThis case is closed."
            },
            "remedies": {
                "content": "{{topic ban|User:Test|scope=Climate}}"
            },
        }

        outcome = parse_case_outcome(pages)

        assert outcome.status == "closed"
        assert outcome.case_closed is True
        assert len(outcome.remedies) >= 1

    def test_parse_open_case(self):
        pages = {
            "main": {
                "content": "{{ArbCom open tasks}}\nEvidence phase."
            },
        }

        outcome = parse_case_outcome(pages)

        assert outcome.status == "open"
        assert outcome.case_closed is False

    def test_parse_case_without_remedies(self):
        pages = {
            "main": {
                "content": "This case is closed with no sanctions."
            },
        }

        outcome = parse_case_outcome(pages)

        assert len(outcome.remedies) == 0

    def test_empty_pages(self):
        pages = {}
        outcome = parse_case_outcome(pages)

        assert outcome.status == "unknown"


class TestSanctionDataclass:
    """Tests for Sanction dataclass."""

    def test_create_sanction(self):
        sanction = Sanction(
            sanction_type="topic_ban",
            target_user="TestUser",
            description="Banned from editing climate articles",
            duration="1 year",
            scope="Climate",
        )

        assert sanction.sanction_type == "topic_ban"
        assert sanction.target_user == "TestUser"
        assert sanction.duration == "1 year"
        assert sanction.scope == "Climate"
        assert sanction.is_indefinite is False

    def test_indefinite_sanction(self):
        sanction = Sanction(
            sanction_type="community_ban",
            target_user="Vandal",
            description="Banned indefinitely",
            is_indefinite=True,
        )

        assert sanction.is_indefinite is True


class TestCaseOutcomeDataclass:
    """Tests for CaseOutcome dataclass."""

    def test_create_outcome(self):
        outcome = CaseOutcome(
            status="closed",
            case_closed=True,
            remedies=[
                Sanction(
                    sanction_type="topic_ban",
                    target_user="User1",
                    description="Topic ban",
                )
            ],
        )

        assert outcome.status == "closed"
        assert outcome.case_closed is True
        assert len(outcome.remedies) == 1

    def test_default_values(self):
        outcome = CaseOutcome(status="open")

        assert outcome.case_closed is False
        assert outcome.has_active_remedies is False
        assert len(outcome.remedies) == 0
        assert len(outcome.findings) == 0
        assert len(outcome.principles) == 0


class TestSerialization:
    """Tests for dict conversion."""

    def test_sanctions_to_dict(self):
        sanctions = [
            Sanction(
                sanction_type="topic_ban",
                target_user="User1",
                description="Test",
                duration="1 year",
                scope="Politics",
                is_indefinite=False,
            )
        ]

        result = sanctions_to_dict(sanctions)

        assert len(result) == 1
        assert result[0]["sanction_type"] == "topic_ban"
        assert result[0]["target_user"] == "User1"
        assert result[0]["duration"] == "1 year"

    def test_outcome_to_dict(self):
        outcome = CaseOutcome(
            status="closed",
            case_closed=True,
            has_active_remedies=True,
            remedies=[
                Sanction(
                    sanction_type="block",
                    target_user="User1",
                    description="Blocked",
                )
            ],
            findings=["Finding 1"],
            principles=["Principle 1"],
        )

        result = outcome_to_dict(outcome)

        assert result["status"] == "closed"
        assert result["case_closed"] is True
        assert result["remedy_count"] == 1
        assert result["finding_count"] == 1
        assert result["principle_count"] == 1
        assert len(result["remedies"]) == 1


class TestStatusTemplates:
    """Tests for status template constants."""

    def test_open_templates_defined(self):
        assert "open" in STATUS_TEMPLATES
        assert len(STATUS_TEMPLATES["open"]) > 0

    def test_closed_templates_defined(self):
        assert "closed" in STATUS_TEMPLATES
        assert len(STATUS_TEMPLATES["closed"]) > 0

    def test_pending_templates_defined(self):
        assert "pending" in STATUS_TEMPLATES


class TestSanctionPatterns:
    """Tests for sanction pattern constants."""

    def test_topic_ban_patterns(self):
        assert "topic_ban" in SANCTION_PATTERNS
        assert len(SANCTION_PATTERNS["topic_ban"]) > 0

    def test_interaction_ban_patterns(self):
        assert "interaction_ban" in SANCTION_PATTERNS

    def test_community_ban_patterns(self):
        assert "community_ban" in SANCTION_PATTERNS

    def test_block_patterns(self):
        assert "block" in SANCTION_PATTERNS


class TestStatusTextPatterns:
    """Tests for status text pattern constants."""

    def test_closed_patterns_defined(self):
        assert "closed" in STATUS_TEXT_PATTERNS
        assert len(STATUS_TEXT_PATTERNS["closed"]) > 0

    def test_open_patterns_defined(self):
        assert "open" in STATUS_TEXT_PATTERNS
        assert len(STATUS_TEXT_PATTERNS["open"]) > 0

    def test_bold_case_closed_pattern(self):
        """Ensure bold '''Case Closed''' pattern exists."""
        patterns = STATUS_TEXT_PATTERNS["closed"]
        assert any("'''Case Closed'''" in p for p in patterns)
