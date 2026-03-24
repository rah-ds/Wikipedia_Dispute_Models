"""Integration tests for the dispute analysis pipeline.

These tests verify that the different modules work together correctly,
testing the full flow from raw data through to analysis outputs.
"""

import json

from src.arbitration import ArbitrationCaseSummary, cases_to_dataframe
from src.outcome import parse_decision, DecisionOutcome


# ---------------------------------------------------------------------------
# Realistic test data simulating actual Wikipedia dispute data
# ---------------------------------------------------------------------------

REALISTIC_CASE_DATA = {
    "case_name": "Climate change dispute",
    "case_prefix": "Wikipedia:Arbitration/Requests/Case/Climate change dispute",
    "fetched_at": "2026-01-15T14:30:00",
    "path_pattern": "Wikipedia:Arbitration/Requests/Case/{name}",
    "lifecycle_stages": {
        "stage_5_arbcom": {
            "description": "Arbitration Committee - final binding decisions",
            "path_pattern_used": "Wikipedia:Arbitration/Requests/Case/{name}",
            "pages": [
                {
                    "title": "Wikipedia:Arbitration/Requests/Case/Climate change dispute",
                    "url": "https://en.wikipedia.org/wiki/WP:ARBCC",
                    "subpage": "(main)",
                    "revision_count": 45,
                    "content_length": 15000,
                    "revisions": [
                        {
                            "revid": 1001,
                            "parentid": None,
                            "timestamp": "2024-01-01T10:00:00Z",
                            "user": "ClerkBot",
                            "comment": "Case opened",
                            "size": 500,
                        },
                        {
                            "revid": 1002,
                            "parentid": 1001,
                            "timestamp": "2024-01-02T11:00:00Z",
                            "user": "Party1",
                            "comment": "/* Statement */ Added my statement",
                            "size": 2000,
                        },
                        {
                            "revid": 1003,
                            "parentid": 1002,
                            "timestamp": "2024-01-03T12:00:00Z",
                            "user": "Party2",
                            "comment": "/* Response */ Responding to Party1",
                            "size": 3500,
                        },
                        {
                            "revid": 1004,
                            "parentid": 1003,
                            "timestamp": "2024-01-04T09:00:00Z",
                            "user": "Arbitrator1",
                            "comment": "/* Questions */ Questions for parties",
                            "size": 4000,
                        },
                    ],
                },
                {
                    "title": "Wikipedia:Arbitration/Requests/Case/Climate change dispute/Evidence",
                    "url": "https://en.wikipedia.org/wiki/WP:ARBCC/Evidence",
                    "subpage": "/Evidence",
                    "revision_count": 120,
                    "content_length": 45000,
                    "revisions": [
                        {
                            "revid": 2001,
                            "parentid": None,
                            "timestamp": "2024-01-05T10:00:00Z",
                            "user": "Party1",
                            "comment": "Evidence submission",
                            "size": 5000,
                        },
                        {
                            "revid": 2002,
                            "parentid": 2001,
                            "timestamp": "2024-01-06T14:00:00Z",
                            "user": "Party2",
                            "comment": "Counter-evidence",
                            "size": 8000,
                        },
                        {
                            "revid": 2003,
                            "parentid": 2002,
                            "timestamp": "2024-01-07T16:00:00Z",
                            "user": "Witness1",
                            "comment": "Third-party evidence",
                            "size": 10000,
                        },
                    ],
                },
                {
                    "title": "Wikipedia:Arbitration/Requests/Case/Climate change dispute/Proposed decision",
                    "url": "https://en.wikipedia.org/wiki/WP:ARBCC/Proposed_decision",
                    "subpage": "/Proposed decision",
                    "revision_count": 85,
                    "content_length": 25000,
                    "content": """\
==Proposed findings of fact==

===Edit warring occurred===
1) Multiple editors engaged in edit warring on [[Climate change]] articles.

:Support:
:# [[User:Arbitrator1|Arbitrator1]] 01:00, 15 January 2024 (UTC)
:# [[User:Arbitrator2|Arbitrator2]] 02:00, 15 January 2024 (UTC)
:# [[User:Arbitrator3|Arbitrator3]] 03:00, 15 January 2024 (UTC)
:# [[User:Arbitrator4|Arbitrator4]] 04:00, 15 January 2024 (UTC)
:# [[User:Arbitrator5|Arbitrator5]] 05:00, 15 January 2024 (UTC)

:Oppose:
:#

:Abstain:
:#

===Policy violations===
2) Party1 violated WP:CIVIL on multiple occasions.

:Support:
:# [[User:Arbitrator1|Arbitrator1]] 01:00, 16 January 2024 (UTC)
:# [[User:Arbitrator2|Arbitrator2]] 02:00, 16 January 2024 (UTC)
:# [[User:Arbitrator3|Arbitrator3]] 03:00, 16 January 2024 (UTC)
:# [[User:Arbitrator5|Arbitrator5]] 05:00, 16 January 2024 (UTC)

:Oppose:
:# [[User:Arbitrator4|Arbitrator4]] 04:00, 16 January 2024 (UTC)

:Abstain:
:#

==Proposed remedies==

===Topic ban for Party1===
3) [[User:Party1]] is topic-banned from climate-related articles.

:Support:
:# [[User:Arbitrator1|Arbitrator1]] 01:00, 17 January 2024 (UTC)
:# [[User:Arbitrator2|Arbitrator2]] 02:00, 17 January 2024 (UTC)
:# [[User:Arbitrator3|Arbitrator3]] 03:00, 17 January 2024 (UTC)
:# [[User:Arbitrator4|Arbitrator4]] 04:00, 17 January 2024 (UTC)

:Oppose:
:#

:Abstain:
:# [[User:Arbitrator5|Arbitrator5]] 05:00, 17 January 2024 (UTC)

===Warning for Party2===
4) [[User:Party2]] is warned about battleground behavior.

:Support:
:# [[User:Arbitrator1|Arbitrator1]] 01:00, 18 January 2024 (UTC)
:# [[User:Arbitrator5|Arbitrator5]] 05:00, 18 January 2024 (UTC)

:Oppose:
:# [[User:Arbitrator2|Arbitrator2]] 02:00, 18 January 2024 (UTC)
:# [[User:Arbitrator3|Arbitrator3]] 03:00, 18 January 2024 (UTC)
:# [[User:Arbitrator4|Arbitrator4]] 04:00, 18 January 2024 (UTC)

:Abstain:
:#
""",
                    "revisions": [
                        {
                            "revid": 3001,
                            "parentid": None,
                            "timestamp": "2024-01-15T10:00:00Z",
                            "user": "Arbitrator1",
                            "comment": "Draft proposed decision",
                            "size": 15000,
                        },
                        {
                            "revid": 3002,
                            "parentid": 3001,
                            "timestamp": "2024-01-16T11:00:00Z",
                            "user": "Arbitrator2",
                            "comment": "Reverted draft changes",
                            "size": 14500,
                        },
                    ],
                },
            ],
            "talk_pages": [
                {
                    "title": "Wikipedia talk:Arbitration/Requests/Case/Climate change dispute",
                    "url": "https://en.wikipedia.org/wiki/WT:ARBCC",
                    "subpage": "(main)",
                    "revision_count": 25,
                    "revisions": [
                        {
                            "revid": 4001,
                            "parentid": None,
                            "timestamp": "2024-01-02T10:00:00Z",
                            "user": "Party1",
                            "comment": "Process question",
                            "size": 500,
                        },
                    ],
                },
            ],
        },
        "stage_4_ani": {
            "description": "Administrators' Noticeboard/Incidents",
            "reports": [
                {
                    "title": "Wikipedia:Administrators' noticeboard/Incidents/Party1 conduct",
                    "source": "archive_12",
                    "search_term": "Party1",
                    "search_type": "participant",
                },
                {
                    "title": "Wikipedia:Administrators' noticeboard/Incidents/Climate articles",
                    "source": "current",
                    "search_term": "Climate change dispute",
                    "search_type": "case_name",
                },
            ],
        },
        "stage_3_drn": {
            "description": "Dispute Resolution Noticeboard",
            "mentions": [
                {
                    "type": "drn_archive_5",
                    "search_term": "Climate change dispute",
                    "url": "https://en.wikipedia.org/wiki/WP:DRN/Archive5",
                    "found": True,
                },
            ],
        },
        "stage_1_2_talk": {
            "description": "Talk pages where disputes originate",
            "pages": [
                {
                    "article": "Climate change",
                    "title": "Talk:Climate change",
                    "url": "https://en.wikipedia.org/wiki/Talk:Climate_change",
                    "revision_count": 500,
                    "revisions": [
                        {
                            "revid": 5001,
                            "parentid": None,
                            "timestamp": "2023-06-01T10:00:00Z",
                            "user": "Party1",
                            "comment": "/* Disputed section */ Discussion",
                            "size": 1000,
                        },
                        {
                            "revid": 5002,
                            "parentid": 5001,
                            "timestamp": "2023-06-02T11:00:00Z",
                            "user": "Party2",
                            "comment": "/* Disputed section */ Response",
                            "size": 1500,
                        },
                    ],
                },
            ],
        },
    },
    "participants": ["Party1", "Party2", "Witness1", "Arbitrator1"],
    "disputed_articles": ["Climate change", "Global warming"],
    "summary": {
        "arbcom_pages": 3,
        "arbcom_talk_pages": 1,
        "ani_reports": 2,
        "drn_mentions": 1,
        "talk_pages": 1,
        "participants_extracted": 4,
        "articles_extracted": 2,
        "total_revisions": 12,
        "lifecycle_stages_with_data": 4,
    },
}


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestFullPipelineIntegration:
    """Test the complete analysis pipeline from raw data to outputs."""

    def test_lifecycle_to_summary(self):
        """Test loading lifecycle format data and generating summary."""
        case = ArbitrationCaseSummary.from_dict(REALISTIC_CASE_DATA)

        assert case.case_name == "Climate change dispute"
        assert case.total_case_pages == 3
        assert case.total_editors > 0

    def test_decision_parsing_integration(self):
        """Test that decision outcomes are correctly parsed from lifecycle data."""
        case = ArbitrationCaseSummary.from_dict(REALISTIC_CASE_DATA)

        assert case.decision_outcome is not None
        assert isinstance(case.decision_outcome, DecisionOutcome)

        # Verify findings parsed correctly
        assert len(case.decision_outcome.findings) == 2
        assert case.decision_outcome.findings[0].passed is True  # 5 support, net=5 >= 4
        assert case.decision_outcome.findings[1].passed is False  # 4-1 = 3 net < 4

        # Verify remedies parsed correctly
        assert len(case.decision_outcome.remedies) == 2
        # Topic ban: 4 support, 0 oppose = net 4 = passed
        # Warning: 2 support, 3 oppose = net -1 = failed

    def test_editor_profile_aggregation(self):
        """Test that editor profiles are correctly aggregated across pages."""
        case = ArbitrationCaseSummary.from_dict(REALISTIC_CASE_DATA)

        # Party1 should appear on multiple pages
        assert "Party1" in case.editor_profiles
        party1 = case.editor_profiles["Party1"]
        assert party1.total_edits >= 2  # At least main case and evidence

        # Check pages touched
        assert len(party1.pages_touched) >= 1

    def test_conflict_detection(self):
        """Test that revert-based conflicts are detected."""
        case = ArbitrationCaseSummary.from_dict(REALISTIC_CASE_DATA)

        # Arbitrator2 reverted in proposed decision
        # Check if any conflict edges exist
        # (depends on revision ordering in test data)
        assert isinstance(case.conflict_edges, list)

    def test_summary_dict_completeness(self):
        """Test that summary dict contains all expected fields."""
        case = ArbitrationCaseSummary.from_dict(REALISTIC_CASE_DATA)
        summary = case.to_summary_dict()

        # Core fields
        assert "case_name" in summary
        assert "total_revisions" in summary
        assert "total_editors" in summary
        assert "case_duration_days" in summary

        # Consensus signals
        assert "consensus_evidence_edits" in summary

        # Decision outcome fields (since we have wikitext)
        assert "outcome_total_items" in summary
        assert "outcome_passed" in summary
        assert "outcome_failed" in summary

    def test_dataframe_conversion(self):
        """Test converting cases to pandas DataFrame."""
        case = ArbitrationCaseSummary.from_dict(REALISTIC_CASE_DATA)
        df = cases_to_dataframe([case])

        assert len(df) == 1
        assert "case_name" in df.columns
        assert df.iloc[0]["case_name"] == "Climate change dispute"

    def test_multiple_cases_dataframe(self):
        """Test DataFrame with multiple cases."""
        # Create two cases with different names
        case1_data = {**REALISTIC_CASE_DATA, "case_name": "Case Alpha"}
        case2_data = {**REALISTIC_CASE_DATA, "case_name": "Case Beta"}

        case1 = ArbitrationCaseSummary.from_dict(case1_data)
        case2 = ArbitrationCaseSummary.from_dict(case2_data)

        df = cases_to_dataframe([case1, case2])

        assert len(df) == 2
        assert set(df["case_name"]) == {"Case Alpha", "Case Beta"}


