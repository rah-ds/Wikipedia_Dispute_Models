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

# Fetch sample data (high + low conflict articles)
make fetch-small

# Or fetch specific data types
make fetch-arb   # Arbitration cases
make fetch-drn   # DRN cases
```

See `make help` for all available targets.

See [`docs/sample_article_selection.md`](docs/sample_article_selection.md) for article selection rationale.


when running with a mac use caffeinate to prevent sleep:

```bash
caffeinate -i make fetch-full
```

---

## Data Sources

| Source | Description |
| ------ | ----------- |
| Arbitration Cases | Binding decisions from ArbCom |
| Revision History | Edit history with timestamps, users, comments |
| Edit Wars | Pages with high revert activity |
| DRN Cases | Dispute Resolution Noticeboard threads |

All data collection runs through `scripts/fetch_all.py` or `scripts/fetch_from_config.py`.

See [`docs/wikimedia_api.md`](docs/wikimedia_api.md) for API documentation.

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
