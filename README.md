# Wikipedia Dispute Models

![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![UVA MSDS](https://img.shields.io/badge/UVA-MSDS-232D4B?style=flat&labelColor=E57200)](https://datascience.virginia.edu/)



This project maps and analyzes Wikipedia's dispute resolution system—tracking how content and conduct conflicts emerge, escalate, and resolve across the platform's five-stage intervention framework.

---

## Project Structure

```bash
├── data/
│   ├── raw/              # Raw API responses
│   ├── processed/        # Cleaned datasets
│   └── external/         # Third-party data
├── docs/                 # Documentation
├── notebooks/            # Exploratory analysis
├── scripts/              # Data collection scripts
├── src/                  # Source code
└── artifacts/            # Model outputs and logs
```

---

## Prerequisites

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js 18+** — only required to run the React dashboard
- A [Wikimedia API token](https://api.wikimedia.org/wiki/Authentication) — optional but strongly recommended (raises rate limit from 500 to 5,000 req/hr)

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/rah-ds/Wikipedia_Dispute_Models.git
cd Wikipedia_Dispute_Models
make setup          # install deps + validate environment

# (Optional) set your Wikimedia token
cp .env.example .env  # then fill in WIKI_API_KEY / WIKIPEDIA_ACCESS_TOKEN

# Fetch a small sample dataset (5 arbitration cases, resumable)
make pull
```

See `make help` for all available targets.

## Data Pulling

The unified data pull runner is the recommended entrypoint for fetching project data.

```bash
python scripts/pull.py --config sample
python scripts/pull.py --config full
python scripts/pull.py --dry-run
python scripts/pull.py --status
python scripts/pull.py --reset
python scripts/pull.py --validate
python scripts/pull.py --skip-validation --skip-speed-test
```

`pull.py` supports the config presets `sample`, `full`, and `dev`, or a custom config file path.

## Data Cleaning

Clean raw arbitration case JSON into processed case files:

```bash
python scripts/clean_arbitration_cases_data.py
```

This interactive script reads from `data/raw/arbitration` and writes cleaned output to `data/processed/clean_arbitration_cases_*.json`.

### Dashboard data

Build the dashboard payload used by the React app:

```bash
python scripts/process_arbitration_for_dashboard.py
```

This writes `dashboard_data.json` to both `data/processed/` and `dashboard/public/data/`, which is required for `dashboard` dev and preview servers.

## BPMN Generation

Generate BPMN diagrams from saved case data.

- Arbitration cases:
  ```bash
  python scripts/bpmn_from_arb.py --input data/raw/arb/ --output artifacts/bpmn/arb/ --max-cases 20
  ```
- Requests for Comments cases:
  ```bash
  python scripts/bpmn_from_rfc.py --input data/raw/rfc/ --output artifacts/bpmn/rfc/ --max-cases 20
  ```
- DRN cases (interactive):
  ```bash
  python scripts/bpmn_from_drn.py
  ```

### Comparative BPMN with Hugging Face

Generate ArbCom BPMN using the Hugging Face NER model:

```bash
python scripts/arbitration_bpmn_hf.py --case "Wikipedia:Requests_for_arbitration/-Ril-"
python scripts/arbitration_bpmn_hf.py --aggregate
python scripts/arbitration_bpmn_hf.py --aggregate --sample 50
python scripts/arbitration_bpmn_hf.py --output-dir artifacts/bpmn/arb
python scripts/arbitration_bpmn_hf.py --no-ner
```

The default output directory is `artifacts/bpmn/arb`.

---

## Testing

```bash
make test           # run full test suite
make test-unit      # unit tests only (no network calls)
make test-cov       # coverage report
```

The test suite lives in `tests/` and covers arbitration parsing, graph construction, outcome extraction, lifecycle tracing, and integration paths.

---

## Running the Dashboard

```bash
# Build the data payload first
python scripts/process_arbitration_for_dashboard.py

# Start the dev server
cd dashboard
npm install
npm run dev
```

The dashboard reads from `dashboard/public/data/dashboard_data.json`. BPMN diagrams in `dashboard/public/bpmn/` are served statically and browsable in the **BPMN Viewer** screen.
Standalone D3 exports in `dashboard/public/d3/` are available inside the dashboard's **D3 Visuals** tab.

---

## Rivanna HPC (UVA)

Large-scale data collection runs on UVA's Rivanna cluster. Requires an SSH key configured for `login.hpc.virginia.edu` and `RIVANNA_ID` set in `.env`.

```bash
make rivanna-sync    # rsync source code to /scratch/<id>/Wikipedia_Dispute_Models
make rivanna-setup   # one-time: install uv + deps on Rivanna, smoke test imports
make rivanna-submit  # submit the full SLURM job pipeline
make rivanna-status  # check running jobs and data collection progress
make rivanna-logs    # tail the 5 most recent SLURM log files
make rivanna-pull    # download collected data/raw, data/processed, slurmlogs
make rivanna-clean   # (destructive) cancel jobs and clear remote data/raw
```

### SLURM Pipeline (`scripts/slurm/`)

Five-stage dependency-ordered pipeline:

| Job | Script | Wall Time | Memory |
|-----|--------|-----------|--------|
| 1 — Update case list | `update_arb_cases.slurm` | 15 min | 2 GB |
| 2 — Full article fetch | `fetch_full.slurm` | 4 hrs | 8 GB |
| 3 — Arb DFS (array) | `fetch_arb_dfs.slurm` | 2 hrs/case | 8 GB |
| 4 — Lifecycle (array) | `fetch_lifecycle.slurm` | 3 hrs/case | 8 GB |
| 5 — Summary email | `pipeline_summary.slurm` | — | — |

Progress is logged to `slurmlogs/progress_*.csv` with quarter-milestone email alerts. See [`docs/rivanna_guide.md`](docs/rivanna_guide.md) for full setup.

---

## Windows Start with WSL
If you are working with Windows, follow here for WSL-friendly setup.
First download WSL via your preferred IDE.
Next this should get you uv installed via bash.
```bash
wget -qO- https://astral.sh/uv/install.sh | sh
```
Move/Copy repo to Linux filesystem to avoid /mnt/c/... (OneDrive/Windows FS causes permissions issues). You can find the wsl location with ```\\wsl$``` in your file explorer.
Once the repo is in the wsl directory, create a WSL terminal and navigate to the repo then run:
```bash
uv venv
make install-dev
```
Run Python/tools via uv & no need to manually activate venv — uv handles it.


---

## Data Sources

| Source | Description | Module / Script |
| ------ | ----------- | --------------- |
| Arbitration Cases | Binding decisions from ArbCom | `src/fetchers.py` → `fetch_arbitration_cases()` |
| Revision History | Edit history with timestamps, users, comments | `src/fetchers.py` → `fetch_revisions()` |
| Edit Wars | Pages with high revert activity | `scripts/detect_edit_wars.py` |
| DRN Cases | Dispute Resolution Noticeboard threads | `src/fetchers.py` → `fetch_drn_page()` |
| Dispute Lifecycle | Full escalation path: Talk → DRN → ANI → ArbCom | `scripts/fetch_dispute_lifecycle.py` |
| Arb Case DFS | Depth-first collection of all related pages | `scripts/fetch_arb_dfs.py` |
| Requests for Comments | RFC threads on Meta-Wikipedia | `scripts/fetch_rfc.py` |
| Declined RFAs | Failed requests for adminship | `scripts/fetch_declined_rfas.py` |
| Page Views | Wikimedia pageview statistics | `src/pageviews.py` |

See [`docs/wikimedia_api.md`](docs/wikimedia_api.md) for full API documentation.

---

## Core Analysis Modules

| Module | Description |
| ------ | ----------- |
| `src/arbitration.py` | Data models for arbitration cases. Parses case JSON into `ArbitrationCaseSummary` objects with editor profiles, conflict networks, and revision timelines. |
| `src/outcome.py` | Parses ArbCom proposed/final decision wikitext to extract structured votes, findings, and remedies with pass/fail status. |
| `src/lifecycle.py` | Traces disputes through all resolution stages (Talk → DRN → ANI → ArbCom). Extracts participants and disputed articles. |
| `src/analysis.py` | Edit war detection, revert analysis, and 3RR violation detection from revision histories. |
| `src/timeline.py` | Constructs chronological dispute timelines with escalation features for modeling. |
| `src/graph.py` | NetworkX `MultiDiGraph` builder with editor, article, and case nodes; `REVERTS`, `EDITS_CASE`, and `CO_OCCURS` edges. |
| `src/network.py` | Graph analysis utilities: centrality, community detection, co-occurrence summaries. |
| `src/ores.py` | ORES (Wikimedia ML) integration for edit quality and damage scoring. |
| `src/models.py` | Shared Pydantic/dataclass models for cases, revisions, and participants. |
| `src/evidence.py` | Evidence diff extraction and enrichment from ArbCom case pages. |
| `src/pageviews.py` | Wikimedia pageview API client for article traffic data. |
| `src/xtools.py` | XTools API client for editor statistics and contribution summaries. |
| `src/pull_config.py` | YAML config management for `pull.py` presets (`sample`, `full`, `dev`). |
| `src/pull_state.py` | JSON state persistence enabling resumable multi-hour data pulls. |
| `src/credentials.py` | API credential loading, validation, and warnings. |
| `src/wiki.py` | Wikipedia API client wrapper with rate limiting, retry logic, and OAuth support. |
| `src/cli_utils.py` | CLI utilities for graceful shutdown handling and memory monitoring in data fetch scripts. |

---

## Dispute Resolution Lifecycle

Wikipedia employs graduated intervention for conflicts:

```text
Talk Page → Third Opinion/RFC → DRN → ANI → Arbitration
```

Content disputes and conduct disputes follow distinct pathways. See [`docs/wikipedia_dispute_resolution_lifecycle.md`](docs/wikipedia_dispute_resolution_lifecycle.md) for the complete mapping.

---

## Important Links

- [Capstone Class Repo](https://github.com/UVADS/ds6015/)
- [Lexipedia Capstone Group Repo](statics.teams.cdn.office.net/evergreen-assets/safelinks/2/atp-safelinks.html)
- [MediaWiki API Documentation](https://www.mediawiki.org/wiki/API:Main_page)
- [Pywikibot Manual](https://www.mediawiki.org/wiki/Manual:Pywikibot)

---

## Development Team

| Role | Name |
| ---- | ---- |
| Authors | Ryan, Louis, Katherine |
| Advisor | Professor Alvarado |
| Project Sponsor | Lexipedia and Wikimedia |
| Domain Expert | Lane |
| Domain Expert | Anson (Lexipedia) |
