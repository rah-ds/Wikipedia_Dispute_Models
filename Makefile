# Load .env file if it exists (provides RIVANNA_ID, WIKI_API_KEY, etc.)
-include .env
export

.PHONY: install install-dev clean data-dirs help lint fetch-all fetch-full fetch-arb fetch-drn fetch-small test test-unit test-cov fetch-venues fetch-ani fetch-talk fetch-arb-dfs fetch-arb-dfs-sample fetch-arb-dfs-sample-full fetch-arb-dfs-all fetch-arb-dfs-all-full update-arb-cases-list fetch-lifecycle fetch-lifecycle-dry fetch-lifecycle-sample fetch-lifecycle-all rivanna-setup rivanna-submit rivanna-status rivanna-ssh rivanna-sync rivanna-logs

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
	@echo "Phase 2 - Dispute Venues:"
	@echo "  fetch-venues ARTICLE=<title>  Fetch all dispute venues for article"
	@echo "  fetch-ani TERM=<term>         Search ANI archives for term"
	@echo "  fetch-talk ARTICLE=<title>    Fetch talk page revisions"
	@echo ""
	@echo "Arbitration Case DFS:"
	@echo "  fetch-arb-dfs CASE=<name>     DFS from arb case to all related pages"
	@echo "  fetch-arb-dfs-dry CASE=<name> Preview what fetch-arb-dfs would fetch"
	@echo "  fetch-arb-dfs-sample          Fetch 5 example arb cases with DFS (limited)"
	@echo "  fetch-arb-dfs-sample-full     Fetch 5 example arb cases with ALL pages"
	@echo "  fetch-arb-dfs-all             Fetch ALL arb cases (~481 cases from Wikipedia)"
	@echo "  fetch-arb-dfs-all-full        Fetch ALL arb cases with ALL pages (very long)"
	@echo "  update-arb-cases-list         Update artifacts/arb_cases.txt from Wikipedia"
	@echo ""
	@echo "Full Dispute Lifecycle (RECOMMENDED - captures all escalation stages):"
	@echo "  fetch-lifecycle CASE=<name>   Fetch full lifecycle: Talk→DRN→ANI→ArbCom"
	@echo "  fetch-lifecycle-dry CASE=<n>  Preview lifecycle fetch"
	@echo "  fetch-lifecycle-sample        Fetch 5 sample cases with full lifecycle"
	@echo "  fetch-lifecycle-all           Fetch ALL cases with full lifecycle"
	@echo ""
	@echo "Rivanna HPC (set RIVANNA_ID in .env):"
	@echo "  rivanna-ssh                   SSH into Rivanna"
	@echo "  rivanna-setup                 One-time setup on Rivanna (over SSH)"
	@echo "  rivanna-sync                  Rsync project to Rivanna"
	@echo "  rivanna-submit                Submit all SLURM jobs on Rivanna"
	@echo "  rivanna-status                Show job progress and data status"
	@echo "  rivanna-logs                  Tail recent SLURM logs from Rivanna"
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
	mkdir -p data/raw/dispute_venues
	mkdir -p data/raw/ani_search
	mkdir -p data/raw/talk_pages
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

# Phase 2: Dispute venue fetchers
# Usage: make fetch-venues ARTICLE="Article Title"
fetch-venues: data-dirs
ifndef ARTICLE
	@echo "Error: ARTICLE is required. Usage: make fetch-venues ARTICLE=\"Article Title\""
	@exit 1
endif
	uv run python scripts/fetch_all.py --venues "$(ARTICLE)"

# Usage: make fetch-ani TERM="search term"
fetch-ani: data-dirs
ifndef TERM
	@echo "Error: TERM is required. Usage: make fetch-ani TERM=\"search term\""
	@exit 1
endif
	uv run python scripts/fetch_all.py --ani "$(TERM)"

# Usage: make fetch-talk ARTICLE="Article Title"
fetch-talk: data-dirs
ifndef ARTICLE
	@echo "Error: ARTICLE is required. Usage: make fetch-talk ARTICLE=\"Article Title\""
	@exit 1
