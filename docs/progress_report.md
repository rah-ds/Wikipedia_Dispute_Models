# Wikipedia Dispute Models — Project Progress Report

**Team:** Ryan Healy, Louis, Katherine
**Advisor:** Professor Alvarado
**Sponsor:** Lexipedia / Wikimedia Foundation
**Domain Experts:** Lane, Anson (Lexipedia)
**Program:** UVA MSDS Capstone
**Last Updated:** May 2026 handoff refresh

> **Historical context:** this report preserves project planning notes and may
> mix older design context with refreshed handoff facts. For the current
> handoff state, use [`docs/handoff.md`](handoff.md); this file preserves
> historical project context.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Wikipedia Dispute Resolution Lifecycle](#2-wikipedia-dispute-resolution-lifecycle)
3. [APIs and Data Sources](#3-apis-and-data-sources)
   - [MediaWiki Action API](#31-mediawiki-action-api)
   - [ORES / Lift Wing ML API](#32-ores--lift-wing-ml-api)
   - [Wikimedia Pageviews API](#33-wikimedia-pageviews-api)
   - [XTools API](#34-xtools-api)
   - [Edit Tags (Embedded in Revisions)](#35-edit-tags-embedded-in-mediawiki-revisions)
   - [SPI Wikitext Scraping](#36-spi-wikitext-scraping)
4. [Data Collection Pipeline](#4-data-collection-pipeline)
5. [Core Modules Reference](#5-core-modules-reference)
6. [Data Schema](#6-data-schema)
7. [Current Progress](#7-current-progress)
8. [Next Steps](#8-next-steps)

---

## 1. Project Overview

This project maps and analyzes Wikipedia's dispute resolution system—tracking how content and conduct conflicts emerge, escalate, and resolve across the platform's five-stage intervention framework.

**Core research questions:**
1. What revert ratios and edit patterns signal an active edit war?
2. Do specific editor pairs drive repeated conflicts across multiple articles?
3. Which article and editor characteristics predict dispute escalation to formal venues?
4. How do disputes transition between venues (Talk → DRN → ANI → ArbCom)?
5. What sanctions and outcomes are applied, and to whom, at arbitration?

**Hypothesis:** The same editors recur across venues. Editor co-occurrence combined with temporal proximity is the strongest linking signal for mapping dispute lifecycles.

**Repository structure:**

```
Wikipedia_Dispute_Models/
├── src/                    # Core Python modules
├── scripts/                # Data collection entry points
├── data/
│   ├── raw/                # Raw API responses (JSON)
│   ├── processed/          # Cleaned datasets
│   └── external/           # Third-party data
├── artifacts/
│   ├── arb_cases.txt       # Master case list (481 cases at handoff)
│   ├── pull_state.json     # Current collection progress
│   └── configs/            # YAML preset configs
├── docs/                   # Documentation
├── notebooks/              # Exploratory analysis
└── tests/                  # Unit and integration tests
```

---

## 2. Wikipedia Dispute Resolution Lifecycle

Wikipedia uses **graduated intervention**: formality and binding force increase as lower-level mechanisms fail. Two distinct pathways exist, which frequently intersect.

```
                    ┌─────────────────────────────────────────────────────┐
                    │              DISPUTE EMERGES                        │
                    └───────────────────┬─────────────────────────────────┘
                                        │
                    ┌───────────────────▼─────────────────────────────────┐
         Stage 1    │              TALK PAGE DISCUSSION                   │
                    │  • Article talk page, direct negotiation            │
                    │  • Requires: good faith, civility, 2+ days effort   │
                    └───┬───────────────────────────────────┬─────────────┘
                        │ Content dispute                   │ Conduct dispute
          ┌─────────────▼──────────────────┐    ┌──────────▼──────────────┐
Stage 2   │ THIRD OPINION (3O) or RFC      │    │   USER TALK WARNING     │
          │ • 3O: exactly 2 editors        │    │   • Formal notice of    │
          │ • RfC: broader community       │    │     policy violations   │
          └─────────────┬──────────────────┘    └──────────┬──────────────┘
                        │                                   │
          ┌─────────────▼──────────────────┐    ┌──────────▼──────────────┐
Stage 3   │ DISPUTE RESOLUTION NOTICEBOARD │    │   ADMINS NOTICEBOARD   │
          │ • Volunteer moderators (DRN)   │    │   INCIDENTS (ANI)      │
          │ • Content disputes only        │    │   • Conduct violations  │
          │ • Non-binding facilitation     │    │   • Admins can sanction │
          └─────────────┬──────────────────┘    └──────────┬──────────────┘
                        │ Unresolved                        │ Unresolved
                    ┌───▼───────────────────────────────────▼─────────────┐
         Stage 5    │         ARBITRATION COMMITTEE (ArbCom)              │
                    │  • Court of last resort                             │
                    │  • Binding decisions: bans, topic restrictions      │
                    │  • Structured subpages: Evidence, Workshop,         │
                    │    Proposed Decision, Remedies                      │
                    └─────────────────────────────────────────────────────┘
```

**What we collect at each stage:**

| Stage | Venue | Data Collected | Module |
|-------|-------|----------------|--------|
| 1 | Talk page | Revisions, participants, revert patterns | `wiki.py` |
| 2 | 3O / RfC | Request text, disputants, outcome | `fetchers.py` |
| 3 | DRN | Case sections, status, participants, linked articles | `fetchers.py` |
| 4 | ANI | Section mentions by editor name or case name, context | `fetchers.py` |
| 5 | ArbCom | Full case subpages, revisions, participant enrichment, outcome | `arbitration.py` |

---

## 3. APIs and Data Sources

### 3.1 MediaWiki Action API

**Primary API for all Wikipedia data access.**

- **Endpoint:** `https://en.wikipedia.org/w/api.php`
- **Auth:** OAuth2 Bearer token (`WIKIPEDIA_ACCESS_TOKEN` env var)
- **Rate limits:**
  - Anonymous: 500 requests/hour per IP
  - Authenticated (bot password / OAuth): 5,000 requests/hour
- **Library:** `src/wiki.py` wraps direct MediaWiki REST/action API calls with
  retries, rate limiting, and optional OAuth support
- **Module:** `src/wiki.py` — `WikiClient` class

**Authentication setup:** set `WIKIPEDIA_ACCESS_TOKEN` or the variables in
`.env.example`; `src/credentials.py` and `src/wiki.py` load them for project
scripts.

---

#### Revision Methods

| Method | What It Returns | API Params Used |
|--------|----------------|-----------------|
| `get_revisions(title, limit, content, include_tags)` | `revid`, `parentid`, `timestamp`, `user`, `comment`, `size`, `tags[]` | `prop=revisions&rvprop=ids\|timestamp\|user\|comment\|size\|tags` |
| `get_revisions_with_tags(title, limit)` | Same as above, guaranteed tags, handles pagination | `prop=revisions&rvprop=ids\|timestamp\|user\|comment\|size\|tags` |
| `get_pages_latest(titles, batch_size)` | Latest revision per page for up to 50 titles in one call | `prop=revisions&rvprop=ids\|timestamp\|user\|comment\|content` |
| `get_revision_content(revid)` | Full wikitext of a specific revision + metadata | `prop=revisions&rvslots=main&rvprop=ids\|timestamp\|user\|comment\|size\|tags\|content` |
| `compare_revisions(from_rev, to_rev)` | HTML diff, size change, both users, both comments | `action=compare&prop=diff\|size\|comment\|user\|title` |

**Revision fields returned:**
```python
{
    "revid": int,
    "parentid": int,
    "timestamp": str,        # ISO 8601
    "user": str,
    "comment": str,
    "size": int,             # bytes
    "tags": list[str],       # edit tags (see §3.5)
    "content": str,          # only when requested
}
```

---

#### User Information Methods

| Method | What It Returns | API Params Used |
|--------|----------------|-----------------|
| `get_user_info(username)` | Full user metadata, current block status | `list=users&usprop=groups\|editcount\|registration\|blockinfo\|gender` |
| `get_users_info(usernames, batch_size=50)` | Same, batched up to 50 per request | `list=users` |

**User fields returned:**
```python
{
    "username": str,
    "user_id": int,
    "edit_count": int,
    "registration": str,     # ISO 8601 or None
    "groups": list[str],     # e.g. ["sysop", "autoreviewer"]
    "is_admin": bool,        # "sysop" in groups
    "is_bot": bool,          # "bot" in groups
    "gender": str,           # "male", "female", "unknown"
    "is_blocked": bool,
    "block_reason": str | None,
    "blocked_by": str | None,
    "block_expiry": str | None,
}
```

---

#### Block History Methods

| Method | What It Returns | API Params Used |
|--------|----------------|-----------------|
| `get_user_blocks(username, limit)` | All blocks currently or previously applied to user | `list=blocks&bkusers=Username&bkprop=id\|user\|by\|timestamp\|expiry\|reason\|flags` |
| `get_block_log(username, limit)` | Block/unblock/reblock log events (more detail than blocks list) | `list=logevents&letype=block&letitle=User:{username}` |

**Block fields returned:**
```python
{
    "block_id": int,
    "user": str,
    "blocked_by": str,
    "timestamp": str,
    "expiry": str,           # "infinity" for indefinite
    "reason": str,
    "is_autoblock": bool,
    "allows_email": bool,
    "allows_usertalk": bool,
    "is_partial": bool,
}
```

**Block log fields returned:**
```python
{
    "log_id": int,
    "action": str,           # "block", "unblock", "reblock"
    "target_user": str,
    "admin": str,
    "timestamp": str,
    "comment": str,
    "duration": str,
    "expiry": str,
    "flags": list[str],
}
```

---

#### Log Events Methods

| Method | What It Returns | API Params Used |
|--------|----------------|-----------------|
| `get_log_events(log_type, title, user, limit)` | Generic paginated log events | `list=logevents&letype={type}` |
| `get_protection_log(title, limit)` | Page protection history + cascade status | `list=logevents&letype=protect&letitle={title}` |

**Log types available:** `block`, `protect`, `rights`, `delete`, `move`, `upload`, `abusefilter`

**Log event fields returned:**
```python
{
    "log_id": int,
    "log_type": str,
    "action": str,
    "title": str,
    "user": str,
    "timestamp": str,
    "comment": str,
    "params": dict,          # action-specific details
}
```

---

#### Page Quality and Metadata Methods

| Method | What It Returns | API Params Used |
|--------|----------------|-----------------|
| `get_page_assessments(title)` | WikiProject quality and importance ratings | `prop=pageassessments&palimit=max` |
| `get_page_protection(title)` | Current edit/move protection level and expiry | `prop=info&inprop=protection` |
| `get_talk_page(title)` | Talk-page metadata/content | MediaWiki title and revisions queries |
| `get_category_pages(name, limit)` | All pages in a category | `list=categorymembers` |

**Assessment fields returned:**
```python
{
    "title": str,
    "assessments": {
        "WikiProject Climate Change": {"class": "GA", "importance": "Top"},
        ...
    },
    "highest_quality": str,     # FA > GA > B > C > Start > Stub
    "highest_importance": str,  # Top > High > Mid > Low
}
```

---

#### Abuse Filter Methods

| Method | What It Returns | API Params Used |
|--------|----------------|-----------------|
| `get_abuse_log(user, title, limit)` | Raw abuse filter log entries | `list=abuselog&aflprop=ids\|filter\|user\|title\|action\|result\|timestamp\|details` |
| `get_user_abuse_hits(username, limit)` | Summarized stats: total hits, by filter, by action, by result | Calls `get_abuse_log` then aggregates |

**Abuse log entry fields:**
```python
{
    "log_id": int,
    "filter_id": int,
    "filter_name": str,
    "user": str,
    "title": str,
    "action": str,       # "edit", "createaccount", etc.
    "result": str,       # "warn", "tag", "disallow", ""
    "timestamp": str,
    "revid": int,
}
```

**Aggregated abuse hits returned by `get_user_abuse_hits()`:**
```python
{
    "username": str,
    "total_hits": int,
    "by_filter": {"filter_name": count, ...},
    "by_action": {"edit": count, ...},
    "by_result": {"warn": count, "disallow": count, ...},
    "entries": list[dict],
}
```

---

### 3.2 ORES / Lift Wing ML API

**ML damage and good-faith scores for individual revisions.**

- **Primary endpoint:** `https://api.wikimedia.org/service/lw/inference/v1/models`
- **Legacy endpoint:** `https://ores.wikimedia.org/v3/scores` (fallback)
- **Rate limit:** 100 requests/second; batches of 50 revisions per request
- **Module:** `src/ores.py` — `OresClient` class
- **Auth:** None required (anonymous); `User-Agent` header mandatory

**Models (English Wikipedia):**
- `enwiki-damaging` — probability an edit harms article quality
- `enwiki-goodfaith` — probability an edit was well-intentioned

| Method | Description |
|--------|-------------|
| `get_score(revid)` | Single revision score |
| `get_scores(revids, models)` | Batch scoring, up to 50 revision IDs per call |
| `score_revisions(revisions)` | Add ORES scores to an existing revisions list in-place |

**`OresScore` dataclass:**
```python
@dataclass
class OresScore:
    revid: int
    damaging: float | None          # 0.0-1.0 probability
    goodfaith: float | None         # 0.0-1.0 probability
    damaging_prediction: bool | None  # binary classification
    goodfaith_prediction: bool | None
    error: str | None
```

**Usage:**
```python
from src.ores import OresClient

client = OresClient(wiki="enwiki")
scores = client.get_scores([123456, 789012, 345678])
# Returns list of OresScore objects
```

**Note:** ORES enrichment is implemented but currently excluded from the main pull. It will run as a separate enrichment pass over collected revision IDs.

---

### 3.3 Wikimedia Pageviews API

**Article traffic statistics for visibility analysis.**

- **Endpoint:** `https://wikimedia.org/api/rest_v1/metrics/pageviews`
- **Rate limit:** 100 requests/second
- **Module:** `src/pageviews.py` — `PageviewsClient` class
- **Auth:** None required; `User-Agent` header mandatory

| Method | Description |
|--------|-------------|
| `get_article_views(title, start, end, granularity, access, agent)` | Core fetch — daily or monthly views for a date range |
| `get_views_last_n_days(title, days)` | Convenience: last N days of views |
| `get_views_around_date(title, date, days_before, days_after)` | Views in a window around an event date |
| `get_traffic_spike(title, event_date, baseline_days, event_days)` | Detect spike: compares baseline period vs. event window |
| `get_top_articles(date, n)` | Top-N most viewed articles for a date |

**`PageviewData` dataclass:**
```python
@dataclass
class PageviewData:
    title: str
    project: str = "en.wikipedia"
    views: list[dict]          # raw per-day/month records
    total_views: int
    avg_daily_views: float
    max_daily_views: int
    min_daily_views: int
```

**`get_traffic_spike()` returns:**
```python
{
    "title": str,
    "event_date": str,
    "baseline_avg": float,
    "event_avg": float,
    "spike_ratio": float,      # event_avg / baseline_avg
    "had_spike": bool,         # spike_ratio >= 2.0
    "max_views": int,
}
```

**Research use:** Correlate traffic spikes with dispute events — does a highly visible article attract more edit warring? Do pageviews spike when a dispute goes to ANI or ArbCom?

---

### 3.4 XTools API

**Pre-aggregated user statistics — avoids computing from raw edit data.**

- **Endpoint:** `https://xtools.wmcloud.org/api`
- **Rate limit:** ~50 requests/minute (estimated; we use conservative 5 req/s)
- **Module:** `src/xtools.py` — `XToolsClient` class
- **Auth:** None required

| Method | Endpoint Pattern | Description |
|--------|-----------------|-------------|
| `get_user_stats(username)` | `/user/simple_editcount/{project}/{user}` | Total edits, groups, admin/bot status, registration |
| `get_user_edit_counts_by_namespace(username)` | `/user/namespace_totals/{project}/{user}` | Edit breakdown by namespace (article, talk, user, etc.) |
| `get_pages_created(username, limit)` | `/user/pages/{project}/{user}` | Pages user created (live and deleted) |
| `get_top_edited_pages(username, limit)` | `/user/topedits/{project}/{user}` | Articles most frequently edited by user |
| `get_month_counts(username)` | `/user/month_counts/{project}/{user}` | Edit counts by year-month (YYYY-MM) |
| `get_article_info(title)` | `/article/articleinfo/{project}/{title}` | Article-level statistics |
| `get_article_top_editors(title, limit)` | `/article/topeditors/{project}/{title}` | Top editors for an article with edit counts |

**`UserStats` dataclass fields:**
```python
@dataclass
class UserStats:
    username: str
    project: str
    total_edit_count: int
    live_edit_count: int
    deleted_edit_count: int
    edits_by_namespace: dict[str, int]  # {"0": 1200, "1": 340, ...}
    first_edit: str | None
    last_edit: str | None
    days_active: int
    pages_created: int
    pages_created_live: int
    pages_created_deleted: int
    thank_count: int
    reverted_count: int         # times this user was reverted
    reverts_done: int           # times this user reverted others
    user_groups: list[str]
    is_admin: bool
    is_bot: bool
    registration: str | None
    error: str | None
```

---

### 3.5 Edit Tags (Embedded in MediaWiki Revisions)

Edit tags are attached to revisions in the MediaWiki database. They surface automatically when you request `rvprop=tags` in a revision query. No separate API call needed.

| Tag | Meaning |
|-----|---------|
| `mw-revert` | MediaWiki software detected this edit as a revert |
| `mw-undo` | Editor used the "Undo" button in the UI |
| `mw-rollback` | Admin or rollbacker used the rollback tool |
| `mw-reverted` | This edit was subsequently reverted by someone else |
| `mw-manual-revert` | Manual revert detected (restored previous content) |

**Research use:** These tags are more reliable than parsing edit summaries for revert detection. `mw-reverted` on an edit means it was reversed — combining this with `mw-revert` on the reversing edit lets us reconstruct exact revert pairs and identify edit war participants.

---

### 3.6 SPI Wikitext Scraping

**Sockpuppet Investigation pages — not a formal API.**

SPI cases are standard wiki pages at `Wikipedia:Sockpuppet investigations/{username}`. We scrape them with the MediaWiki API and parse the wikitext manually.

- **Module:** `src/fetchers.py` — `fetch_spi_case()`, `parse_spi_outcome()`, `check_user_spi_status()`
- **Page format:** `Wikipedia:Sockpuppet investigations/{username}`

| Function | Description |
|----------|-------------|
| `fetch_spi_case(client, username)` | Fetch and return SPI page content + metadata |
| `parse_spi_outcome(content)` | Extract status (confirmed/declined/stale/archived), checkuser use, sockpuppet list |
| `check_user_spi_status(client, username)` | Summary: `has_spi_case`, `is_confirmed_sockpuppet`, `case_url` |

**`check_user_spi_status()` returns:**
```python
{
    "username": str,
    "has_spi_case": bool,
    "is_confirmed_sockpuppet": bool,
    "case_url": str | None,
    "status": str | None,        # "confirmed", "declined", "stale", "archived"
    "used_checkuser": bool,
    "sockpuppets": list[str],
}
```

---

## 4. Data Collection Pipeline

### 4.1 Main Orchestrator

**Entry point:** `scripts/pull.py` — `PullRunner` class

```
PullRunner.run()
    ├── check_internet_speed()              # log bandwidth
    ├── StateManager.load()                 # resume from checkpoint
    ├── WikiClient.__init__(use_oauth=True) # authenticate
    │
    ├── _process_arbitration()              # for each case in case_list:
    │   └── fetch_full_arbitration_case()
    │       ├── _resolve_arb_case_title()   # try 3 URL patterns
    │       ├── fetch case + 5 subpages     # main, evidence, workshop,
    │       │                               #   proposed_decision, remedies
    │       ├── fetch talk pages            # for each subpage
    │       ├── extract_participants()      # from wikitext links
    │       ├── extract_article_links()     # articles mentioned
    │       ├── get_users_info()            # batch user enrichment (50/req)
    │       ├── get_user_blocks()           # top 30 participants
    │       ├── get_user_abuse_hits()       # top 20 participants
    │       ├── get_page_assessments()      # per article
    │       ├── get_page_protection()       # per article
    │       ├── get_protection_log()        # per article
    │       ├── get_revisions_with_tags()   # per article (top 10)
    │       ├── search_ani_mentions()       # case name + top 5 participants
    │       ├── search_drn_mentions()       # case name + top 3 participants
    │       └── parse_case_outcome()        # status, sanctions, remedies
    │
    ├── _process_lifecycle()                # for each case:
    │   └── collect_dispute_lifecycle()
    │       ├── fetch ArbCom case           # Stage 5
    │       ├── search_ani_mentions()       # Stage 4
    │       ├── search_drn_mentions()       # Stage 3
    │       └── fetch_talk_page_revisions() # Stage 1 (up to 10 articles)
    │
    └── _process_drn()                      # stub — pending
```

**Output:** `data/raw/{source}/{case_name}.json`

---

### 4.2 Configuration

Three preset configs in `src/pull_config.py`:

| Config | Cases | Rev Limit | Enrich | ANI/DRN | Use |
|--------|-------|-----------|--------|---------|-----|
| `dev` | 1 (Climate change) | 10 | Off | Off | Development only |
| `sample` | 5 (hardcoded) | 50 | On | On | Testing, smoke test |
| `full` | All from `arb_cases.txt` | None | On | On | Full data collection |

**Commands:**
```bash
make pull                  # sample (5 cases)
make pull CONFIG=full      # all cases
make pull CONFIG=dev       # dev (1 case)
make pull-status           # show progress
make pull-reset            # clear state for fresh start
```

**Key config fields (`PullConfig`):**

```python
state_file: str = "artifacts/pull_state.json"
resume_enabled: bool = True
checkpoint_interval: int = 10    # save state every N items

rate_limit: RateLimitConfig
    requests_per_second: float = 5.0
    burst_size: int = 10
    min_delay_between_requests: float = 0.1

retry: RetryConfig
    max_retries: int = 10
    base_delay: float = 2.0
    max_delay: float = 300.0     # 5 min max backoff
    exponential_base: float = 2.0
```

---

### 4.3 Resilience Architecture

**`retry_on_rate_limit` decorator** (`src/wiki.py`):
- Wraps all WikiClient methods
- Catches `APIError` (ratelimit, maxlag) and `ServerError` (5xx)
- Exponential backoff: `delay = base_delay × 2^attempt × jitter(0.5–1.5)`
- Up to 10 retries; max wait 5 minutes

**Circuit breaker** (`src/network.py`):
- Opens after 5 consecutive failures → rejects requests
- Half-open after 60s timeout → allows test request
- Closes after 3 consecutive successes
- Prevents cascading failures during extended outages

**Rate tracking** (`src/rate_tracker.py`):
- Sliding-window tracking for all APIs (session totals + current window usage)
- Logs every 50 requests with hourly breakdown
- `estimate_pull_capacity()` estimates cases/hour from connection speed + rate limits

**State management** (`src/pull_state.py`):
- Per-item status: `pending → in_progress → completed / failed / skipped`
- State saved every 10 items (configurable)
- Survives `Ctrl+C` via signal handlers (`SIGINT`, `SIGTERM`)
- `make pull` resumes from last checkpoint automatically

---

## 5. Core Modules Reference

| Module | Purpose | Key Classes / Functions | Status |
|--------|---------|-------------------------|--------|
| `src/wiki.py` | MediaWiki API wrapper | `WikiClient` (46+ methods), `retry_on_rate_limit` | ✅ Complete |
| `src/fetchers.py` | High-level data fetch functions | `fetch_arbitration_cases`, `search_ani_mentions`, `search_drn_mentions`, `fetch_talk_page_revisions`, `fetch_spi_case`, `fetch_dispute_lifecycle` | ✅ Complete |
| `src/arbitration.py` | ArbCom case data collection | `fetch_full_arbitration_case`, `extract_participants`, `extract_article_links`, `find_case_path` | ✅ Complete |
| `src/outcome.py` | Decision and sanction parsing | `CaseOutcome`, `Sanction`, `parse_case_outcome` | ✅ Complete |
| `src/models.py` | Data models | `DisputeStage`, `DisputeType`, `DisputeEvent`, `DisputeTimeline`, `EditorProfile`, `Revision` | ✅ Complete |
| `src/timeline.py` | Timeline reconstruction | `build_timeline`, `TimelineEntry`, talk post detection | ✅ Complete |
| `src/analysis.py` | Edit war detection | `analyze_edit_war`, revert ratio calculation | ✅ Complete |
| `src/ores.py` | ORES/Lift Wing ML scores | `OresClient`, `OresScore`, `get_scores` (batched) | ✅ Complete |
| `src/pageviews.py` | Article traffic | `PageviewsClient`, `PageviewData`, `get_traffic_spike` | ✅ Complete |
| `src/xtools.py` | Pre-aggregated user stats | `XToolsClient`, `UserStats`, 7 methods | ✅ Complete |
| `src/pull_config.py` | Collection configuration | `PullConfig`, `DataSourceConfig`, `get_sample_config`, `get_full_config` | ✅ Complete |
| `src/pull_state.py` | Resumable state tracking | `StateManager`, item-level status, checkpointing | ✅ Complete |
| `src/rate_tracker.py` | API usage tracking | `RateTracker`, `RateWindow`, `estimate_pull_capacity` | ✅ Complete |
| `src/network.py` | Network resilience | `CircuitBreaker`, exponential backoff, retry logic | ✅ Complete |
| `src/logging_config.py` | Centralized logging | Structured logging, progress bars (tqdm) | ✅ Complete |
| `src/credentials.py` | Env validation | Token loading, API credential checks | ✅ Complete |

---

## 6. Data Schema

### 6.1 Arbitration Case JSON

Output path: `data/raw/arbitration/{case_name}.json`

```python
{
    "case_name": str,
    "case_prefix": str,        # e.g. "Wikipedia:Arbitration/Requests/Case/Climate change"
    "path_pattern": str,       # which URL pattern matched
    "fetched_at": str,         # ISO 8601

    "pages": {
        "main": {
            "title": str, "url": str, "exists": bool,
            "content": str,        # full wikitext
            "content_length": int,
            "revisions": list[RevisionDict],
            "revision_count": int
        },
        "evidence": {...},
        "workshop": {...},
        "proposed_decision": {...},
        "remedies": {...}
    },

    "talk_pages": [
        {"title": str, "url": str, "revisions": list[RevisionDict], ...}
    ],

    "all_participants": list[str],   # all usernames extracted from case wikitext
    "all_articles": list[str],       # all article titles linked in the case

    "participants": {
        "Username": {
            "username": str, "user_id": int, "edit_count": int,
            "registration": str, "groups": list, "is_admin": bool,
            "is_bot": bool, "gender": str,
            "is_blocked": bool, "block_reason": str | None,
            "blocked_by": str | None, "block_expiry": str | None
        }
    },

    "participant_blocks": {
        "Username": [BlockDict, ...]    # block history (top 30 participants)
    },

    "participant_abuse_hits": {
        "Username": {
            "total_hits": int,
            "by_filter": {...}, "by_action": {...}, "by_result": {...}
        }
    },

    "articles": {
        "Article Title": {
            "quality_class": str | None,   # FA, GA, B, C, Start, Stub
            "importance": str | None,      # Top, High, Mid, Low
            "assessments": {...},
            "protection_level": str,
            "protection": dict,
            "protection_history": list[LogEventDict],
            "protection_count": int
        }
    },

    "article_revisions": {
        "Article Title": list[RevisionDict]    # top 10 articles only
    },

    "ani_mentions": [
        {
            "title": str, "source": str, "source_url": str,
            "search_term": str, "search_type": "case_name" | "participant",
            "content": str      # relevant section text
        }
    ],

    "drn_mentions": [
        {"type": str, "search_term": str, "url": str, "found": bool}
    ],

    "outcome": {
        "status": str,          # "accepted", "rejected", "decided", etc.
        "decision_date": str | None,
        "sanctions": list[SanctionDict],
        "findings": list[str],
        "remedy_count": int
    },

    "summary": {
        "case_pages_found": int,
        "talk_pages_found": int,
        "participants_extracted": int,
        "participants_enriched": int,
        "participants_with_blocks": int,
        "participants_with_abuse_hits": int,
        "articles_extracted": int,
        "articles_enriched": int,
        "articles_with_revisions": int,
        "ani_mentions": int,
        "drn_mentions": int,
        "outcome_status": str,
        "remedy_count": int,
        "total_revisions": int
    }
}
```

### 6.2 Lifecycle JSON

Output path: `data/raw/dispute_venues/{case_name}_lifecycle.json`

```python
{
    "case_name": str,
    "fetched_at": str,
    "stages": {
        "stage_5_arbcom": {RevisionData per subpage},
        "stage_4_ani": [MentionDict, ...],
        "stage_3_drn": [MentionDict, ...],
        "stage_1_talk": {ArticleTitle: RevisionData, ...}
    },
    "summary": {
        "arbitration_revisions": int,
        "ani_mentions": int,
        "drn_mentions": int,
        "talk_articles_found": int,
        "talk_revisions_total": int,
        "all_participants": list[str]
    }
}
```

### 6.3 Key Fields for Downstream Analysis

| Field | Location | Research Use |
|-------|----------|-------------|
| `revisions[].user` | Case pages, talk pages, articles | Who edited what and when |
| `revisions[].tags` | Article revisions | Identify reverts without parsing summaries |
| `participants[].edit_count` | Participant enrichment | Editor experience level |
| `participants[].is_admin` | Participant enrichment | Admin involvement in disputes |
| `participant_blocks[].reason` | Block history | Policy violations tied to dispute |
| `participant_abuse_hits.by_result` | Abuse hits | Disallowed actions, warnings |
| `articles[].quality_class` | Article enrichment | High-quality articles more likely disputed |
| `articles[].protection_count` | Protection history | Protection as proxy for edit war severity |
| `ani_mentions[].search_type` | ANI search | Distinguish case-level vs. editor-level escalation |
| `outcome.sanctions` | Outcome parsing | What happened to editors who were found at fault |

---

## 7. Current Progress

### 7.1 Collection Status

| Source | Status | Detail |
|--------|--------|--------|
| **Canonical ArbCom case list** | ✅ Complete | 481 cases in `artifacts/arb_cases.txt` |
| **Raw per-case arbitration JSON** | ✅ Complete | 481 raw records present |
| **Usable arbitration/lifecycle data** | ✅ Mostly complete | 472 usable records; 9 zero-data records need inspection |
| **Dashboard/D3 exports** | ✅ Partial | 466 JSON files in `data/processed/d3/`, including `manifest.json`; regenerate after raw fixes |
| **Evidence diff enrichment** | ✅ Implemented | `src/evidence.py` and `scripts/enrich_evidence_diffs.py` extract `Special:Diff` evidence |
| **Graph layer** | ✅ Implemented | `src/graph.py` builds editor/article/case `MultiDiGraph` exports |

**Case list:** `artifacts/arb_cases.txt` — 481 canonical ArbCom cases from
2004–2025. See [`handoff.md`](handoff.md) for the current zero-data case list
and lifecycle-stage distribution.

### 7.2 Implemented Capabilities

| Capability | Status |
|------------|--------|
| WikiClient (all methods) | ✅ |
| Arbitration case collection (full enrichment) | ✅ |
| Dispute lifecycle collection (Talk → ANI → ArbCom) | ✅ |
| ANI archive search | ✅ |
| DRN archive search | ✅ |
| Talk page revision collection | ✅ |
| 3O and RfC fetching | ✅ |
| User info, block history, abuse hits | ✅ |
| SPI case fetching and parsing | ✅ |
| ORES/Lift Wing ML scoring | ✅ implemented |
| Pageviews traffic analysis | ✅ implemented |
| XTools user stats | ✅ implemented |
| Edit war detection (`analyze_edit_war`) | ✅ |
| Outcome parsing (sanctions, remedies) | ✅ |
| Graph construction | ✅ |
| Evidence diff extraction | ✅ |
| Analysis phase (modeling, ML) | Prototype / future work |

### 7.3 Handoff References

The historical commit list that used to appear here is no longer maintained.
For current handoff state, use:

- `docs/handoff.md` for coverage, gaps, and maintainer priorities
- `artifacts/arb_cases.txt` for the canonical case list
- `data/raw/arbitration/` for raw per-case records
- `data/processed/d3/manifest.json` for dashboard export coverage

---

## 8. Next Steps

### Immediate (Data Quality)
1. **Repair zero-data ArbCom records** — inspect or refetch the 9 cases listed in [`handoff.md`](handoff.md)
2. **Regenerate dashboard payloads** — run the D3 export after raw fixes so dashboard coverage matches usable raw coverage
3. **Validate outcomes** — hand-check parsed sanctions/remedies before using them as labels

### Analysis Phase
4. **Revert ratio analysis** — compute per-article and per-editor revert ratios using `mw-revert` / `mw-reverted` tags
5. **Editor co-occurrence networks** — use the graph layer to identify editors who appear together across cases and venues
6. **Escalation prediction** — collect non-escalated or declined disputes as a negative class before training
7. **Traffic spike correlation** — use Pageviews data to test whether high-visibility articles attract more edit warring
8. **Sanction outcome classification** — model participant characteristics only after outcome labels are validated

### Deliverables
9. Capstone paper (UVA MSDS DS 6015 submission)
10. Dataset release (Lexipedia / Wikimedia)
11. Visualization dashboard (dispute lifecycle maps, editor network graphs)

---

## Appendix: Arbitration Case URL Patterns

The project supports three historical ArbCom URL formats:

```python
ARB_PATH_PATTERNS = [
    "Wikipedia:Arbitration/Requests/Case/{name}",  # Post-2010 (current)
    "Wikipedia:Requests for arbitration/{name}",   # Pre-2010
    "Wikipedia:Arbitration/{name}",                # Very old format
]
```

Cases in `arb_cases.txt` are stored as short names (e.g., `Climate change`). The `_resolve_arb_case_title()` function in `src/fetchers.py` tries each pattern until a live page is found.

---

## Appendix: Sample Case Names (from `arb_cases.txt`)

The full list contains 481 cases spanning 2004–2025. A representative sample:

```
Climate change
Gamergate
Eastern Europe
Scientology
Muhammad images
Palestine-Israel articles
Tea Party movement
Abortion
GamerGate 2
Genetically modified organisms
Sexology
Homeopathy
...
```

See `artifacts/arb_cases.txt` for the full list.

---

*See also:*
- [docs/wikipedia_dispute_resolution_lifecycle.md](wikipedia_dispute_resolution_lifecycle.md) — Full five-stage process analysis with policy citations
- [docs/wikimedia_api.md](wikimedia_api.md) — Original API reference
- [docs/api_expansion_design.md](api_expansion_design.md) — Design document for the API expansion phase
- [docs/sample_article_selection.md](sample_article_selection.md) — Rationale for the five sample cases
