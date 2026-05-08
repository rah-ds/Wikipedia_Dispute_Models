#!/bin/bash
#SBATCH -A msds_ds6015                  # allocation
#SBATCH -p standard                     # CPU partition
#SBATCH --qos=class
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=8G
#SBATCH -c 1
#SBATCH -t 2-00:00:00                   # 2 days per case
#SBATCH -o ./slurmlogs/arb_dfs_%A_%a.out
#SBATCH -e ./slurmlogs/arb_dfs_%A_%a.err
#SBATCH -J wiki-arb-dfs
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=rah5ff@virginia.edu

## SLURM Array Job: Fetch arbitration case data via DFS traversal
## Each array task processes one case from artifacts/arb_cases.txt.
##
## Usage:
##   # First, ensure arb_cases.txt exists (run update_arb_cases.slurm)
##   TOTAL=$(wc -l < artifacts/arb_cases.txt)
##   sbatch --array=1-${TOTAL}%2 scripts/slurm/fetch_arb_dfs.slurm
##
## The %2 limits to 2 concurrent tasks to respect Wikipedia API rate limits.
## Adjust the concurrency cap as needed: %1 (safest), %2 (default), %4 (aggressive).

_PROJECT="${WIKI_PROJECT_ROOT:-/scratch/rah5ff/Wikipedia_Dispute_Models}"
source "${_PROJECT}/scripts/slurm/common.sh"

# ---------------------------------------------------------------------------
# Read case name from arb_cases.txt using the array task ID as line number
# ---------------------------------------------------------------------------
ARB_CASES_FILE="artifacts/arb_cases.txt"

if [[ ! -f "$ARB_CASES_FILE" ]]; then
    echo "ERROR: $ARB_CASES_FILE not found."
    echo "  Run update_arb_cases.slurm first."
    exit 1
fi

TOTAL_CASES=$(wc -l < "$ARB_CASES_FILE" | tr -d ' ')
TASK_ID="${SLURM_ARRAY_TASK_ID}"

if (( TASK_ID < 1 || TASK_ID > TOTAL_CASES )); then
    echo "ERROR: SLURM_ARRAY_TASK_ID=$TASK_ID out of range [1, $TOTAL_CASES]"
    exit 1
fi

CASE_NAME=$(sed -n "${TASK_ID}p" "$ARB_CASES_FILE" | xargs)

if [[ -z "$CASE_NAME" ]]; then
    echo "ERROR: Empty case name at line $TASK_ID"
    exit 1
fi

echo "Case [$TASK_ID/$TOTAL_CASES]: $CASE_NAME"
echo ""

# ---------------------------------------------------------------------------
# Skip if output already exists (allows safe resubmission after cancel)
# ---------------------------------------------------------------------------
SAFE_NAME=$(echo "$CASE_NAME" | tr '/ :' '___')
EXISTING=$(find data/raw/arbitration -name "arb_dfs_${SAFE_NAME}_*.json" 2>/dev/null | head -1)
if [[ -n "$EXISTING" ]]; then
    echo "SKIP: Output already exists: $EXISTING"
    log_progress "arb_dfs" "$CASE_NAME" "SUCCESS" "skipped=already_exists,file=$(basename $EXISTING)"
    print_summary "arb_dfs" "$CASE_NAME" "SKIPPED (output exists)"
    exit 0
fi

log_progress "arb_dfs" "$CASE_NAME" "STARTED" "task=${TASK_ID}/${TOTAL_CASES}"

# Stagger start times to avoid burst API requests when concurrent tasks launch
sleep $(( (TASK_ID % 5) * 30 ))

# ---------------------------------------------------------------------------
# Run the DFS fetcher
# ---------------------------------------------------------------------------
BEFORE_COUNT=$(count_outputs data/raw/arbitration "arb_dfs_*")

EXIT_CODE=0
uv run python scripts/fetch_arb_dfs.py -- "$CASE_NAME" || EXIT_CODE=$?

AFTER_COUNT=$(count_outputs data/raw/arbitration "arb_dfs_*")
NEW_FILES=$((AFTER_COUNT - BEFORE_COUNT))

if [[ $EXIT_CODE -eq 0 ]]; then
    log_progress "arb_dfs" "$CASE_NAME" "SUCCESS" "new_files=${NEW_FILES},total=${AFTER_COUNT}"
    print_summary "arb_dfs" "$CASE_NAME" "SUCCESS"
else
    log_progress "arb_dfs" "$CASE_NAME" "FAILED" "exit_code=${EXIT_CODE}"
    print_summary "arb_dfs" "$CASE_NAME" "FAILED (exit $EXIT_CODE)"

    # Send failure email with stderr excerpt
    ERR_FILE="slurmlogs/arb_dfs_${SLURM_ARRAY_JOB_ID}_${TASK_ID}.err"
    LAST_ERR=$(tail -20 "$ERR_FILE" 2>/dev/null || echo "(no stderr)")
    send_report "[Rivanna] arb_dfs FAILED: $CASE_NAME (task $TASK_ID)" \
        "Case:       $CASE_NAME\nTask:       $TASK_ID / $TOTAL_CASES\nExit code:  $EXIT_CODE\n\nLast 20 lines of stderr:\n$LAST_ERR"
fi

# Check for quarter milestones (25%, 50%, 75%, 100%)
check_milestone "arb_dfs" "$TOTAL_CASES"

echo "Output: data/raw/arbitration/ (+${NEW_FILES} files)"
exit $EXIT_CODE
