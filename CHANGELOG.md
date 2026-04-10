## v0.1.1 (2026-04-10)

### Fix

- resolve pipeline crashes on Rivanna (unauthenticated mode, missing function, namespace filter)

## v0.1.0 (2026-04-09)

### Feat

- add arbitration, outcome, lifecycle modules with comprehensive tests
- add robust data fetching with checkpointing and full dataset config
- add YAML config for sample article selection
- API credential warnings, 3RR detection, and EDA improvements

### Fix

- forward WIKIPEDIA_ACCESS_TOKEN in sbatch --export
- SLURM job failures — common.sh sourcing, dash-prefixed cases, rate limiting
- code quality improvements and add missing tests
- Move dev/analysis dependencies to optional dev group
- improve 3RR violation detection to report worst violation per user

### Refactor

- consolidate 4 fetch scripts into src/fetchers.py
