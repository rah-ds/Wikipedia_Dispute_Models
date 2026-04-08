# API Expansion Design Document

This document outlines proposed additions to the Wikimedia API data collection, how each integrates with the existing architecture, and implementation priorities.

## Current Architecture Overview

```
src/
├── wiki.py          # WikiClient - low-level API wrapper
├── fetchers.py      # High-level fetch functions (cases, revisions, ANI, DRN)
├── lifecycle.py     # Dispute lifecycle tracing (Talk → DRN → ANI → ArbCom)
├── arbitration.py   # Case data models (ArbitrationCaseSummary, EditorProfile)
├── outcome.py       # Decision parsing (votes, findings, remedies)
├── analysis.py      # Edit war detection, revert analysis
├── timeline.py      # Chronological dispute timelines
└── models.py        # Core entity models (Editor, Dispute, etc.)
```

**Data flow:**
1. `wiki.py` provides raw API access
2. `fetchers.py` orchestrates multi-page fetches
3. `lifecycle.py` traces cross-venue dispute paths
4. `arbitration.py` structures case-level summaries
5. `analysis.py` / `timeline.py` compute derived features

---

## Proposed Additions

### Tier 1: High Value, Easy Integration

#### 1.1 Edit Tags (mw-revert, mw-undo, mw-rollback, mw-reverted)

**What it provides:**
- MediaWiki's own classification of reverts
- More reliable than comment-based detection
- `mw-reverted` tag marks edits that were later undone

**Integration point:** `wiki.py` → `get_revisions()`

**Changes needed:**
```python
# In wiki.py get_revisions(), add to rvprop:
"rvprop": "ids|timestamp|user|comment|size|tags"

# Return tags in revision dict:
{
    "revid": 123,
    "tags": ["mw-rollback", "mw-reverted"],
    ...
}
```

**Downstream impact:**
- `analysis.py`: Use tags instead of/alongside comment parsing for `is_revert()`
- `arbitration.py`: `Revision.is_revert` can use tags as ground truth
- More accurate conflict edge detection

---

#### 1.2 User Block History

**What it provides:**
- When editors were blocked, duration, reason, blocking admin
- Direct outcome data for dispute participants
- Can identify editors with history of sanctions

**Integration point:** New method in `wiki.py`, new data in `EditorProfile`

**Changes needed:**
```python
# New method in wiki.py:
def get_user_blocks(self, username: str) -> list[dict]:
    """Fetch block history for a user."""
    # Uses list=blocks&bkusers=Username

# Extend EditorProfile in arbitration.py:
@dataclass
class EditorProfile:
    ...
    block_history: list[dict] = field(default_factory=list)
    was_blocked_during_case: bool = False
    total_blocks: int = 0
```

**New file consideration:** Could create `src/users.py` for user-centric data

---

#### 1.3 User Groups and Registration

**What it provides:**
- User's permissions (admin, rollbacker, extended-confirmed)
- Account age and total edit count
- Context for understanding participant roles

**Integration point:** `wiki.py` new method, enhance `EditorProfile`

**Changes needed:**
```python
# New method in wiki.py:
def get_user_info(self, username: str) -> dict:
    """Fetch user groups, registration date, edit count."""
    # Uses list=users&usprop=groups|editcount|registration|blockinfo

# Extend EditorProfile:
@dataclass
class EditorProfile:
    ...
    user_groups: list[str] = field(default_factory=list)  # ["extendedconfirmed", "rollbacker"]
    is_admin: bool = False
    registration_date: str | None = None
    global_edit_count: int = 0
```

---

### Tier 2: Medium Value, Moderate Effort

#### 2.1 Log Events (blocks, protection, rights)

**What it provides:**
- Historical record of administrative actions
- Protection events indicate contentious articles
- Rights changes show trust/sanction patterns

**Integration point:** New `wiki.py` methods, potentially new module

**Changes needed:**
```python
# New methods in wiki.py:
def get_log_events(
    self,
    log_type: str,  # "block", "protect", "rights"
    title: str | None = None,
    user: str | None = None,
    limit: int = 100
) -> list[dict]:
    """Fetch log events filtered by type, page, or user."""

def get_protection_log(self, title: str) -> list[dict]:
    """Get protection history for a page."""

def get_block_log(self, username: str) -> list[dict]:
    """Get all blocks/unblocks for a user."""
```

**New data structures:**
```python
@dataclass
class ProtectionEvent:
    timestamp: str
    admin: str
    action: str  # "protect", "modify", "unprotect"
    level: str   # "autoconfirmed", "sysop"
    expiry: str
    reason: str

@dataclass
class PageProtectionHistory:
    title: str
    events: list[ProtectionEvent]
    currently_protected: bool
    protection_level: str | None
```

