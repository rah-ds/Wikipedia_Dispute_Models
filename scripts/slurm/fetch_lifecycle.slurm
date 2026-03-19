#!/bin/bash
#SBATCH -A msds_ds6015                  # allocation
#SBATCH -p standard                     # CPU partition
#SBATCH --qos=class
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=8G
#SBATCH -c 1
#SBATCH -t 03:00:00                     # 3 hours per case (lifecycle traces more stages)
#SBATCH -o ./slurmlogs/lifecycle_%A_%a.out
#SBATCH -e ./slurmlogs/lifecycle_%A_%a.err
#SBATCH -J wiki-lifecycle

## SLURM Array Job: Fetch full dispute lifecycle for each arbitration case
## Traces: Talk Pages -> DRN -> ANI -> ArbCom
## Each array task processes one case from artifacts/arb_cases.txt.
##
## Usage:
##   TOTAL=$(wc -l < artifacts/arb_cases.txt)
##   sbatch --array=1-${TOTAL}%2 scripts/slurm/fetch_lifecycle.slurm
##
## The %2 limits to 2 concurrent tasks to respect Wikipedia API rate limits.

source "$(dirname "$0")/common.sh"

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

log_progress "lifecycle" "$CASE_NAME" "STARTED" "task=${TASK_ID}/${TOTAL_CASES}"

# ---------------------------------------------------------------------------
# Run the lifecycle fetcher
# ---------------------------------------------------------------------------
BEFORE_COUNT=$(count_outputs data/raw/dispute_venues "lifecycle_*")

EXIT_CODE=0
uv run python scripts/fetch_dispute_lifecycle.py "$CASE_NAME" || EXIT_CODE=$?

AFTER_COUNT=$(count_outputs data/raw/dispute_venues "lifecycle_*")
NEW_FILES=$((AFTER_COUNT - BEFORE_COUNT))

if [[ $EXIT_CODE -eq 0 ]]; then
    log_progress "lifecycle" "$CASE_NAME" "SUCCESS" "new_files=${NEW_FILES},total=${AFTER_COUNT}"
    print_summary "lifecycle" "$CASE_NAME" "SUCCESS"
else
    log_progress "lifecycle" "$CASE_NAME" "FAILED" "exit_code=${EXIT_CODE}"
    print_summary "lifecycle" "$CASE_NAME" "FAILED (exit $EXIT_CODE)"
fi

echo "Output: data/raw/dispute_venues/ (+${NEW_FILES} files)"
exit $EXIT_CODE
