"""Analysis utilities for Wikipedia dispute detection."""

from __future__ import annotations

from collections import Counter

# Keywords indicating reverts
REVERT_KEYWORDS = [
    "revert",
    "reverted",
    "rv ",
    "undo",
    "undid",
    "restore",
    "restored",
    "rollback",
]


def is_revert(comment: str) -> bool:
    """
    Check if an edit comment indicates a revert.

    Args:
        comment: Edit summary text

    Returns:
        True if comment suggests a revert
    """
    if not comment:
        return False
    comment_lower = comment.lower()
    return any(kw in comment_lower for kw in REVERT_KEYWORDS)


def detect_reverts(revisions: list[dict]) -> list[dict]:
    """
    Identify reverts in a list of revisions.

    Args:
        revisions: List of revision dictionaries with 'comment' field

    Returns:
        List of revisions flagged as reverts
    """
    reverts = []
    for rev in revisions:
        if is_revert(rev.get("comment", "")):
            reverts.append(rev)
    return reverts


def analyze_edit_war(
    revisions: list[dict],
    threshold: float = 0.1,
) -> dict:
    """
    Analyze revisions for edit war indicators.

    Args:
        revisions: List of revision dictionaries
        threshold: Revert ratio threshold for flagging (default: 0.1 = 10%)

    Returns:
        Dictionary with edit war analysis metrics
    """
    total = len(revisions)
    if total == 0:
        return {
            "revisions_analyzed": 0,
            "revert_count": 0,
            "revert_ratio": 0.0,
            "edit_war_detected": False,
        }

    # Flag reverts
    for rev in revisions:
        rev["is_revert"] = is_revert(rev.get("comment", ""))

    reverts = [r for r in revisions if r["is_revert"]]
    revert_count = len(reverts)
    revert_ratio = revert_count / total

    # User analysis
    all_users = Counter(r.get("user") for r in revisions)
    revert_users = Counter(r.get("user") for r in reverts)

    return {
        "revisions_analyzed": total,
        "revert_count": revert_count,
        "revert_ratio": round(revert_ratio, 4),
        "unique_editors": len(all_users),
        "unique_reverters": len(revert_users),
        "top_editors": dict(all_users.most_common(10)),
        "top_reverters": dict(revert_users.most_common(10)),
        "edit_war_detected": revert_ratio > threshold,
        "recent_reverts": reverts[:20],
    }


def extract_user_conflicts(revisions: list[dict]) -> list[tuple[str, str, int]]:
    """
    Find pairs of users who frequently revert each other.

    Args:
        revisions: List of revision dictionaries in chronological order

    Returns:
        List of (user1, user2, count) tuples sorted by conflict count
    """
    conflicts: Counter[tuple[str, str]] = Counter()

    for i, rev in enumerate(revisions):
        if not rev.get("is_revert") and not is_revert(rev.get("comment", "")):
            continue

        # Find who was reverted (previous editor)
        if i + 1 < len(revisions):
            reverted_user = revisions[i + 1].get("user")
            reverter = rev.get("user")
            if reverted_user and reverter and reverted_user != reverter:
                pair = tuple(sorted([reverted_user, reverter]))
                conflicts[pair] += 1

    return [(u1, u2, count) for (u1, u2), count in conflicts.most_common()]