**Integration with lifecycle:**
- Add protection history to disputed articles
- Correlate protection timing with dispute escalation

---

#### 2.2 ORES/Lift Wing ML Scores

**What it provides:**
- Pre-computed ML predictions per revision
- `damaging`: probability edit harms quality (0-1)
- `goodfaith`: probability edit was well-intentioned (0-1)
- Free signal without training your own models

**Integration point:** New external API client, revision enrichment

**Considerations:**
- Separate API endpoint (not MediaWiki Action API)
- Rate limits apply
- Can batch up to 50 revisions per request
- May want to fetch lazily or cache

**Changes needed:**
```python
# New file: src/ores.py
class OresClient:
    """Client for ORES/Lift Wing scoring API."""

    BASE_URL = "https://ores.wikimedia.org/v3/scores"

    def get_scores(
        self,
        revids: list[int],
        models: list[str] = ["damaging", "goodfaith"]
    ) -> dict[int, dict]:
        """Fetch ML scores for revisions."""

# Extend Revision in arbitration.py:
@dataclass
class Revision:
    ...
    ores_damaging: float | None = None
    ores_goodfaith: float | None = None
```

**Use cases:**
- Identify bad-faith editing patterns
- Weight reverts by severity (reverting damaging edit vs good edit)
- Characterize editor behavior profiles

---

#### 2.3 Article Quality Assessments

**What it provides:**
- WikiProject quality ratings (Stub, Start, C, B, GA, FA)
- Importance ratings (Low, Mid, High, Top)
- Indicates article maturity and community attention

**Integration point:** `wiki.py` new method, article metadata

**Changes needed:**
```python
# New method in wiki.py:
def get_page_assessments(self, title: str) -> dict:
    """Get WikiProject quality and importance ratings."""
    # Uses prop=pageassessments

# Return structure:
{
    "title": "Climate change",
    "assessments": {
        "WikiProject Climate change": {"class": "B", "importance": "Top"},
        "WikiProject Environment": {"class": "B", "importance": "High"}
    },
    "highest_class": "B",
    "highest_importance": "Top"
}
```

**Use in analysis:**
- Do disputes cluster around certain quality levels?
- Do high-importance articles escalate faster?

---

### Tier 3: Valuable but More Complex

#### 3.1 Diff/Compare Content

**What it provides:**
- Actual text changes between revisions
- Size of changes in bytes
- Could compute edit similarity, content analysis

**Integration point:** `wiki.py` new method, optional enrichment

**Considerations:**
- Large data volume if fetched for all revisions
- Better suited for targeted analysis (e.g., reverts only)
- HTML diff output needs parsing

**Changes needed:**
```python
# New method in wiki.py:
def compare_revisions(
    self,
    from_rev: int,
    to_rev: int,
    props: list[str] = ["diff", "size"]
) -> dict:
    """Get diff between two revisions."""
    # Uses action=compare
```

---

#### 3.2 XTools External API

**What it provides:**
- Pre-aggregated user statistics
- Edit counts by namespace, month
- Top-edited pages, automated tool usage
- Avoids heavy computation on our side

**Integration point:** New external client, user enrichment

**Changes needed:**
```python
# New file: src/xtools.py
class XToolsClient:
    """Client for XTools API."""

    BASE_URL = "https://xtools.wmcloud.org/api"

    def get_user_stats(self, username: str) -> dict:
        """Fetch aggregated user statistics."""

    def get_pages_created(self, username: str) -> list[dict]:
        """Fetch pages created by user."""
```

**Privacy note:** Some stats require user opt-in

---

#### 3.3 Pageviews API

**What it provides:**
- Daily/monthly traffic for articles
- Can identify high-visibility disputes
- Traffic spikes may correlate with external events

**Integration point:** New external client, article metadata

**Changes needed:**
```python
# New file: src/pageviews.py
class PageviewsClient:
    """Client for Wikimedia Pageviews API."""

    def get_article_views(
        self,
        title: str,
        start: str,  # YYYYMMDD
        end: str,
        granularity: str = "daily"
    ) -> dict:
        """Fetch pageview counts for an article."""
```

---

#### 3.4 Sockpuppet Investigations (Page Scraping)

**What it provides:**
- Cases of suspected/confirmed sock puppetry
- Links editors to investigation outcomes
- Indicates coordinated abuse patterns

**Integration point:** `fetchers.py` new function, page parsing

**Considerations:**
- Not a structured API - requires wikitext parsing
- Pages at `Wikipedia:Sockpuppet investigations/{username}`
- Outcome templates indicate confirmed/unconfirmed

