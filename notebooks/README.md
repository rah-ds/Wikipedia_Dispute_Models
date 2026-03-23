# Notebooks Directory

Jupyter notebooks for exploratory analysis and model development.

## Current Notebooks

| Notebook | Description |
|----------|-------------|
| `eda_arbitration_cases.ipynb` | Explore ArbCom case data: topics, temporal patterns, participants |
| `eda_edit_wars.ipynb` | Analyze edit war patterns: reverts, 3RR violations, user conflicts |

## Data Requirements

Run `make fetch-small` before using these notebooks to collect sample data.

See [docs/sample_article_selection.md](../docs/sample_article_selection.md) for article selection rationale.

## Naming Convention

Name notebooks with sequential numbering and descriptive titles:

- `01_data_exploration.ipynb`
- `02_feature_engineering.ipynb`
- `03_model_training.ipynb`
- `04_evaluation.ipynb`

Prefix with initials for collaborative work:

- `01_jd_data_exploration.ipynb` (John Doe)
- `02_as_feature_engineering.ipynb` (Alice Smith)
