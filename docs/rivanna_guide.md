# Rivanna HPC Guide — Wikipedia Dispute Models

How to connect to UVA's Rivanna HPC cluster and run the Wikipedia data collection SLURM jobs.

## Prerequisites

1. **UVA computing ID** with Rivanna access
2. **Allocation**: `msds_ds6015` (or another valid allocation — check with `allocations` on Rivanna)
3. **VPN**: If off-grounds, install and connect to [UVA VPN](https://virginia.service-now.com/its?id=itsweb_kb_article&sys_id=f24e5cdfdb3acb804f32fb671d9619d0)
4. **Wikimedia API key** (recommended — gives 5,000 req/hr vs 500 unauthenticated)

## 1. Set Up SSH Access

Generate an SSH key pair and configure your `~/.ssh/config` so you can connect with a short alias.

```bash
# Generate a key (skip if you already have one)
ssh-keygen -t ed25519
```

Add to `~/.ssh/config`:

```
Host rivanna
    HostName login.hpc.virginia.edu
    User <your_computing_id>
    ServerAliveInterval 60
    IdentityFile ~/.ssh/id_ed25519
```

Copy your public key to Rivanna:

```bash
# macOS
ssh-copy-id -i ~/.ssh/id_ed25519 rivanna

# Windows
cat .\id_ed25519.pub | ssh rivanna "cat >> .ssh/authorized_keys"
```

Test it:

```bash
ssh rivanna 'echo "Connected as $(whoami)"'
```

## 2. Configure Your Local `.env`

In the project root, create a `.env` file with your credentials:

```dotenv
# Required
RIVANNA_ID=<your_computing_id>

# Recommended — Wikimedia API key for authenticated access
WIKI_API_KEY=<your_api_key>

# Optional — other credentials (see .env.example if available)
WIKIPEDIA_ACCESS_TOKEN=<same_as_api_key>
WIKI_EMAIL=<your_email>
```

This file is `.gitignore`d and gets synced to Rivanna via `make rivanna-sync`, where the SLURM jobs read it automatically.

## 3. Sync and Set Up Rivanna

```bash
# Push project files to /scratch/<id>/Wikipedia_Dispute_Models on Rivanna
make rivanna-sync

# One-time setup: installs uv, creates .venv, installs Python deps, runs smoke test
make rivanna-setup
```

The setup script installs everything into `/scratch/<id>/Wikipedia_Dispute_Models/`. This uses the SCRATCH partition (10 TB limit) rather than HOME (50 GB limit).

**Note**: If your computing ID is different from what's in the Makefile, update `RIVANNA_HOST` and the path in `scripts/slurm/common.sh` accordingly.

## 4. Submit Jobs

```bash
make rivanna-submit
```

This submits 4 SLURM jobs with proper dependency ordering:

| # | Job | What it does | Wall time | Depends on |
|---|-----|-------------|-----------|------------|
| 1 | `update_arb_cases` | Fetches case name list from Wikipedia | 15 min | — |
| 2 | `fetch_full` | Fetches 51-article dataset (revisions, arb, DRN) | 2 days | — |
| 3 | `fetch_arb_dfs` | DFS traversal per arb case (481 array tasks, 2 concurrent) | 2 days/task | Job 1 |
| 4 | `fetch_lifecycle` | Full dispute lifecycle per case (481 array tasks, 2 concurrent) | 2 days/task | Job 1 |

All jobs use **standard** (CPU) partition with `--qos=class` — data fetching is I/O-bound API calls, no GPU needed.

## 5. Monitor and Manage

```bash
# Job queue and data status summary
make rivanna-status

# Tail recent log files
make rivanna-logs

# Pull collected data from Rivanna to your local machine
make rivanna-pull

# Cancel all jobs and clear data on Rivanna
make rivanna-clean

# SSH into Rivanna for manual inspection
make rivanna-ssh
```

### Manual monitoring on Rivanna

```bash
# View your queued/running jobs
squeue -u $USER

# Detailed job info
sacct -j <job_id> --format=JobID,JobName,State,ExitCode,Elapsed,MaxRSS

# Follow a log in real-time
tail -f slurmlogs/fetch_full_<job_id>.out

# Count completed cases
ls data/raw/arbitration/arb_dfs_*.json 2>/dev/null | wc -l
```

## 6. Pull Data Locally

Once jobs complete (or while they're running):

```bash
make rivanna-pull
```

This syncs `data/raw/`, `slurmlogs/`, and `artifacts/` from Rivanna to your local project.

## Changing the Allocation

If your allocation is different from `msds_ds6015`, update the `#SBATCH -A` line in all 4 slurm files:

- `scripts/slurm/update_arb_cases.slurm`
- `scripts/slurm/fetch_full.slurm`
- `scripts/slurm/fetch_arb_dfs.slurm`
- `scripts/slurm/fetch_lifecycle.slurm`

Also check whether your allocation requires `--qos=class` (instructional allocations typically do). You can verify your allocations with:

```bash
ssh rivanna 'allocations'
ssh rivanna 'sacctmgr show associations user=$USER format=Account%30,Partition%20,QOS%30'
```

## Changing the Remote Project Path

The project defaults to `/scratch/<id>/Wikipedia_Dispute_Models`. To change this:

1. Update `RIVANNA_PROJECT` in the `Makefile`
2. Update the default path in `scripts/slurm/common.sh` (`WIKI_PROJECT_ROOT` variable)
3. Re-sync: `make rivanna-sync`

Or override at runtime without editing files:

```bash
sbatch --export=ALL,WIKI_PROJECT_ROOT=/scratch/$USER/my_custom_path \
    scripts/slurm/fetch_full.slurm
```

## Troubleshooting

### "Invalid account or account/partition combination"
Your allocation name or QOS is wrong. Check your allocations (`ssh rivanna 'allocations'`) and verify the `#SBATCH -A` and `--qos` lines match.

### "uv not found"
Run `make rivanna-setup` first.

### Job timed out
Increase the wall time in the `.slurm` file (`#SBATCH -t`). Max is 7 days for `standard` partition.

### Rate limit errors
The scripts have built-in exponential backoff. If still hitting limits, reduce array concurrency from `%2` to `%1` in `submit_all.sh`.

### Partial results / interrupted job
Fetch scripts save progress incrementally. Re-running skips already-fetched data. For array jobs, re-submit only the failed task indices:

```bash
# Re-run just case #42
sbatch --export=ALL --array=42 scripts/slurm/fetch_arb_dfs.slurm
```

## Data Output

All fetched data lands in `data/raw/` on Rivanna:

```
data/raw/
├── arbitration/      # Arbitration case pages + DFS results
├── revisions/        # Article revision histories
├── edit_wars/        # Edit war analysis results
├── drn/              # Dispute Resolution Noticeboard data
├── dispute_venues/   # Full lifecycle data (Talk → DRN → ANI → ArbCom)
├── ani_search/       # Administrators' Noticeboard search results
└── talk_pages/       # Article talk page revisions
```

Use `make rivanna-pull` to download this to your local machine.
