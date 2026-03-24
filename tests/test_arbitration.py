"""Tests for src.arbitration module."""

import json
import pytest

from src.arbitration import (
    ArbitrationCaseSummary,
    ConflictEdge,
    PageSummary,
    Revision,
    load_all_cases,
    cases_to_dataframe,
)
from src.outcome import DecisionOutcome


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_CASE = {
    "case_name": "Test Case",
    "case_prefix": "Wikipedia:Arbitration/Requests/Case/Test Case",
    "fetched_at": "2026-01-31T00:00:00",
    "case_pages": [
        {
            "title": "Wikipedia:Arbitration/Requests/Case/Test Case",
            "url": "https://en.wikipedia.org/wiki/Test",
            "subpage": "(main)",
            "exists": True,
            "revisions": [
                {
                    "revid": 1,
                    "parentid": None,
                    "timestamp": "2024-01-01T00:00:00Z",
                    "user": "Alice",
                    "comment": "Initial filing",
                    "size": 1000,
                },
                {
                    "revid": 2,
                    "parentid": 1,
                    "timestamp": "2024-01-02T00:00:00Z",
                    "user": "Bob",
                    "comment": "Reverted edits by Alice",
                    "size": 950,
                },
                {
                    "revid": 3,
                    "parentid": 2,
                    "timestamp": "2024-01-03T00:00:00Z",
                    "user": "Alice",
                    "comment": "/* Proposed remedies */ updated",
                    "size": 1100,
                },
            ],
        },
        {
            "title": "Wikipedia:Arbitration/Requests/Case/Test Case/Evidence",
            "url": "https://en.wikipedia.org/wiki/Test/Evidence",
            "subpage": "/Evidence",
            "exists": True,
            "revisions": [
                {
                    "revid": 10,
                    "parentid": None,
                    "timestamp": "2024-01-05T00:00:00Z",
                    "user": "Charlie",
                    "comment": "Adding evidence",
                    "size": 2000,
                },
            ],
        },
    ],
    "case_talk_pages": [],
    "linked_articles": [],
    "article_talk_pages": [],
    "summary": {"total_linked_articles": 5},
}


@pytest.fixture
def minimal_case():
    return ArbitrationCaseSummary.from_dict(MINIMAL_CASE)


@pytest.fixture
def minimal_case_json(tmp_path):
    path = tmp_path / "arb_dfs_Test_Case_20260101_000000.json"
    path.write_text(json.dumps(MINIMAL_CASE))
    return path


# ---------------------------------------------------------------------------
# Revision tests
# ---------------------------------------------------------------------------


class TestRevision:
    def test_from_dict(self):
        r = Revision.from_dict(
            {
                "revid": 42,
                "parentid": 41,
                "timestamp": "2024-06-15T12:00:00Z",
                "user": "Editor1",
                "comment": "fixed typo",
                "size": 500,
            }
        )
        assert r.revid == 42
        assert r.user == "Editor1"
        assert not r.is_revert

    def test_detects_revert(self):
        r = Revision.from_dict(
            {
                "revid": 1,
                "timestamp": "2024-01-01T00:00:00Z",
                "user": "A",
                "comment": "Reverted edits by B",
            }
        )
        assert r.is_revert

    def test_extracts_section(self):
        r = Revision.from_dict(
            {
                "revid": 1,
                "timestamp": "2024-01-01T00:00:00Z",
                "user": "A",
                "comment": "/* Climate data */ added source",
            }
        )
        assert r.section == "Climate data"


# ---------------------------------------------------------------------------
# PageSummary tests
# ---------------------------------------------------------------------------


class TestPageSummary:
    def test_from_dict_populates_editors(self):
        p = PageSummary.from_dict(MINIMAL_CASE["case_pages"][0])
        assert "Alice" in p.editors
        assert "Bob" in p.editors
        assert p.revision_count == 3

    def test_first_last_edit(self):
        p = PageSummary.from_dict(MINIMAL_CASE["case_pages"][0])
        assert p.first_edit == "2024-01-01T00:00:00Z"
        assert p.last_edit == "2024-01-03T00:00:00Z"


# ---------------------------------------------------------------------------
# ArbitrationCaseSummary tests
# ---------------------------------------------------------------------------


