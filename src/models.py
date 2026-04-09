"""
Data models for Wikipedia Dispute Resolution Lifecycle mapping.

This module defines the entity-relationship model for tracking disputes
from talk page emergence through arbitration.

Key insight: The SAME EDITORS appear across venues. Editor co-occurrence
combined with temporal proximity is the strongest linking signal.

Lifecycle stages (from docs/wikipedia_dispute_resolution_lifecycle.md):

    Talk Page → 3O/RfC → DRN → ANI → ArbCom → Resolved
       │          │       │      │      │
       └──────────┴───────┴──────┴──────┘
              (can skip stages)

Content vs Conduct split:
    - Content disputes: Talk → 3O/RfC → DRN
    - Conduct disputes: Talk → ANI → ArbCom
    - Hybrid: Content dispute that generates edit warring → becomes conduct
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class DisputeStage(Enum):
    """Stages in the dispute resolution lifecycle."""

    TALK = "talk"  # Talk page discussion
    THIRD_OPINION = "3o"  # Third Opinion request (2 editors only)
    RFC = "rfc"  # Request for Comment (multiple editors)
    DRN = "drn"  # Dispute Resolution Noticeboard
    ANI = "ani"  # Administrators' Noticeboard/Incidents
    ARBCOM = "arbcom"  # Arbitration Committee
    RESOLVED = "resolved"  # Dispute concluded


class DisputeType(Enum):
    """Type of dispute - determines pathway."""

    CONTENT = "content"  # Disagreement about article text
    CONDUCT = "conduct"  # Editor behavior violation
    HYBRID = "hybrid"  # Started as content, escalated to conduct


class OutcomeType(Enum):
    """Possible outcomes at each stage."""

    CONSENSUS = "consensus"  # Agreement reached
    NO_CONSENSUS = "no_consensus"  # Stalemate, no resolution
    ESCALATED = "escalated"  # Moved to higher venue
    SANCTIONS = "sanctions"  # Admin/ArbCom imposed sanctions
    WITHDRAWN = "withdrawn"  # Filer withdrew
    CLOSED = "closed"  # Closed by moderator/admin
    PENDING = "pending"  # Still active


@dataclass
class Editor:
    """A Wikipedia editor involved in disputes."""

    username: str

    # Aggregated metrics (computed from revision data)
    total_edits: int = 0
    total_reverts: int = 0
    articles_edited: list[str] = field(default_factory=list)

    # Sanction history
    sanctions: list[dict] = field(default_factory=list)
    # e.g., [{'type': 'topic_ban', 'date': '2023-01-15', 'topic': 'climate'}]

    # Dispute involvement
    dispute_events: list[str] = field(default_factory=list)  # Event IDs

    def __hash__(self):
        return hash(self.username)

    def __eq__(self, other):
        if isinstance(other, Editor):
            return self.username == other.username
        return False


@dataclass
class Article:
    """A Wikipedia article that is the subject of disputes."""

    title: str
    url: str = ""

    # Edit war metrics (from existing analysis)
    revert_ratio: float = 0.0
    revert_count: int = 0
    unique_editors: int = 0
    edit_war_detected: bool = False

    # Protection status
    protection: dict = field(default_factory=dict)

    # Topic categorization
    topic_area: str = ""  # e.g., "geopolitics", "science", "politics"

    # Linked dispute events
    dispute_events: list[str] = field(default_factory=list)  # Event IDs

    # Related arbitration cases
    arbitration_cases: list[str] = field(default_factory=list)


@dataclass
class DisputeEvent:
    """
    A single event in the dispute resolution process.

    This is the core entity for lifecycle mapping. Each filing at a venue
    (3O request, DRN case, ANI report, ArbCom case) is a DisputeEvent.

    Events are linked by:
    1. Explicit wikilinks (strongest signal)
    2. Editor overlap + temporal proximity (heuristic)
    3. Article overlap (weaker signal)
    """

    # Unique identifier
    event_id: str  # Format: "{stage}_{article}_{date}" or page title

    # Core attributes
    stage: DisputeStage
    dispute_type: DisputeType

    # Temporal
    date_filed: Optional[datetime] = None
    date_closed: Optional[datetime] = None
    duration_days: Optional[int] = None

    # Outcome
    outcome: OutcomeType = OutcomeType.PENDING
    outcome_details: str = ""  # Free text description

    # Participants
    filer: str = ""  # Editor who filed
    participants: list[str] = field(default_factory=list)  # All involved editors

    # Related articles
    articles: list[str] = field(default_factory=list)
    primary_article: str = ""  # Main article in dispute

    # Linkage to other events
    escalated_from: Optional[str] = None  # Event ID of prior stage
    escalated_to: Optional[str] = None  # Event ID of next stage
    related_events: list[str] = field(default_factory=list)

    # Source data
    source_url: str = ""
    source_page: str = ""  # Wikipedia page title
    raw_content: str = ""  # Preserved for re-parsing

    # Linking confidence
    link_confidence: float = 1.0  # 1.0 = explicit link, <1.0 = heuristic
    link_method: str = ""  # How linkage was determined


@dataclass
class DisputeTimeline:
    """
    Complete timeline of a dispute from emergence to resolution.

    Aggregates multiple DisputeEvents plus revision/talk activity
    into a single chronological view.
    """

    # Identifier
    timeline_id: str
    primary_article: str

    # Core editors involved throughout
    core_participants: list[str] = field(default_factory=list)

    # Ordered sequence of events
    events: list[TimelineEntry] = field(default_factory=list)

    # Summary metrics
    total_duration_days: Optional[int] = None
    stages_reached: list[DisputeStage] = field(default_factory=list)
    final_outcome: OutcomeType = OutcomeType.PENDING

    # Did it reach arbitration?
    reached_arbcom: bool = False

    # Features for modeling
    features: dict = field(default_factory=dict)


@dataclass
class TimelineEntry:
    """
    A single entry in a dispute timeline.

    Can be:
    - A revision (edit or revert)
    - A talk page post
    - A formal dispute event (3O, DRN, ANI, etc.)
    """

    timestamp: datetime
    entry_type: str  # 'edit', 'revert', 'talk_post', 'dispute_event'

    # For edits/reverts
    user: str = ""
    reverted_user: str = ""  # If this is a revert
    edit_summary: str = ""

    # For dispute events
    event_id: str = ""
    stage: Optional[DisputeStage] = None

    # For talk posts
    thread_title: str = ""

    # Computed
    is_escalation: bool = False  # Does this entry represent escalation?


# --- Linking Functions ---


def compute_editor_overlap(event1: DisputeEvent, event2: DisputeEvent) -> float:
    """
    Compute Jaccard similarity of participants between two events.

    Returns:
        Float between 0 and 1. Higher = more overlap.
    """
    set1 = set(event1.participants)
    set2 = set(event2.participants)

    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def compute_temporal_proximity(event1: DisputeEvent, event2: DisputeEvent) -> float:
    """
    Compute temporal proximity score between two events.

    Uses exponential decay: events within 7 days score ~1.0,
    events 30+ days apart score near 0.

    Returns:
        Float between 0 and 1. Higher = closer in time.
    """
    import math

    if not event1.date_filed or not event2.date_filed:
        return 0.0

    days_apart = abs((event1.date_filed - event2.date_filed).days)

    # Exponential decay with half-life of 14 days
    half_life = 14
    return math.exp(-0.693 * days_apart / half_life)


def compute_article_overlap(event1: DisputeEvent, event2: DisputeEvent) -> float:
    """
    Compute Jaccard similarity of articles between two events.
    """
    set1 = set(event1.articles)
    set2 = set(event2.articles)

    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def compute_link_score(
    event1: DisputeEvent, event2: DisputeEvent, weights: dict | None = None
) -> tuple[float, str]:
    """
    Compute overall linkage score between two events.

    Args:
        event1: First event
        event2: Second event
        weights: Optional weight dict for components

    Returns:
        Tuple of (score, method_description)
    """
    if weights is None:
        weights = {
            "editor_overlap": 0.5,
            "temporal_proximity": 0.3,
            "article_overlap": 0.2,
        }

    editor_score = compute_editor_overlap(event1, event2)
    temporal_score = compute_temporal_proximity(event1, event2)
    article_score = compute_article_overlap(event1, event2)

    total = (
        weights["editor_overlap"] * editor_score
        + weights["temporal_proximity"] * temporal_score
        + weights["article_overlap"] * article_score
    )

    method = f"editor={editor_score:.2f}, time={temporal_score:.2f}, article={article_score:.2f}"

    return total, method


def should_link_events(
    event1: DisputeEvent, event2: DisputeEvent, threshold: float = 0.5
) -> bool:
    """
    Determine if two events should be linked as part of the same dispute.

    Args:
        event1: First event
        event2: Second event
        threshold: Minimum link score to consider linked

    Returns:
        True if events appear to be part of the same dispute
    """
    # Check for explicit link first
    if event1.event_id in event2.related_events:
        return True
    if event2.event_id in event1.related_events:
        return True
    if event1.escalated_to == event2.event_id:
        return True
    if event2.escalated_from == event1.event_id:
        return True

    # Fall back to heuristic
    score, _ = compute_link_score(event1, event2)
    return score >= threshold


# --- State Transition Analysis ---

# Valid transitions in the lifecycle (from the mermaid diagram)
VALID_TRANSITIONS = {
    DisputeStage.TALK: [
        DisputeStage.THIRD_OPINION,
        DisputeStage.RFC,
        DisputeStage.DRN,
        DisputeStage.ANI,  # If conduct violation
        DisputeStage.RESOLVED,
    ],
    DisputeStage.THIRD_OPINION: [
        DisputeStage.DRN,
        DisputeStage.RFC,
        DisputeStage.ANI,
        DisputeStage.RESOLVED,
    ],
    DisputeStage.RFC: [
        DisputeStage.DRN,
        DisputeStage.ANI,
        DisputeStage.ARBCOM,  # For policy interpretation
        DisputeStage.RESOLVED,
    ],
    DisputeStage.DRN: [
        DisputeStage.ANI,
        DisputeStage.RFC,  # Referral back
        DisputeStage.ARBCOM,
        DisputeStage.RESOLVED,
    ],
    DisputeStage.ANI: [
        DisputeStage.ARBCOM,
        DisputeStage.RESOLVED,
    ],
    DisputeStage.ARBCOM: [
        DisputeStage.RESOLVED,  # Binding decision
    ],
    DisputeStage.RESOLVED: [],  # Terminal state
}


def is_valid_transition(from_stage: DisputeStage, to_stage: DisputeStage) -> bool:
    """Check if a stage transition is valid per the lifecycle model."""
    return to_stage in VALID_TRANSITIONS.get(from_stage, [])


def is_escalation(from_stage: DisputeStage, to_stage: DisputeStage) -> bool:
    """
    Determine if transition represents escalation (higher authority).

    Escalation order: TALK < 3O/RFC < DRN < ANI < ARBCOM
    """
    stage_order = {
        DisputeStage.TALK: 0,
        DisputeStage.THIRD_OPINION: 1,
        DisputeStage.RFC: 1,
        DisputeStage.DRN: 2,
        DisputeStage.ANI: 3,
        DisputeStage.ARBCOM: 4,
        DisputeStage.RESOLVED: 5,
    }

    return stage_order.get(to_stage, 0) > stage_order.get(from_stage, 0)


# ============================================================================
# Enhanced Data Models for API Expansion
# ============================================================================


@dataclass
class EditorProfile:
    """
    Enhanced editor profile with API-sourced enrichment data.

    Combines case-specific activity with global account metadata.
    """

    # === Core identification ===
    username: str

    # === Case-specific metrics (computed from revision data) ===
    edits_by_subpage: dict[str, int] = field(default_factory=dict)
    total_edits: int = 0
    total_reverts: int = 0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    pages_touched: list[str] = field(default_factory=list)
    sections_edited: list[str] = field(default_factory=list)

    # === Account metadata (from API:Users) ===
    user_id: Optional[int] = None
    user_groups: list[str] = field(default_factory=list)
    is_admin: bool = False
    is_bot: bool = False
    registration_date: Optional[str] = None
    global_edit_count: Optional[int] = None
    gender: Optional[str] = None

    # === Sanction history (from API:Blocks + logevents) ===
    block_history: list[dict] = field(default_factory=list)
    total_blocks: int = 0
    was_blocked_during_case: bool = False
    current_block: Optional[dict] = None

    # === Behavioral signals (from ORES) ===
    avg_damaging_score: Optional[float] = None
    avg_goodfaith_score: Optional[float] = None
    pct_edits_reverted: Optional[float] = None

    # === External enrichment (from XTools) ===
    xtools_stats: Optional[dict] = None

    # === Derived features ===
    account_age_days: Optional[int] = None
    edits_per_day: Optional[float] = None
    is_experienced: bool = False  # 500+ edits, 30+ days

    def __hash__(self):
        return hash(self.username)

    def __eq__(self, other):
        if isinstance(other, EditorProfile):
            return self.username == other.username
        return False

    def compute_derived_features(self) -> None:
        """Compute derived features from base data."""
        # Account age
        if self.registration_date:
            from datetime import datetime

            try:
                reg_date = datetime.fromisoformat(
                    self.registration_date.replace("Z", "+00:00")
                )
                self.account_age_days = (datetime.now(reg_date.tzinfo) - reg_date).days
            except (ValueError, TypeError):
                pass

        # Edits per day
        if (
            self.account_age_days
            and self.account_age_days > 0
            and self.global_edit_count
        ):
            self.edits_per_day = self.global_edit_count / self.account_age_days

        # Experienced editor
        self.is_experienced = (self.global_edit_count or 0) >= 500 and (
            self.account_age_days or 0
        ) >= 30


@dataclass
class PageMetadata:
    """
    Rich metadata for a Wikipedia page.

    Combines assessment data, protection status, and traffic.
    """

    title: str

    # === Quality assessment (from PageAssessments API) ===
    quality_class: Optional[str] = None  # Stub, Start, C, B, GA, FA
    importance: Optional[str] = None  # Low, Mid, High, Top
    assessments: dict[str, dict] = field(default_factory=dict)  # by WikiProject

    # === Protection status (from API:Info + protection log) ===
    protection_level: Optional[str] = None  # None, autoconfirmed, sysop
    protection_expiry: Optional[str] = None
    protection_history: list[dict] = field(default_factory=list)
    protection_count: int = 0

    # === Traffic (from Pageviews API) ===
    avg_daily_views: Optional[float] = None
    total_views_30d: Optional[int] = None
    view_trend: Optional[str] = None  # increasing, stable, decreasing
    had_traffic_spike: bool = False

    # === Edit statistics ===
    total_revisions: Optional[int] = None
    unique_editors: Optional[int] = None
    revert_rate: Optional[float] = None

    # === Topic categorization ===
    categories: list[str] = field(default_factory=list)
    wikiproject_count: int = 0

    def is_high_profile(self) -> bool:
        """Determine if page is high-profile based on metrics."""
        return (
            self.importance in ("Top", "High")
            or self.quality_class in ("FA", "GA")
            or (self.avg_daily_views is not None and self.avg_daily_views > 1000)
            or self.protection_level == "sysop"
        )

    def is_contentious(self) -> bool:
        """Determine if page shows signs of contentiousness."""
        return (
            self.protection_count > 2
            or self.protection_level is not None
            or (self.revert_rate is not None and self.revert_rate > 0.1)
        )


@dataclass
class Revision:
    """
    Enhanced revision with ORES scores and edit tags.

    Represents a single edit with quality metrics.
    """

    revid: int
    parentid: Optional[int] = None
    timestamp: Optional[str] = None
    user: Optional[str] = None
    comment: str = ""
    size: Optional[int] = None

    # === Edit tags (from rvprop=tags) ===
    tags: list[str] = field(default_factory=list)

    # === ORES scores (from Lift Wing API) ===
    ores_damaging: Optional[float] = None
    ores_goodfaith: Optional[float] = None

    # === Derived flags ===
    is_revert: bool = False
    is_minor: bool = False
    is_bot: bool = False

    def compute_flags(self) -> None:
        """Set derived flags from tags and data."""
        revert_tags = {"mw-revert", "mw-undo", "mw-rollback", "mw-manual-revert"}
        self.is_revert = bool(set(self.tags) & revert_tags)
        self.is_bot = "bot" in self.tags

    @property
    def was_reverted(self) -> bool:
        """Check if this edit was later reverted."""
        return "mw-reverted" in self.tags

    @property
    def is_likely_damaging(self) -> bool:
        """Check if ORES predicts this edit as likely damaging."""
        return self.ores_damaging is not None and self.ores_damaging > 0.5

    @property
    def is_likely_bad_faith(self) -> bool:
        """Check if ORES predicts this edit as likely bad faith."""
        return self.ores_goodfaith is not None and self.ores_goodfaith < 0.5
