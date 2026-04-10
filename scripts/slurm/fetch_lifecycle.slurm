#!/bin/bash
#SBATCH -A msds_ds6015                  # allocation
#SBATCH -p standard                     # CPU partition
#SBATCH --qos=class
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=8G
#SBATCH -c 1
#SBATCH -t 2-00:00:00                   # 2 days per case
#SBATCH -o ./slurmlogs/lifecycle_%A_%a.out
#SBATCH -e ./slurmlogs/lifecycle_%A_%a.err
#SBATCH -J wiki-lifecycle
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=rah5ff@virginia.edu

## SLURM Array Job: Fetch full dispute lifecycle for each arbitration case
## Traces: Talk Pages -> DRN -> ANI -> ArbCom
## Each array task processes one case from artifacts/arb_cases.txt.
##
## Usage:
##   TOTAL=$(wc -l < artifacts/arb_cases.txt)
##   sbatch --array=1-${TOTAL}%2 scripts/slurm/fetch_lifecycle.slurm
##
## The %2 limits to 2 concurrent tasks to respect Wikipedia API rate limits.

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

CASE_NAME=$(sed -n "${TASK_ID}p" "$ARB_CASES_FILE")

if [[ -z "$CASE_NAME" ]]; then
    echo "ERROR: Empty case name at line $TASK_ID"
    exit 1
fi

echo "Lifecycle [$TASK_ID/$TOTAL_CASES]: $CASE_NAME"
echo "Stages: Talk Pages -> DRN -> ANI -> ArbCom"
echo ""

# ---------------------------------------------------------------------------
# Skip if output already exists (allows safe resubmission after cancel)
# ---------------------------------------------------------------------------
SAFE_NAME=$(echo "$CASE_NAME" | tr '/ :' '___')
EXISTING=$(find data/raw/dispute_venues -name "lifecycle_${SAFE_NAME}_*.json" 2>/dev/null | head -1)
if [[ -n "$EXISTING" ]]; then
    echo "SKIP: Output already exists: $EXISTING"
    log_progress "lifecycle" "$CASE_NAME" "SUCCESS" "skipped=already_exists,file=$(basename $EXISTING)"
    print_summary "lifecycle" "$CASE_NAME" "SKIPPED (output exists)"
    exit 0
fi

log_progress "lifecycle" "$CASE_NAME" "STARTED" "task=${TASK_ID}/${TOTAL_CASES}"

# Stagger start times to avoid burst API requests when concurrent tasks launch
sleep $(( (TASK_ID % 5) * 30 ))

# ---------------------------------------------------------------------------
# Run the lifecycle fetcher
# ---------------------------------------------------------------------------
BEFORE_COUNT=$(count_outputs data/raw/dispute_venues "lifecycle_*")

EXIT_CODE=0
uv run python scripts/fetch_dispute_lifecycle.py -- "$CASE_NAME" || EXIT_CODE=$?

AFTER_COUNT=$(count_outputs data/raw/dispute_venues "lifecycle_*")
NEW_FILES=$((AFTER_COUNT - BEFORE_COUNT))

if [[ $EXIT_CODE -eq 0 ]]; then
    log_progress "lifecycle" "$CASE_NAME" "SUCCESS" "new_files=${NEW_FILES},total=${AFTER_COUNT}"
    print_summary "lifecycle" "$CASE_NAME" "SUCCESS"
else
    log_progress "lifecycle" "$CASE_NAME" "FAILED" "exit_code=${EXIT_CODE}"
    print_summary "lifecycle" "$CASE_NAME" "FAILED (exit $EXIT_CODE)"

    # Send failure email with stderr excerpt
    ERR_FILE="slurmlogs/lifecycle_${SLURM_ARRAY_JOB_ID}_${TASK_ID}.err"
    LAST_ERR=$(tail -20 "$ERR_FILE" 2>/dev/null || echo "(no stderr)")
    send_report "[Rivanna] lifecycle FAILED: $CASE_NAME (task $TASK_ID)" \
        "Case:       $CASE_NAME\nTask:       $TASK_ID / $TOTAL_CASES\nExit code:  $EXIT_CODE\n\nLast 20 lines of stderr:\n$LAST_ERR"
fi

# Check for quarter milestones (25%, 50%, 75%, 100%)
check_milestone "lifecycle" "$TOTAL_CASES"

echo "Output: data/raw/dispute_venues/ (+${NEW_FILES} files)"
exit $EXIT_CODE
