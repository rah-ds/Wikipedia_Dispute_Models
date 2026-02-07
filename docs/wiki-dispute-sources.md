# Wikipedia Dispute Sources - Complete Page & Category Map

All locations where editor-vs-editor disputes are recorded on English Wikipedia. Organized by venue type and escalation level.

---

## 1. ARBITRATION (Formal - Highest Level)

### Categories
- `Category:Wikipedia arbitration` — umbrella (7 subcategories, 18 pages)
- `Category:Wikipedia arbitration cases` — **~485 individual case pages**
- `Category:Wikipedia arbitration archives` — 17 pages of archived cases
- `Category:Wikipedia Arbitration Committee` — committee structure/process pages
- `Category:Wikipedia Arbitration Committee rulings`
- `Category:Wikipedia arbitration enforcement current sanctions` — ~5,872 active sanctions

### Pages (fetch & parse)
- `Wikipedia:Arbitration/Requests` — intake page for new cases
- `Wikipedia:Arbitration/Requests/Case` — active case requests
- `Wikipedia:Arbitration/Requests/Clarification and Amendment` — reopened/modified cases
- `Wikipedia:Arbitration/Requests/Enforcement` — enforcement requests against editors
- `Wikipedia:Arbitration/Current` — currently active cases
- `Wikipedia:Arbitration/Index/Principles` — principles from past rulings

### Archive pattern
- Individual cases: `Wikipedia:Requests for arbitration/{Case Name}` (older format)
- Individual cases: `Wikipedia:Arbitration/Requests/Case/{Case Name}` (newer format)

---

## 2. DISPUTE RESOLUTION NOTICEBOARD (DRN) — Content Disputes

### Pages (fetch & parse)
- `Wikipedia:Dispute resolution noticeboard` — active cases (what your script fetches now)

### Archive pattern
- `Wikipedia:Dispute resolution noticeboard/Archive 1` through `Archive 240+`
- Archives are numbered sequentially, ~2,520+ total cases through mid-2020

### Related subpages
- `Wikipedia:Dispute resolution noticeboard/Header`
- `Wikipedia:Dispute resolution noticeboard/Guide`

---

## 3. ADMINISTRATORS' NOTICEBOARD / INCIDENTS (ANI) — Conduct Disputes

### Pages (fetch & parse)
- `Wikipedia:Administrators' noticeboard/Incidents` — active conduct reports
- `Wikipedia:Administrators' noticeboard` — general admin coordination

### Archive pattern
- `Wikipedia:Administrators' noticeboard/IncidentArchive{N}` — numbered archives (1 through 1100+)
- Some named subpages: `Wikipedia:Administrators' noticeboard/Incidents/{Topic Name}`

---

## 4. EDIT WARRING NOTICEBOARD (AN/EW, formerly AN/3RR)

### Pages (fetch & parse)
- `Wikipedia:Administrators' noticeboard/Edit warring` — active edit war reports

### Archive pattern
- `Wikipedia:Administrators' noticeboard/3RRArchive{N}` — older archives (uses legacy "3RR" name)
- `Wikipedia:Administrators' noticeboard/Edit warring/Archive{N}` — newer archives

### Related subpages
- `Wikipedia:Administrators' noticeboard/Edit warring/Administrator instructions`

### Category
- `Category:Wikipedia edit warring` — 1 subcategory, 6 pages

---

## 5. THIRD OPINION (3O) — Two-Editor Disputes

### Pages (fetch & parse)
- `Wikipedia:Third opinion` — active requests for a third opinion
- `Wikipedia:Third opinion/Active` — list of active 3O requests

### Archive pattern
- `Wikipedia:Third opinion/Archive{N}`

---

## 6. REQUESTS FOR COMMENT (RfC) — Community Input

### Pages (fetch & parse)
- `Wikipedia:Requests for comment` — main RfC page
- `Wikipedia:Requests for comment/All` — aggregated listing of all active RfCs