endif
	uv run python scripts/fetch_all.py --talk "$(ARTICLE)"

# Arbitration Case DFS: Depth-first search from a case to all related pages
# Usage: make fetch-arb-dfs CASE="Case Name"
fetch-arb-dfs: data-dirs
ifndef CASE
	@echo "Error: CASE is required. Usage: make fetch-arb-dfs CASE=\"Case Name\""
	@exit 1
endif
	uv run python scripts/fetch_arb_dfs.py "$(CASE)"

fetch-arb-dfs-dry: data-dirs
ifndef CASE
	@echo "Error: CASE is required. Usage: make fetch-arb-dfs-dry CASE=\"Case Name\""
	@exit 1
endif
	uv run python scripts/fetch_arb_dfs.py "$(CASE)" --dry-run

# Sample arbitration cases - fetch 5 notable cases with DFS
# Good examples spanning different topic areas and time periods
SAMPLE_ARB_CASES := "Climate change" "Gamergate" "Eastern Europe" "Scientology" "Muhammad images"

fetch-arb-dfs-sample: data-dirs
	@echo "Fetching 5 sample arbitration cases with DFS (limited)..."
	@echo "Cases: $(SAMPLE_ARB_CASES)"
	@echo ""
	@for case in $(SAMPLE_ARB_CASES); do \
		echo "========================================"; \
		echo "Fetching: $$case"; \
		echo "========================================"; \
		uv run python scripts/fetch_arb_dfs.py "$$case"; \
	done
	@echo ""
	@echo "✓ Sample arbitration cases fetched to data/raw/arbitration/"

# Full sample - fetch ALL pages for 5 sample arbitration cases (no limits)
fetch-arb-dfs-sample-full: data-dirs
	@echo "Fetching 5 sample arbitration cases with FULL DFS (all pages, all revisions)..."
	@echo "Cases: $(SAMPLE_ARB_CASES)"
	@echo "⚠️  This will take significantly longer - fetching ALL talk pages and ALL revisions"
	@echo ""
	@for case in $(SAMPLE_ARB_CASES); do \
		echo "========================================"; \
		echo "Fetching (FULL): $$case"; \
		echo "========================================"; \
		uv run python scripts/fetch_arb_dfs.py "$$case" --max-talk-pages 0 --revision-limit 0; \
	done
	@echo ""
	@echo "✓ FULL sample arbitration cases fetched to data/raw/arbitration/"

# Path to the list of all arbitration cases (fetched from Wikipedia category)
ARB_CASES_FILE := artifacts/arb_cases.txt

# Update the arbitration cases list from Wikipedia
update-arb-cases-list:
	@echo "Fetching arbitration cases list from Wikipedia..."
	uv run python scripts/fetch_arb_cases_list.py --output $(ARB_CASES_FILE)
	@echo "✓ Updated $(ARB_CASES_FILE)"

# Fetch all arbitration cases with default limits
# Cases are read from artifacts/arb_cases.txt (sourced from Wikipedia category)
fetch-arb-dfs-all: data-dirs
	@if [ ! -f $(ARB_CASES_FILE) ]; then \
		echo "Case list not found. Fetching from Wikipedia..."; \
		uv run python scripts/fetch_arb_cases_list.py --output $(ARB_CASES_FILE); \
	fi
	@total=$$(wc -l < $(ARB_CASES_FILE) | tr -d ' '); \
	echo "Fetching ALL arbitration cases with DFS..."; \
	echo "Total cases: $$total (from $(ARB_CASES_FILE))"; \
	echo "Source: https://en.wikipedia.org/wiki/Category:Wikipedia_arbitration_cases"; \
	echo "⚠️  This will take many hours. Use Ctrl+C to interrupt (progress is saved)."; \
	echo ""; \
	count=0; \
	while IFS= read -r case || [ -n "$$case" ]; do \
		count=$$((count + 1)); \
		echo ""; \
		echo "========================================"; \
		echo "[$$count/$$total] Fetching: $$case"; \
		echo "========================================"; \
		uv run python scripts/fetch_arb_dfs.py "$$case" || echo "⚠️  Failed: $$case (continuing...)"; \
	done < $(ARB_CASES_FILE)
	@echo ""
	@echo "✓ All arbitration cases fetched to data/raw/arbitration/"

