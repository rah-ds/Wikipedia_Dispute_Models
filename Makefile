.PHONY: install install-dev clean data-dirs help lint fetch-all fetch-full fetch-arb fetch-drn fetch-small test test-unit test-cov fetch-venues fetch-ani fetch-talk fetch-arb-dfs fetch-arb-dfs-sample fetch-arb-dfs-sample-full fetch-arb-dfs-all fetch-arb-dfs-all-full update-arb-cases-list fetch-lifecycle fetch-lifecycle-dry fetch-lifecycle-sample fetch-lifecycle-all setup pull pull-status pull-reset validate archive clear-results pull-full-arb pull-full-arb-estimate pull-full-arb-force rivanna-sync rivanna-setup rivanna-submit rivanna-status rivanna-logs rivanna-pull rivanna-clean rivanna-ssh rivanna-train enrich-diffs enrich-diffs-dry fetch-declined fetch-declined-dry build-features fetch-missing viz-export viz-update viz-serve dashboard dashboard-build

# =============================================================================
# QUICK START - Three simple commands to get started
# =============================================================================
# make setup  - Install dependencies and validate environment
# make test   - Run tests
# make pull   - Fetch data (resumable, uses sample config by default)
# =============================================================================

# ANSI color codes
BOLD    := \033[1m
RESET   := \033[0m
CYAN    := \033[36m
GREEN   := \033[32m
YELLOW  := \033[33m
MAGENTA := \033[35m
DIM     := \033[2m

# Default target
help:
	@printf "\n"
	@printf "$(BOLD)$(CYAN)  Wikipedia Dispute Models$(RESET)\n"
	@printf "$(DIM)  ════════════════════════$(RESET)\n"
	@printf "\n"
	@printf "$(BOLD)$(GREEN)  Quick Start$(RESET) $(DIM)(recommended)$(RESET)\n"
	@printf "    $(CYAN)make setup$(RESET)       Set up environment (install + validate)\n"
	@printf "    $(CYAN)make test$(RESET)        Run all tests\n"
	@printf "    $(CYAN)make pull$(RESET)        Fetch data (resumable, sample config)\n"
	@printf "\n"
	@printf "$(BOLD)$(GREEN)  Pull Commands$(RESET)\n"
	@printf "    $(CYAN)make pull$(RESET)                     Fetch with sample config (5 cases)\n"
	@printf "    $(CYAN)make pull CONFIG=full$(RESET)         Fetch all data (hours)\n"
	@printf "    $(CYAN)make pull CONFIG=dev$(RESET)          Minimal fetch for testing\n"
	@printf "    $(CYAN)make pull-status$(RESET)              Show current pull progress\n"
	@printf "    $(CYAN)make pull-reset$(RESET)               Reset state for fresh start\n"
	@printf "    $(CYAN)make validate$(RESET)                 Check environment is ready\n"
	@printf "\n"
	@printf "$(BOLD)$(GREEN)  Full Arbitration Pull$(RESET) $(DIM)(COMPREHENSIVE)$(RESET)\n"
	@printf "    $(CYAN)make pull-full-arb$(RESET)            Pull ALL arb cases with full enrichment\n"
	@printf "    $(DIM)                                (shows estimate first, resumable)$(RESET)\n"
	@printf "    $(CYAN)make pull-full-arb-estimate$(RESET)   Show time/storage estimate only\n"
	@printf "    $(CYAN)make pull-full-arb-force$(RESET)      Pull without storage check\n"
	@printf "\n"
	@printf "$(BOLD)$(GREEN)  Data Management$(RESET)\n"
	@printf "    $(CYAN)make archive$(RESET)         Archive results to timestamped zip file\n"
	@printf "    $(CYAN)make clear-results$(RESET)   Clear all results (data/raw, data/processed)\n"
	@printf "\n"
	@printf "$(BOLD)$(YELLOW)  Development$(RESET)\n"
	@printf "    $(CYAN)make install$(RESET)     Install base dependencies\n"
	@printf "    $(CYAN)make install-dev$(RESET) Install with dev dependencies + pre-commit hooks\n"
	@printf "    $(CYAN)make lint$(RESET)        Run ruff linter and formatter\n"
	@printf "    $(CYAN)make test-unit$(RESET)   Run unit tests only (no network)\n"
	@printf "    $(CYAN)make test-cov$(RESET)    Run tests with coverage\n"
	@printf "    $(CYAN)make data-dirs$(RESET)   Create data directory structure\n"
	@printf "    $(CYAN)make clean$(RESET)       Remove generated files (cache, pycache)\n"
	@printf "\n"
	@printf "$(BOLD)$(YELLOW)  Legacy Data Collection$(RESET) $(DIM)(still supported)$(RESET)\n"
	@printf "    $(CYAN)fetch-small$(RESET)     Fetch sample dataset (10 articles, 5 arb cases)\n"
	@printf "    $(CYAN)fetch-small-dry$(RESET) Preview what fetch-small would fetch\n"
	@printf "    $(CYAN)fetch-full$(RESET)      Fetch full dataset (51 articles, 50 arb cases)\n"
	@printf "    $(CYAN)fetch-full-dry$(RESET)  Preview what fetch-full would fetch\n"
	@printf "    $(CYAN)fetch-all$(RESET)       Run arb + drn collectors only (no articles)\n"
	@printf "    $(CYAN)fetch-arb$(RESET)       Fetch arbitration cases only\n"
	@printf "    $(CYAN)fetch-drn$(RESET)       Fetch DRN cases only\n"
	@printf "\n"
	@printf "$(BOLD)$(YELLOW)  Phase 2 — Dispute Venues$(RESET)\n"
	@printf "    $(CYAN)fetch-venues ARTICLE=<title>$(RESET)  Fetch all dispute venues for article\n"
	@printf "    $(CYAN)fetch-ani TERM=<term>$(RESET)         Search ANI archives for term\n"
	@printf "    $(CYAN)fetch-talk ARTICLE=<title>$(RESET)    Fetch talk page revisions\n"
	@printf "\n"
	@printf "$(BOLD)$(YELLOW)  Arbitration Case DFS$(RESET)\n"
	@printf "    $(CYAN)fetch-arb-dfs CASE=<name>$(RESET)     DFS from arb case to all related pages\n"
	@printf "    $(CYAN)fetch-arb-dfs-dry CASE=<name>$(RESET) Preview what fetch-arb-dfs would fetch\n"
	@printf "    $(CYAN)fetch-arb-dfs-sample$(RESET)          Fetch 5 example arb cases with DFS (limited)\n"
	@printf "    $(CYAN)fetch-arb-dfs-sample-full$(RESET)     Fetch 5 example arb cases with ALL pages\n"
	@printf "    $(CYAN)fetch-arb-dfs-all$(RESET)             Fetch ALL arb cases (~481 cases from Wikipedia)\n"
	@printf "    $(CYAN)fetch-arb-dfs-all-full$(RESET)        Fetch ALL arb cases with ALL pages (very long)\n"
	@printf "    $(CYAN)update-arb-cases-list$(RESET)         Update artifacts/arb_cases.txt from Wikipedia\n"
	@printf "\n"
	@printf "$(BOLD)$(YELLOW)  Full Dispute Lifecycle$(RESET) $(DIM)(RECOMMENDED — captures all escalation stages)$(RESET)\n"
	@printf "    $(CYAN)fetch-lifecycle CASE=<name>$(RESET)   Fetch full lifecycle: Talk→DRN→ANI→ArbCom\n"
	@printf "    $(CYAN)fetch-lifecycle-dry CASE=<n>$(RESET)  Preview lifecycle fetch\n"
	@printf "    $(CYAN)fetch-lifecycle-sample$(RESET)        Fetch 5 sample cases with full lifecycle\n"
	@printf "    $(CYAN)fetch-lifecycle-all$(RESET)           Fetch ALL cases with full lifecycle\n"
	@printf "\n"
	@printf "$(BOLD)$(YELLOW)  Data Quality$(RESET)\n"
	@printf "    $(CYAN)make enrich-diffs$(RESET)             Fetch evidence diffs for all case JSONs\n"
	@printf "    $(CYAN)make enrich-diffs CASE=<name>$(RESET) Fetch evidence diffs for one case\n"
	@printf "    $(CYAN)make enrich-diffs-dry$(RESET)         Preview enrich-diffs without API calls\n"
	@printf "    $(CYAN)make fetch-declined$(RESET)           Fetch declined ArbCom requests (negative class)\n"
	@printf "    $(CYAN)make fetch-declined-dry$(RESET)       Preview fetch-declined without API calls\n"
	@printf "\n"
	@printf "$(BOLD)$(MAGENTA)  Rivanna HPC$(RESET) $(DIM)(requires RIVANNA_ID in .env + SSH key)$(RESET)\n"
	@printf "    $(CYAN)make rivanna-sync$(RESET)    Sync project to Rivanna /scratch\n"
	@printf "    $(CYAN)make rivanna-setup$(RESET)   One-time setup (uv, venv, deps)\n"
	@printf "    $(CYAN)make rivanna-submit$(RESET)  Submit all SLURM jobs\n"
	@printf "    $(CYAN)make rivanna-status$(RESET)  Show SLURM job progress\n"
	@printf "    $(CYAN)make rivanna-logs$(RESET)    Tail recent SLURM log output\n"
	@printf "    $(CYAN)make rivanna-pull$(RESET)    Download collected data locally\n"
	@printf "    $(CYAN)make rivanna-clean$(RESET)   Cancel jobs and clear remote data\n"
	@printf "    $(CYAN)make rivanna-ssh$(RESET)     SSH into Rivanna interactively\n"
	@printf "    $(CYAN)make rivanna-train$(RESET)   Submit Gemma4 BPMN GPU job\n"
	@printf "\n"
	@printf "$(BOLD)$(MAGENTA)  Visualization Pipeline$(RESET)\n"
	@printf "    $(CYAN)make viz-update$(RESET)              Fetch missing cases + re-export dashboard data\n"
	@printf "    $(CYAN)make viz-update LIMIT=20$(RESET)     Fetch at most 20 missing cases this run\n"
	@printf "    $(CYAN)make fetch-missing$(RESET)           Fetch uncollected cases from arb_cases.txt\n"
	@printf "    $(CYAN)make fetch-missing DRY=1$(RESET)     List missing cases without fetching\n"
	@printf "    $(CYAN)make viz-export$(RESET)              Re-export D3 JSONs + update manifest only\n"
	@printf "    $(CYAN)make viz-serve$(RESET)               Serve D3 viz → http://localhost:8765/viz/dashboard.html\n"
	@printf "    $(CYAN)make viz-serve VIZ_PORT=9000$(RESET) Serve on a custom port\n"
	@printf "    $(CYAN)make dashboard$(RESET)               Start the React dashboard (http://localhost:5173)\n"
	@printf "    $(CYAN)make dashboard-build$(RESET)         Build the React dashboard for production\n"
	@printf "\n"

# =============================================================================
# QUICK START COMMANDS
# =============================================================================

# Setup: Install dependencies, create directories, validate environment
setup: install-dev data-dirs
	@echo ""
	@echo "Environment setup complete!"
	@echo ""
	@echo "Next steps:"
	@echo "  1. Copy .env.example to .env and add your Wikipedia access token"
	@echo "  2. Run 'make validate' to check your environment"
	@echo "  3. Run 'make pull' to fetch sample data"
	@echo ""

# Validate environment (credentials, directories, API connectivity)
validate:
	uv run python scripts/pull.py --validate

# Unified data pull with config
# Usage: make pull                  (uses sample config)
#        make pull CONFIG=full      (uses full config)
#        make pull CONFIG=dev       (minimal for testing)
#        make pull CONFIG=path.yaml (custom config)
pull: data-dirs
	uv run python scripts/pull.py --config $(or $(CONFIG),sample)

# Show current pull status
pull-status:
	uv run python scripts/pull.py --config $(or $(CONFIG),sample) --status

# Reset pull state for fresh start
pull-reset:
	uv run python scripts/pull.py --config $(or $(CONFIG),sample) --reset

# Dry run - show what would be fetched
pull-dry:
	uv run python scripts/pull.py --config $(or $(CONFIG),sample) --dry-run

# =============================================================================
# END QUICK START
# =============================================================================

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
	uv run --extra dev pytest tests/ -v

test-unit:
	uv run --extra dev pytest tests/ -v -m "not integration"

test-cov:
	uv run --extra dev pytest tests/ -v --cov=src --cov-report=term-missing

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

# Clean generated files (cache, pycache, logs)
clean:
	rm -rf artifacts/logs/*
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "✓ Cleaned cache and log files"

# Archive results to timestamped zip file
# Archives are stored in artifacts/archives/ and gitignored
archive:
	@mkdir -p artifacts/archives
	@TIMESTAMP=$$(date +%Y%m%d_%H%M%S); \
	ARCHIVE_NAME="results_$$TIMESTAMP.zip"; \
	echo "Creating archive: artifacts/archives/$$ARCHIVE_NAME"; \
	if [ -d "data/raw" ] && [ "$$(ls -A data/raw 2>/dev/null)" ]; then \
		zip -r "artifacts/archives/$$ARCHIVE_NAME" data/raw data/processed artifacts/results 2>/dev/null || \
		zip -r "artifacts/archives/$$ARCHIVE_NAME" data/raw data/processed 2>/dev/null || \
		zip -r "artifacts/archives/$$ARCHIVE_NAME" data/raw 2>/dev/null; \
		echo "✓ Archive created: artifacts/archives/$$ARCHIVE_NAME"; \
		ls -lh "artifacts/archives/$$ARCHIVE_NAME"; \
	else \
		echo "⚠️  No data to archive (data/raw is empty)"; \
	fi

# Clear all results (data/raw, data/processed)
# WARNING: This permanently deletes fetched data. Use 'make archive' first to backup.
clear-results:
	@echo "⚠️  This will permanently delete all fetched data!"
	@echo "    - data/raw/*"
	@echo "    - data/processed/*"
	@echo ""
	@read -p "Are you sure? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		rm -rf data/raw/*; \
		rm -rf data/processed/*; \
		echo "✓ All results cleared"; \
	else \
		echo "Cancelled"; \
	fi

# Force clear results without confirmation (for scripts)
clear-results-force:
	rm -rf data/raw/*
	rm -rf data/processed/*
	@echo "✓ All results cleared"

# Rebuild features.csv from raw data (arb_dfs + enriched + lifecycle)
build-features:
	uv run python scripts/build_features.py

# =============================================================================
# VISUALIZATION PIPELINE
# =============================================================================

# Fetch cases in artifacts/arb_cases.txt that are not yet on disk,
# then re-export D3 JSONs and update the manifest for the dashboard.
#
# Usage:
#   make viz-update              # fetch missing + re-export (recommended)
#   make viz-update LIMIT=20     # fetch at most 20 missing cases this run
#   make fetch-missing           # only identify and fetch missing cases
#   make fetch-missing DRY=1     # list what would be fetched without API calls
#   make viz-export              # only re-export D3 JSONs + update manifest

fetch-missing: data-dirs
	@echo "Checking for uncollected arbitration cases..."
	$(if $(DRY), \
		uv run python scripts/fetch_missing_cases.py --dry-run, \
		uv run python scripts/fetch_missing_cases.py $(if $(LIMIT),--limit $(LIMIT),) --delay 1 \
	)

viz-export:
	@echo "Exporting D3 JSONs and updating manifest..."
	uv run python scripts/export_d3_all.py --workers 4
	@echo "✓ Dashboard data updated → data/processed/d3/manifest.json"

viz-update: fetch-missing viz-export
	@echo ""
	@echo "✓ Done. Serve the D3 viz with: make viz-serve"

VIZ_PORT ?= 8765

viz-serve:
	@echo "Serving D3 viz → http://localhost:$(VIZ_PORT)/viz/dashboard.html"
	@open "http://localhost:$(VIZ_PORT)/viz/dashboard.html" 2>/dev/null || true
	python3 -m http.server $(VIZ_PORT)

# =============================================================================
# REACT DASHBOARD
# =============================================================================

DASH_PORT ?= 5173

dashboard:
	@echo "Starting React dashboard → http://localhost:$(DASH_PORT)"
	cd dashboard && npm install --silent && npm run dev -- --port $(DASH_PORT)

dashboard-build:
	@echo "Building React dashboard..."
	cd dashboard && npm install --silent && npm run build
	@echo "✓ Built → dashboard/dist/"
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
# FULL ARBITRATION PULL - COMPREHENSIVE DATA COLLECTION
# =============================================================================
# Pulls ALL arbitration cases with FULL enrichment:
# - All case pages (main, evidence, workshop, proposed decision, remedies)
# - Full revision history for all pages
# - Participant profiles (edit count, registration, groups, admin status)
# - Participant block history and abuse filter hits
# - Article assessments (WikiProject quality/importance)
# - Article protection status and history
# - Article revision history with edit tags
# - ANI and DRN venue mentions
# - Case outcome (status, remedies, sanctions)
#
# Features:
# - Checkpointing: resumes from where it left off if interrupted
# - Storage check: warns if disk space would drop below 10GB
# - Progress tracking: tqdm progress bars, timing stats, rate limit monitoring

# Show estimate only
pull-full-arb-estimate:
	@if [ ! -f $(ARB_CASES_FILE) ]; then \
		echo "Case list not found. Fetching from Wikipedia..."; \
		uv run python scripts/fetch_arb_cases_list.py --output $(ARB_CASES_FILE); \
	fi
	@uv run python scripts/estimate_pull.py --case-file $(ARB_CASES_FILE)

# Full pull with estimate and storage check
pull-full-arb: data-dirs
	@if [ ! -f $(ARB_CASES_FILE) ]; then \
		echo "Case list not found. Fetching from Wikipedia..."; \
		uv run python scripts/fetch_arb_cases_list.py --output $(ARB_CASES_FILE); \
	fi
	@echo ""
	@uv run python scripts/estimate_pull.py --case-file $(ARB_CASES_FILE) || exit 1
	@echo ""
	@read -p "Proceed with full arbitration pull? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		echo ""; \
		echo "Starting full arbitration pull..."; \
		echo "Use Ctrl+C to interrupt (progress is saved, resume with same command)"; \
		echo ""; \
		uv run python scripts/pull.py --config full; \
	else \
		echo "Cancelled"; \
	fi

# Full pull without storage check (force mode)
pull-full-arb-force: data-dirs
	@if [ ! -f $(ARB_CASES_FILE) ]; then \
		echo "Case list not found. Fetching from Wikipedia..."; \
		uv run python scripts/fetch_arb_cases_list.py --output $(ARB_CASES_FILE); \
	fi
	@echo ""
	@uv run python scripts/estimate_pull.py --case-file $(ARB_CASES_FILE) --force
	@echo ""
	@echo "Starting full arbitration pull (force mode)..."
	@echo "Use Ctrl+C to interrupt (progress is saved, resume with same command)"
	@echo ""
	uv run python scripts/pull.py --config full

# =============================================================================
# DATA QUALITY: EVIDENCE DIFFS & DECLINED REQUESTS
# =============================================================================

# Enrich arbitration case JSONs with evidence page diffs
# Usage: make enrich-diffs
#        make enrich-diffs CASE="Gamergate"
enrich-diffs: data-dirs
	uv run python scripts/enrich_evidence_diffs.py $(if $(CASE),--case "$(CASE)",)

enrich-diffs-dry: data-dirs
	uv run python scripts/enrich_evidence_diffs.py --dry-run $(if $(CASE),--case "$(CASE)",)

# Fetch declined arbitration requests (negative class for escalation models)
fetch-declined: data-dirs
	uv run python scripts/fetch_declined_rfas.py

fetch-declined-dry: data-dirs
	uv run python scripts/fetch_declined_rfas.py --dry-run

# =============================================================================
# RIVANNA HPC TARGETS
# =============================================================================
# Local convenience targets that SSH into Rivanna to manage SLURM jobs.
# Requires: RIVANNA_ID set in .env, SSH key configured (see docs/rivanna_guide.md)

# Load RIVANNA_ID from .env if not already set
RIVANNA_ID ?= $(shell grep '^RIVANNA_ID=' .env 2>/dev/null | cut -d= -f2)
RIVANNA_HOST := $(RIVANNA_ID)@login.hpc.virginia.edu
RIVANNA_PROJECT := /scratch/$(RIVANNA_ID)/Wikipedia_Dispute_Models

# Sync project files to Rivanna (excludes large/generated dirs)
rivanna-sync:
	@if [ -z "$(RIVANNA_ID)" ]; then echo "Error: RIVANNA_ID not set. Add it to .env"; exit 1; fi
	rsync -avz --delete \
		--exclude='.venv' --exclude='__pycache__' --exclude='node_modules' \
		--exclude='data/raw' --exclude='data/processed' --exclude='apicache' \
		--exclude='.git' --exclude='slurmlogs/*.out' --exclude='slurmlogs/*.err' \
		--exclude='slurmlogs/progress_*.csv' --exclude='slurmlogs/progress_*.csv.lock' \
		./ $(RIVANNA_HOST):$(RIVANNA_PROJECT)/
	@echo "✓ Synced to $(RIVANNA_HOST):$(RIVANNA_PROJECT)"

# One-time setup: install uv, create venv, install deps, smoke test
rivanna-setup: rivanna-sync
	ssh $(RIVANNA_HOST) 'cd $(RIVANNA_PROJECT) && bash scripts/slurm/setup_rivanna.sh'

# Submit all SLURM jobs (update cases → fetch_full, arb_dfs, lifecycle)
rivanna-submit:
	ssh $(RIVANNA_HOST) 'cd $(RIVANNA_PROJECT) && bash scripts/slurm/submit_all.sh'

# Show SLURM job progress and data collection status
rivanna-status:
	ssh $(RIVANNA_HOST) 'cd $(RIVANNA_PROJECT) && bash scripts/slurm/status.sh'

# Tail recent SLURM log output
rivanna-logs:
	ssh $(RIVANNA_HOST) 'cd $(RIVANNA_PROJECT) && for f in $$(ls -t slurmlogs/*.out 2>/dev/null | head -5); do echo "=== $$f ==="; tail -20 "$$f"; echo; done'

# Pull collected data from Rivanna to local machine
rivanna-pull:
	@if [ -z "$(RIVANNA_ID)" ]; then echo "Error: RIVANNA_ID not set. Add it to .env"; exit 1; fi
	rsync -avz $(RIVANNA_HOST):$(RIVANNA_PROJECT)/data/raw/ data/raw/
	rsync -avz $(RIVANNA_HOST):$(RIVANNA_PROJECT)/data/processed/ data/processed/
	rsync -avz $(RIVANNA_HOST):$(RIVANNA_PROJECT)/slurmlogs/ slurmlogs/
	rsync -avz --include='*.txt' --include='*.yaml' --include='*.json' --exclude='*' \
		$(RIVANNA_HOST):$(RIVANNA_PROJECT)/artifacts/ artifacts/
	@echo "✓ Pulled data from Rivanna"

# Cancel all SLURM jobs and clear remote data
rivanna-clean:
	@echo "This will cancel all your SLURM jobs and delete remote data/raw/*"
	@read -p "Are you sure? [y/N] " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		ssh $(RIVANNA_HOST) 'scancel -u $(RIVANNA_ID) 2>/dev/null; \
			cd $(RIVANNA_PROJECT) && rm -rf data/raw/* slurmlogs/*.out slurmlogs/*.err'; \
		echo "✓ Cancelled jobs and cleared data on Rivanna"; \
	else \
		echo "Cancelled"; \
	fi

# SSH into Rivanna interactively
rivanna-ssh:
	ssh $(RIVANNA_HOST)

# Submit Gemma4 BPMN GPU job to Rivanna
rivanna-train: rivanna-sync
	ssh $(RIVANNA_HOST) 'cd $(RIVANNA_PROJECT) && mkdir -p logs && sbatch scripts/rivanna_gemma4.slurm'
