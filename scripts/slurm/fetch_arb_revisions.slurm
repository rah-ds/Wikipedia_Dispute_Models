#!/bin/bash
#SBATCH -A msds_ds6015                  # allocation
#SBATCH -p standard                     # CPU partition (API fetching, no GPU needed)
#SBATCH --qos=class
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=8G
#SBATCH -c 1
#SBATCH -t 2-00:00:00                   # 2 days max
#SBATCH -o ./slurmlogs/fetch_arb_revisions_%j.out
#SBATCH -e ./slurmlogs/fetch_arb_revisions_%j.err
#SBATCH -J wiki-arb-revisions
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=rah5ff@virginia.edu

## Fetch revision history + edit-war analysis for all arb case articles
## (~330+ unique articles derived from the full arbitration case corpus).
##
## Extends the 51-article sample to full arb coverage.
## Idempotent: skips articles already present in data/raw/revisions/.
##
## Submit from project root:
##   sbatch scripts/slurm/fetch_arb_revisions.slurm

_PROJECT="${WIKI_PROJECT_ROOT:-/scratch/rah5ff/Wikipedia_Dispute_Models}"
source "${_PROJECT}/scripts/slurm/common.sh"

log_progress "fetch_arb_revisions" "arb_corpus" "STARTED" "full arb article corpus"

echo "Starting fetch_arb_revisions: full arbitration article corpus"
echo "Estimated runtime: 4-12 hours (depends on how many are already fetched)"
echo ""

# Count files before
BEFORE_REV=$(count_outputs data/raw/revisions)
BEFORE_EW=$(count_outputs data/raw/edit_wars)

EXIT_CODE=0
uv run python scripts/fetch_arb_revisions.py \
    --notify-email "${NOTIFY_EMAIL:-rah5ff@virginia.edu}" \
    || EXIT_CODE=$?

# Count files after
AFTER_REV=$(count_outputs data/raw/revisions)
AFTER_EW=$(count_outputs data/raw/edit_wars)

NEW_REV=$((AFTER_REV - BEFORE_REV))
NEW_EW=$((AFTER_EW - BEFORE_EW))
DETAILS="new_rev=${NEW_REV},new_ew=${NEW_EW},size=$(dir_size data/raw/)"

# Check stderr for 429 rate-limit errors
ERR_FILE="slurmlogs/fetch_arb_revisions_${SLURM_JOB_ID}.err"
N429=$(grep -c 'Http response status 429\|status_code.*429' "$ERR_FILE" 2>/dev/null || echo 0)

if [[ $EXIT_CODE -eq 0 ]]; then
    log_progress "fetch_arb_revisions" "arb_corpus" "SUCCESS" "$DETAILS"

    REPORT="Wikipedia Dispute Models — fetch_arb_revisions Complete
═══════════════════════════════════════════════════════
Job ID:      $SLURM_JOB_ID
Node:        $SLURM_NODELIST

New revision files:   $NEW_REV
New edit-war files:   $NEW_EW
Total 429 errors:     $N429

Data size after run:  $(dir_size data/raw/)
"
    echo "$REPORT"
    uv run python scripts/slurm/send_email.py \
        --to "${NOTIFY_EMAIL:-rah5ff@virginia.edu}" \
        --subject "[Rivanna] fetch_arb_revisions DONE — ${NEW_REV} new rev files" \
        --body "$REPORT" 2>/dev/null || true
else
    log_progress "fetch_arb_revisions" "arb_corpus" "FAILED" "exit_code=${EXIT_CODE}"

    REPORT="Wikipedia Dispute Models — fetch_arb_revisions FAILED
Job ID:  $SLURM_JOB_ID
Exit:    $EXIT_CODE
Details: $DETAILS
"
    echo "$REPORT"
    uv run python scripts/slurm/send_email.py \
        --to "${NOTIFY_EMAIL:-rah5ff@virginia.edu}" \
        --subject "[Rivanna] fetch_arb_revisions FAILED (exit $EXIT_CODE)" \
        --body "$REPORT" 2>/dev/null || true
fi

exit $EXIT_CODE