class TestArbitrationCaseSummary:
    def test_from_dict(self, minimal_case):
        assert minimal_case.case_name == "Test Case"
        assert minimal_case.total_case_pages == 2
        assert minimal_case.total_revisions == 4  # 3 + 1

    def test_total_editors(self, minimal_case):
        assert minimal_case.total_editors == 3  # Alice, Bob, Charlie

    def test_editor_profiles(self, minimal_case):
        assert "Alice" in minimal_case.editor_profiles
        assert minimal_case.editor_profiles["Alice"].total_edits == 2
        assert minimal_case.editor_profiles["Bob"].total_reverts == 1

    def test_top_editors(self, minimal_case):
        top = minimal_case.top_editors(2)
        assert len(top) == 2
        assert top[0].username == "Alice"  # 2 edits
        assert top[0].total_edits >= top[1].total_edits

    def test_conflict_edges(self, minimal_case):
        # Bob reverted Alice (revid 2 is a revert, previous edit is Alice's revid 1)
        assert len(minimal_case.conflict_edges) >= 1
        edge = minimal_case.conflict_edges[0]
        assert isinstance(edge, ConflictEdge)
        assert edge.count >= 1

    def test_consensus_signals(self, minimal_case):
        cs = minimal_case.consensus_signals()
        assert "evidence_edits" in cs
        assert cs["evidence_edits"] == 1
        assert "case_duration_days" in cs

    def test_subpage_edit_counts(self, minimal_case):
        counts = minimal_case.subpage_edit_counts()
        assert counts["(main)"] == 3
        assert counts["/Evidence"] == 1

    def test_revision_timeline(self, minimal_case):
        tl = minimal_case.revision_timeline()
        assert len(tl) == 4
        # Should be sorted chronologically
        for i in range(len(tl) - 1):
            assert tl[i].timestamp <= tl[i + 1].timestamp

    def test_revision_timeline_filtered(self, minimal_case):
        tl = minimal_case.revision_timeline(subpage="/Evidence")
        assert len(tl) == 1
        assert tl[0].user == "Charlie"

    def test_monthly_activity(self, minimal_case):
        ma = minimal_case.monthly_activity()
        assert "2024-01" in ma
        assert ma["2024-01"] == 4

    def test_to_summary_dict(self, minimal_case):
        d = minimal_case.to_summary_dict()
        assert d["case_name"] == "Test Case"
        assert d["total_revisions"] == 4
        assert "consensus_evidence_edits" in d

    def test_from_json_path(self, minimal_case_json):
        cs = ArbitrationCaseSummary.from_json_path(minimal_case_json)
        assert cs.case_name == "Test Case"

    def test_editor_overlap(self, minimal_case):
        overlap = minimal_case.editor_overlap("(main)", "/Evidence")
        # Charlie only on Evidence, Alice and Bob only on main
        assert len(overlap) == 0

    def test_editors_on_subpage(self, minimal_case):
        editors = minimal_case.editors_on_subpage("(main)")
        names = {e.username for e in editors}
        assert "Alice" in names
        assert "Bob" in names
        assert "Charlie" not in names

    def test_case_duration_days(self, minimal_case):
        # 2024-01-01 to 2024-01-05 = 4 days
        assert minimal_case.case_duration_days == 4


# ---------------------------------------------------------------------------
# Batch loader tests
# ---------------------------------------------------------------------------


class TestBatchLoader:
    def test_load_all_cases(self, tmp_path):
        # Write two case files
        for name in ["CaseA", "CaseB"]:
            d = {**MINIMAL_CASE, "case_name": name}
            (tmp_path / f"arb_dfs_{name}_20260101_000000.json").write_text(
                json.dumps(d)
            )

        cases = load_all_cases(tmp_path, "arb_dfs_*.json")
        assert len(cases) == 2

    def test_cases_to_dataframe(self, tmp_path):
        for name in ["CaseA", "CaseB"]:
            d = {**MINIMAL_CASE, "case_name": name}
            (tmp_path / f"arb_dfs_{name}_20260101_000000.json").write_text(
                json.dumps(d)
            )

        cases = load_all_cases(tmp_path, "arb_dfs_*.json")
        df = cases_to_dataframe(cases)
        assert len(df) == 2
        assert "case_name" in df.columns
        assert "total_revisions" in df.columns