### RfC subpage listings (active RfCs by topic)
- `Wikipedia:Requests for comment/Biographies`
- `Wikipedia:Requests for comment/Economy, trade, and companies`
- `Wikipedia:Requests for comment/History and geography`
- `Wikipedia:Requests for comment/Language and linguistics`
- `Wikipedia:Requests for comment/Mathematics, science, and technology`
- `Wikipedia:Requests for comment/Media, the arts, and architecture`
- `Wikipedia:Requests for comment/Politics, government, and law`
- `Wikipedia:Requests for comment/Religion and philosophy`
- `Wikipedia:Requests for comment/Society, sports, and culture`
- `Wikipedia:Requests for comment/Wikipedia policies and guidelines`
- `Wikipedia:Requests for comment/Wikipedia proposals`
- `Wikipedia:Requests for comment/Wikipedia information pages and essays`
- `Wikipedia:Requests for comment/Wikipedia style and naming`
- `Wikipedia:Requests for comment/Wikipedia templates, categories, and WikiProjects`

### User conduct RfCs (discontinued but archived)
- `Wikipedia:Requests for comment/User conduct` — discontinued, redirects to ANI now
- `Wikipedia:Requests for comment/User conduct/UsersList` — list of past user conduct RfCs
- `Wikipedia:Requests for comment/User conduct/Archive` — archived user conduct cases

### Category
- `Category:Wikipedia requests for comment` — 4 subcategories, 56 pages

---

## 7. MEDIATION — Formal Content Dispute Resolution

### Pages (fetch & parse)
- `Wikipedia:Mediation Committee` — formal mediation (largely inactive now)
- `Wikipedia:Mediation Committee/Cases` — case listings
- `Wikipedia:Mediation Cabal` — informal mediation (also largely inactive)
- `Wikipedia:Mediation Cabal/Cases` — case listings

### Category
- `Category:Wikipedia mediation` — 1 subcategory, 3 pages

---

## 8. SOCKPUPPET INVESTIGATIONS (SPI) — Account Abuse

### Pages (fetch & parse)
- `Wikipedia:Sockpuppet investigations` — main SPI page with active cases

### Archive pattern
- `Wikipedia:Sockpuppet investigations/{Username}` — individual investigation pages
- `Wikipedia:Sockpuppet investigations/{Username}/Archive` — archived investigations

---

## 9. POLICY-SPECIFIC NOTICEBOARDS (Disputes Over Policy Application)

These noticeboards often contain disputes between editors about specific policy areas:

- `Wikipedia:Biographies of living persons/Noticeboard` — BLP disputes
- `Wikipedia:Conflict of interest/Noticeboard` — COI disputes
- `Wikipedia:Neutral point of view/Noticeboard` — NPOV disputes
- `Wikipedia:Fringe theories/Noticeboard` — fringe theory disputes
- `Wikipedia:No original research/Noticeboard` — original research disputes
- `Wikipedia:Reliable sources/Noticeboard` — source reliability disputes
- `Wikipedia:External links/Noticeboard` — external link disputes

---

## 10. UMBRELLA CATEGORIES

### Main dispute resolution category tree
- `Category:Wikipedia dispute resolution` — top-level (10 subcategories, 100 pages)
  - `Category:Wikipedia arbitration`
  - `Category:Dispute resolution noticeboard`
  - `Category:Wikipedia disputes` — 7 subcategories
  - `Category:Wikipedia edit warring`
  - `Category:Wikipedia mediation`
  - `Category:Wikipedia personal attacks` — 5 pages
  - `Category:Wikipedia reconciliation` — 3 subcategories, 1 page
  - `Category:Wikipedia requests for comment`
  - `Category:User essays on dispute resolution` — 20 pages
  - `Category:Wikipedia consensus-building templates`

---

## Data Access Strategy

### Category-based (use `get_category_pages`)
Best for: Arbitration cases, established dispute categories
```
client.get_category_pages("Category:Wikipedia arbitration cases")
```

### Page-based (fetch & parse wikitext)
Best for: Noticeboards with active/archived cases embedded in page content
```
page = client.get_page("Wikipedia:Dispute resolution noticeboard")
```

### Archive iteration (loop through numbered archives)
Best for: Historical data from DRN, ANI, AN/EW
```python
for i in range(1, 250):
    page = client.get_page(f"Wikipedia:Dispute resolution noticeboard/Archive {i}")
```

### Notes
- DRN archives: numbered 1–240+ (each contains ~10-20 cases)
- ANI archives: numbered 1–1100+ (IncidentArchive format, very large)
- Edit warring: uses legacy "3RR" naming for older archives
- RfCs: distributed across talk pages, aggregated via bot on subpages
- SPI: one subpage per investigated user
