"""Tests for src/analysis.py."""

from src.analysis import (
    analyze_edit_war,
    detect_reverts,
    detect_3rr_violations,
    detect_revert_chains,
    extract_user_conflicts,
    is_revert,
)


class TestIsRevert:
    """Tests for is_revert function."""

    def test_revert_keyword_detected(self):
        assert is_revert("Reverted edits by User123") is True
        assert is_revert("Undid revision 12345") is True
        assert is_revert("rv vandalism") is True
        assert is_revert("Restored previous version") is True
        assert is_revert("Rollback edits") is True

    def test_normal_edit_not_flagged(self):
        assert is_revert("Added section on history") is False
        assert is_revert("Fixed typo") is False
        assert is_revert("Updated references") is False

    def test_empty_or_none_comment(self):
        assert is_revert("") is False
        assert is_revert(None) is False

    def test_case_insensitive(self):
        assert is_revert("REVERTED vandalism") is True
        assert is_revert("Reverted VANDALISM") is True


class TestDetectReverts:
    """Tests for detect_reverts function."""

    def test_finds_reverts_in_list(self):
        revisions = [
            {"comment": "Added info"},
            {"comment": "Reverted to previous"},
            {"comment": "Fixed typo"},
            {"comment": "Undid bad edit"},
        ]
        reverts = detect_reverts(revisions)
        assert len(reverts) == 2

    def test_empty_list(self):
        assert detect_reverts([]) == []

    def test_no_reverts(self):
        revisions = [
            {"comment": "Added section"},
            {"comment": "Updated references"},
        ]
        assert detect_reverts(revisions) == []


class TestAnalyzeEditWar:
    """Tests for analyze_edit_war function."""

    def test_basic_analysis(self):
        revisions = [
            {"user": "Alice", "comment": "Added content"},
            {"user": "Bob", "comment": "Reverted Alice"},
            {"user": "Alice", "comment": "Restored my edit"},
            {"user": "Bob", "comment": "Undid Alice again"},
            {"user": "Charlie", "comment": "Fixed formatting"},
        ]
        result = analyze_edit_war(revisions, threshold=0.5)

        assert result["revisions_analyzed"] == 5
        assert result["revert_count"] == 3
        assert result["revert_ratio"] == 0.6
        assert result["unique_editors"] == 3
        assert result["edit_war_detected"] is True

    def test_no_edit_war(self):
        revisions = [
            {"user": "Alice", "comment": "Added section"},
            {"user": "Bob", "comment": "Expanded content"},
            {"user": "Charlie", "comment": "Fixed typos"},
        ]
        result = analyze_edit_war(revisions, threshold=0.1)

        assert result["revert_count"] == 0
        assert result["edit_war_detected"] is False

    def test_empty_revisions(self):
        result = analyze_edit_war([], threshold=0.1)
        assert result["revisions_analyzed"] == 0
        assert result["edit_war_detected"] is False

    def test_threshold_boundary(self):
        # 1 revert out of 10 = 10% exactly
        revisions = [{"user": f"User{i}", "comment": "Normal edit"} for i in range(9)]
        revisions.append({"user": "Reverter", "comment": "Reverted vandalism"})

        # At threshold 0.1, exactly 10% should NOT trigger (need > threshold)
        result = analyze_edit_war(revisions, threshold=0.1)
        assert result["edit_war_detected"] is False

        # At threshold 0.09, 10% should trigger
        result = analyze_edit_war(revisions, threshold=0.09)
        assert result["edit_war_detected"] is True


