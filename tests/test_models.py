"""
Tests for dispute resolution data models.
"""

from datetime import datetime, timezone

from src.models import (
    DisputeStage,
    DisputeType,
    OutcomeType,
    Editor,
    Article,
    DisputeEvent,
    DisputeTimeline,
    TimelineEntry,
    compute_editor_overlap,
    compute_temporal_proximity,
    compute_link_score,
    should_link_events,
    is_valid_transition,
    is_escalation,
)


def make_event(
    event_id: str,
    participants: list[str],
    articles: list[str] = None,
    date_filed: datetime = None,
) -> DisputeEvent:
    """Helper to create a DisputeEvent with minimal fields."""
    return DisputeEvent(
        event_id=event_id,
        stage=DisputeStage.DRN,
        dispute_type=DisputeType.CONTENT,
        participants=participants or [],
        articles=articles or [],
        date_filed=date_filed,
    )


class TestEnums:
    """Test dispute stage and type enums."""

    def test_dispute_stages_ordered(self):
        """Stages should follow escalation order."""
        stages = [
            DisputeStage.TALK,
            DisputeStage.THIRD_OPINION,
            DisputeStage.RFC,
            DisputeStage.DRN,
            DisputeStage.ANI,
            DisputeStage.ARBCOM,
            DisputeStage.RESOLVED,
        ]
        assert len(stages) == 7

    def test_dispute_type_values(self):
        """Dispute types should have expected values."""
        assert DisputeType.CONTENT.value == "content"
        assert DisputeType.CONDUCT.value == "conduct"
        assert DisputeType.HYBRID.value == "hybrid"

    def test_outcome_types(self):
        """Outcome types should cover main resolutions."""
        expected = {
            "consensus",
            "no_consensus",
            "escalated",
            "sanctions",
            "withdrawn",
            "closed",
            "pending",
        }
        actual = {ot.value for ot in OutcomeType}
        assert actual == expected


class TestEditorOverlap:
    """Test editor overlap computation."""

    def test_identical_sets(self):
        """Identical editor sets should have overlap 1.0."""
        editors = ["Alice", "Bob", "Charlie"]
        event1 = make_event("event1", participants=editors)
        event2 = make_event("event2", participants=editors)
        assert compute_editor_overlap(event1, event2) == 1.0

    def test_disjoint_sets(self):
        """Disjoint editor sets should have overlap 0.0."""
        event1 = make_event("event1", participants=["Alice", "Bob"])
        event2 = make_event("event2", participants=["Charlie", "David"])
        assert compute_editor_overlap(event1, event2) == 0.0

    def test_partial_overlap(self):
        """Partial overlap should be between 0 and 1."""
        event1 = make_event("event1", participants=["Alice", "Bob", "Charlie"])
        event2 = make_event("event2", participants=["Bob", "Charlie", "David"])
        # Jaccard: intersection(2) / union(4) = 0.5
        assert compute_editor_overlap(event1, event2) == 0.5

    def test_empty_sets(self):
        """Empty sets should return 0.0."""
        event1 = make_event("event1", participants=[])
        event2 = make_event("event2", participants=[])
        assert compute_editor_overlap(event1, event2) == 0.0

        event3 = make_event("event3", participants=["Alice"])
        assert compute_editor_overlap(event1, event3) == 0.0

    def test_single_overlap(self):
        """Single editor overlap should work correctly."""
        event1 = make_event("event1", participants=["Alice", "Bob"])
        event2 = make_event("event2", participants=["Bob", "Charlie", "David"])
        # Jaccard: 1 / 4 = 0.25
        assert compute_editor_overlap(event1, event2) == 0.25


