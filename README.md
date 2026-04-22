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
├── final_paper/          # IEEE paper sources synced with Overleaf
├── notebooks/            # Exploratory analysis
├── scripts/              # Data collection scripts
├── src/                  # Source code
└── artifacts/            # Model outputs and logs
```

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/rah-ds/Wikipedia_Dispute_Models.git
cd Wikipedia_Dispute_Models
make install-dev

# Fetch data
make fetch-arb
make fetch-drn
```

See `make help` for all available targets.

## Final Paper / Overleaf Sync

The `RH_4_6/final_paper` branch keeps the paper source in `final_paper/` so collaborators can review it on GitHub, while `scripts/final_paper_overleaf_sync.sh` handles pull/push sync with the existing Overleaf Git project.

```bash
make paper-overleaf-status
make paper-overleaf-diff
make paper-overleaf-pull
make paper-overleaf-push
```

See `docs/final_paper_overleaf_sync.md` for the workflow and the Overleaf-specific constraints behind it.

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

## Core Analysis Modules

| Module | Description |
| ------ | ----------- |
| `src/arbitration.py` | Data models for arbitration cases. Parses case JSON into `ArbitrationCaseSummary` objects with editor profiles, conflict networks, and revision timelines. |
| `src/outcome.py` | Parses ArbCom proposed/final decision wikitext to extract structured votes, findings, and remedies with pass/fail status. |
| `src/lifecycle.py` | Traces disputes through all resolution stages (Talk → DRN → ANI → ArbCom). Extracts participants and disputed articles. |
| `src/analysis.py` | Edit war detection, revert analysis, and 3RR violation detection from revision histories. |
| `src/timeline.py` | Constructs chronological dispute timelines with escalation features for modeling. |
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
