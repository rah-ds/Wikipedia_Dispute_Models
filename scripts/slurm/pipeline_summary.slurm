#!/bin/bash
#SBATCH -A msds_ds6015                  # allocation
#SBATCH -p standard                     # CPU partition
#SBATCH --qos=class
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=512M
#SBATCH -c 1
#SBATCH -t 00:05:00                     # 5 minutes (just reads CSVs and sends email)
#SBATCH -o ./slurmlogs/pipeline_summary_%j.out
#SBATCH -e ./slurmlogs/pipeline_summary_%j.err
#SBATCH -J wiki-summary
#SBATCH --mail-type=NONE

## Pipeline summary: runs after all other jobs complete, sends one summary email.
## Submitted with --dependency=afterany:<last_job> by submit_all.sh.

_PROJECT="${WIKI_PROJECT_ROOT:-/scratch/rah5ff/Wikipedia_Dispute_Models}"
source "${_PROJECT}/scripts/slurm/common.sh"

echo "Generating pipeline summary report..."

# ---------------------------------------------------------------------------
# Read progress CSVs and tally results
# ---------------------------------------------------------------------------
report_job_type() {
    local job_type="$1"
    local progress_file="$PROGRESS_DIR/progress_${job_type}.csv"

    if [[ ! -f "$progress_file" ]]; then
        printf "  %-16s  No data (progress CSV not found)\n" "$job_type:"
        return
    fi

    local success
    success=$(grep -c ',SUCCESS,' "$progress_file" 2>/dev/null || echo 0)
    local failed
    failed=$(grep -c ',FAILED,' "$progress_file" 2>/dev/null || echo 0)
    local started
    started=$(grep -c ',STARTED,' "$progress_file" 2>/dev/null || echo 0)
    # Cases that started but didn't finish (started - success - failed, >= 0)
    local incomplete=$(( started - success - failed ))
    (( incomplete < 0 )) && incomplete=0

    printf "  %-16s  %d success, %d failed, %d incomplete\n" \
        "$job_type:" "$success" "$failed" "$incomplete"
}

# Build the report
BODY="Wikipedia Dispute Models — Pipeline Summary
═══════════════════════════════════════════════

Job Results
───────────
$(report_job_type fetch_full)
$(report_job_type arb_dfs)
$(report_job_type lifecycle)

Data Collected
──────────────
  arbitration:     $(count_outputs data/raw/arbitration) files, $(dir_size data/raw/arbitration)
  revisions:       $(count_outputs data/raw/revisions) files, $(dir_size data/raw/revisions)
  edit_wars:       $(count_outputs data/raw/edit_wars) files, $(dir_size data/raw/edit_wars)
  drn:             $(count_outputs data/raw/drn) files, $(dir_size data/raw/drn)
  dispute_venues:  $(count_outputs data/raw/dispute_venues) files, $(dir_size data/raw/dispute_venues)
  Total:           $(dir_size data/raw/)"

# Add failed cases detail
TOTAL_FAILED=0
FAILED_DETAIL=""
for job_type in fetch_full arb_dfs lifecycle; do
    pf="$PROGRESS_DIR/progress_${job_type}.csv"
    if [[ -f "$pf" ]]; then
        n=$(grep -c ',FAILED,' "$pf" 2>/dev/null || echo 0)
        TOTAL_FAILED=$((TOTAL_FAILED + n))
        if (( n > 0 )); then
            FAILED_DETAIL+="
  ${job_type} (${n} failed):
$(grep ',FAILED,' "$pf" | awk -F, '{printf "    - %s (job %s, task %s): %s\n", $4, $2, $3, $7}')"
        fi
    fi
done

if (( TOTAL_FAILED > 0 )); then
    BODY+="

Failed Cases (${TOTAL_FAILED} total)
─────────────────────────${FAILED_DETAIL}"
else
    BODY+="

No failures — all cases completed successfully."
fi

BODY+="

Pipeline submitted from: ${PROJECT_ROOT}
Timestamp: $(date -Iseconds)"

echo "$BODY"

# Determine overall status for subject line
if (( TOTAL_FAILED > 0 )); then
    SUBJECT="[Rivanna] Pipeline complete — ${TOTAL_FAILED} failures"
else
    SUBJECT="[Rivanna] Pipeline complete — all jobs succeeded"
fi

send_report "$SUBJECT" "$BODY"
echo ""
echo "Summary email sent."
