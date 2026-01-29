<<<<<<< Updated upstream
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
# Clone and install
git clone https://github.com/rah-ds/Wikipedia_Dispute_Models.git
cd Wikipedia_Dispute_Models
make install-dev

# Fetch data
make fetch-arb
make fetch-drn
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

| Source | Description | Script |
| ------ | ----------- | ------ |
| Arbitration Cases | Binding decisions from ArbCom | `fetch_arbitration_cases.py` |
| Revision History | Edit history with timestamps, users, comments | `fetch_revisions.py` |
| Edit Wars | Pages with high revert activity | `detect_edit_wars.py` |
| DRN Cases | Dispute Resolution Noticeboard threads | `fetch_drn_cases.py` |

See [`docs/wikimedia_api.md`](docs/wikimedia_api.md) for full API documentation.

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
=======
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
# Clone and install
git clone https://github.com/rah-ds/Wikipedia_Dispute_Models.git
cd Wikipedia_Dispute_Models
make install-dev

# Fetch data
make fetch-arb
make fetch-drn
```

See `make help` for all available targets.


---

## Data Sources

| Source | Description | Script |
| ------ | ----------- | ------ |
| Arbitration Cases | Binding decisions from ArbCom | `fetch_arbitration_cases.py` |
| Revision History | Edit history with timestamps, users, comments | `fetch_revisions.py` |
| Edit Wars | Pages with high revert activity | `detect_edit_wars.py` |
| DRN Cases | Dispute Resolution Noticeboard threads | `fetch_drn_cases.py` |

See [`docs/wikimedia_api.md`](docs/wikimedia_api.md) for full API documentation.

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
>>>>>>> Stashed changes