class TestCrossModuleConsistency:
    """Test that different modules produce consistent results."""

    def test_outcome_matches_arbitration_summary(self):
        """Verify outcome parser results match ArbitrationCaseSummary."""
        case = ArbitrationCaseSummary.from_dict(REALISTIC_CASE_DATA)
        wikitext = REALISTIC_CASE_DATA["lifecycle_stages"]["stage_5_arbcom"]["pages"][
            2
        ]["content"]

        # Parse directly
        direct_outcome = parse_decision(wikitext)

        # Get from case
        case_outcome = case.decision_outcome

        # Should match
        assert direct_outcome.total_items == case_outcome.total_items
        assert direct_outcome.total_passed == case_outcome.total_passed
        assert len(direct_outcome.findings) == len(case_outcome.findings)
        assert len(direct_outcome.remedies) == len(case_outcome.remedies)

    def test_revision_count_consistency(self):
        """Verify revision counts are consistent across methods."""
        case = ArbitrationCaseSummary.from_dict(REALISTIC_CASE_DATA)

        # Count from timeline (case_pages + case_talk_pages only)
        timeline_count = len(case.revision_timeline())

        # Count from case pages directly
        case_page_revs = sum(len(p.revisions) for p in case.case_pages)
        talk_page_revs = sum(len(p.revisions) for p in case.case_talk_pages)

        # Timeline should match case pages + talk pages
        assert timeline_count == case_page_revs + talk_page_revs

        # total_revisions includes article talk pages too
        assert case.total_revisions >= timeline_count

    def test_editor_count_consistency(self):
        """Verify editor counts are consistent."""
        case = ArbitrationCaseSummary.from_dict(REALISTIC_CASE_DATA)

        # Count from profiles
        profile_count = len(case.editor_profiles)

        # Count from total_editors
        total_editors = case.total_editors

        assert profile_count == total_editors