**Changes needed:**
```python
# In fetchers.py:
def fetch_spi_case(client: WikiClient, username: str) -> dict | None:
    """Fetch sockpuppet investigation for a user if exists."""

def parse_spi_outcome(wikitext: str) -> dict:
    """Parse SPI case outcome from wikitext."""
    # Look for {{SPI archive notice}}, {{checkuser}} results, etc.
```

---

## Data Model Evolution

### Current EditorProfile (arbitration.py)
```python
@dataclass
class EditorProfile:
    username: str
    edits_by_subpage: dict[str, int]
    total_edits: int
    total_reverts: int
    first_seen: str | None
    last_seen: str | None
    pages_touched: list[str]
    sections_edited: list[str]
```

### Proposed Enhanced EditorProfile
```python
@dataclass
class EditorProfile:
    # === Existing fields ===
    username: str
    edits_by_subpage: dict[str, int]
    total_edits: int
    total_reverts: int
    first_seen: str | None
    last_seen: str | None
    pages_touched: list[str]
    sections_edited: list[str]

    # === Account metadata (from API:Users) ===
    user_groups: list[str] = field(default_factory=list)
    is_admin: bool = False
    is_bot: bool = False
    registration_date: str | None = None
    global_edit_count: int | None = None

    # === Sanction history (from API:Blocks + logevents) ===
    block_history: list[dict] = field(default_factory=list)
    total_blocks: int = 0
    was_blocked_during_case: bool = False
    current_block: dict | None = None

    # === Behavioral signals (from ORES) ===
    avg_damaging_score: float | None = None
    avg_goodfaith_score: float | None = None
    pct_edits_reverted: float | None = None

    # === External enrichment (from XTools) ===
    xtools_stats: dict | None = None
```

### New PageMetadata Model
```python
@dataclass
class PageMetadata:
    """Rich metadata for a Wikipedia page."""
    title: str

    # Quality assessment
    quality_class: str | None = None  # Stub, Start, C, B, GA, FA
    importance: str | None = None     # Low, Mid, High, Top

    # Protection status
    protection_level: str | None = None
    protection_expiry: str | None = None
    protection_history: list[dict] = field(default_factory=list)

    # Traffic (optional, from Pageviews API)
    avg_daily_views: float | None = None
    view_trend: str | None = None  # "increasing", "stable", "decreasing"
```

---

## Implementation Order

### Phase 1: Core Enhancements (Immediate)
1. **Edit tags** - Minimal change, high value
2. **User info** - Groups, registration, edit count
3. **Block history** - Direct sanction outcomes

### Phase 2: Contextual Data
4. **Log events** - Protection, rights changes
5. **Article assessments** - Quality ratings
6. **ORES scores** - ML-based edit quality

### Phase 3: External Enrichment
7. **XTools integration** - Pre-aggregated stats
8. **Pageviews** - Article traffic
9. **Diff content** - Targeted content analysis

### Phase 4: Advanced Sources
10. **SPI scraping** - Sockpuppet investigations
11. **Abuse filter logs** - Automated catches

---

## Testing Strategy

Each new data source should have:

1. **Unit tests** for parsing/transformation
2. **Integration tests** with mocked API responses
3. **Live API tests** (marked skip by default, require credentials)

Example test structure:
```
tests/
├── test_wiki.py           # Extended with new methods
├── test_users.py          # New user data module
├── test_ores.py           # ORES client tests
├── test_xtools.py         # XTools client tests
├── test_pageviews.py      # Pageviews client tests
└── fixtures/
    ├── block_history.json
    ├── user_info.json
    ├── ores_scores.json
    └── page_assessments.json
```

---

## Rate Limit Considerations

| API | Limit | Strategy |
|-----|-------|----------|
| MediaWiki Action API | 5000/hr (authenticated) | Existing retry logic |
| ORES | 100 req/s | Batch requests (50 revids each) |
| XTools | Unknown | Add delay, cache results |
| Pageviews | 100 req/s | Batch by date range |

---

## Open Questions

1. **Lazy vs eager loading**: Fetch user enrichment data on-demand or pre-fetch for all participants?
2. **Caching strategy**: Store enrichment data alongside case JSON or in separate files?
3. **Privacy**: Some data (edit counts, user groups) may change - how to handle temporal accuracy?
4. **Scope creep**: At what point does this become too much data to manage?

---

## Next Steps

1. Create task list for each data source
2. Implement Phase 1 (edit tags, user info, blocks)
3. Update `EditorProfile` with new fields
4. Add tests for new functionality
5. Document new data in API reference