class TestExtractUserConflicts:
    """Tests for extract_user_conflicts function."""

    def test_finds_conflict_pairs(self):
        # Revisions in reverse chronological order (newest first)
        revisions = [
            {"user": "Bob", "comment": "Reverted again", "is_revert": True},
            {"user": "Alice", "comment": "Content again", "is_revert": False},
            {"user": "Bob", "comment": "Reverted", "is_revert": True},
            {"user": "Alice", "comment": "Added content", "is_revert": False},
        ]
        conflicts = extract_user_conflicts(revisions)

        # Bob reverted Alice twice
        assert len(conflicts) >= 1
        # Check that Alice-Bob pair exists with count 2
        alice_bob = [c for c in conflicts if "Alice" in c[:2] and "Bob" in c[:2]]
        assert len(alice_bob) == 1
        assert alice_bob[0][2] == 2  # Count should be 2

    def test_empty_revisions(self):
        assert extract_user_conflicts([]) == []

    def test_no_reverts(self):
        revisions = [
            {"user": "Alice", "comment": "Added content", "is_revert": False},
            {"user": "Bob", "comment": "More content", "is_revert": False},
        ]
        conflicts = extract_user_conflicts(revisions)
        assert conflicts == []

    def test_self_revert_ignored(self):
        """User reverting themselves should not count as conflict."""
        revisions = [
            {"user": "Alice", "comment": "Reverted myself", "is_revert": True},
            {"user": "Alice", "comment": "Oops wrong edit", "is_revert": False},
        ]
        conflicts = extract_user_conflicts(revisions)
        assert conflicts == []

    def test_multiple_conflict_pairs(self):
        """Test that multiple distinct conflict pairs are detected."""
        revisions = [
            {"user": "Charlie", "comment": "Reverted", "is_revert": True},
            {"user": "Dave", "comment": "Edit", "is_revert": False},
            {"user": "Bob", "comment": "Reverted", "is_revert": True},
            {"user": "Alice", "comment": "Edit", "is_revert": False},
        ]
        conflicts = extract_user_conflicts(revisions)

        # Should have two pairs: Charlie-Dave and Alice-Bob
        assert len(conflicts) == 2
        users_in_conflicts = set()
        for u1, u2, _ in conflicts:
            users_in_conflicts.add(u1)
            users_in_conflicts.add(u2)
        assert users_in_conflicts == {"Alice", "Bob", "Charlie", "Dave"}

    def test_detects_revert_from_comment_if_no_flag(self):
        """Test that reverts are detected from comment even without is_revert flag."""
        revisions = [
            {"user": "Bob", "comment": "Reverted vandalism"},
            {"user": "Alice", "comment": "Bad edit"},
        ]
        conflicts = extract_user_conflicts(revisions)

        assert len(conflicts) == 1
        assert "Alice" in conflicts[0][:2]
        assert "Bob" in conflicts[0][:2]

    def test_sorted_by_count(self):
        """Conflicts should be returned sorted by count descending."""
        revisions = [
            {"user": "Bob", "comment": "Reverted", "is_revert": True},
            {"user": "Alice", "comment": "Edit", "is_revert": False},
            {"user": "Bob", "comment": "Reverted", "is_revert": True},
            {"user": "Alice", "comment": "Edit", "is_revert": False},
            {"user": "Bob", "comment": "Reverted", "is_revert": True},
            {"user": "Alice", "comment": "Edit", "is_revert": False},
            {"user": "Dave", "comment": "Reverted", "is_revert": True},
            {"user": "Charlie", "comment": "Edit", "is_revert": False},
        ]
        conflicts = extract_user_conflicts(revisions)

        # Alice-Bob should be first with 3, Charlie-Dave second with 1
        assert len(conflicts) == 2
        assert conflicts[0][2] >= conflicts[1][2]  # Sorted descending