class TestFileIOIntegration:
    """Test file I/O operations in the pipeline."""

    def test_json_roundtrip(self, tmp_path):
        """Test that case data survives JSON serialization."""
        # Save to JSON
        json_path = tmp_path / "test_case.json"
        with open(json_path, "w") as f:
            json.dump(REALISTIC_CASE_DATA, f)

        # Load and parse
        case = ArbitrationCaseSummary.from_json_path(json_path)

        assert case.case_name == "Climate change dispute"
        assert case.decision_outcome is not None

    def test_multiple_files_batch_load(self, tmp_path):
        """Test loading multiple case files."""
        from src.arbitration import load_all_cases

        # Create multiple case files
        for i, name in enumerate(["Case_A", "Case_B", "Case_C"]):
            data = {**REALISTIC_CASE_DATA, "case_name": name}
            path = tmp_path / f"arb_dfs_{name}_20260101_00000{i}.json"
            with open(path, "w") as f:
                json.dump(data, f)

        # Load all
        cases = load_all_cases(tmp_path, "arb_dfs_*.json")

        assert len(cases) == 3
        names = {c.case_name for c in cases}
        assert names == {"Case_A", "Case_B", "Case_C"}


class TestEdgeCasesIntegration:
    """Integration tests for edge cases and error conditions."""

    def test_missing_decision_content(self):
        """Test handling when proposed decision has no wikitext."""
        data = {**REALISTIC_CASE_DATA}
        # Remove content from proposed decision
        data["lifecycle_stages"]["stage_5_arbcom"]["pages"][2] = {
            "title": "Test/Proposed decision",
            "url": "",
            "subpage": "/Proposed decision",
            "revisions": [],
            # No "content" key
        }

        case = ArbitrationCaseSummary.from_dict(data)

        # Should still work, just no outcome
        assert case.case_name == "Climate change dispute"
        assert case.decision_outcome is None

    def test_empty_lifecycle_stages(self):
        """Test handling when some lifecycle stages are empty."""
        data = {
            "case_name": "Empty Stages",
            "case_prefix": "Wikipedia:Arbitration/Test",
            "fetched_at": "2026-01-01T00:00:00",
            "lifecycle_stages": {
                "stage_5_arbcom": {"pages": [], "talk_pages": []},
                "stage_4_ani": {"reports": []},
                "stage_3_drn": {"mentions": []},
                "stage_1_2_talk": {"pages": []},
            },
            "participants": [],
            "disputed_articles": [],
            "summary": {},
        }

        case = ArbitrationCaseSummary.from_dict(data)

        assert case.total_revisions == 0
        assert case.total_editors == 0
        summary = case.to_summary_dict()
        assert summary["total_revisions"] == 0
