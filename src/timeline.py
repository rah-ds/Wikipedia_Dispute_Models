"""
Timeline reconstruction for dispute resolution lifecycle.

This module builds chronological timelines from raw data,
linking events across venues into coherent dispute narratives.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
import re

from src.models import (
    DisputeStage,
    DisputeEvent,
    DisputeTimeline,
    TimelineEntry,
)


def build_timeline_from_revisions(
    article_title: str,
    article_revisions: list[dict],
    talk_revisions: list[dict] | None = None,
) -> list[TimelineEntry]:
    """
    Build timeline entries from revision data.

    Args:
        article_title: Title of the article
        article_revisions: List of article revision dicts
        talk_revisions: Optional list of talk page revision dicts

    Returns:
        Sorted list of TimelineEntry objects
    """
    entries = []

    # Process article revisions
    for rev in article_revisions:
        comment = rev.get("comment", "") or ""
        user = rev.get("user", "")
        timestamp_str = rev.get("timestamp", "")

        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue

        # Detect if this is a revert
        is_revert = any(
            kw in comment.lower()
            for kw in ["revert", "rv ", "undo", "undid", "restore", "rollback"]
        )

        # Try to extract reverted user from comment
        reverted_user = ""
        if is_revert:
            # Common patterns: "Reverted edits by User", "Undid revision by User"
            match = re.search(r"(?:by|edits by|revision by)\s+([^\s\]]+)", comment)
            if match:
                reverted_user = match.group(1)

        entry = TimelineEntry(
            timestamp=timestamp,
            entry_type="revert" if is_revert else "edit",
            user=user,
            reverted_user=reverted_user,
            edit_summary=comment[:200],  # Truncate
        )
        entries.append(entry)

    # Process talk page revisions
    if talk_revisions:
        for rev in talk_revisions:
            comment = rev.get("comment", "") or ""
            user = rev.get("user", "")
            timestamp_str = rev.get("timestamp", "")

            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                continue

            # Extract section/thread from edit summary if present
            thread_title = ""
            section_match = re.search(r"/\*\s*([^*]+)\s*\*/", comment)
            if section_match:
                thread_title = section_match.group(1).strip()

            entry = TimelineEntry(
                timestamp=timestamp,
                entry_type="talk_post",
                user=user,
                edit_summary=comment[:200],
                thread_title=thread_title,
            )
            entries.append(entry)

    # Sort by timestamp
    entries.sort(key=lambda e: e.timestamp)

    return entries


def detect_dispute_emergence(
    entries: list[TimelineEntry],
    revert_threshold: int = 3,
    window_days: int = 7,
) -> Optional[datetime]:
    """
    Detect when a dispute likely emerged based on revert patterns.

    A dispute is considered to have emerged when we see multiple
    reverts between different users within a time window.

    Args:
        entries: Timeline entries (sorted by time)
        revert_threshold: Number of reverts to trigger detection
        window_days: Time window to consider

    Returns:
        Datetime of dispute emergence, or None if not detected
    """
    reverts = [e for e in entries if e.entry_type == "revert"]

    if len(reverts) < revert_threshold:
        return None

    # Sliding window detection
    for i, revert in enumerate(reverts):
        window_start = revert.timestamp
        window_end = window_start + timedelta(days=window_days)

        # Count reverts in window
        window_reverts = [r for r in reverts[i:] if r.timestamp <= window_end]

        if len(window_reverts) >= revert_threshold:
            # Check if multiple users involved (not just one editor cleaning up)
            users = set(r.user for r in window_reverts)
            if len(users) >= 2:
                return window_start

    return None


def identify_conflict_pairs(
    entries: list[TimelineEntry],
) -> list[tuple[str, str, int]]:
    """
    Identify pairs of users who frequently revert each other.

    Returns:
        List of (user1, user2, count) tuples, sorted by count descending
    """
    pair_counts = defaultdict(int)

    for entry in entries:
        if entry.entry_type == "revert" and entry.reverted_user:
            # Normalize pair order for consistent counting
            pair = tuple(sorted([entry.user, entry.reverted_user]))
            pair_counts[pair] += 1

    # Convert to list and sort
    pairs = [(pair[0], pair[1], count) for pair, count in pair_counts.items()]
    pairs.sort(key=lambda x: -x[2])

    return pairs


def compute_escalation_features(
    entries: list[TimelineEntry],
    dispute_events: list[DisputeEvent] | None = None,
) -> dict:
    """
    Compute features that may predict escalation.

    These features can be used in a model to predict:
    P(escalation | current_state, features)

    Args:
        entries: Timeline entries
        dispute_events: Optional list of formal dispute events

    Returns:
        Dict of feature name -> value
    """
    features = {}

    # Revert metrics
    reverts = [e for e in entries if e.entry_type == "revert"]
    total_edits = len([e for e in entries if e.entry_type in ("edit", "revert")])

    features["revert_count"] = len(reverts)
    features["revert_ratio"] = len(reverts) / total_edits if total_edits > 0 else 0

    # User metrics
    all_users = set(e.user for e in entries if e.user)
    reverting_users = set(e.user for e in reverts)

    features["unique_editors"] = len(all_users)
    features["unique_reverters"] = len(reverting_users)

    # Conflict pair metrics
    conflict_pairs = identify_conflict_pairs(entries)
    features["conflict_pairs"] = len(conflict_pairs)
    features["max_pair_conflicts"] = conflict_pairs[0][2] if conflict_pairs else 0

    # Talk page activity
    talk_posts = [e for e in entries if e.entry_type == "talk_post"]
    features["talk_posts"] = len(talk_posts)
    features["talk_participants"] = len(set(e.user for e in talk_posts if e.user))

    # Temporal metrics
    if entries:
        first_ts = entries[0].timestamp
        last_ts = entries[-1].timestamp
        features["duration_days"] = (last_ts - first_ts).days
    else:
        features["duration_days"] = 0

    # Dispute event metrics
    if dispute_events:
        features["prior_dispute_events"] = len(dispute_events)
        stages = [e.stage for e in dispute_events]
        features["highest_stage_reached"] = max(
            stages,
            key=lambda s: [
                DisputeStage.TALK,
                DisputeStage.THIRD_OPINION,
                DisputeStage.RFC,
                DisputeStage.DRN,
                DisputeStage.ANI,
                DisputeStage.ARBCOM,
            ].index(s)
            if s
            in [
                DisputeStage.TALK,
                DisputeStage.THIRD_OPINION,
                DisputeStage.RFC,
                DisputeStage.DRN,
                DisputeStage.ANI,
                DisputeStage.ARBCOM,
            ]
            else -1,
        ).value

    return features


def build_dispute_timeline(
    article_title: str,
    article_revisions: list[dict],
    talk_revisions: list[dict] | None = None,
    dispute_events: list[DisputeEvent] | None = None,
) -> DisputeTimeline:
    """
    Build a complete dispute timeline for an article.

    Args:
        article_title: Title of the article
        article_revisions: Article revision history
        talk_revisions: Talk page revision history
        dispute_events: Formal dispute events (3O, DRN, ANI, ArbCom)

    Returns:
        DisputeTimeline object with all events merged chronologically
    """
    # Build base timeline from revisions
    entries = build_timeline_from_revisions(
        article_title, article_revisions, talk_revisions
    )

    # Add dispute events to timeline
    if dispute_events:
        for event in dispute_events:
            if event.date_filed:
                entry = TimelineEntry(
                    timestamp=event.date_filed,
                    entry_type="dispute_event",
                    event_id=event.event_id,
                    stage=event.stage,
                    is_escalation=True,  # Formal filing is always escalation
                )
                entries.append(entry)

        # Re-sort after adding events
        entries.sort(key=lambda e: e.timestamp)

    # Identify core participants (editors with most activity)
    user_activity = defaultdict(int)
    for entry in entries:
        if entry.user:
            user_activity[entry.user] += 1

    core_participants = [
        user for user, count in sorted(user_activity.items(), key=lambda x: -x[1])[:10]
    ]

    # Determine stages reached
    stages_reached = []
    if any(e.entry_type == "talk_post" for e in entries):
        stages_reached.append(DisputeStage.TALK)
    if dispute_events:
        for event in dispute_events:
            if event.stage not in stages_reached:
                stages_reached.append(event.stage)

    # Compute features
    features = compute_escalation_features(entries, dispute_events)

    # Build timeline object
    timeline = DisputeTimeline(
        timeline_id=f"timeline_{article_title.replace(' ', '_')}",
        primary_article=article_title,
        core_participants=core_participants,
        events=entries,
        stages_reached=stages_reached,
        reached_arbcom=DisputeStage.ARBCOM in stages_reached,
        features=features,
    )

    # Compute duration
    if entries:
        timeline.total_duration_days = (
            entries[-1].timestamp - entries[0].timestamp
        ).days

    return timeline


def summarize_timeline(timeline: DisputeTimeline) -> dict:
    """
    Generate a summary of a dispute timeline for analysis.

    Returns:
        Dict with key metrics and narrative summary
    """
    summary = {
        "article": timeline.primary_article,
        "duration_days": timeline.total_duration_days,
        "total_events": len(timeline.events),
        "core_participants": timeline.core_participants[:5],
        "stages_reached": [s.value for s in timeline.stages_reached],
        "reached_arbcom": timeline.reached_arbcom,
        "features": timeline.features,
    }

    # Count by event type
    type_counts = defaultdict(int)
    for entry in timeline.events:
        type_counts[entry.entry_type] += 1
    summary["event_counts"] = dict(type_counts)

    # Narrative summary
    narrative_parts = []

    if timeline.features.get("revert_ratio", 0) > 0.1:
        narrative_parts.append(
            f"High conflict ({timeline.features['revert_ratio']:.0%} reverts)"
        )

    if timeline.features.get("conflict_pairs", 0) > 0:
        narrative_parts.append(
            f"{timeline.features['conflict_pairs']} conflict pairs identified"
        )

    if timeline.reached_arbcom:
        narrative_parts.append("Escalated to Arbitration Committee")
    elif DisputeStage.ANI in timeline.stages_reached:
        narrative_parts.append("Reached ANI (administrative intervention)")
    elif DisputeStage.DRN in timeline.stages_reached:
        narrative_parts.append("Went through DRN")

    summary["narrative"] = (
        "; ".join(narrative_parts) if narrative_parts else "Routine editing"
    )

    return summary