class TestDetect3RRViolations:
    """Tests for detect_3rr_violations function."""

    def test_detects_violation(self):
        """User with 4 reverts in 24h should be flagged."""
        from datetime import datetime, timedelta

        base_time = datetime(2025, 1, 1, 12, 0, 0)
        revisions = [
            {
                "user": "WarEditor",
                "timestamp": (base_time + timedelta(hours=i)).isoformat() + "Z",
                "is_revert": True,
            }
            for i in range(4)
        ]
        violations = detect_3rr_violations(revisions)

        assert len(violations) == 1
        assert violations[0]["user"] == "WarEditor"
        assert violations[0]["reverts_in_window"] == 4

    def test_no_violation_under_threshold(self):
        """3 reverts in 24h should NOT be flagged (need > 3)."""
        from datetime import datetime, timedelta

        base_time = datetime(2025, 1, 1, 12, 0, 0)
        revisions = [
            {
                "user": "NormalUser",
                "timestamp": (base_time + timedelta(hours=i)).isoformat() + "Z",
                "is_revert": True,
            }
            for i in range(3)
        ]
        violations = detect_3rr_violations(revisions)

        assert len(violations) == 0

    def test_no_violation_outside_window(self):
        """4 reverts spread over >24h should NOT be flagged."""
        from datetime import datetime, timedelta

        base_time = datetime(2025, 1, 1, 12, 0, 0)
        revisions = [
            {
                "user": "SpreadUser",
                "timestamp": (base_time + timedelta(hours=i * 10)).isoformat() + "Z",
                "is_revert": True,
            }
            for i in range(4)
        ]
        violations = detect_3rr_violations(revisions)

        assert len(violations) == 0

    def test_empty_revisions(self):
        assert detect_3rr_violations([]) == []

    def test_reports_worst_violation_per_user(self):
        """Should report the worst (highest count) violation window per user."""
        from datetime import datetime, timedelta

        base_time = datetime(2025, 1, 1, 12, 0, 0)
        # User has 4 reverts in first window, then 6 reverts in a later window
        revisions = [
            # First window: 4 reverts in hours 0-3
            {
                "user": "PowerEditor",
                "timestamp": (base_time + timedelta(hours=0)).isoformat() + "Z",
                "is_revert": True,
            },
            {
                "user": "PowerEditor",
                "timestamp": (base_time + timedelta(hours=1)).isoformat() + "Z",
                "is_revert": True,
            },
            {
                "user": "PowerEditor",
                "timestamp": (base_time + timedelta(hours=2)).isoformat() + "Z",
                "is_revert": True,
            },
            {
                "user": "PowerEditor",
                "timestamp": (base_time + timedelta(hours=3)).isoformat() + "Z",
                "is_revert": True,
            },
            # Gap
            # Second window: 6 reverts in hours 30-35 (worse violation)
            {
                "user": "PowerEditor",
                "timestamp": (base_time + timedelta(hours=30)).isoformat() + "Z",
                "is_revert": True,
            },
            {
                "user": "PowerEditor",
                "timestamp": (base_time + timedelta(hours=31)).isoformat() + "Z",
                "is_revert": True,
            },
            {
                "user": "PowerEditor",
                "timestamp": (base_time + timedelta(hours=32)).isoformat() + "Z",
                "is_revert": True,
            },
            {
                "user": "PowerEditor",
                "timestamp": (base_time + timedelta(hours=33)).isoformat() + "Z",
                "is_revert": True,
            },
            {
                "user": "PowerEditor",
                "timestamp": (base_time + timedelta(hours=34)).isoformat() + "Z",
                "is_revert": True,
            },
            {
                "user": "PowerEditor",
                "timestamp": (base_time + timedelta(hours=35)).isoformat() + "Z",
                "is_revert": True,
            },
        ]
        violations = detect_3rr_violations(revisions)

        # Should report only ONE violation for PowerEditor, with the highest count (6)
        assert len(violations) == 1
        assert violations[0]["user"] == "PowerEditor"
        assert violations[0]["reverts_in_window"] == 6
        # Should be from the second window (check just the date/time portion)
        assert violations[0]["window_start"].startswith("2025-01-02T18:00:00")


class TestDetectRevertChains:
    """Tests for detect_revert_chains function."""

    def test_detects_chain(self):
        """3+ consecutive reverts should be detected."""
        revisions = [
            {"user": "Alice", "comment": "Normal edit", "is_revert": False},
            {
                "user": "Bob",
                "comment": "Reverted",
                "is_revert": True,
                "timestamp": "2025-01-01T01:00:00Z",
            },
            {
                "user": "Alice",
                "comment": "Reverted back",
                "is_revert": True,
                "timestamp": "2025-01-01T02:00:00Z",
            },
            {
                "user": "Bob",
                "comment": "Reverted again",
                "is_revert": True,
                "timestamp": "2025-01-01T03:00:00Z",
            },
            {"user": "Charlie", "comment": "Normal edit", "is_revert": False},
        ]
        chains = detect_revert_chains(revisions, min_chain_length=3)

        assert len(chains) == 1
        assert chains[0]["length"] == 3
        assert set(chains[0]["users"]) == {"Alice", "Bob"}

    def test_no_chain_below_threshold(self):
        """2 consecutive reverts should NOT be flagged with min_chain_length=3."""
        revisions = [
            {"user": "Bob", "comment": "Reverted", "is_revert": True},
            {"user": "Alice", "comment": "Reverted back", "is_revert": True},
            {"user": "Charlie", "comment": "Normal edit", "is_revert": False},
        ]
        chains = detect_revert_chains(revisions, min_chain_length=3)

        assert len(chains) == 0

    def test_empty_revisions(self):
        assert detect_revert_chains([]) == []

    def test_multiple_chains(self):
        """Multiple separate chains should be detected."""
        revisions = [
            {"user": "A", "comment": "Reverted", "is_revert": True, "timestamp": "T1"},
            {"user": "B", "comment": "Reverted", "is_revert": True, "timestamp": "T2"},
            {"user": "A", "comment": "Reverted", "is_revert": True, "timestamp": "T3"},
            {"user": "C", "comment": "Normal", "is_revert": False},  # breaks chain
            {"user": "D", "comment": "Reverted", "is_revert": True, "timestamp": "T4"},
            {"user": "E", "comment": "Reverted", "is_revert": True, "timestamp": "T5"},
            {"user": "D", "comment": "Reverted", "is_revert": True, "timestamp": "T6"},
        ]
        chains = detect_revert_chains(revisions, min_chain_length=3)

        assert len(chains) == 2
