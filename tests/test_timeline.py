"""
Tests for timeline reconstruction module.
"""

from datetime import datetime, timezone

from src.models import DisputeStage, DisputeType, DisputeEvent
from src.timeline import (
    build_timeline_from_revisions,
    detect_dispute_emergence,
    identify_conflict_pairs,
    compute_escalation_features,
    build_dispute_timeline,
    summarize_timeline,
)


class TestTimelineFromRevisions:
    """Test building timeline entries from revision data."""

    def test_basic_edits(self):
        """Basic edits should create timeline entries."""
        revisions = [
            {
                "user": "Alice",
                "timestamp": "2023-01-01T12:00:00Z",
                "comment": "Added section on methodology",
            },
            {
                "user": "Bob",
                "timestamp": "2023-01-02T12:00:00Z",
                "comment": "Minor formatting",
            },
        ]

        entries = build_timeline_from_revisions("Test Article", revisions)

        assert len(entries) == 2
        assert entries[0].user == "Alice"
        assert entries[0].entry_type == "edit"
        assert entries[1].user == "Bob"

    def test_revert_detection(self):
        """Reverts should be detected from edit summaries."""
        revisions = [
            {
                "user": "Alice",
                "timestamp": "2023-01-01T12:00:00Z",
                "comment": "Added content",
            },
            {
                "user": "Bob",
                "timestamp": "2023-01-02T12:00:00Z",
                "comment": "Reverted edits by Alice - unsourced",
            },
            {
                "user": "Alice",
                "timestamp": "2023-01-03T12:00:00Z",
                "comment": "Undid revision by Bob",
            },
        ]

        entries = build_timeline_from_revisions("Test Article", revisions)

        assert entries[0].entry_type == "edit"
        assert entries[1].entry_type == "revert"
        assert entries[1].reverted_user == "Alice"
        assert entries[2].entry_type == "revert"

    def test_talk_page_entries(self):
        """Talk page revisions should be captured."""
        article_revisions = [
            {"user": "Alice", "timestamp": "2023-01-01T12:00:00Z", "comment": "Edit"}
        ]
        talk_revisions = [
            {
                "user": "Alice",
                "timestamp": "2023-01-02T12:00:00Z",
                "comment": "/* Methodology section */ Starting discussion",
            },
            {
                "user": "Bob",
                "timestamp": "2023-01-02T14:00:00Z",
                "comment": "/* Methodology section */ Reply",
            },
        ]

        entries = build_timeline_from_revisions(
            "Test Article", article_revisions, talk_revisions
        )

        assert len(entries) == 3

        # Check talk post entries
        talk_entries = [e for e in entries if e.entry_type == "talk_post"]
        assert len(talk_entries) == 2
        assert talk_entries[0].thread_title == "Methodology section"


class TestDisputeEmergence:
    """Test dispute emergence detection."""

    def test_no_dispute_few_reverts(self):
        """Few reverts should not trigger dispute detection."""
        entries = build_timeline_from_revisions(
            "Test",
            [
                {
                    "user": "Alice",
                    "timestamp": "2023-01-01T12:00:00Z",
                    "comment": "Edit",
                },
                {
                    "user": "Bob",
                    "timestamp": "2023-01-02T12:00:00Z",
                    "comment": "Revert",
                },
            ],
        )

        emergence = detect_dispute_emergence(entries)
        assert emergence is None

    def test_dispute_detected_multiple_reverts(self):
        """Multiple reverts between users should detect dispute."""
        revisions = [
            {
                "user": "Alice",
                "timestamp": "2023-01-01T10:00:00Z",
                "comment": "Added content",
            },
            {
                "user": "Bob",
                "timestamp": "2023-01-01T11:00:00Z",
                "comment": "Reverted edits by Alice",
            },
            {
                "user": "Alice",
                "timestamp": "2023-01-01T12:00:00Z",
                "comment": "Reverted edits by Bob",
            },
            {
                "user": "Bob",
                "timestamp": "2023-01-01T13:00:00Z",
                "comment": "Reverted edits by Alice again",
            },
            {
                "user": "Alice",
                "timestamp": "2023-01-01T14:00:00Z",
                "comment": "Undid revision by Bob",
            },
        ]

        entries = build_timeline_from_revisions("Test", revisions)

        # Verify we have enough reverts
        reverts = [e for e in entries if e.entry_type == "revert"]
        assert len(reverts) >= 3, f"Expected at least 3 reverts, got {len(reverts)}"

        emergence = detect_dispute_emergence(entries, revert_threshold=3, window_days=7)

        # Should detect dispute at first revert in the pattern
        assert emergence is not None


