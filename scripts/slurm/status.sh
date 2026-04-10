#!/bin/bash
# status.sh — Report on SLURM job progress and data collection status
#
# Reads progress CSVs from slurmlogs/ and summarizes:
#   - How many tasks started / succeeded / failed  for each job type
#   - Which cases are still pending (not yet attempted)
#   - Data directory file counts and sizes
#   - Recent SLURM log tail
#
# Usage:
#   bash scripts/slurm/status.sh              # full report
#   bash scripts/slurm/status.sh --short      # compact summary
#   bash scripts/slurm/status.sh --failed     # show only failed cases

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT"

MODE="${1:---full}"

# ---------------------------------------------------------------------------
# Colors (if terminal supports them)
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    RED='' GREEN='' YELLOW='' CYAN='' BOLD='' NC=''
fi

# ---------------------------------------------------------------------------
# Helper: parse a progress CSV and count statuses
# ---------------------------------------------------------------------------
report_job_type() {
    local job_type="$1"
    local log_file="slurmlogs/progress_${job_type}.csv"

    if [[ ! -f "$log_file" ]]; then
        printf "  ${YELLOW}No progress log found${NC} (no tasks have run yet)\n"
        return
    fi

    local started=$(grep -c ',STARTED,' "$log_file" 2>/dev/null || echo 0)
    local success=$(grep -c ',SUCCESS,' "$log_file" 2>/dev/null || echo 0)
    local failed=$(grep -c ',FAILED,' "$log_file" 2>/dev/null || echo 0)

    printf "  ${GREEN}Succeeded${NC}: %d\n" "$success"
    printf "  ${RED}Failed${NC}:    %d\n" "$failed"
    printf "  ${YELLOW}Started${NC}:   %d  (includes succeeded + failed + in-progress)\n" "$started"

    # Show failed cases
    if (( failed > 0 )); then
        printf "\n  ${RED}Failed cases:${NC}\n"
        grep ',FAILED,' "$log_file" | while IFS=',' read -r ts jid aid case status elapsed details; do
            printf "    - %s  (job %s, task %s, %s)\n" "$case" "$jid" "$aid" "$details"
        done
    fi
}

# ---------------------------------------------------------------------------
# Helper: show pending cases for array jobs
# ---------------------------------------------------------------------------
show_pending() {
    local job_type="$1"
    local log_file="slurmlogs/progress_${job_type}.csv"
    local cases_file="artifacts/arb_cases.txt"

    if [[ ! -f "$cases_file" ]]; then
        printf "  ${YELLOW}No arb_cases.txt found — run update-arb-cases-list first${NC}\n"
        return
    fi

    local total_cases
    total_cases=$(wc -l < "$cases_file" | tr -d ' ')

    if [[ ! -f "$log_file" ]]; then
        printf "  All %d cases are pending (no tasks have run)\n" "$total_cases"
        return
    fi

    # Extract successfully completed case names
    local completed_cases
    completed_cases=$(grep ',SUCCESS,' "$log_file" | cut -d',' -f4 | sort -u)

    local completed_count
    completed_count=$(echo "$completed_cases" | grep -c . 2>/dev/null || echo 0)

    local pending_count=$((total_cases - completed_count))

    printf "  Total cases:  %d\n" "$total_cases"
    printf "  ${GREEN}Completed${NC}:    %d\n" "$completed_count"
    printf "  ${YELLOW}Remaining${NC}:    %d\n" "$pending_count"

    # Show completion percentage
    if (( total_cases > 0 )); then
        local pct=$((completed_count * 100 / total_cases))
        local bar_width=30
        local filled=$((pct * bar_width / 100))
        local empty=$((bar_width - filled))
        printf "  Progress:     [${GREEN}"
        printf '%0.s█' $(seq 1 $filled 2>/dev/null) || true
        printf "${NC}"
        printf '%0.s░' $(seq 1 $empty 2>/dev/null) || true
        printf "] %d%%\n" "$pct"
    fi
}

