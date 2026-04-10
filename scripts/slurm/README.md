# Running Data Fetchers on Rivanna (SLURM)

SLURM batch scripts for running Wikipedia data-fetching jobs on UVA's Rivanna HPC cluster.

## Prerequisites

- **Rivanna access** with allocation `msds_ds6015` and `--qos=class`
- **VPN** connected (if off-grounds) — see [Rivanna guide](../../docs/rivanna_guide.md)
- **Repo synced** to `/scratch/<id>/Wikipedia_Dispute_Models` via `make rivanna-sync`
- **(Recommended)** A Wikimedia API key for authenticated access (5,000+ req/hr vs 500)

## Quick Start

```bash
# 1. SSH into Rivanna
ssh rivanna

# 2. Or use the Makefile from your local machine:
make rivanna-sync     # sync project to /scratch/<id>/Wikipedia_Dispute_Models
make rivanna-setup    # one-time setup (installs uv, creates venv)
make rivanna-submit   # submit all SLURM jobs
make rivanna-status   # check progress
make rivanna-pull     # download collected data locally
make rivanna-clean    # cancel jobs and clear data
```

## Files

| File | Purpose |
|------|---------|
| `setup_rivanna.sh` | One-time interactive setup (installs uv, creates venv, installs deps) |
| `common.sh` | Shared environment setup sourced by all SLURM scripts |
| `submit_all.sh` | Orchestrates all jobs with proper dependency ordering |
| `update_arb_cases.slurm` | Fetches case name list from Wikipedia (~1 min) |
| `fetch_full.slurm` | Fetches 51-article dataset (~2-4 hrs) |
| `fetch_arb_dfs.slurm` | Array job: DFS traversal per arbitration case (~2 hrs/case) |
| `fetch_lifecycle.slurm` | Array job: full dispute lifecycle per case (~3 hrs/case) |

## Jobs Overview

### Pipeline

```
submit_all.sh
  ├── update_arb_cases.slurm    (runs first, ~1 min)
  ├── fetch_full.slurm          (runs immediately, independent)
  ├── fetch_arb_dfs.slurm       (waits for update_arb_cases, array job)
  └── fetch_lifecycle.slurm     (waits for update_arb_cases, array job)
```

### Resource Usage

All jobs use the **standard** (CPU) partition — data fetching is I/O-bound API calls, no GPU needed.

| Job | Partition | Memory | Wall Time | Notes |
|-----|-----------|--------|-----------|-------|
| update_arb_cases | standard | 2 GB | 15 min | Single quick API call |
| fetch_full | standard | 8 GB | 2 days | 51 articles + arb cases + DRN |
| fetch_arb_dfs | standard | 8 GB | 2 days/task | Array job, 2 concurrent tasks |
| fetch_lifecycle | standard | 8 GB | 2 days/task | Array job, 2 concurrent tasks |

### Array Jobs

`fetch_arb_dfs` and `fetch_lifecycle` are **SLURM array jobs** — each array task processes one arbitration case from `artifacts/arb_cases.txt`. The `%2` concurrency throttle ensures at most 2 tasks run simultaneously, respecting Wikipedia's API rate limits.

## Submitting Individual Jobs

Instead of `submit_all.sh`, you can submit jobs individually:

```bash
# Just the full 51-article fetch:
sbatch --export=ALL,WIKI_API_KEY=$WIKI_API_KEY scripts/slurm/fetch_full.slurm

# Update case list, then run DFS on all cases:
sbatch scripts/slurm/update_arb_cases.slurm
# Wait for it to complete, then:
TOTAL=$(wc -l < artifacts/arb_cases.txt)
sbatch --export=ALL,WIKI_API_KEY=$WIKI_API_KEY \
    --array=1-${TOTAL}%2 \
    scripts/slurm/fetch_arb_dfs.slurm

# Run DFS on just the first 5 cases:
sbatch --export=ALL,WIKI_API_KEY=$WIKI_API_KEY \
    --array=1-5 \
    scripts/slurm/fetch_arb_dfs.slurm

# Re-run a single failed case (e.g., case #42):
sbatch --export=ALL,WIKI_API_KEY=$WIKI_API_KEY \
    --array=42 \
    scripts/slurm/fetch_arb_dfs.slurm
```

## Monitoring

```bash
# View your queued/running jobs
squeue -u $USER

# Detailed job info
sacct -j <job_id> --format=JobID,JobName,State,ExitCode,Elapsed,MaxRSS

# Follow a job's output in real-time
tail -f slurmlogs/fetch_full_<job_id>.out

# Check array job status
sacct -j <array_job_id> --format=JobID%20,State,ExitCode,Elapsed

# See how many cases have completed
ls data/raw/arbitration/arb_dfs_*.json 2>/dev/null | wc -l
ls data/raw/dispute_venues/lifecycle_*.json 2>/dev/null | wc -l
```

## API Credentials

For authenticated API access (5,000+ req/hr vs 500 unauthenticated), set `WIKI_API_KEY`:

```bash
# Option 1: Export before submitting (session-only)
export WIKI_API_KEY='your-key-here'
bash scripts/slurm/submit_all.sh

# Option 2: Add to ~/.bashrc (persistent)
echo 'export WIKI_API_KEY="your-key-here"' >> ~/.bashrc
source ~/.bashrc

# Option 3: Pass directly to sbatch
sbatch --export=ALL,WIKI_API_KEY=your-key-here scripts/slurm/fetch_full.slurm
```

The `submit_all.sh` script automatically forwards `WIKI_API_KEY` and `PYWIKIBOT_PASSWORD` to all submitted jobs via `--export`.

## Data Output

All fetched data is saved under `data/raw/`:

```
data/raw/
├── arbitration/     # Arbitration case pages + DFS results
├── revisions/       # Article revision histories
├── edit_wars/       # Edit war analysis results
├── drn/             # Dispute Resolution Noticeboard data
├── dispute_venues/  # Full lifecycle data (Talk → DRN → ANI → ArbCom)
├── ani_search/      # Administrators' Noticeboard search results
└── talk_pages/      # Article talk page revisions
```

## Troubleshooting

### Job failed with rate limit errors
The scripts have built-in exponential backoff (up to 10 retries, 5 min max delay). If still hitting limits, reduce the array concurrency:
```bash
# Use %1 instead of %2 for single-task execution
sbatch --array=1-${TOTAL}%1 scripts/slurm/fetch_arb_dfs.slurm
```

### Job timed out
Increase the wall time:
```bash
sbatch --time=04:00:00 --array=42 scripts/slurm/fetch_arb_dfs.slurm
```

### "uv not found" error
Run the setup script first:
```bash
bash scripts/slurm/setup_rivanna.sh
```

### Partial results / interrupted job
The fetch scripts save progress incrementally. Re-running will skip already-fetched data (use `--force` to re-fetch). For array jobs, just re-submit the failed task indices.

### Custom project location
The project defaults to `/scratch/<id>/Wikipedia_Dispute_Models`. Override with:
```bash
sbatch --export=ALL,WIKI_PROJECT_ROOT=/scratch/$USER/my_path \
    scripts/slurm/fetch_full.slurm
```
