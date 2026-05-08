#!/bin/bash
# common.sh — Shared environment setup sourced by all SLURM scripts
# Usage: source "$(dirname "$0")/common.sh"

set -euo pipefail

# ---------------------------------------------------------------------------
# Project root — override with WIKI_PROJECT_ROOT env var if needed
# Default: the repo cloned into $HOME
# ---------------------------------------------------------------------------
export PROJECT_ROOT="${WIKI_PROJECT_ROOT:-/scratch/rah5ff/Wikipedia_Dispute_Models}"

if [[ ! -d "$PROJECT_ROOT" ]]; then
    echo "ERROR: PROJECT_ROOT=$PROJECT_ROOT does not exist."
    echo "  Clone the repo or set WIKI_PROJECT_ROOT to the correct path."
    exit 1
fi

cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Load .env file if present (provides WIKI_API_KEY, etc.)
# ---------------------------------------------------------------------------
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
fi

# ---------------------------------------------------------------------------
# Load uv — installed to ~/.local/bin by the astral installer
# ---------------------------------------------------------------------------
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv &>/dev/null; then
    echo "ERROR: uv not found. Run scripts/slurm/setup_rivanna.sh first."
    exit 1
fi

# Activate the project venv so scripts find the right Python
export VIRTUAL_ENV="$PROJECT_ROOT/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"

if [[ ! -d "$VIRTUAL_ENV" ]]; then
    echo "ERROR: Virtual environment not found at $VIRTUAL_ENV"
    echo "  Run scripts/slurm/setup_rivanna.sh first."
    exit 1
fi

# ---------------------------------------------------------------------------
# Ensure data directories exist (mirrors Makefile data-dirs target)
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Credential check — warn if no API credentials are set
# ---------------------------------------------------------------------------
if [[ -z "${WIKI_API_KEY:-}" ]] && [[ -z "${PYWIKIBOT_PASSWORD:-}" ]]; then
    echo "WARNING: Neither WIKI_API_KEY nor PYWIKIBOT_PASSWORD is set."
    echo "  API requests will be unauthenticated (500 req/hr limit)."
    echo "  For better throughput, pass credentials via:"
    echo "    sbatch --export=ALL,WIKI_API_KEY=<your-key> ..."
    echo ""
fi

# ---------------------------------------------------------------------------
# Print job info
# ---------------------------------------------------------------------------
SLURM_START_TIME=$(date -Iseconds)
SLURM_START_EPOCH=$(date +%s)

printf "\n======================================\n"
printf "[ HOSTNAME ]   : %s\n" "$(hostname)"
printf "[ PARTITION ]  : %s\n" "${SLURM_JOB_PARTITION:-unknown}"
printf "[ JOB ID ]     : %s\n" "${SLURM_JOB_ID:-${SLURM_ARRAY_JOB_ID:-unknown}}"
printf "[ ARRAY ID ]   : %s\n" "${SLURM_ARRAY_TASK_ID:-N/A}"
printf "[ CPUS ]       : %s\n" "${SLURM_CPUS_ON_NODE:-unknown}"
printf "[ MEMORY ]     : %s\n" "${SLURM_MEM_PER_NODE:-unknown}"
printf "[ START TIME ] : %s\n" "$SLURM_START_TIME"
printf "[ PROJECT ]    : %s\n" "$PROJECT_ROOT"
printf "[ PYTHON ]     : %s\n" "$(which python)"
printf "[ UV ]         : %s\n" "$(which uv)"
printf "======================================\n\n"

# Repeat to stderr (goes to .err file)
printf "\n======================================\n" >&2
printf "[ HOSTNAME ]   : %s\n" "$(hostname)" >&2
printf "[ JOB ID ]     : %s\n" "${SLURM_JOB_ID:-${SLURM_ARRAY_JOB_ID:-unknown}}" >&2
printf "[ ARRAY ID ]   : %s\n" "${SLURM_ARRAY_TASK_ID:-N/A}" >&2
printf "[ START TIME ] : %s\n" "$SLURM_START_TIME" >&2
printf "======================================\n\n" >&2

# ---------------------------------------------------------------------------
# Progress logging — shared CSV log for tracking array task completion
# ---------------------------------------------------------------------------
# Usage in SLURM scripts:
#   log_progress <job_type> <case_name> <status> [details]
#
# Writes one line per task to slurmlogs/progress_<job_type>.csv
# Format: timestamp,job_id,array_id,case_name,status,elapsed_sec,details
#
# Status values: SUCCESS, FAILED, STARTED

PROGRESS_DIR="$PROJECT_ROOT/slurmlogs"

log_progress() {
    local job_type="$1"
    local case_name="$2"
    local status="$3"
    local details="${4:-}"
    local log_file="$PROGRESS_DIR/progress_${job_type}.csv"
    local now
    now=$(date -Iseconds)
    local elapsed=$(( $(date +%s) - SLURM_START_EPOCH ))
    local job_id="${SLURM_JOB_ID:-${SLURM_ARRAY_JOB_ID:-unknown}}"
    local array_id="${SLURM_ARRAY_TASK_ID:-N/A}"

    # Create header if file is new
    if [[ ! -f "$log_file" ]]; then
        echo "timestamp,job_id,array_task_id,case_name,status,elapsed_sec,details" > "$log_file"
    fi

    # Append progress entry (use flock for safe concurrent writes from array tasks)
    (
        flock -w 10 200
        echo "${now},${job_id},${array_id},${case_name},${status},${elapsed},${details}" >> "$log_file"
    ) 200>"${log_file}.lock"
}

# Helper: count output files in a directory matching a pattern
count_outputs() {
    local dir="$1"
    local pattern="${2:-*.json}"
    find "$dir" -name "$pattern" 2>/dev/null | wc -l | tr -d ' '
}

# Helper: get total size of a directory
dir_size() {
    du -sh "$1" 2>/dev/null | cut -f1 || echo "0"
}

# Helper: print a summary banner at job end
print_summary() {
    local job_type="$1"
    local case_name="$2"
    local status="$3"
    local elapsed=$(( $(date +%s) - SLURM_START_EPOCH ))
    local elapsed_fmt
    elapsed_fmt="$(printf '%02d:%02d:%02d' $((elapsed/3600)) $(((elapsed%3600)/60)) $((elapsed%60)))"

    printf "\n======================================\n"
    printf "[ COMPLETED ]  : %s\n" "$(date -Iseconds)"
    printf "[ JOB TYPE ]   : %s\n" "$job_type"
    printf "[ CASE ]       : %s\n" "$case_name"
    printf "[ STATUS ]     : %s\n" "$status"
    printf "[ ELAPSED ]    : %s\n" "$elapsed_fmt"
    printf "======================================\n"
}
