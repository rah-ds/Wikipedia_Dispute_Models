#!/bin/bash
#SBATCH -A msds_ds6015                  # allocation
#SBATCH -p standard                     # CPU partition (no GPU needed for API fetching)
#SBATCH --qos=class
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=8G
#SBATCH -c 1
#SBATCH -t 06:00:00                     # 6 hours (estimate: 2-4 hrs for 51 articles)
#SBATCH -o ./slurmlogs/fetch_full_%j.out
#SBATCH -e ./slurmlogs/fetch_full_%j.err
#SBATCH -J wiki-fetch-full

## Fetch full dataset: 51 articles (27 high-conflict + 24 low-conflict)
## plus arbitration cases and DRN data.
## Equivalent to: make fetch-full

source "$(dirname "$0")/common.sh"

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

if [[ $EXIT_CODE -eq 0 ]]; then
    log_progress "fetch_full" "full_dataset" "SUCCESS" "$DETAILS"
    print_summary "fetch_full" "full_dataset" "SUCCESS"
else
    log_progress "fetch_full" "full_dataset" "FAILED" "exit_code=${EXIT_CODE},${DETAILS}"
    print_summary "fetch_full" "full_dataset" "FAILED (exit $EXIT_CODE)"
fi

echo ""
echo "Output files (new / total):"
echo "  Arbitration: +${NEW_ARB} / ${AFTER_ARB} files"
echo "  Revisions:   +${NEW_REV} / ${AFTER_REV} files"
echo "  Edit wars:   +${NEW_EW} / ${AFTER_EW} files"
echo "  DRN:         +${NEW_DRN} / ${AFTER_DRN} files"
echo "  Total size:  $(dir_size data/raw/)"

exit $EXIT_CODE
