
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

## Sources

1. MediaWiki. "API:Main page." <https://www.mediawiki.org/wiki/API:Main_page>
2. MediaWiki. "Manual:Pywikibot." <https://www.mediawiki.org/wiki/Manual:Pywikibot>
3. Wikimedia. "API:Etiquette." <https://www.mediawiki.org/wiki/API:Etiquette>
4. Wikipedia. "Wikipedia:Database download." <https://en.wikipedia.org/wiki/Wikipedia:Database_download>
5. Wikimedia. "Rate limits." <https://api.wikimedia.org/wiki/Rate_limits>