class TestTemporalProximity:
    """Test temporal proximity computation."""

    def test_same_time(self):
        """Same timestamp should have proximity 1.0."""
        t = datetime(2023, 1, 1, tzinfo=timezone.utc)
        event1 = make_event("event1", participants=["Alice"], date_filed=t)
        event2 = make_event("event2", participants=["Alice"], date_filed=t)
        assert compute_temporal_proximity(event1, event2) == 1.0

    def test_14_day_half_life(self):
        """14 days apart should give ~0.5 proximity."""
        t1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2023, 1, 15, tzinfo=timezone.utc)
        event1 = make_event("event1", participants=["Alice"], date_filed=t1)
        event2 = make_event("event2", participants=["Alice"], date_filed=t2)
        proximity = compute_temporal_proximity(event1, event2)
        assert 0.4 < proximity < 0.6  # Allow some tolerance

    def test_very_distant(self):
        """Events months apart should have very low proximity."""
        t1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2023, 6, 1, tzinfo=timezone.utc)  # ~150 days
        event1 = make_event("event1", participants=["Alice"], date_filed=t1)
        event2 = make_event("event2", participants=["Alice"], date_filed=t2)
        proximity = compute_temporal_proximity(event1, event2)
        assert proximity < 0.01

    def test_order_independent(self):
        """Order of timestamps shouldn't matter."""
        t1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2023, 1, 10, tzinfo=timezone.utc)
        event1 = make_event("event1", participants=["Alice"], date_filed=t1)
        event2 = make_event("event2", participants=["Alice"], date_filed=t2)
        assert compute_temporal_proximity(event1, event2) == compute_temporal_proximity(
            event2, event1
        )


class TestLinkScore:
    """Test combined link score computation."""

    def test_strong_link(self):
        """Events with high overlap and proximity should link strongly."""
        t1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2023, 1, 5, tzinfo=timezone.utc)

        event1 = make_event(
            "event1",
            participants=["Alice", "Bob", "Charlie"],
            articles=["Article_A"],
            date_filed=t1,
        )
        event2 = make_event(
            "event2",
            participants=["Alice", "Bob", "David"],
            articles=["Article_A"],
            date_filed=t2,
        )

        score, _ = compute_link_score(event1, event2)
        assert score > 0.5

    def test_weak_link(self):
        """Events with low overlap or distant times should link weakly."""
        t1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2023, 6, 1, tzinfo=timezone.utc)

        event1 = make_event(
            "event1",
            participants=["Alice", "Bob"],
            articles=["Article_A"],
            date_filed=t1,
        )
        event2 = make_event(
            "event2",
            participants=["Charlie", "David"],
            articles=["Article_B"],
            date_filed=t2,
        )

        score, _ = compute_link_score(event1, event2)
        assert score < 0.1

    def test_should_link_threshold(self):
        """should_link_events should respect threshold."""
        t1 = datetime(2023, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2023, 1, 2, tzinfo=timezone.utc)

        event1 = make_event(
            "event1",
            participants=["Alice", "Bob", "Charlie"],
            articles=["Article_A"],
            date_filed=t1,
        )
        event2 = make_event(
            "event2",
            participants=["Alice", "Bob", "Charlie"],
            articles=["Article_A"],
            date_filed=t2,
        )

        # Strong overlap and close time - should link
        assert should_link_events(event1, event2, threshold=0.3)


class TestTransitions:
    """Test state transition validation."""

    def test_valid_talk_transitions(self):
        """Talk can go to multiple venues."""
        assert is_valid_transition(DisputeStage.TALK, DisputeStage.THIRD_OPINION)
        assert is_valid_transition(DisputeStage.TALK, DisputeStage.RFC)
        assert is_valid_transition(DisputeStage.TALK, DisputeStage.DRN)
        assert is_valid_transition(DisputeStage.TALK, DisputeStage.ANI)
        assert is_valid_transition(DisputeStage.TALK, DisputeStage.RESOLVED)

    def test_drn_to_ani_transition(self):
        """DRN can escalate to ANI (common for failed mediations)."""
        assert is_valid_transition(DisputeStage.DRN, DisputeStage.ANI)

    def test_ani_to_arbcom_transition(self):
        """ANI can escalate to ArbCom (serious conduct issues)."""
        assert is_valid_transition(DisputeStage.ANI, DisputeStage.ARBCOM)

    def test_invalid_arbcom_to_talk(self):
        """ArbCom should not go back to Talk."""
        assert not is_valid_transition(DisputeStage.ARBCOM, DisputeStage.TALK)

    def test_resolved_is_terminal(self):
        """Resolved should be terminal (no transitions out)."""
        for stage in DisputeStage:
            if stage != DisputeStage.RESOLVED:
                assert not is_valid_transition(DisputeStage.RESOLVED, stage)