# Fetch all arbitration cases with NO limits (full data)
fetch-arb-dfs-all-full: data-dirs
	@if [ ! -f $(ARB_CASES_FILE) ]; then \
		echo "Case list not found. Fetching from Wikipedia..."; \
		uv run python scripts/fetch_arb_cases_list.py --output $(ARB_CASES_FILE); \
	fi
	@total=$$(wc -l < $(ARB_CASES_FILE) | tr -d ' '); \
	echo "Fetching ALL arbitration cases with FULL DFS (all pages, all revisions)..."; \
	echo "Total cases: $$total (from $(ARB_CASES_FILE))"; \
	echo "Source: https://en.wikipedia.org/wiki/Category:Wikipedia_arbitration_cases"; \
	echo "⚠️  WARNING: This will take MANY hours. Fetching ALL pages and ALL revisions."; \
	echo ""; \
	count=0; \
	while IFS= read -r case || [ -n "$$case" ]; do \
		count=$$((count + 1)); \
		echo ""; \
		echo "========================================"; \
		echo "[$$count/$$total] Fetching (FULL): $$case"; \
		echo "========================================"; \
		uv run python scripts/fetch_arb_dfs.py "$$case" --max-articles 0 --revision-limit 0 || echo "⚠️  Failed: $$case (continuing...)"; \
	done < $(ARB_CASES_FILE)
	@echo ""
	@echo "✓ FULL arbitration cases fetched to data/raw/arbitration/"