class TestConflictPairs:
    """Test identification of conflict pairs."""

    def test_identify_conflict_pairs(self):
        """Should identify pairs who revert each other frequently."""
        revisions = [
            {"user": "Alice", "timestamp": "2023-01-01T10:00:00Z", "comment": "Edit"},
            {
                "user": "Bob",
                "timestamp": "2023-01-01T11:00:00Z",
                "comment": "Revert edits by Alice",
            },
            {
                "user": "Alice",
                "timestamp": "2023-01-01T12:00:00Z",
                "comment": "Revert edits by Bob",
            },
            {
                "user": "Charlie",
                "timestamp": "2023-01-01T13:00:00Z",
                "comment": "Revert edits by Alice",
            },
        ]

        entries = build_timeline_from_revisions("Test", revisions)
        pairs = identify_conflict_pairs(entries)

        assert len(pairs) >= 1
        # Alice-Bob should be the top conflict pair (2 reverts between them)
        top_pair = pairs[0]
        assert "Alice" in top_pair[:2]
        assert "Bob" in top_pair[:2]


class TestEscalationFeatures:
    """Test computation of escalation prediction features."""

    def test_basic_features(self):
        """Should compute basic features from entries."""
        revisions = [
            {"user": "Alice", "timestamp": "2023-01-01T10:00:00Z", "comment": "Edit 1"},
            {"user": "Bob", "timestamp": "2023-01-02T10:00:00Z", "comment": "Edit 2"},
            {
                "user": "Alice",
                "timestamp": "2023-01-03T10:00:00Z",
                "comment": "Revert edits by Bob",
            },
        ]
        talk_revisions = [
            {
                "user": "Alice",
                "timestamp": "2023-01-01T12:00:00Z",
                "comment": "/* Discussion */ Started talk",
            },
        ]

        entries = build_timeline_from_revisions("Test", revisions, talk_revisions)
        features = compute_escalation_features(entries)

        assert features["revert_count"] == 1
        assert features["unique_editors"] >= 2
        assert features["talk_posts"] == 1

    def test_high_revert_ratio(self):
        """High revert ratio should be captured."""
        revisions = [
            {"user": "Alice", "timestamp": "2023-01-01T10:00:00Z", "comment": "Edit"},
            {"user": "Bob", "timestamp": "2023-01-01T11:00:00Z", "comment": "Revert"},
            {"user": "Alice", "timestamp": "2023-01-01T12:00:00Z", "comment": "Revert"},
            {"user": "Bob", "timestamp": "2023-01-01T13:00:00Z", "comment": "Revert"},
        ]

        entries = build_timeline_from_revisions("Test", revisions)
        features = compute_escalation_features(entries)

        assert features["revert_ratio"] >= 0.5  # 3 reverts / 4 edits


class TestFullTimeline:
    """Test building complete dispute timelines."""

    def test_build_complete_timeline(self):
        """Should build a complete timeline with all metadata."""
        revisions = [
            {
                "user": "Alice",
                "timestamp": "2023-01-01T10:00:00Z",
                "comment": "Initial",
            },
            {"user": "Bob", "timestamp": "2023-01-02T10:00:00Z", "comment": "Expanded"},
            {
                "user": "Alice",
                "timestamp": "2023-01-05T10:00:00Z",
                "comment": "Revert Bob",
            },
        ]

        timeline = build_dispute_timeline("Test Article", revisions)

        assert timeline.primary_article == "Test Article"
        assert len(timeline.events) == 3
        assert "Alice" in timeline.core_participants
        assert "Bob" in timeline.core_participants

    def test_timeline_with_dispute_events(self):
        """Should incorporate formal dispute events."""
        revisions = [
            {"user": "Alice", "timestamp": "2023-01-01T10:00:00Z", "comment": "Edit"},
        ]

        dispute_events = [
            DisputeEvent(
                event_id="drn_test_123",
                stage=DisputeStage.DRN,
                dispute_type=DisputeType.CONTENT,
                date_filed=datetime(2023, 1, 15, tzinfo=timezone.utc),
                participants=["Alice", "Bob"],
                articles=["Test Article"],
            )
        ]

        timeline = build_dispute_timeline(
            "Test Article", revisions, dispute_events=dispute_events
        )

        assert DisputeStage.DRN in timeline.stages_reached
        # Should have both the edit and the dispute event
        assert len(timeline.events) == 2


class TestSummarize:
    """Test timeline summarization."""

    def test_summary_generation(self):
        """Should generate a readable summary."""
        revisions = [
            {"user": "Alice", "timestamp": "2023-01-01T10:00:00Z", "comment": "Edit"},
            {
                "user": "Bob",
                "timestamp": "2023-01-02T10:00:00Z",
                "comment": "Revert Alice",
            },
            {
                "user": "Alice",
                "timestamp": "2023-01-03T10:00:00Z",
                "comment": "Revert Bob",
            },
        ]

        timeline = build_dispute_timeline("Test Article", revisions)
        summary = summarize_timeline(timeline)

        assert summary["article"] == "Test Article"
        assert "event_counts" in summary
        assert "features" in summary
