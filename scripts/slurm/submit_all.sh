#!/bin/bash
# submit_all.sh — Submit all Wikipedia data-fetching jobs to SLURM
#
# This orchestrates the full pipeline with proper dependencies:
#   1. update_arb_cases  (quick, ~1 min)
#   2. fetch_full        (independent, ~2-4 hrs)
#   3. fetch_arb_dfs     (depends on step 1, array job)
#   4. fetch_lifecycle    (depends on step 1, array job)
#
# Usage:
#   export WIKI_API_KEY='your-key-here'   # recommended for 5,000+ req/hr
#   bash scripts/slurm/submit_all.sh
#
# Or submit individual jobs — see README.md for details.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Load .env file if present (provides WIKI_API_KEY, etc.)
# ---------------------------------------------------------------------------
if [[ -f .env ]]; then
    set -a
    source .env
    set +a
    echo "Loaded credentials from .env"
fi

# ---------------------------------------------------------------------------
# Validate environment
# ---------------------------------------------------------------------------
if [[ -z "${WIKI_API_KEY:-}" ]] && [[ -z "${PYWIKIBOT_PASSWORD:-}" ]]; then
    echo "WARNING: No API credentials set. Jobs will use unauthenticated access (500 req/hr)."
    echo "  To fix: add WIKI_API_KEY to .env or export it before running."
    echo ""
fi

# Ensure slurmlogs directory exists
mkdir -p slurmlogs

# Build the --export flag to forward credentials
EXPORT_VARS="ALL"
if [[ -n "${WIKI_API_KEY:-}" ]]; then
    EXPORT_VARS="ALL,WIKI_API_KEY=$WIKI_API_KEY"
fi
if [[ -n "${PYWIKIBOT_PASSWORD:-}" ]]; then
    EXPORT_VARS="ALL,PYWIKIBOT_PASSWORD=$PYWIKIBOT_PASSWORD"
fi

echo "========================================="
echo "  Wikipedia Arbitration — Job Submission"
echo "========================================="
echo ""

# ---------------------------------------------------------------------------
# Step 1: Update arbitration cases list
# ---------------------------------------------------------------------------
echo "[1/4] Submitting: update_arb_cases"
UPDATE_JOB=$(sbatch --export="$EXPORT_VARS" \
    --parsable \
    "$SCRIPT_DIR/update_arb_cases.slurm")
echo "  Job ID: $UPDATE_JOB"

# ---------------------------------------------------------------------------
# Step 2: Fetch full dataset (independent — no dependency on step 1)
# ---------------------------------------------------------------------------
echo "[2/4] Submitting: fetch_full"
FULL_JOB=$(sbatch --export="$EXPORT_VARS" \
    --parsable \
    "$SCRIPT_DIR/fetch_full.slurm")
echo "  Job ID: $FULL_JOB"

# ---------------------------------------------------------------------------
# Step 3: Fetch arb DFS (depends on step 1 for arb_cases.txt)
# ---------------------------------------------------------------------------
# We need arb_cases.txt to exist to determine the array size.
# If it already exists, use it; otherwise wait for step 1 and use a default.
if [[ -f artifacts/arb_cases.txt ]]; then
    TOTAL_CASES=$(wc -l < artifacts/arb_cases.txt | tr -d ' ')
else
    # arb_cases.txt doesn't exist yet — estimate ~480 cases
    # The actual array will be capped by the file length at runtime
    TOTAL_CASES=500
    echo "  NOTE: artifacts/arb_cases.txt not found yet. Using estimate of $TOTAL_CASES cases."
    echo "  The update_arb_cases job will create it before array tasks start."
fi

echo "[3/4] Submitting: fetch_arb_dfs (array 1-${TOTAL_CASES}, max 1 concurrent)"
ARB_DFS_JOB=$(sbatch --export="$EXPORT_VARS" \
    --dependency=afterok:${UPDATE_JOB} \
    --array=1-${TOTAL_CASES}%1 \
    --parsable \
    "$SCRIPT_DIR/fetch_arb_dfs.slurm")
echo "  Job ID: $ARB_DFS_JOB"

# ---------------------------------------------------------------------------
# Step 4: Fetch lifecycle (depends on step 1 for arb_cases.txt)
# ---------------------------------------------------------------------------
echo "[4/4] Submitting: fetch_lifecycle (array 1-${TOTAL_CASES}, max 1 concurrent)"
LIFECYCLE_JOB=$(sbatch --export="$EXPORT_VARS" \
    --dependency=afterok:${UPDATE_JOB} \
    --array=1-${TOTAL_CASES}%1 \
    --parsable \
    "$SCRIPT_DIR/fetch_lifecycle.slurm")
echo "  Job ID: $LIFECYCLE_JOB"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "========================================="
echo "  All jobs submitted!"
echo "========================================="
echo ""
echo "  Job IDs:"
echo "    update_arb_cases : $UPDATE_JOB"
echo "    fetch_full       : $FULL_JOB"
echo "    fetch_arb_dfs    : $ARB_DFS_JOB (array)"
echo "    fetch_lifecycle  : $LIFECYCLE_JOB (array)"
echo ""
echo "  Dependencies:"
echo "    fetch_full       -> runs immediately"
echo "    fetch_arb_dfs    -> waits for update_arb_cases ($UPDATE_JOB)"
echo "    fetch_lifecycle  -> waits for update_arb_cases ($UPDATE_JOB)"
echo ""
echo "  Monitor:"
echo "    squeue -u \$USER                     # view queue"
echo "    sacct -j $UPDATE_JOB,$FULL_JOB,$ARB_DFS_JOB,$LIFECYCLE_JOB  # job accounting"
echo "    tail -f slurmlogs/fetch_full_${FULL_JOB}.out   # follow fetch_full output"
echo ""
echo "  Cancel all:"
echo "    scancel $UPDATE_JOB $FULL_JOB $ARB_DFS_JOB $LIFECYCLE_JOB"