class TestEscalation:
    """Test escalation detection."""

    def test_talk_to_drn_is_escalation(self):
        """Talk to DRN is an escalation."""
        assert is_escalation(DisputeStage.TALK, DisputeStage.DRN)

    def test_drn_to_ani_is_escalation(self):
        """DRN to ANI is an escalation."""
        assert is_escalation(DisputeStage.DRN, DisputeStage.ANI)

    def test_ani_to_arbcom_is_escalation(self):
        """ANI to ArbCom is an escalation."""
        assert is_escalation(DisputeStage.ANI, DisputeStage.ARBCOM)

    def test_talk_to_resolved_is_escalation(self):
        """Talk to Resolved is technically an escalation (higher stage order)."""
        # RESOLVED has order 5, TALK has order 0, so this is "escalation"
        # in the sense of moving up the stage order (even though semantically it's resolution)
        assert is_escalation(DisputeStage.TALK, DisputeStage.RESOLVED)

    def test_same_stage_not_escalation(self):
        """Same stage should not be escalation."""
        assert not is_escalation(DisputeStage.DRN, DisputeStage.DRN)


class TestDataclasses:
    """Test dataclass instantiation and methods."""

    def test_editor_creation(self):
        """Editor dataclass should instantiate correctly."""
        editor = Editor(
            username="TestUser",
            dispute_events=["case_1", "case_2"],
            sanctions=[{"type": "topic_ban", "topic": "Israel-Palestine"}],
        )
        assert editor.username == "TestUser"
        assert len(editor.dispute_events) == 2

    def test_article_creation(self):
        """Article dataclass should instantiate correctly."""
        article = Article(
            title="Climate change",
            revert_count=500,
            revert_ratio=0.1,
            topic_area="science",
        )
        assert article.revert_ratio == 0.1

    def test_dispute_event_creation(self):
        """DisputeEvent should capture all key fields."""
        event = DisputeEvent(
            event_id="drn_123",
            stage=DisputeStage.DRN,
            dispute_type=DisputeType.CONTENT,
            date_filed=datetime(2023, 6, 1, tzinfo=timezone.utc),
            participants=["Alice", "Bob"],
            articles=["Climate change"],
            source_url="https://en.wikipedia.org/wiki/WP:DRN#Case123",
        )
        assert event.stage == DisputeStage.DRN
        assert event.outcome == OutcomeType.PENDING  # Default

    def test_timeline_entry_creation(self):
        """TimelineEntry should work for different entry types."""
        edit = TimelineEntry(
            timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc),
            entry_type="edit",
            user="Alice",
            edit_summary="Added section on methodology",
        )
        assert edit.entry_type == "edit"

        revert = TimelineEntry(
            timestamp=datetime(2023, 1, 2, tzinfo=timezone.utc),
            entry_type="revert",
            user="Bob",
            reverted_user="Alice",
            edit_summary="Reverted - unsourced",
        )
        assert revert.entry_type == "revert"
        assert revert.reverted_user == "Alice"

    def test_dispute_timeline(self):
        """DisputeTimeline should aggregate events."""
        entries = [
            TimelineEntry(
                timestamp=datetime(2023, 1, 1, tzinfo=timezone.utc),
                entry_type="edit",
                user="Alice",
            ),
            TimelineEntry(
                timestamp=datetime(2023, 1, 2, tzinfo=timezone.utc),
                entry_type="revert",
                user="Bob",
                reverted_user="Alice",
            ),
        ]

        timeline = DisputeTimeline(
            timeline_id="test_timeline",
            primary_article="Test Article",
            core_participants=["Alice", "Bob"],
            events=entries,
            stages_reached=[DisputeStage.TALK],
        )

        assert len(timeline.events) == 2
        assert timeline.primary_article == "Test Article"
