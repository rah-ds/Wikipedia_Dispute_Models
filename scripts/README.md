# Scripts

This directory contains the main CLI for data collection.

## fetch_all.py

Unified CLI for Wikipedia dispute data collection. All data fetching logic
is consolidated in `src/fetchers.py`.

### Usage

```bash
# Run all collectors (arbitration + DRN)
uv run python scripts/fetch_all.py

# Specific collectors
uv run python scripts/fetch_all.py --arb              # Arbitration cases only
uv run python scripts/fetch_all.py --drn              # DRN cases only
uv run python scripts/fetch_all.py --revisions "Title" # Revisions for article
uv run python scripts/fetch_all.py --editwar "Title"  # Edit war analysis

# Options
--limit N       # Limit number of cases/revisions (default: 50)
--threshold X   # Edit war revert ratio threshold (default: 0.1)
--dry-run       # Preview without making API calls
```

### Output

Data is saved to `data/raw/{type}/{prefix}_{timestamp}.json`.
Logs go to `artifacts/logs/data_pull/`.


* [rivanna how to ](https://github.com/JustUnoptimized/ds6050-rivanna.git)
