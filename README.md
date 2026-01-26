# Wikipedia Dispute Models

Capstone for UVA MSDS 2026

## Project Description

This project aims to analyze and model dispute patterns in Wikipedia articles using machine learning techniques.

## Team Members

- [Add team member 1]
- [Add team member 2]
- [Add team member 3]
- [Add team member 4]

## Project Structure

```
.
├── data/               # Data files (not committed to git)
│   ├── raw/           # Original, immutable data
│   ├── processed/     # Cleaned, transformed data
│   └── external/      # External data sources
├── notebooks/         # Jupyter notebooks for exploration
├── src/               # Source code for the project
├── tests/             # Unit tests
├── docs/              # Documentation
├── results/           # Model outputs, figures, etc.
├── requirements.txt   # Python dependencies
└── environment.yml    # Conda environment file
```

## Getting Started

### Prerequisites

- Python 3.11+
- pip or conda

### Installation

#### Using pip

```bash
# Clone the repository
git clone https://github.com/rah-ds/Wikipedia_Dispute_Models.git
cd Wikipedia_Dispute_Models

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### Using conda

```bash
# Clone the repository
git clone https://github.com/rah-ds/Wikipedia_Dispute_Models.git
cd Wikipedia_Dispute_Models

# Create conda environment
conda env create -f environment.yml
conda activate wikipedia-disputes
```

### Configuration

1. Copy `.env.example` to `.env`
2. Fill in any necessary API keys or configuration values

## Usage

[Add usage instructions here as the project develops]

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

[Add linting/formatting guidelines if applicable]

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for collaboration guidelines.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- University of Virginia MSDS Program
- [Add any data sources, tools, or references]