# ---------------------------------------------------------------------------
# Decision outcome integration tests
# ---------------------------------------------------------------------------

# Wikitext for a /Proposed decision page with votes
SAMPLE_PROPOSED_DECISION_WIKITEXT = """\
==Proposed findings of fact==
===Test finding===
1) This is a test finding about the dispute.

:Support:
:# [[User:Arb1|Arb1]] 01:00, 1 Jan 2024 (UTC)
:# [[User:Arb2|Arb2]] 02:00, 1 Jan 2024 (UTC)
:# [[User:Arb3|Arb3]] 03:00, 1 Jan 2024 (UTC)
:# [[User:Arb4|Arb4]] 04:00, 1 Jan 2024 (UTC)
:# [[User:Arb5|Arb5]] 05:00, 1 Jan 2024 (UTC)

:Oppose:
:#

:Abstain:
:#

==Proposed remedies==
===Editor topic-banned===
2) [[User:Troublemaker]] is topic-banned.

:Support:
:# [[User:Arb1|Arb1]] 01:00, 2 Jan 2024 (UTC)
:# [[User:Arb2|Arb2]] 02:00, 2 Jan 2024 (UTC)
:# [[User:Arb3|Arb3]] 03:00, 2 Jan 2024 (UTC)
:# [[User:Arb4|Arb4]] 04:00, 2 Jan 2024 (UTC)

:Oppose:
:#

:Abstain:
:# [[User:Arb5|Arb5]] 05:00, 2 Jan 2024 (UTC)

===Editor banned===
3) [[User:Troublemaker]] is site-banned.

:Support:
:#

:Oppose:
:# [[User:Arb1|Arb1]] 01:00, 3 Jan 2024 (UTC)
:# [[User:Arb2|Arb2]] 02:00, 3 Jan 2024 (UTC)
:# [[User:Arb3|Arb3]] 03:00, 3 Jan 2024 (UTC)
:# [[User:Arb4|Arb4]] 04:00, 3 Jan 2024 (UTC)

:Abstain:
:# [[User:Arb5|Arb5]] 05:00, 3 Jan 2024 (UTC)
"""

CASE_WITH_WIKITEXT = {
    "case_name": "Wikitext Case",
    "case_prefix": "Wikipedia:Arbitration/Requests/Case/Wikitext Case",
    "fetched_at": "2026-01-31T00:00:00",
    "case_pages": [
        {
            "title": "Wikipedia:Arbitration/Requests/Case/Wikitext Case",
            "url": "https://en.wikipedia.org/wiki/Test",
            "subpage": "(main)",
            "exists": True,
            "revisions": [
                {
                    "revid": 1,
                    "parentid": None,
                    "timestamp": "2024-01-01T00:00:00Z",
                    "user": "Alice",
                    "comment": "Initial filing",
                    "size": 1000,
                },
            ],
        },
        {
            "title": "Wikipedia:Arbitration/Requests/Case/Wikitext Case/Proposed decision",
            "url": "https://en.wikipedia.org/wiki/Test/Proposed_decision",
            "subpage": "/Proposed decision",
            "exists": True,
            "content": SAMPLE_PROPOSED_DECISION_WIKITEXT,
            "revisions": [
                {
                    "revid": 100,
                    "parentid": None,
                    "timestamp": "2024-01-10T00:00:00Z",
                    "user": "Arb1",
                    "comment": "Draft proposed decision",
                    "size": 5000,
                },
            ],
        },
    ],
    "case_talk_pages": [],
    "linked_articles": [],
    "article_talk_pages": [],
    "summary": {},
}


@pytest.fixture
def case_with_wikitext():
    return ArbitrationCaseSummary.from_dict(CASE_WITH_WIKITEXT)


