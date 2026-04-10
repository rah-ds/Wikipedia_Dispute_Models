#!/bin/bash
#SBATCH -A msds_ds6015                  # allocation
#SBATCH -p standard                     # CPU partition
#SBATCH --qos=class
#SBATCH --ntasks=1
#SBATCH --nodes=1
#SBATCH --mem=2G
#SBATCH -c 1
#SBATCH -t 00:15:00                     # 15 minutes (usually takes < 1 min)
#SBATCH -o ./slurmlogs/update_arb_cases_%j.out
#SBATCH -e ./slurmlogs/update_arb_cases_%j.err
#SBATCH -J wiki-update-cases

## Fetch the list of all Wikipedia arbitration case names from
## Category:Wikipedia_arbitration_cases and save to artifacts/arb_cases.txt.
## This is a prerequisite for fetch_arb_dfs and fetch_lifecycle array jobs.

_PROJECT="${WIKI_PROJECT_ROOT:-/scratch/rah5ff/Wikipedia_Dispute_Models}"
source "${_PROJECT}/scripts/slurm/common.sh"

echo "Fetching arbitration case list from Wikipedia..."

uv run python scripts/fetch_arb_cases_list.py --output artifacts/arb_cases.txt

CASE_COUNT=$(wc -l < artifacts/arb_cases.txt | tr -d ' ')
echo ""
echo "Done. $CASE_COUNT cases saved to artifacts/arb_cases.txt"
