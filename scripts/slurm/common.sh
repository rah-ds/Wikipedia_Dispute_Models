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

# ---------------------------------------------------------------------------
# Email notifications — send progress/completion reports via UVA email
# ---------------------------------------------------------------------------
# Usage:
#   send_report "subject line" "body text"
#   send_report "subject line" "body text" "/path/to/body_file"  (reads file)
#
# Respects NOTIFY_EMAIL env var (set in .env). Does nothing if unset.
# Runs in background with timeout — never blocks the job.

send_report() {
    local subject="$1"
    local body="${2:-}"
    local body_file="${3:-}"

    local to="${NOTIFY_EMAIL:-}"
    if [[ -z "$to" ]]; then
        return 0  # no recipient configured
    fi

    local email_script="$PROJECT_ROOT/scripts/slurm/send_email.py"
    if [[ ! -f "$email_script" ]]; then
        echo "WARNING: send_email.py not found at $email_script" >&2
        return 0
    fi

    # Add job metadata header to body
    local elapsed=$(( $(date +%s) - SLURM_START_EPOCH ))
    local elapsed_fmt
    elapsed_fmt="$(printf '%02d:%02d:%02d' $((elapsed/3600)) $(((elapsed%3600)/60)) $((elapsed%60)))"
    local header
    header="$(printf 'Job ID:     %s\nHost:       %s\nElapsed:    %s\nTimestamp:  %s\n' \
        "${SLURM_JOB_ID:-${SLURM_ARRAY_JOB_ID:-unknown}}" \
        "$(hostname)" \
        "$elapsed_fmt" \
        "$(date -Iseconds)")"

    local full_body
    if [[ -n "$body_file" ]] && [[ -f "$body_file" ]]; then
        full_body="${header}\n\n$(cat "$body_file")"
    else
        full_body="${header}\n\n${body}"
    fi

    # Fire-and-forget: background with 30s timeout, never crash the job
    (
        echo -e "$full_body" | timeout 30 python "$email_script" \
            --to "$to" \
            --subject "$subject" 2>/dev/null
    ) &
}

# Helper: send report for array job milestones (25%, 50%, 75%, 100%)
# Uses marker files to prevent duplicate emails from concurrent tasks.
#
# Usage: check_milestone <job_type> <total_cases>
#   Reads progress CSV, counts successes, sends email if a new quarter is hit.

check_milestone() {
    local job_type="$1"
    local total_cases="$2"
    local progress_file="$PROGRESS_DIR/progress_${job_type}.csv"

    if [[ ! -f "$progress_file" ]]; then
        return 0
    fi

    local done
    done=$(grep -c ',SUCCESS,' "$progress_file" 2>/dev/null || echo 0)
    local failed
    failed=$(grep -c ',FAILED,' "$progress_file" 2>/dev/null || echo 0)

    for pct in 25 50 75 100; do
        local threshold=$(( total_cases * pct / 100 ))
        local marker="$PROGRESS_DIR/.milestone_${job_type}_${pct}"

        if (( done >= threshold )) && [[ ! -f "$marker" ]]; then
            # Use flock to prevent race between concurrent array tasks
            (
                flock -n 200 || exit 0
                # Re-check after acquiring lock
                if [[ -f "$marker" ]]; then exit 0; fi
                touch "$marker"

                local body
                body="$(printf 'Wikipedia Dispute Models — Progress Report\n')"
                body+="$(printf '═══════════════════════════════════════════\n\n')"
                body+="$(printf 'Job Type:    %s\n' "$job_type")"
                body+="$(printf 'Progress:    %d%% — %d of %d cases complete\n' "$pct" "$done" "$total_cases")"
                body+="$(printf 'Failed:      %d cases\n' "$failed")"
                body+="$(printf 'Remaining:   %d cases\n\n' "$((total_cases - done - failed))")"

                if (( failed > 0 )); then
                    body+="$(printf 'Failed Cases:\n')"
                    body+="$(grep ',FAILED,' "$progress_file" | awk -F, '{printf "  - %s (job %s, task %s): %s\n", $4, $2, $3, $7}')"
                    body+="$(printf '\n')"
                fi

                body+="$(printf 'Data Sizes:\n')"
                body+="$(printf '  arbitration:     %s\n' "$(dir_size data/raw/arbitration)")"
                body+="$(printf '  revisions:       %s\n' "$(dir_size data/raw/revisions)")"
                body+="$(printf '  dispute_venues:  %s\n' "$(dir_size data/raw/dispute_venues)")"
                body+="$(printf '  edit_wars:       %s\n' "$(dir_size data/raw/edit_wars)")"

                if (( pct < 100 )); then
                    body+="$(printf '\nNext milestone email at %d%%.\n' "$((pct + 25))")"
                fi

                send_report "[Rivanna] ${job_type} — ${pct}% complete (${done}/${total_cases})" "$body"
            ) 200>"${marker}.lock"
        fi
    done
}
