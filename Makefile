.PHONY: install install-dev clean data-dirs help lint fetch-all fetch-full fetch-arb fetch-drn fetch-small test test-unit test-cov

# Default target
help:
	@echo "Wikipedia Dispute Models"
	@echo "========================"
	@echo ""
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@echo "  install      Install base dependencies"
	@echo "  install-dev  Install with dev dependencies + pre-commit hooks"
	@echo "  lint         Run ruff linter and formatter"
	@echo "  test         Run all tests"
	@echo "  test-unit    Run unit tests only (no network)"
	@echo "  test-cov     Run tests with coverage"
	@echo "  data-dirs    Create data directory structure"
	@echo "  clean        Remove generated files"
	@echo ""
	@echo "Data Collection:"
	@echo "  fetch-small     Fetch sample dataset (10 articles, 5 arb cases)"
	@echo "  fetch-small-dry Preview what fetch-small would fetch"
	@echo "  fetch-full      Fetch full dataset (51 articles, 50 arb cases, 2-4 hrs)"
	@echo "  fetch-full-dry  Preview what fetch-full would fetch"
	@echo "  fetch-all       Run arb + drn collectors only (no articles)"
	@echo "  fetch-arb       Fetch arbitration cases only"
	@echo "  fetch-drn       Fetch DRN cases only"
	@echo ""

# Installation
install:
	uv pip install -e .

install-dev:
	uv pip install -e ".[dev]"
	pre-commit install

# Alternative: pip install
pip-install:
	pip install -e .

pip-install-dev:
	pip install -e ".[dev]"
	pre-commit install

# Linting
lint:
	uv run ruff check --fix .
	uv run ruff format .

# Testing
test:
	uv run pytest tests/ -v

test-unit:
	uv run pytest tests/ -v -m "not integration"

test-cov:
	uv run pytest tests/ -v --cov=src --cov-report=term-missing

# Create data directories
data-dirs:
	mkdir -p data/raw/arbitration
	mkdir -p data/raw/revisions
	mkdir -p data/raw/edit_wars
	mkdir -p data/raw/drn
	mkdir -p data/processed
	mkdir -p data/external
	mkdir -p artifacts/models
	mkdir -p artifacts/logs/data_pull

# Data collection targets
fetch-all: data-dirs
	uv run python scripts/fetch_all.py --all

# Sample dataset from YAML config
# Edit artifacts/sample_articles.yaml to customize article selection
fetch-small: data-dirs
	@echo "Fetching sample dataset from artifacts/sample_articles.yaml"
	@echo "Edit the YAML file to customize article selection"
	@echo ""
	uv run python scripts/fetch_from_config.py

fetch-small-dry: data-dirs
	uv run python scripts/fetch_from_config.py --dry-run

# Full dataset from YAML config (51 articles, 50 arb cases)
# Edit artifacts/full_articles.yaml to customize
fetch-full: data-dirs
	@echo "Fetching FULL dataset from artifacts/full_articles.yaml"
	@echo "This will take 2-4 hours. Use Ctrl+C to interrupt (progress is saved)."
	@echo ""
	uv run python scripts/fetch_from_config.py --config artifacts/full_articles.yaml

fetch-full-dry: data-dirs
	uv run python scripts/fetch_from_config.py --config artifacts/full_articles.yaml --dry-run

fetch-arb: data-dirs
	uv run python scripts/fetch_all.py --arb

fetch-drn: data-dirs
	uv run python scripts/fetch_all.py --drn

# Clean generated files
clean:
	rm -rf data/raw/*
	rm -rf data/processed/*
	rm -rf artifacts/logs/*
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