class TestDecisionOutcomeIntegration:
    """Tests that ArbitrationCaseSummary correctly parses decision outcomes."""

    def test_decision_outcome_parsed(self, case_with_wikitext):
        assert case_with_wikitext.decision_outcome is not None
        assert isinstance(case_with_wikitext.decision_outcome, DecisionOutcome)

    def test_findings_extracted(self, case_with_wikitext):
        outcome = case_with_wikitext.decision_outcome
        assert len(outcome.findings) == 1
        assert outcome.findings[0].votes.support == 5
        assert outcome.findings[0].passed is True

    def test_remedies_extracted(self, case_with_wikitext):
        outcome = case_with_wikitext.decision_outcome
        assert len(outcome.remedies) == 2
        # First remedy passes (4 support, 0 oppose)
        passed = [r for r in outcome.remedies if r.passed]
        assert len(passed) == 1
        # Second remedy fails (0 support, 4 oppose)
        failed = [r for r in outcome.remedies if not r.passed]
        assert len(failed) == 1

    def test_outcome_in_summary_dict(self, case_with_wikitext):
        d = case_with_wikitext.to_summary_dict()
        assert "outcome_total_items" in d
        assert d["outcome_total_items"] == 3
        assert d["outcome_passed"] == 2  # finding + topic-ban
        assert d["outcome_failed"] == 1  # site-ban
        assert d["outcome_findings_passed"] == 1
        assert d["outcome_remedies_passed"] == 1

    def test_no_wikitext_no_outcome(self, minimal_case):
        """Cases without wikitext content should have no outcome."""
        assert minimal_case.decision_outcome is None

    def test_no_outcome_fields_in_summary_without_wikitext(self, minimal_case):
        d = minimal_case.to_summary_dict()
        assert "outcome_total_items" not in d

    def test_from_json_with_wikitext(self, tmp_path):
        path = tmp_path / "arb_dfs_WikitextCase_20260101_000000.json"
        path.write_text(json.dumps(CASE_WITH_WIKITEXT))
        case = ArbitrationCaseSummary.from_json_path(path)
        assert case.decision_outcome is not None
        assert case.decision_outcome.total_items == 3


# ---------------------------------------------------------------------------
# Error handling and edge case tests
# ---------------------------------------------------------------------------


class TestArbitrationErrorHandling:
    """Tests for error handling and edge cases in arbitration module."""

    def test_empty_case_data(self):
        """Empty dict should create valid but empty summary."""
        case = ArbitrationCaseSummary.from_dict({})
        assert case.case_name == ""
        assert case.total_revisions == 0
        assert case.total_editors == 0

    def test_missing_revisions(self):
        """Pages without revisions should be handled gracefully."""
        data = {
            "case_name": "No Revisions",
            "case_pages": [
                {
                    "title": "Test",
                    "url": "https://example.com",
                    "subpage": "(main)",
                    "revisions": [],
                }
            ],
        }
        case = ArbitrationCaseSummary.from_dict(data)
        assert case.total_revisions == 0

    def test_malformed_revision_data(self):
        """Revisions with missing fields should use defaults."""
        data = {
            "case_name": "Malformed",
            "case_pages": [
                {
                    "title": "Test",
                    "url": "",
                    "subpage": "(main)",
                    "revisions": [
                        {},  # Empty revision
                        {"revid": 1},  # Missing most fields
                        {"user": "Alice", "timestamp": "2024-01-01T00:00:00Z"},
                    ],
                }
            ],
        }
        case = ArbitrationCaseSummary.from_dict(data)
        assert case.total_revisions == 3

    def test_none_user_in_revision(self):
        """Revisions with None/empty user should be skipped in profiles."""
        data = {
            "case_name": "None User",
            "case_pages": [
                {
                    "title": "Test",
                    "url": "",
                    "subpage": "(main)",
                    "revisions": [
                        {"user": "", "timestamp": "2024-01-01T00:00:00Z"},
                        {"user": None, "timestamp": "2024-01-02T00:00:00Z"},
                        {"user": "ValidUser", "timestamp": "2024-01-03T00:00:00Z"},
                    ],
                }
            ],
        }
        case = ArbitrationCaseSummary.from_dict(data)
        assert case.total_editors == 1
        assert "ValidUser" in case.editor_profiles

    def test_lifecycle_format_detection(self):
        """Should correctly detect and parse lifecycle format."""
        lifecycle_data = {
            "case_name": "Lifecycle Case",
            "case_prefix": "Wikipedia:Arbitration/Requests/Case/Test",
            "fetched_at": "2026-01-01T00:00:00",
            "lifecycle_stages": {
                "stage_5_arbcom": {
                    "pages": [
                        {
                            "title": "Test",
                            "url": "",
                            "subpage": "(main)",
                            "revisions": [
                                {
                                    "revid": 1,
                                    "user": "Editor",
                                    "timestamp": "2024-01-01T00:00:00Z",
                                    "comment": "Edit",
                                }
                            ],
                        }
                    ],
                    "talk_pages": [],
                },
                "stage_4_ani": {"reports": []},
                "stage_3_drn": {"mentions": []},
                "stage_1_2_talk": {"pages": []},
            },
            "participants": ["Editor"],
            "disputed_articles": ["Article1"],
            "summary": {},
        }
        case = ArbitrationCaseSummary.from_dict(lifecycle_data)
        assert case.case_name == "Lifecycle Case"
        assert case.total_revisions == 1

    def test_load_all_cases_skips_invalid(self, tmp_path):
        """load_all_cases should skip files that fail to parse."""
        # Valid file
        valid = {**MINIMAL_CASE, "case_name": "Valid"}
        (tmp_path / "arb_dfs_Valid_20260101_000000.json").write_text(json.dumps(valid))

        # Invalid JSON
        (tmp_path / "arb_dfs_Invalid_20260101_000000.json").write_text("not json")

        cases = load_all_cases(tmp_path, "arb_dfs_*.json")
        assert len(cases) == 1
        assert cases[0].case_name == "Valid"


