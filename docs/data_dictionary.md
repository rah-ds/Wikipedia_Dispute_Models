# Data Dictionary

This document defines the repository terms used in the README and handoff
notes. It focuses on the handoff artifacts rather than every field in every
JSON file.

## Coverage terms

| Term | Definition |
| --- | --- |
| Canonical ArbCom case | A unique case name listed in `artifacts/arb_cases.txt` |
| Raw per-case JSON record | A JSON file in `data/raw/arbitration/` for one canonical case |
| Usable arbitration/lifecycle record | A raw record with at least one ArbCom page, at least one collected revision, and at least one observed lifecycle stage |
| Zero-data record | A raw record that exists but has no usable ArbCom pages/revisions/lifecycle data |
| D3 JSON file | A JSON file in `data/processed/d3/`; this directory includes per-case payloads and `manifest.json` |
| Per-case D3 payload | A D3-ready JSON export for one case, named `data/processed/d3/<slug>.json` |
| D3 manifest | `data/processed/d3/manifest.json`, the export audit file written by `scripts/export_d3_all.py` |
| Dashboard overview payload | `dashboard/public/data/dashboard_data.json`, used by the React Arbitration Overview tab |
| Feature table | `data/processed/features.csv` or `features.parquet`, rebuilt by `scripts/build_features.py` |

## Current handoff counts

| Measure | Count | Meaning |
| --- | ---: | --- |
| Canonical ArbCom cases | 481 | Unique names in `artifacts/arb_cases.txt` |
| Raw per-case JSON records | 481 | One raw file exists for every listed case |
| Usable raw records | 472 | Records with ArbCom pages, revisions, and lifecycle-stage data |
| Zero-data records | 9 | Raw files exist but do not yet support analysis |
| JSON files in `data/processed/d3/` | 466 | Includes `manifest.json`; not all are per-case payloads |
| Successful per-case D3 exports in current manifest | 465 | `cases_with_data` in `data/processed/d3/manifest.json` |
| Skipped/no-data D3 exports in current manifest | 16 | `cases_no_data` in `data/processed/d3/manifest.json` |

## `lifecycle_stages_with_data`

`lifecycle_stages_with_data` is a summary count on a raw arbitration case
record. It counts how many lifecycle stage buckets contain collected data for
that case. In the current representation the relevant buckets are drawn from:

- Talk-page activity
- DRN references or records
- ANI references or records
- ArbCom pages

This value measures what the collector observed. It should not be interpreted
as proof that a real dispute skipped earlier venues. Older Talk, RfC, DRN, and
ANI records can be difficult to match retrospectively because archives and page
names changed over time.

## Raw JSON vs processed outputs

### Raw arbitration JSON

Location: `data/raw/arbitration/`

Raw records preserve fetched public Wikimedia data and case summaries. They are
the source of truth for coverage audits. At handoff, use per-case JSON files in
this directory for counts rather than aggregate files.

### D3 payloads

Location: `data/processed/d3/`

D3 payloads are visualization exports derived from raw/enriched case records.
The directory includes one `manifest.json` plus successful per-case payloads.
The manifest records both successful and failed/skipped exports.

### Dashboard overview data

Location: `dashboard/public/data/dashboard_data.json`

This payload feeds the React dashboard overview charts. It is a presentation
artifact, not the canonical source for coverage.

### Feature tables

Location: `data/processed/features.csv` and `data/processed/features.parquet`

These tables are modeling-oriented outputs rebuilt by `scripts/build_features.py`.
The builder prioritizes enriched arbitration JSON, then falls back to older
Arb-DFS or lifecycle-only records when necessary.

## Aggregate files to treat carefully

Do not use aggregate arbitration JSON files for final coverage counts unless
you first inspect their contents. During the project, some aggregate files were
intermediate samples, empty outputs, or Git LFS placeholders. The safer
coverage source is:

1. `artifacts/arb_cases.txt` for the canonical list.
2. Per-case files in `data/raw/arbitration/` for raw coverage.
3. `data/processed/d3/manifest.json` for D3 export coverage.

## Practical checks

```bash
# Count canonical cases.
grep -v '^[[:space:]]*$' artifacts/arb_cases.txt | grep -v '^#' | wc -l

# Count raw per-case files, excluding aggregate files.
find data/raw/arbitration -maxdepth 1 -name '*.json' ! -name 'arbitration_cases*' | wc -l

# Inspect D3 export status.
python3 - <<'PY'
import json
from pathlib import Path
m = json.loads(Path("data/processed/d3/manifest.json").read_text())
print(m["total_cases"], m["cases_with_data"], m["cases_no_data"])
PY
```
