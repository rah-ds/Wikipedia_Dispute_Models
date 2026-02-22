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

## Quick Start

```bash
# Clone and setup
git clone https://github.com/rah-ds/Wikipedia_Dispute_Models.git
cd Wikipedia_Dispute_Models
make setup

# Configure credentials
cp .env.example .env
# Edit .env and add your Wikipedia access token

# Validate environment
make validate

# Fetch sample data (5 cases, resumable)
make pull

# Fetch full data (all cases, resumable)
make pull CONFIG=full
```

### Three Main Commands

| Command | Description |
| ------- | ----------- |
| `make setup` | Install dependencies and create directories |
| `make test` | Run all tests |
| `make pull` | Fetch data (resumable, configurable) |

### Pull Options

```bash
make pull                    # Sample config (5 cases)
make pull CONFIG=full        # Full data (all cases)
make pull CONFIG=dev         # Minimal for testing
make pull-status             # Show current progress
make pull-reset              # Reset state for fresh start
```

See `make help` for all available targets.

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

See [`docs/wikimedia_api.md`](docs/wikimedia_api.md) for full API documentation.

---

## Core Modules

| Module | Description |
| ------ | ----------- |
| `src/wiki.py` | WikiClient - low-level API wrapper with rate limiting |
| `src/fetchers.py` | High-level fetch functions (cases, revisions, ANI, DRN) |
| `src/lifecycle.py` | Dispute lifecycle tracing (Talk → DRN → ANI → ArbCom) |
| `src/arbitration.py` | Case data models (ArbitrationCaseSummary, EditorProfile) |
| `src/outcome.py` | Decision parsing (votes, findings, remedies) |
| `src/analysis.py` | Edit war detection, revert analysis |
| `src/logging_config.py` | Centralized logging with progress tracking |
| `src/network.py` | Network resilience (circuit breaker, retry) |
| `src/pull_config.py` | Data pull configuration (sample, full, custom) |
| `src/pull_state.py` | Resumable state management |

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