class TestRevisionEdgeCases:
    """Edge case tests for Revision class."""

    def test_revert_keywords(self):
        """Test all revert keyword variations."""
        keywords = ["revert", "rv ", "undo", "undid", "rollback"]
        for kw in keywords:
            r = Revision.from_dict(
                {"revid": 1, "timestamp": "", "user": "A", "comment": f"{kw} something"}
            )
            assert r.is_revert, f"Should detect '{kw}' as revert"

    def test_no_false_positive_reverts(self):
        """Words containing revert keywords shouldn't trigger."""
        r = Revision.from_dict(
            {
                "revid": 1,
                "timestamp": "",
                "user": "A",
                "comment": "converted to new format",
            }
        )
        assert not r.is_revert

    def test_section_extraction_edge_cases(self):
        """Test section extraction from various comment formats."""
        # Multiple sections
        r = Revision.from_dict(
            {
                "revid": 1,
                "timestamp": "",
                "user": "A",
                "comment": "/* First */ text /* Second */",
            }
        )
        assert r.section == "First"  # Should get first match

        # Empty section
        r = Revision.from_dict(
            {"revid": 1, "timestamp": "", "user": "A", "comment": "/*  */ empty"}
        )
        assert r.section == ""

    def test_timestamp_parsing(self):
        """Test timestamp parsing with various formats."""
        r = Revision.from_dict(
            {
                "revid": 1,
                "timestamp": "2024-06-15T12:30:45Z",
                "user": "A",
                "comment": "",
            }
        )
        ts = r.ts
        assert ts.year == 2024
        assert ts.month == 6
        assert ts.day == 15


class TestEditorProfile:
    """Tests for EditorProfile class."""

    def test_revert_ratio_zero_edits(self):
        """Revert ratio should handle zero edits."""
        from src.arbitration import EditorProfile

        p = EditorProfile(username="Test")
        assert p.revert_ratio == 0.0

    def test_active_days_calculation(self):
        """Test active days with various date ranges."""
        from src.arbitration import EditorProfile

        p = EditorProfile(
            username="Test",
            first_seen="2024-01-01T00:00:00Z",
            last_seen="2024-01-10T00:00:00Z",
        )
        assert p.active_days == 9

    def test_active_days_same_day(self):
        """Same day activity should return 0 days."""
        from src.arbitration import EditorProfile

        p = EditorProfile(
            username="Test",
            first_seen="2024-01-01T10:00:00Z",
            last_seen="2024-01-01T20:00:00Z",
        )
        assert p.active_days == 0

    def test_active_days_no_timestamps(self):
        """No timestamps should return 0."""
        from src.arbitration import EditorProfile

        p = EditorProfile(username="Test")
        assert p.active_days == 0
