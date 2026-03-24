
# Wikimedia API Reference

## Overview

Wikipedia data can be accessed through multiple APIs and data sources. For research on edit wars, disputes, and arbitration, the **MediaWiki Action API** combined with **Pywikibot** provides the most comprehensive access to revision histories, talk pages, and user contributions.

---

## API Options

### 1. MediaWiki Action API

The primary API for programmatic Wikipedia access.

**Endpoint pattern**: `https://{lang}.wikipedia.org/w/api.php`

| Wiki | Endpoint |
| ---- | -------- |
| English Wikipedia | `https://en.wikipedia.org/w/api.php` |
| Meta-Wiki | `https://meta.wikimedia.org/w/api.php` |
| MediaWiki | `https://www.mediawiki.org/w/api.php` |

**Key modules for dispute research**:

- `action=query&prop=revisions` — Full revision history with timestamps, users, comments
- `action=query&list=usercontribs` — All edits by a specific user
- `action=query&prop=info` — Page protection status, watchers
- `action=compare` — Diff between two revisions
- `action=parse` — Rendered page content

### 2. Wikimedia REST API

Simpler interface for common operations.

**Endpoint**: `https://en.wikipedia.org/api/rest_v1/`

### 3. Database Dumps

For large-scale analysis, download complete dumps.

**Source**: <https://dumps.wikimedia.org/enwiki/>

| File | Contents |
| ---- | -------- |
| `pages-articles-multistream.xml.bz2` | Current revisions, no talk pages (~25 GB compressed) |
| `pages-meta-current.xml.bz2` | Current revisions, all pages including talk |
| `pages-meta-history*.xml.bz2` | Full revision history (multiple TB) |

---

## Python Libraries

### Recommended: Pywikibot

**Pywikibot** is the official Python library for MediaWiki automation. Winner of the 2020 Coolest Tool Award.

**Install**:

```bash
pip install pywikibot
```

**Why Pywikibot for dispute research**:

- Built-in handling of API pagination, rate limits, authentication
- Direct access to revision histories, diffs, user contributions
- Talk page parsing support
- Mature, well-documented, actively maintained

**Basic usage**:

```python
import pywikibot

# Connect to English Wikipedia
site = pywikibot.Site('en', 'wikipedia')

# Get a page and its revision history
page = pywikibot.Page(site, 'Article_title')

# Iterate through all revisions
for rev in page.revisions():
    print(rev.timestamp, rev.user, rev.comment)

# Get talk page
talk = page.toggleTalkPage()
for rev in talk.revisions():
    print(rev.timestamp, rev.user)
```

**Fetching edit wars** (pages with high revert activity):

```python
import pywikibot

site = pywikibot.Site('en', 'wikipedia')
page = pywikibot.Page(site, 'Contentious_Article')

revisions = list(page.revisions(content=False))

# Detect reverts by checking for "revert" in edit summaries
reverts = [r for r in revisions if r.comment and 'revert' in r.comment.lower()]
print(f"Reverts: {len(reverts)} / {len(revisions)} total edits")
```

### Alternative: mwapi

Lightweight wrapper for direct API calls.

```bash
pip install mwapi
```

```python
import mwapi

session = mwapi.Session('https://en.wikipedia.org', user_agent='MyBot/1.0')

# Get revision history
response = session.get(
    action='query',
    titles='Article_title',
    prop='revisions',
    rvprop='ids|timestamp|user|comment',
    rvlimit=500
)
```

### Alternative: mwparserfromhell

For parsing wikitext (talk page discussions, templates).

```bash
pip install mwparserfromhell
```

```python
import mwparserfromhell

wikicode = mwparserfromhell.parse(page_text)
templates = wikicode.filter_templates()
```

---

## Rate Limits

Limits apply to `api.wikimedia.org` endpoints:

| Authentication | Limit |
| -------------- | ----- |
| Anonymous (no token) | 500 requests/hour per IP |
| Personal API token | 5,000 requests/hour |

A `429` response indicates rate limit exceeded.

**Best practices**:

- Set a descriptive `User-Agent` header
- Use `maxlag` parameter to back off during server load
- Cache responses locally
- For bulk data, use database dumps instead

---

## Accessing Dispute Resolution Data

### Arbitration Cases

Arbitration cases are stored as wiki pages:

- **Case pages**: `Wikipedia:Arbitration/Requests/Case/{CaseName}`
- **Evidence**: `Wikipedia:Arbitration/Requests/Case/{CaseName}/Evidence`
- **Workshop**: `Wikipedia:Arbitration/Requests/Case/{CaseName}/Workshop`

```python
import pywikibot

site = pywikibot.Site('en', 'wikipedia')

# List all arbitration case pages
arb_cat = pywikibot.Category(site, 'Category:Wikipedia arbitration cases')
for page in arb_cat.articles():
    print(page.title())
```

### Dispute Resolution Noticeboard

DRN discussions at: `Wikipedia:Dispute resolution noticeboard`

### Edit War Detection

Query revision history for revert patterns:

```python
# Get revisions with size changes (potential reverts restore previous size)
for rev in page.revisions(content=False):
    # Large negative size change may indicate revert
    if hasattr(rev, 'size') and hasattr(rev, 'parentsize'):
        delta = rev.size - rev.parentsize
        if abs(delta) > 1000:
            print(f"{rev.timestamp}: {rev.user} changed {delta} bytes")
```

---

## Authentication

### Personal API Token

