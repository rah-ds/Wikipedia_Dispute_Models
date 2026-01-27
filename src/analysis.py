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


def detect_3rr_violations(
    revisions: list[dict],
    window_hours: int = 24,
    threshold: int = 3,
) -> list[dict]:
    """
    Detect potential 3RR (Three-Revert Rule) violations.

    A violation occurs when a user makes more than `threshold` reverts
    on the same article within `window_hours`. Reports only the first
    violation found per user (the earliest window that exceeds threshold).

    Args:
        revisions: List of revision dicts with 'user', 'timestamp', 'is_revert' fields
        window_hours: Sliding window size in hours (default: 24)
        threshold: Number of reverts that triggers a violation (default: 3)

    Returns:
        List of violation dicts with 'user', 'reverts_in_window', 'window_start'.
        Each user appears at most once in the list.
    """
    from datetime import datetime, timedelta
    import logging

    logger = logging.getLogger(__name__)
    violations = []

    # Filter to reverts only and sort by timestamp
    revert_revisions = [
        r for r in revisions
        if r.get("is_revert") or is_revert(r.get("comment", ""))
    ]

    # Group by user
    user_reverts: dict[str, list[datetime]] = {}
    for rev in revert_revisions:
        user = rev.get("user")
        ts_str = rev.get("timestamp")
        if not user or not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            logger.warning(
                f"Could not parse timestamp '{ts_str}' for user '{user}': {e}"
            )
            continue
        user_reverts.setdefault(user, []).append(ts)

    # Check each user for violations - find the worst violation per user
    for user, timestamps in user_reverts.items():
        timestamps.sort()
        worst_violation = None
        max_reverts = threshold  # Only report if exceeds threshold
        
        for i, ts in enumerate(timestamps):
            window_end = ts + timedelta(hours=window_hours)
            reverts_in_window = sum(1 for t in timestamps if ts <= t < window_end)

            if reverts_in_window > max_reverts:
                max_reverts = reverts_in_window
                worst_violation = {
                    "user": user,
                    "reverts_in_window": reverts_in_window,
                    "window_start": ts.isoformat(),
                }
        
        # Add the worst violation for this user, if any
        if worst_violation:
            violations.append(worst_violation)

    return violations


def detect_revert_chains(
    revisions: list[dict],
    min_chain_length: int = 3,
) -> list[dict]:
    """
    Detect chains of consecutive reverts (rapid-fire edit warring).

    Args:
        revisions: List of revision dicts in chronological order
        min_chain_length: Minimum consecutive reverts to report

    Returns:
        List of chain dicts with 'start_idx', 'length', 'users', 'timestamps'
    """
    chains = []
    chain_start = None
    chain_users = []
    chain_timestamps = []

    for i, rev in enumerate(revisions):
        is_rev = rev.get("is_revert") or is_revert(rev.get("comment", ""))

        if is_rev:
            if chain_start is None:
                chain_start = i
            chain_users.append(rev.get("user"))
            chain_timestamps.append(rev.get("timestamp"))
        else:
            # Chain broken - check if long enough to report
            if chain_start is not None and len(chain_users) >= min_chain_length:
                chains.append({
                    "start_idx": chain_start,
                    "length": len(chain_users),
                    "users": chain_users,
                    "timestamps": chain_timestamps,
                })
            chain_start = None
            chain_users = []
            chain_timestamps = []

    # Check final chain
    if chain_start is not None and len(chain_users) >= min_chain_length:
        chains.append({
            "start_idx": chain_start,
            "length": len(chain_users),
            "users": chain_users,
            "timestamps": chain_timestamps,
        })

    return chains
