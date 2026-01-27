.PHONY: install install-dev clean data-dirs help lint fetch-all fetch-arb fetch-drn fetch-small test test-unit test-cov

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
	@echo "  fetch-all    Run all data collectors"
	@echo "  fetch-small  Fetch small sample dataset for testing"
	@echo "  fetch-arb    Fetch arbitration cases"
	@echo "  fetch-drn    Fetch DRN cases"
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

# Sample dataset with balanced high/low conflict articles
# See docs/sample_article_selection.md for rationale
fetch-small: data-dirs
	@echo "Fetching sample dataset (high + low conflict articles)..."
	@echo "See docs/sample_article_selection.md for selection rationale"
	@echo ""
	@echo "=== Arbitration Cases (5) ==="
	uv run python scripts/fetch_all.py --arb --limit 5
	@echo ""
	@echo "=== DRN Cases ==="
	uv run python scripts/fetch_all.py --drn
	@echo ""
	@echo "=== High-Conflict Articles (revisions) ==="
	uv run python scripts/fetch_all.py --revisions "Climate change" --limit 500
	uv run python scripts/fetch_all.py --revisions "Donald Trump" --limit 500
	uv run python scripts/fetch_all.py --revisions "Israeli–Palestinian conflict" --limit 500
	uv run python scripts/fetch_all.py --revisions "Abortion" --limit 500
	uv run python scripts/fetch_all.py --revisions "COVID-19 pandemic" --limit 500
	@echo ""
	@echo "=== Low-Conflict Articles (control group) ==="
	uv run python scripts/fetch_all.py --revisions "Speed of light" --limit 500
	uv run python scripts/fetch_all.py --revisions "Pythagorean theorem" --limit 500
	uv run python scripts/fetch_all.py --revisions "Mount Everest" --limit 500
	uv run python scripts/fetch_all.py --revisions "Photosynthesis" --limit 500
	uv run python scripts/fetch_all.py --revisions "Mona Lisa" --limit 500
	@echo ""
	@echo "=== Edit War Analysis (high-conflict) ==="
	uv run python scripts/fetch_all.py --editwar "Climate change"
	uv run python scripts/fetch_all.py --editwar "Donald Trump"
	uv run python scripts/fetch_all.py --editwar "Israeli–Palestinian conflict"
	uv run python scripts/fetch_all.py --editwar "Abortion"
	uv run python scripts/fetch_all.py --editwar "COVID-19 pandemic"
	@echo ""
	@echo "=== Edit War Analysis (low-conflict control) ==="
	uv run python scripts/fetch_all.py --editwar "Speed of light"
	uv run python scripts/fetch_all.py --editwar "Pythagorean theorem"
	uv run python scripts/fetch_all.py --editwar "Mount Everest"
	uv run python scripts/fetch_all.py --editwar "Photosynthesis"
	uv run python scripts/fetch_all.py --editwar "Mona Lisa"
	@echo ""
	@echo "✓ Sample dataset complete!"

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