# Clean generated files
clean:
	rm -rf data/raw/*
	rm -rf data/processed/*
	rm -rf artifacts/logs/*
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
# =============================================================================
# FULL DISPUTE LIFECYCLE FETCHER (RECOMMENDED)
# =============================================================================
# This is the correct way to study dispute escalation patterns.
# Collects data from ALL stages: Talk Pages → DRN → ANI → ArbCom
# See docs/wikipedia_dispute_resolution_lifecycle.md for the theory.

# Single case lifecycle fetch
# Usage: make fetch-lifecycle CASE="Climate change"
fetch-lifecycle: data-dirs
ifndef CASE
	@echo "Error: CASE is required. Usage: make fetch-lifecycle CASE=\"Case Name\""
	@exit 1
endif
	uv run python scripts/fetch_dispute_lifecycle.py "$(CASE)"

fetch-lifecycle-dry: data-dirs
ifndef CASE
	@echo "Error: CASE is required. Usage: make fetch-lifecycle-dry CASE=\"Case Name\""
	@exit 1
endif
	uv run python scripts/fetch_dispute_lifecycle.py "$(CASE)" --dry-run

# Fetch 5 sample cases with full lifecycle data
fetch-lifecycle-sample: data-dirs
	@echo "Fetching 5 sample cases with FULL DISPUTE LIFECYCLE..."
	@echo "Stages collected: Talk Pages → DRN → ANI → ArbCom"
	@echo "Cases: $(SAMPLE_ARB_CASES)"
	@echo ""
	@for case in $(SAMPLE_ARB_CASES); do \
		echo "========================================"; \
		echo "Fetching lifecycle: $$case"; \
		echo "========================================"; \
		uv run python scripts/fetch_dispute_lifecycle.py "$$case"; \
	done
	@echo ""
	@echo "✓ Sample lifecycle data saved to data/raw/dispute_venues/"

# Fetch ALL cases with full lifecycle
fetch-lifecycle-all: data-dirs
	@if [ ! -f $(ARB_CASES_FILE) ]; then \
		echo "Case list not found. Fetching from Wikipedia..."; \
		uv run python scripts/fetch_arb_cases_list.py --output $(ARB_CASES_FILE); \
	fi
	@total=$$(wc -l < $(ARB_CASES_FILE) | tr -d ' '); \
	echo "Fetching ALL cases with FULL DISPUTE LIFECYCLE..."; \
	echo "Stages: Talk Pages → DRN → ANI → ArbCom"; \
	echo "Total cases: $$total (from $(ARB_CASES_FILE))"; \
	echo "⚠️  This will take many hours. Use Ctrl+C to interrupt."; \
	echo ""; \
	count=0; \
	while IFS= read -r case || [ -n "$$case" ]; do \
		count=$$((count + 1)); \
		echo ""; \
		echo "========================================"; \
		echo "[$$count/$$total] Lifecycle: $$case"; \
		echo "========================================"; \
		uv run python scripts/fetch_dispute_lifecycle.py "$$case" || echo "⚠️  Failed: $$case (continuing...)"; \
	done < $(ARB_CASES_FILE)
	@echo ""
	@echo "✓ All lifecycle data saved to data/raw/dispute_venues/"

# =============================================================================
# RIVANNA HPC — SLURM job management
# =============================================================================
# Set RIVANNA_ID in .env (e.g., RIVANNA_ID=abc1de)
# All targets SSH into Rivanna to run commands remotely.

RIVANNA_HOST := $(RIVANNA_ID)@rivanna.hpc.virginia.edu
RIVANNA_PROJECT := ~/Wikipedia_Arbitration

# Validate RIVANNA_ID is set
_check-rivanna-id:
	@if [ -z "$(RIVANNA_ID)" ]; then \
		echo "Error: RIVANNA_ID not set. Add it to .env:"; \
		echo "  echo 'RIVANNA_ID=your_computing_id' >> .env"; \
		exit 1; \
	fi

# SSH into Rivanna
rivanna-ssh: _check-rivanna-id
	ssh $(RIVANNA_HOST)

# Rsync project files to Rivanna (excludes data, venv, cache)
rivanna-sync: _check-rivanna-id
	@echo "Syncing project to Rivanna ($(RIVANNA_HOST):$(RIVANNA_PROJECT))..."
	rsync -avz --progress \
		--exclude '.venv/' \
		--exclude '__pycache__/' \
		--exclude 'data/raw/' \
		--exclude 'data/processed/' \
		--exclude 'data/external/' \
		--exclude 'apicache/' \
		--exclude 'slurmlogs/*.out' \
		--exclude 'slurmlogs/*.err' \
		--exclude '.git/' \
		--exclude 'notebooks/' \
		./ $(RIVANNA_HOST):$(RIVANNA_PROJECT)/
	@echo "✓ Sync complete"

# One-time setup on Rivanna
rivanna-setup: _check-rivanna-id rivanna-sync
	@echo "Running setup on Rivanna..."
	ssh $(RIVANNA_HOST) 'cd $(RIVANNA_PROJECT) && bash scripts/slurm/setup_rivanna.sh'

# Submit all SLURM jobs
rivanna-submit: _check-rivanna-id
	@echo "Submitting SLURM jobs on Rivanna..."
	ssh $(RIVANNA_HOST) 'cd $(RIVANNA_PROJECT) && bash scripts/slurm/submit_all.sh'

# Show job progress and data collection status
rivanna-status: _check-rivanna-id
	@ssh $(RIVANNA_HOST) 'cd $(RIVANNA_PROJECT) && bash scripts/slurm/status.sh'

# Show compact status
rivanna-status-short: _check-rivanna-id
	@ssh $(RIVANNA_HOST) 'cd $(RIVANNA_PROJECT) && bash scripts/slurm/status.sh --short'

# Tail recent SLURM output logs
rivanna-logs: _check-rivanna-id
	@echo "Most recent SLURM log files:"
	@ssh $(RIVANNA_HOST) 'cd $(RIVANNA_PROJECT) && \
		echo "" && \
		echo "=== Recent .out files ===" && \
		ls -lt slurmlogs/*.out 2>/dev/null | head -10 && \
		echo "" && \
		echo "=== Last 30 lines of most recent log ===" && \
		tail -30 $$(ls -t slurmlogs/*.out 2>/dev/null | head -1) 2>/dev/null || echo "No logs yet."'