# ---------------------------------------------------------------------------
# Data directory summary
# ---------------------------------------------------------------------------
data_summary() {
    printf "\n${BOLD}Data Directory Summary${NC}\n"
    printf "%-25s %8s %10s\n" "Directory" "Files" "Size"
    printf "%-25s %8s %10s\n" "-------------------------" "--------" "----------"

    for dir in arbitration revisions edit_wars drn dispute_venues ani_search talk_pages; do
        local path="data/raw/$dir"
        if [[ -d "$path" ]]; then
            local count
            count=$(find "$path" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
            local size
            size=$(du -sh "$path" 2>/dev/null | cut -f1 || echo "0")
            printf "%-25s %8s %10s\n" "raw/$dir" "$count" "$size"
        fi
    done

    printf "%-25s %8s %10s\n" "-------------------------" "--------" "----------"
    local total_count
    total_count=$(find data/raw -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
    local total_size
    total_size=$(du -sh data/raw 2>/dev/null | cut -f1 || echo "0")
    printf "%-25s %8s %10s\n" "TOTAL (data/raw/)" "$total_count" "$total_size"
}

# ---------------------------------------------------------------------------
# SLURM queue status (only works on Rivanna)
# ---------------------------------------------------------------------------
slurm_queue() {
    if command -v squeue &>/dev/null; then
        printf "\n${BOLD}Active SLURM Jobs${NC}\n"
        squeue -u "$USER" -o "%.10i %.20j %.8T %.10M %.6D %.4C %R" 2>/dev/null || \
            printf "  ${YELLOW}Could not query SLURM (are you on Rivanna?)${NC}\n"
    fi
}

# ---------------------------------------------------------------------------
# Recent log entries
# ---------------------------------------------------------------------------
recent_logs() {
    printf "\n${BOLD}Recent Log Entries${NC} (last 5 per job type)\n"

    for job_type in fetch_full arb_dfs lifecycle; do
        local log_file="slurmlogs/progress_${job_type}.csv"
        if [[ -f "$log_file" ]]; then
            printf "\n  ${CYAN}${job_type}:${NC}\n"
            tail -5 "$log_file" | while IFS=',' read -r ts jid aid case status elapsed details; do
                # Skip header
                [[ "$ts" == "timestamp" ]] && continue
                local color="$NC"
                [[ "$status" == "SUCCESS" ]] && color="$GREEN"
                [[ "$status" == "FAILED" ]] && color="$RED"
                [[ "$status" == "STARTED" ]] && color="$YELLOW"
                printf "    %s  ${color}%-8s${NC}  %s  (%ss)\n" "$ts" "$status" "$case" "$elapsed"
            done
        fi
    done
}

# ===========================================================================
# Main report
# ===========================================================================
printf "\n${BOLD}=========================================${NC}\n"
printf "${BOLD}  Wikipedia Arbitration — SLURM Status${NC}\n"
printf "${BOLD}=========================================${NC}\n"
printf "  Report time: %s\n" "$(date -Iseconds)"
printf "  Project:     %s\n\n" "$PROJECT_ROOT"

# --- fetch_full ---
printf "${BOLD}[fetch_full]${NC} Full dataset (51 articles)\n"
report_job_type "fetch_full"

# --- arb_dfs ---
printf "\n${BOLD}[arb_dfs]${NC} Arbitration case DFS\n"
report_job_type "arb_dfs"
if [[ "$MODE" != "--short" ]]; then
    show_pending "arb_dfs"
fi

# --- lifecycle ---
printf "\n${BOLD}[lifecycle]${NC} Full dispute lifecycle\n"
report_job_type "lifecycle"
if [[ "$MODE" != "--short" ]]; then
    show_pending "lifecycle"
fi

# --- Data summary (always show) ---
data_summary

# --- SLURM queue (always try) ---
slurm_queue

# --- Recent logs (full mode only) ---
if [[ "$MODE" == "--full" ]] || [[ "$MODE" == "--failed" ]]; then
    recent_logs
fi

printf "\n${BOLD}=========================================${NC}\n"
printf "  Logs:   slurmlogs/progress_*.csv\n"
printf "  Detail: slurmlogs/*.out / *.err\n"
printf "${BOLD}=========================================${NC}\n\n"
