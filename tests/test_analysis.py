"""Tests for src/analysis.py."""

from src.analysis import (
    analyze_edit_war,
    detect_reverts,
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
        revisions = [
            {"user": "Alice", "comment": "Added content", "is_revert": False},
            {"user": "Bob", "comment": "Reverted", "is_revert": True},
            {"user": "Alice", "comment": "Content again", "is_revert": False},
            {"user": "Bob", "comment": "Reverted again", "is_revert": True},
        ]
        conflicts = extract_user_conflicts(revisions)

        # Bob reverted Alice twice
        assert len(conflicts) >= 1
        alice_bob = [c for c in conflicts if "Alice" in c and "Bob" in c]
        assert len(alice_bob) == 1

    def test_empty_revisions(self):
        assert extract_user_conflicts([]) == []
