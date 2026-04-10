#!/bin/bash
# setup_rivanna.sh — One-time setup for running Wikipedia data fetchers on Rivanna
# Run this interactively (NOT via sbatch) after cloning the repo.
#
# Usage:
#   ssh <computing_id>@rivanna.hpc.virginia.edu
#   cd ~/Wikipedia_Dispute_Models   # or wherever you cloned
#   bash scripts/slurm/setup_rivanna.sh

set -euo pipefail

echo "========================================="
echo "  Wikipedia Arbitration — Rivanna Setup"
echo "========================================="
echo ""

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"
echo "Project root: $PROJECT_ROOT"

# ---------------------------------------------------------------------------
# 1. Install uv (if not already installed)
# ---------------------------------------------------------------------------
echo ""
echo "[1/5] Checking for uv..."

if command -v uv &>/dev/null; then
    echo "  uv already installed: $(uv --version)"
else
    echo "  Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    echo "  Installed: $(uv --version)"
fi

# ---------------------------------------------------------------------------
# 2. Create virtual environment and install dependencies
# ---------------------------------------------------------------------------
echo ""
echo "[2/5] Setting up Python environment..."

if [[ -d ".venv" ]]; then
    echo "  Virtual environment already exists at .venv/"
    echo "  To recreate, delete it first: rm -rf .venv"
else
    echo "  Creating virtual environment with Python 3.12..."
    uv venv .venv --python 3.12
fi

echo "  Installing project dependencies..."
uv pip install -e .
# httpx is used by fetch_arb_cases_list.py
uv pip install httpx

echo "  Installed packages:"
uv pip list 2>/dev/null | head -20
echo "  ..."

# ---------------------------------------------------------------------------
# 3. Create data directories
# ---------------------------------------------------------------------------
echo ""
echo "[3/5] Creating data directories..."

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
mkdir -p slurmlogs

echo "  Data directories created."

# ---------------------------------------------------------------------------
# 4. Smoke test
# ---------------------------------------------------------------------------
echo ""
echo "[4/5] Running smoke test..."

.venv/bin/python -c "
from src.io import PROJECT_ROOT, DATA_DIR
print(f'  PROJECT_ROOT = {PROJECT_ROOT}')
print(f'  DATA_DIR     = {DATA_DIR}')
assert DATA_DIR.exists(), 'DATA_DIR does not exist!'

from src.wiki import WikiClient
print('  WikiClient import: OK')

from src.fetchers import fetch_arbitration_cases
print('  fetchers import:   OK')

from src.io import check_api_credentials
check_api_credentials()
print('  Smoke test passed!')
"

# ---------------------------------------------------------------------------
# 5. Credential reminder
# ---------------------------------------------------------------------------
echo ""
echo "[5/5] API Credentials"
echo ""

if [[ -n "${WIKI_API_KEY:-}" ]]; then
    echo "  WIKI_API_KEY is set in your environment."
elif [[ -n "${PYWIKIBOT_PASSWORD:-}" ]]; then
    echo "  PYWIKIBOT_PASSWORD is set in your environment."
else
    echo "  No API credentials detected."
    echo ""
    echo "  For authenticated access (5,000+ req/hr vs 500), either:"
    echo ""
    echo "  Option A — Export before submitting jobs:"
    echo "    export WIKI_API_KEY='your-key-here'"
    echo "    bash scripts/slurm/submit_all.sh"
    echo ""
    echo "  Option B — Add to your ~/.bashrc:"
    echo "    echo 'export WIKI_API_KEY=\"your-key-here\"' >> ~/.bashrc"
    echo "    source ~/.bashrc"
    echo ""
fi

echo ""
echo "========================================="
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Set WIKI_API_KEY (see above)"
echo "    2. Submit all jobs:  bash scripts/slurm/submit_all.sh"
echo "    3. Monitor:          squeue -u \$USER"
echo "========================================="
