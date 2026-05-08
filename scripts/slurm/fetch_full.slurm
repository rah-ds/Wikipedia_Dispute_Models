#!/bin/bash
#SBATCH -A msds_ds6015                  # allocation
#SBATCH -p standard                     # CPU partition (no GPU needed for API fetching)
#SBATCH --qos=class
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=8G
#SBATCH -c 1
#SBATCH -t 2-00:00:00                   # 2 days
#SBATCH -o ./slurmlogs/fetch_full_%j.out
#SBATCH -e ./slurmlogs/fetch_full_%j.err
#SBATCH -J wiki-fetch-full
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=rah5ff@virginia.edu

## Fetch full dataset: 51 articles (27 high-conflict + 24 low-conflict)
## plus arbitration cases and DRN data.
## Equivalent to: make fetch-full

_PROJECT="${WIKI_PROJECT_ROOT:-/scratch/rah5ff/Wikipedia_Dispute_Models}"
source "${_PROJECT}/scripts/slurm/common.sh"

log_progress "fetch_full" "full_dataset" "STARTED" "51 articles from full_articles.yaml"

echo "Starting fetch-full: 51 articles from artifacts/full_articles.yaml"
echo "Estimated runtime: 2-4 hours"
echo ""

# Count files before
BEFORE_REV=$(count_outputs data/raw/revisions)
BEFORE_ARB=$(count_outputs data/raw/arbitration)
BEFORE_EW=$(count_outputs data/raw/edit_wars)
BEFORE_DRN=$(count_outputs data/raw/drn)

EXIT_CODE=0
uv run python scripts/fetch_from_config.py --config artifacts/full_articles.yaml || EXIT_CODE=$?

# Count files after
AFTER_REV=$(count_outputs data/raw/revisions)
AFTER_ARB=$(count_outputs data/raw/arbitration)
AFTER_EW=$(count_outputs data/raw/edit_wars)
AFTER_DRN=$(count_outputs data/raw/drn)

NEW_REV=$((AFTER_REV - BEFORE_REV))
NEW_ARB=$((AFTER_ARB - BEFORE_ARB))
NEW_EW=$((AFTER_EW - BEFORE_EW))
NEW_DRN=$((AFTER_DRN - BEFORE_DRN))

DETAILS="rev=${NEW_REV},arb=${NEW_ARB},ew=${NEW_EW},drn=${NEW_DRN},size=$(dir_size data/raw/)"

# Check stderr for 429 rate-limit errors
ERR_FILE="slurmlogs/fetch_full_${SLURM_JOB_ID}.err"
N429=$(grep -c 'Http response status 429\|status_code.*429' "$ERR_FILE" 2>/dev/null || echo 0)

if [[ $EXIT_CODE -eq 0 ]]; then
    log_progress "fetch_full" "full_dataset" "SUCCESS" "$DETAILS"
    print_summary "fetch_full" "full_dataset" "SUCCESS"

    REPORT="Wikipedia Dispute Models — fetch_full Complete
═══════════════════════════════════════════

Status:      SUCCESS

Output files (new / total):
  Arbitration: +${NEW_ARB} / ${AFTER_ARB} files
  Revisions:   +${NEW_REV} / ${AFTER_REV} files
  Edit wars:   +${NEW_EW} / ${AFTER_EW} files
  DRN:         +${NEW_DRN} / ${AFTER_DRN} files
  Total size:  $(dir_size data/raw/)

Rate-limit 429 errors: ${N429}"

    send_report "[Rivanna] fetch_full — COMPLETE" "$REPORT"
else
    log_progress "fetch_full" "full_dataset" "FAILED" "exit_code=${EXIT_CODE},${DETAILS}"
    print_summary "fetch_full" "full_dataset" "FAILED (exit $EXIT_CODE)"

    LAST_ERR=$(tail -20 "$ERR_FILE" 2>/dev/null || echo "(no stderr)")
    REPORT="Wikipedia Dispute Models — fetch_full FAILED
═══════════════════════════════════════════

Status:      FAILED (exit code ${EXIT_CODE})

Partial output (new / total):
  Arbitration: +${NEW_ARB} / ${AFTER_ARB} files
  Revisions:   +${NEW_REV} / ${AFTER_REV} files
  Edit wars:   +${NEW_EW} / ${AFTER_EW} files
  DRN:         +${NEW_DRN} / ${AFTER_DRN} files
  Total size:  $(dir_size data/raw/)

Rate-limit 429 errors: ${N429}

Last 20 lines of stderr:
${LAST_ERR}"

    send_report "[Rivanna] fetch_full — FAILED (exit $EXIT_CODE)" "$REPORT"
fi

# Warn separately about excessive 429s
if (( N429 > 5 )); then
    send_report "[Rivanna] WARNING: ${N429} rate-limit 429s in fetch_full" \
        "fetch_full encountered ${N429} HTTP 429 rate-limit errors.\nThis may indicate the inter-request delay needs to be increased.\n\nCheck: tail -50 $ERR_FILE"
fi

echo ""
echo "Output files (new / total):"
echo "  Arbitration: +${NEW_ARB} / ${AFTER_ARB} files"
echo "  Revisions:   +${NEW_REV} / ${AFTER_REV} files"
echo "  Edit wars:   +${NEW_EW} / ${AFTER_EW} files"
echo "  DRN:         +${NEW_DRN} / ${AFTER_DRN} files"
echo "  Total size:  $(dir_size data/raw/)"

exit $EXIT_CODE
