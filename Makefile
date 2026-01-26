.PHONY: install install-dev clean data-dirs help lint fetch-all fetch-arb fetch-drn test test-unit test-cov

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
	ruff check --fix .
	ruff format .

# Testing
test:
	pytest tests/ -v

test-unit:
	pytest tests/ -v -m "not integration"

test-cov:
	pytest tests/ -v --cov=src --cov-report=term-missing

# Create data directories
data-dirs:
	mkdir -p data/raw/arbitration
	mkdir -p data/raw/revisions
	mkdir -p data/raw/edit_wars
	mkdir -p data/raw/drn
	mkdir -p data/processed
	mkdir -p data/external
	mkdir -p artifacts/models
	mkdir -p artifacts/logs

# Data collection targets
fetch-all: data-dirs
	python scripts/fetch_all.py --all

fetch-arb: data-dirs
	python scripts/fetch_all.py --arb

fetch-drn: data-dirs
	python scripts/fetch_all.py --drn

# Clean generated files
clean:
	rm -rf data/raw/*
	rm -rf data/processed/*
	rm -rf artifacts/logs/*
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
