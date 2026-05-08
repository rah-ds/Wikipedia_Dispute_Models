"""
Arbitration case data model and extraction utilities.

Maps ALL data available from a Wikipedia arbitration case file, including:
- Case metadata and structure (subpages, timing)
- Editors / participants across every role
- Revision history per subpage and talk page
- Evidence diffs and workshop proposals
- Proposed decisions, remedies, findings of fact
- Cross-references to disputed articles and their talk pages
- Editor co-occurrence and conflict networks

Data sources (per case JSON produced by fetch_dispute_lifecycle.py):
    case_pages          – Main, /Evidence, /Workshop, /Proposed decision
    case_talk_pages     – Talk counterparts for each case page
    linked_articles     – Wikipedia articles named in the case
    article_talk_pages  – Talk pages for disputed articles
    summary             – Aggregate counts from the fetcher

The classes here are intentionally *read-only summaries* over the raw JSON.
They do not duplicate the data; they index and cross-reference it so that
notebooks and downstream analysis can ask questions without re-parsing.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.outcome import DecisionOutcome, parse_decision

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Recognised ArbCom subpage suffixes (order = procedural order)
SUBPAGE_ORDER = [
    "(main)",
    "/Evidence",
    "/Workshop",
    "/Proposed decision",
    "/Final decision",
    "/Remedies",
    "/Clarification requests",
]

#: Regex for extracting User: / User talk: links from wikitext
_USER_RE = re.compile(r"\[\[User(?:\s+talk)?:([^\]|]+)", re.IGNORECASE)

#: Regex for edit-summary section anchors like /* Section Title */
_SECTION_RE = re.compile(r"/\*\s*(.+?)\s*\*/")


# ---------------------------------------------------------------------------
# Lightweight value objects
# ---------------------------------------------------------------------------


@dataclass
class Revision:
    """A single page revision (edit)."""

    revid: int
    parentid: int | None
    timestamp: str  # ISO-8601
    user: str
    comment: str
    size: int | None

    # Computed fields
    is_revert: bool = False
    section: str = ""  # extracted from /* … */ in comment

    def __post_init__(self):
        comment_lower = (self.comment or "").lower()
        self.is_revert = any(
            kw in comment_lower for kw in ("revert", "rv ", "undo", "undid", "rollback")
        )
        match = _SECTION_RE.search(self.comment or "")
        if match:
            self.section = match.group(1).strip()

    @property
    def ts(self) -> datetime:
        """Parse timestamp to datetime."""
        return datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))

    @classmethod
    def from_dict(cls, d: dict) -> "Revision":
        return cls(
            revid=d.get("revid", 0),
            parentid=d.get("parentid"),
            timestamp=d.get("timestamp", ""),
            user=d.get("user", ""),
            comment=d.get("comment", ""),
            size=d.get("size"),
        )


@dataclass
class PageSummary:
    """Summary of a single wiki page within a case."""

    title: str
    url: str
    subpage: str  # e.g. "(main)", "/Evidence"
    exists: bool
    revision_count: int
    revisions: list[Revision] = field(default_factory=list, repr=False)

    # Derived
    editors: list[str] = field(default_factory=list)
    first_edit: str | None = None
    last_edit: str | None = None

    def __post_init__(self):
        if self.revisions:
            users = [r.user for r in self.revisions if r.user]
            self.editors = list(dict.fromkeys(users))  # unique, order-preserving
            timestamps = sorted(r.timestamp for r in self.revisions if r.timestamp)
            if timestamps:
                self.first_edit = timestamps[0]
                self.last_edit = timestamps[-1]

    @classmethod
    def from_dict(cls, d: dict) -> "PageSummary":
        revisions = [Revision.from_dict(r) for r in d.get("revisions", [])]
        return cls(
            title=d.get("title", ""),
            url=d.get("url", ""),
            subpage=d.get("subpage", ""),
            exists=d.get("exists", True),
            revision_count=len(revisions),
            revisions=revisions,
        )


@dataclass
class EditorProfile:
    """
    Aggregated view of a single editor across an arbitration case.

    Tracks every subpage they touched, how many edits, reverts,
    and which roles they played (filer, witness, arbitrator, etc.).
    """

    username: str

    # Per-subpage edit counts  {subpage_label: count}
    edits_by_subpage: dict[str, int] = field(default_factory=dict)

    total_edits: int = 0
    total_reverts: int = 0

    # Timestamps of first / last activity anywhere in the case
    first_seen: str | None = None
    last_seen: str | None = None

    # Which case pages this editor touched
    pages_touched: list[str] = field(default_factory=list)

    # Sections they edited (from /* … */ comments)
    sections_edited: list[str] = field(default_factory=list)

    @property
    def revert_ratio(self) -> float:
        return self.total_reverts / self.total_edits if self.total_edits else 0.0

    @property
    def active_days(self) -> int:
        """Calendar days between first and last activity."""
        if not self.first_seen or not self.last_seen:
            return 0
        t0 = datetime.fromisoformat(self.first_seen.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(self.last_seen.replace("Z", "+00:00"))
        return max((t1 - t0).days, 0)


@dataclass
class ConflictEdge:
    """A directed revert relationship between two editors."""

    reverter: str
    reverted: str
    count: int = 0
    pages: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Main case-level summary
# ---------------------------------------------------------------------------


@dataclass
class ArbitrationCaseSummary:
    """
    Comprehensive read-only summary of everything available from one
    arbitration case JSON file.

    Attributes expose every dimension of data that downstream analysis
    or modelling might need:
      - case identity and timing
      - subpage inventory (main, evidence, workshop, proposed decision)
      - talk-page inventory
      - all participant/editor profiles
      - disputed articles and their revision data
      - editor co-occurrence / conflict network
      - revision-level statistics and distributions
    """

    # --- Identity ---
    case_name: str
    case_prefix: str
    fetched_at: str

    # --- Subpage inventories ---
    case_pages: list[PageSummary] = field(default_factory=list)
    case_talk_pages: list[PageSummary] = field(default_factory=list)

    # --- Disputed articles ---
    linked_article_titles: list[str] = field(default_factory=list)
    linked_articles: list[PageSummary] = field(default_factory=list)
    article_talk_pages: list[PageSummary] = field(default_factory=list)

    # --- Editor profiles (built from all revision streams) ---
    editor_profiles: dict[str, EditorProfile] = field(default_factory=dict)

    # --- Conflict / co-occurrence network ---
    conflict_edges: list[ConflictEdge] = field(default_factory=list)

    # --- Aggregate metrics ---
    total_revisions: int = 0
    total_editors: int = 0
    total_case_pages: int = 0
    total_talk_pages: int = 0
    total_linked_articles: int = 0

    # Timing
    earliest_activity: str | None = None
    latest_activity: str | None = None
    case_duration_days: int = 0

    # Raw summary dict from fetcher (passthrough)
    raw_summary: dict = field(default_factory=dict)

    # Parsed decision outcome (if wikitext was available)
    decision_outcome: DecisionOutcome | None = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_json_path(cls, path: str | Path) -> "ArbitrationCaseSummary":
        """Load a case JSON file and build the full summary."""
        path = Path(path)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "ArbitrationCaseSummary":
        """Build summary from an already-loaded dict (any format)."""
        # Detect which format: lifecycle vs enriched (pages-as-dict) vs legacy
        if "lifecycle_stages" in data:
            return cls._from_lifecycle_dict(data)
        if isinstance(data.get("pages"), dict):
            return cls._from_enriched_dict(data)
        return cls._from_legacy_dict(data)

    # ---- enriched format (fetch_arb_dfs.py output, pages as dict) ----

    @classmethod
    def _from_enriched_dict(cls, data: dict) -> "ArbitrationCaseSummary":
        """Parse the enriched/DFS format where ``pages`` is a dict keyed by
        subpage label (e.g. ``"main"``, ``"/Evidence"``)."""
        pages_dict = data.get("pages", {})
        case_pages: list[PageSummary] = []
        raw_page_dicts: list[dict] = []
        for subpage_label, page_data in pages_dict.items():
            if not isinstance(page_data, dict):
                continue
            # Normalise to PageSummary.from_dict format
            normalised = {
                "title": page_data.get("title", ""),
                "url": page_data.get("url", ""),
                "subpage": f"({subpage_label})"
                if subpage_label == "main"
                else f"/{subpage_label}"
                if not subpage_label.startswith("/")
                else subpage_label,
                "exists": True,
                "revisions": page_data.get("revisions", []),
                "content": page_data.get("content", ""),
            }
            case_pages.append(PageSummary.from_dict(normalised))
            raw_page_dicts.append(normalised)

        talk_dict = data.get("talk_pages", {})
        case_talk_pages: list[PageSummary] = []
        for subpage_label, page_data in (
            talk_dict if isinstance(talk_dict, dict) else {}
        ).items():
            if not isinstance(page_data, dict):
                continue
            normalised = {
                "title": page_data.get("title", ""),
                "url": page_data.get("url", ""),
                "subpage": subpage_label,
                "exists": True,
                "revisions": page_data.get("revisions", []),
            }
            case_talk_pages.append(PageSummary.from_dict(normalised))

        # Article revision data
        linked_articles: list[PageSummary] = []
        article_revs = data.get("article_revisions", {})
        article_titles = data.get("all_articles", [])
        if isinstance(article_revs, dict):
            for art_title, revisions in article_revs.items():
                normalised = {
                    "title": art_title,
                    "url": "",
                    "subpage": "",
                    "exists": True,
                    "revisions": revisions if isinstance(revisions, list) else [],
                }
                linked_articles.append(PageSummary.from_dict(normalised))

        summary = cls(
            case_name=data.get("case_name", ""),
            case_prefix=data.get("case_prefix", ""),
            fetched_at=data.get("fetched_at", ""),
            case_pages=case_pages,
            case_talk_pages=case_talk_pages,
            linked_article_titles=article_titles,
            linked_articles=linked_articles,
            total_case_pages=len(case_pages),
            total_talk_pages=len(case_talk_pages),
            total_linked_articles=len(article_titles),
            raw_summary=data.get("summary", {}),
        )
        summary._compute_derived()
        summary._parse_decision_from_pages(raw_page_dicts)
        return summary

    # ---- legacy format (fetch_dispute_lifecycle.py old output) ----

    @classmethod
    def _from_legacy_dict(cls, data: dict) -> "ArbitrationCaseSummary":
        case_pages = [PageSummary.from_dict(p) for p in data.get("case_pages", [])]
        case_talk_pages = [
            PageSummary.from_dict(p) for p in data.get("case_talk_pages", [])
        ]
        linked_articles = [
            PageSummary.from_dict(a) for a in data.get("linked_articles", [])
        ]
        article_talk_pages = [
            PageSummary.from_dict(a) for a in data.get("article_talk_pages", [])
        ]

        summary = cls(
            case_name=data.get("case_name", ""),
            case_prefix=data.get("case_prefix", ""),
            fetched_at=data.get("fetched_at", ""),
            case_pages=case_pages,
            case_talk_pages=case_talk_pages,
            linked_article_titles=[a.title for a in linked_articles],
            linked_articles=linked_articles,
            article_talk_pages=article_talk_pages,
            total_case_pages=len(case_pages),
            total_talk_pages=len(case_talk_pages),
            total_linked_articles=data.get("summary", {}).get(
                "total_linked_articles", len(linked_articles)
            ),
            raw_summary=data.get("summary", {}),
        )
        summary._compute_derived()
        summary._parse_decision_from_pages(data.get("case_pages", []))
        return summary

    # ---- lifecycle format (fetch_dispute_lifecycle.py new output) ----

    @classmethod
    def _from_lifecycle_dict(cls, data: dict) -> "ArbitrationCaseSummary":
        stages = data.get("lifecycle_stages", {})

        arbcom = stages.get("stage_5_arbcom", {})
        case_pages = [PageSummary.from_dict(p) for p in arbcom.get("pages", [])]
        case_talk_pages = [
            PageSummary.from_dict(p) for p in arbcom.get("talk_pages", [])
        ]

        talk_stage = stages.get("stage_1_2_talk", {})
        article_talk_pages = [
            PageSummary.from_dict(p) for p in talk_stage.get("pages", [])
        ]

        summary = cls(
            case_name=data.get("case_name", ""),
            case_prefix=data.get("case_prefix", ""),
            fetched_at=data.get("fetched_at", ""),
            case_pages=case_pages,
            case_talk_pages=case_talk_pages,
            linked_article_titles=data.get("disputed_articles", []),
            article_talk_pages=article_talk_pages,
            total_case_pages=len(case_pages),
            total_talk_pages=len(case_talk_pages),
            total_linked_articles=len(data.get("disputed_articles", [])),
            raw_summary=data.get("summary", {}),
        )
        summary._compute_derived()
        summary._parse_decision_from_pages(arbcom.get("pages", []))
        return summary

    # ---- decision outcome extraction ----

    def _parse_decision_from_pages(self, raw_pages: list[dict]):
        """
        Look for wikitext content in /Proposed decision or /Final decision
        page dicts and parse structured outcomes.
        """
        # Priority: /Final decision > /Proposed decision > (main)
        for suffix in ("/Final decision", "/Proposed decision", ""):
            subpage_label = suffix or "(main)"
            for page_dict in raw_pages:
                page_sub = page_dict.get("subpage", "")
                if page_sub == subpage_label and page_dict.get("content"):
                    self.decision_outcome = parse_decision(page_dict["content"])
                    return

    # ---- shared post-construction ----

    def _compute_derived(self):
        """Populate editor profiles, conflict edges, and aggregate metrics."""
        all_revisions: list[tuple[str, Revision]] = []  # (page_label, rev)

        # Collect every revision across all page inventories
        for page in self.case_pages + self.case_talk_pages:
            label = page.subpage or page.title
            for rev in page.revisions:
                all_revisions.append((label, rev))

        for page in self.linked_articles + self.article_talk_pages:
            label = f"article:{page.title}"
            for rev in page.revisions:
                all_revisions.append((label, rev))

        self.total_revisions = len(all_revisions)

        # Build editor profiles
        profiles: dict[str, EditorProfile] = {}
        all_timestamps: list[str] = []

        for label, rev in all_revisions:
            user = rev.user
            if not user:
                continue

            if user not in profiles:
                profiles[user] = EditorProfile(username=user)
            p = profiles[user]

            p.total_edits += 1
            p.edits_by_subpage[label] = p.edits_by_subpage.get(label, 0) + 1
            if rev.is_revert:
                p.total_reverts += 1
            if label not in p.pages_touched:
                p.pages_touched.append(label)
            if rev.section and rev.section not in p.sections_edited:
                p.sections_edited.append(rev.section)

            ts = rev.timestamp
            if ts:
                all_timestamps.append(ts)
                if p.first_seen is None or ts < p.first_seen:
                    p.first_seen = ts
                if p.last_seen is None or ts > p.last_seen:
                    p.last_seen = ts

        self.editor_profiles = profiles
        self.total_editors = len(profiles)

        # Global timing
        if all_timestamps:
            all_timestamps.sort()
            self.earliest_activity = all_timestamps[0]
            self.latest_activity = all_timestamps[-1]
            t0 = datetime.fromisoformat(all_timestamps[0].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(all_timestamps[-1].replace("Z", "+00:00"))
            self.case_duration_days = max((t1 - t0).days, 0)

        # Conflict network (consecutive-revert heuristic across each page)
        self._build_conflict_edges()

    def _build_conflict_edges(self):
        """Detect revert-based conflict edges across all pages."""
        edge_counts: Counter[tuple[str, str]] = Counter()
        edge_pages: dict[tuple[str, str], set] = defaultdict(set)

        for page in self.case_pages + self.case_talk_pages:
            revs = sorted(page.revisions, key=lambda r: r.timestamp)
            for i, rev in enumerate(revs):
                if rev.is_revert and i + 1 < len(revs):
                    reverted_user = revs[i + 1].user
                    if reverted_user and rev.user and rev.user != reverted_user:
                        pair = (rev.user, reverted_user)
                        edge_counts[pair] += 1
                        edge_pages[pair].add(page.subpage or page.title)

        self.conflict_edges = [
            ConflictEdge(
                reverter=pair[0],
                reverted=pair[1],
                count=count,
                pages=list(edge_pages[pair]),
            )
            for pair, count in edge_counts.most_common()
        ]

    # ------------------------------------------------------------------
    # Query helpers (used by notebooks / analysis)
    # ------------------------------------------------------------------

    def top_editors(self, n: int = 20) -> list[EditorProfile]:
        """Return editors sorted by total edits (descending)."""
        return sorted(
            self.editor_profiles.values(), key=lambda e: e.total_edits, reverse=True
        )[:n]

    def editors_on_subpage(self, subpage: str) -> list[EditorProfile]:
        """Return editors who touched a specific subpage."""
        return [
            p for p in self.editor_profiles.values() if subpage in p.edits_by_subpage
        ]

    def editor_overlap(self, page_a: str, page_b: str) -> set[str]:
        """Editors who edited both page_a and page_b labels."""
        a = {p.username for p in self.editors_on_subpage(page_a)}
        b = {p.username for p in self.editors_on_subpage(page_b)}
        return a & b

    def subpage_edit_counts(self) -> dict[str, int]:
        """Total edits per subpage label."""
        counts: Counter[str] = Counter()
        for p in self.editor_profiles.values():
            for label, c in p.edits_by_subpage.items():
                counts[label] += c
        return dict(counts.most_common())

    def revision_timeline(self, subpage: str | None = None) -> list[Revision]:
        """
        All revisions in chronological order, optionally filtered to
        a single subpage label.
        """
        sources = self.case_pages + self.case_talk_pages
        if subpage:
            sources = [p for p in sources if (p.subpage or p.title) == subpage]
        all_revs = [r for page in sources for r in page.revisions]
        all_revs.sort(key=lambda r: r.timestamp)
        return all_revs

    def monthly_activity(self) -> dict[str, int]:
        """Revision counts bucketed by YYYY-MM."""
        buckets: Counter[str] = Counter()
        for rev in self.revision_timeline():
            month = rev.timestamp[:7]  # "YYYY-MM"
            buckets[month] += 1
        return dict(sorted(buckets.items()))

    def consensus_signals(self) -> dict:
        """
        Heuristic indicators of consensus (or lack thereof).

        Looks at:
        - Workshop vs Evidence edit ratio (high workshop = more proposals)
        - Revert ratio on proposed-decision page
        - Number of unique editors on /Proposed decision
        - Duration from first evidence to proposed decision
        """
        ws_edits = sum(
            1
            for p in self.case_pages
            if "Workshop" in (p.subpage or "")
            for _ in p.revisions
        )
        ev_edits = sum(
            1
            for p in self.case_pages
            if "Evidence" in (p.subpage or "")
            for _ in p.revisions
        )
        pd_pages = [
            p for p in self.case_pages if "Proposed decision" in (p.subpage or "")
        ]
        pd_reverts = sum(1 for p in pd_pages for r in p.revisions if r.is_revert)
        pd_total = sum(len(p.revisions) for p in pd_pages)
        pd_editors = set()
        for p in pd_pages:
            pd_editors.update(r.user for r in p.revisions if r.user)

        return {
            "workshop_edits": ws_edits,
            "evidence_edits": ev_edits,
            "workshop_to_evidence_ratio": (
                ws_edits / ev_edits if ev_edits else float("inf")
            ),
            "proposed_decision_edits": pd_total,
            "proposed_decision_reverts": pd_reverts,
            "proposed_decision_revert_ratio": (
                pd_reverts / pd_total if pd_total else 0.0
            ),
            "proposed_decision_unique_editors": len(pd_editors),
            "case_duration_days": self.case_duration_days,
        }

    def to_summary_dict(self) -> dict:
        """
        Flat dictionary suitable for a DataFrame row (one row per case).
        """
        cs = self.consensus_signals()
        top = self.top_editors(5)
        return {
            "case_name": self.case_name,
            "fetched_at": self.fetched_at,
            "total_revisions": self.total_revisions,
            "total_editors": self.total_editors,
            "total_case_pages": self.total_case_pages,
            "total_talk_pages": self.total_talk_pages,
            "total_linked_articles": self.total_linked_articles,
            "case_duration_days": self.case_duration_days,
            "earliest_activity": self.earliest_activity,
            "latest_activity": self.latest_activity,
            # Subpage breakdowns
            **{
                f"edits_{k.replace('/', '_').replace(' ', '_').strip('_')}": v
                for k, v in self.subpage_edit_counts().items()
            },
            # Consensus signals
            **{f"consensus_{k}": v for k, v in cs.items()},
            # Conflict
            "conflict_edge_count": len(self.conflict_edges),
            "max_conflict_reverts": (
                self.conflict_edges[0].count if self.conflict_edges else 0
            ),
            # Top editors
            "top_editor_1": top[0].username if len(top) > 0 else "",
            "top_editor_1_edits": top[0].total_edits if len(top) > 0 else 0,
            "top_editor_2": top[1].username if len(top) > 1 else "",
            "top_editor_2_edits": top[1].total_edits if len(top) > 1 else 0,
            # Decision outcome (from parsed wikitext, if available)
            **(
                self.decision_outcome.to_summary_dict() if self.decision_outcome else {}
            ),
        }


# ---------------------------------------------------------------------------
# Batch loader (scan a directory of case JSONs)
# ---------------------------------------------------------------------------


def load_all_cases(
    data_dir: str | Path = "data/raw/arbitration",
    glob_pattern: str = "*.json",
    exclude_prefixes: tuple[str, ...] = ("arbitration_cases_",),
) -> list[ArbitrationCaseSummary]:
    """
    Load every case JSON in a directory and return ArbitrationCaseSummary
    objects. Skips files that fail to parse (with a warning).

    Parameters
    ----------
    data_dir : directory containing case JSON files
    glob_pattern : filename glob (default matches all JSON)
    exclude_prefixes : skip files whose name starts with these prefixes
        (e.g. index / manifest files)
    """
    import logging

    logger = logging.getLogger(__name__)
    data_dir = Path(data_dir)
    summaries = []

    for path in sorted(data_dir.glob(glob_pattern)):
        if any(path.name.startswith(p) for p in exclude_prefixes):
            continue
        try:
            summaries.append(ArbitrationCaseSummary.from_json_path(path))
        except Exception as exc:
            logger.warning(f"Skipping {path.name}: {exc}")

    return summaries


def cases_to_dataframe(cases: list[ArbitrationCaseSummary]):
    """
    Convert a list of ArbitrationCaseSummary objects into a pandas
    DataFrame with one row per case.
    """
    import pandas as pd

    rows = [c.to_summary_dict() for c in cases]
    df = pd.DataFrame(rows)

    # Sort by case name
    if "case_name" in df.columns:
        df = df.sort_values("case_name").reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# Convenience fetcher used by scripts/pull.py
# ---------------------------------------------------------------------------


def fetch_full_arbitration_case(
    client,
    case_name: str,
    revision_limit: int = 100,
    max_articles: int = 20,
    enrich_participants: bool = True,
    enrich_articles: bool = True,
    include_ani: bool = True,
    include_drn: bool = True,
) -> dict:
    """Fetch a single arbitration case with full lifecycle enrichment.

    Thin wrapper around :func:`src.lifecycle.fetch_dispute_lifecycle` that
    maps the enrichment flags used by ``scripts/pull.py`` to the
    underlying lifecycle parameters.
    """
    from src.lifecycle import fetch_dispute_lifecycle

    result = fetch_dispute_lifecycle(
        client,
        case_name,
        max_talk_pages=max_articles,
        revision_limit=revision_limit,
        ani_limit=30 if include_ani else 0,
        drn_archive_limit=20 if include_drn else 0,
        delay=getattr(client, "default_delay", 0.5),
    )

    # If ANI/DRN are disabled, clear those stages so downstream doesn't
    # misinterpret empty-because-skipped as empty-because-none-found.
    if not include_ani:
        result["lifecycle_stages"]["stage_4_ani"]["reports"] = []
    if not include_drn:
        result["lifecycle_stages"]["stage_3_drn"]["mentions"] = []

    # Provide enrichment counts expected by pull.py timing / rate logic
    result.setdefault("summary", {})
    result["summary"]["participants_enriched"] = (
        len(result.get("participants", [])) if enrich_participants else 0
    )
    result["summary"]["articles_enriched"] = (
        len(result.get("disputed_articles", [])) if enrich_articles else 0
    )

    return result