1. Create Wikimedia account
2. Go to `Special:BotPasswords` on the wiki
3. Create new bot password with required permissions
4. Use in requests:

```python
headers = {
    'Authorization': 'Bearer YOUR_ACCESS_TOKEN',
    'User-Agent': 'YourApp/1.0 (your@email.com)'
}
```

### OAuth (for user-facing applications)

Register at <https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration>

---

## Extended API Coverage (WikiClient Methods)

Our `WikiClient` class in `src/wiki.py` wraps the MediaWiki API with additional methods for dispute research:

### Revision Methods

| Method | Description | API Endpoint |
| ------ | ----------- | ------------ |
| `get_revisions()` | Fetch revision history with optional edit tags | `action=query&prop=revisions&rvprop=tags` |
| `get_revisions_with_tags()` | Direct API call ensuring tag retrieval | `action=query&prop=revisions&rvprop=tags` |
| `compare_revisions()` | Get diff between two revisions | `action=compare` |
| `get_revision_content()` | Get full content of specific revision | `action=query&prop=revisions&rvslots=main` |

**Edit Tags** (from `rvprop=tags`):
- `mw-revert` — MediaWiki detected this as a revert
- `mw-undo` — Editor used the undo feature
- `mw-rollback` — Admin/rollbacker used rollback
- `mw-reverted` — This edit was later reverted
- `mw-manual-revert` — Manual revert detected

### User Methods

| Method | Description | API Endpoint |
| ------ | ----------- | ------------ |
| `get_user_info()` | User groups, registration, edit count | `list=users&usprop=groups\|editcount\|registration` |
| `get_users_info()` | Batch user info (max 50 per request) | `list=users` |
| `get_user_blocks()` | Block history for a user | `list=blocks&bkusers=Username` |
| `get_block_log()` | Block/unblock log entries | `list=logevents&letype=block` |
| `get_user_abuse_hits()` | Abuse filter statistics for user | `list=abuselog&afluser=Username` |

### Log Events

| Method | Description | API Endpoint |
| ------ | ----------- | ------------ |
| `get_log_events()` | Generic log event fetching | `list=logevents&letype={type}` |
| `get_protection_log()` | Page protection history | `list=logevents&letype=protect` |
| `get_abuse_log()` | Abuse filter log entries | `list=abuselog` |

### Page Metadata

| Method | Description | API Endpoint |
| ------ | ----------- | ------------ |
| `get_page_assessments()` | WikiProject quality ratings | `prop=pageassessments` |
| `get_page_protection()` | Current protection status | `prop=info&inprop=protection` |

---

## External APIs

In addition to the MediaWiki Action API, we integrate with external services:

### ORES/Lift Wing (ML Scores)

**Module**: `src/ores.py`

ORES provides ML predictions for revision quality:
- **damaging**: Probability edit harms article quality (0-1)
- **goodfaith**: Probability edit was well-intentioned (0-1)

```python
from src.ores import OresClient

client = OresClient(wiki="enwiki")
scores = client.get_scores([123456, 789012])  # revision IDs
```

**Endpoint**: `https://api.wikimedia.org/service/lw/inference/v1/models`

**Rate limit**: 100 requests/second (batches of 50 revisions)

### Pageviews API

**Module**: `src/pageviews.py`

Article traffic data for visibility analysis:

```python
from src.pageviews import PageviewsClient

client = PageviewsClient()
data = client.get_views_last_n_days("Climate change", days=30)
print(f"Avg daily views: {data.avg_daily_views}")
```

**Endpoint**: `https://wikimedia.org/api/rest_v1/metrics/pageviews`

**Rate limit**: 100 requests/second

### XTools API

**Module**: `src/xtools.py`

Pre-aggregated user statistics:

```python
from src.xtools import XToolsClient

client = XToolsClient()
stats = client.get_user_stats("ExampleUser")
print(f"Total edits: {stats.total_edit_count}")
```

**Endpoint**: `https://xtools.wmcloud.org/api`

**Rate limit**: Unknown, use conservative delays

---

## Sockpuppet Investigations

**Module**: `src/fetchers.py` (functions `fetch_spi_case`, `parse_spi_outcome`)

SPI cases are wiki pages that require wikitext parsing:

```python
from src.fetchers import fetch_spi_case, check_user_spi_status

# Check if user has SPI case
status = check_user_spi_status(client, "Username")
if status["has_spi_case"]:
    print(f"Confirmed sockpuppet: {status['is_confirmed_sockpuppet']}")
```

**Page format**: `Wikipedia:Sockpuppet investigations/{username}`

---

## Sources

1. MediaWiki. "API:Main page." <https://www.mediawiki.org/wiki/API:Main_page>
2. MediaWiki. "Manual:Pywikibot." <https://www.mediawiki.org/wiki/Manual:Pywikibot>
3. Wikimedia. "API:Etiquette." <https://www.mediawiki.org/wiki/API:Etiquette>
4. Wikipedia. "Wikipedia:Database download." <https://en.wikipedia.org/wiki/Wikipedia:Database_download>
5. Wikimedia. "Rate limits." <https://api.wikimedia.org/wiki/Rate_limits>
6. Wikimedia. "Lift Wing API." <https://api.wikimedia.org/wiki/Lift_Wing_API>
7. Wikimedia. "Pageviews API." <https://wikitech.wikimedia.org/wiki/Analytics/AQS/Pageviews>
8. XTools. "API Documentation." <https://xtools.wmcloud.org/api>
