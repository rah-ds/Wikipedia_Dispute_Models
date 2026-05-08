# Rivanna Run Estimates — April 10, 2026

> Historical planning note. These estimates describe the April large-pull
> submission strategy, not the final handoff state. For current coverage and
> remaining data gaps, see [`handoff.md`](handoff.md).

## Current Pipeline (Serialized)

Jobs run one at a time to avoid Wikipedia API rate limit (429) exhaustion.

```
update_arb_cases (done) → fetch_full (RUNNING) → arb_dfs (481 cases) → lifecycle (481 cases)
```

## Timing Data from Previous Run

| Job | Case | Elapsed | Notes |
|-----|------|---------|-------|
| arb_dfs | `-Ril-` | 2 min | Small case, no linked articles |
| arb_dfs | `168.209.97.34` | 2.5 min | Small case |
| arb_dfs | `172` | 2.5 min | Small case |
| arb_dfs | `172 2` | 3.7 hrs | Large — rate-limited (ran concurrent) |
| arb_dfs | `194x144x90x118` | 1.1 hrs | Medium |
| arb_dfs | `8bitJake` | 1.3 min | Small |
| arb_dfs | `A Man In Black` | 1.7 hrs | 51 linked articles, 2372 revisions |
| arb_dfs | `A Nobody` | 10.8 min | 11 linked articles, 997 revisions |
| lifecycle | `-Ril-` | 6.7 hrs | Full lifecycle (Talk → DRN → ANI → ArbCom), ran concurrent |
| fetch_full | — | 8+ hrs | Was rate-limited; didn't finish (ran concurrent) |

## Estimates (Serialized — No Concurrent Rate Limit Pressure)

### fetch_full (51 articles)

- **Previous attempt**: 8+ hours and didn't finish (competing with 2 other jobs)
- **Estimated solo**: **4–8 hours** (much less sleeping on 429s)
- **Walltime limit**: 48 hours
- **Expected completion**: ~Apr 10, 12:00–16:00 ET

### arb_dfs (481 cases, 5 already done → 476 remaining)

Per-case time varies enormously (1 min → 1.7 hrs). Using solo (non-rate-limited) estimates:

| Case Size | Estimated Time | % of Cases | Count |
|-----------|---------------|------------|-------|
| Small (no linked articles) | 1–3 min | ~40% | ~192 |
| Medium (5–15 articles) | 10–30 min | ~40% | ~192 |
| Large (50+ articles) | 1–2 hrs | ~20% | ~92 |

**Conservative estimate**: avg ~20 min/case × 476 = **~160 hours (6.6 days)**
**Optimistic estimate**: avg ~12 min/case × 476 = **~95 hours (4 days)**

- **Walltime limit**: 48 hours per task (plenty for any single case)
- **Expected start**: After fetch_full completes (~Apr 10 afternoon)
- **Expected completion**: ~Apr 14–17

### lifecycle (481 cases, 1 already done → 480 remaining)

Only 1 data point: `-Ril-` took 6.7 hrs (but was heavily rate-limited by concurrency).

- **Estimated solo per case**: 1–3 hours (Talk + DRN + ANI + ArbCom stages)
- **Conservative estimate**: avg ~2 hrs × 480 = **~960 hours (40 days)**
- **Optimistic estimate**: avg ~1 hr × 480 = **~480 hours (20 days)**
- **Expected start**: After arb_dfs completes (~Apr 14–17)
- **Expected completion**: May 4–27

> **Note**: lifecycle may not be feasible in a single submission window.
> Consider running arb_dfs to completion first, then assessing if lifecycle
> scope can be reduced (fewer stages, or only cases with confirmed escalation).

## Check-In Schedule

| When | What to Check | Command |
|------|--------------|---------|
| **Apr 10, 10:00 ET** | fetch_full progressing without 429 sleeps? | `make rivanna-logs` |
| **Apr 10, 16:00 ET** | fetch_full done? arb_dfs starting? | `make rivanna-status` |
| **Apr 11, morning** | arb_dfs throughput — how many cases/hour? | `make rivanna-status` |
| **Apr 12, morning** | arb_dfs ~25% done? Any failures? | `make rivanna-status` |
| **Apr 14, morning** | arb_dfs ~75% done? Estimate lifecycle feasibility | `make rivanna-status` |
| **Apr 16–17** | arb_dfs complete? lifecycle starting? | `make rivanna-status` |
| **Weekly** | lifecycle progress, check for 429 patterns | `make rivanna-status` + `make rivanna-logs` |

## Key Risks

1. **Walltime timeout on fetch_full**: Unlikely now (48hr limit, solo run should finish in 4–8hr)
2. **Rate limits still hitting**: Even solo, MediaWiki API throttling can occur. Check `.err` logs for `Retryable error: ... Waiting ...` lines, HTTP 429s, or the `running unauthenticated (500 req/hour limit)` warning
3. **Lifecycle total runtime**: At 20–40 days, may exceed practical window. Mitigation: reduce scope or increase concurrency (`%2`) once arb_dfs is done
4. **SLURM allocation limits**: Check if your allocation has monthly hour limits (`sacct` or allocation dashboard)
5. **Skip-completed logic**: If a case output file exists but is corrupt/incomplete, it will be skipped. Check file sizes if results look wrong

## Quick Commands

```bash
make rivanna-status     # Full status report
make rivanna-logs       # Tail recent .out logs
make rivanna-pull       # Download data to local machine

# Check rate limit behavior in error logs
ssh rah5ff@login.hpc.virginia.edu \
  'tail -20 /scratch/rah5ff/Wikipedia_Dispute_Models/slurmlogs/fetch_full_11441912.err'

# Check if authenticated (should NOT see "unauthenticated" warning)
ssh rah5ff@login.hpc.virginia.edu \
  'head -20 /scratch/rah5ff/Wikipedia_Dispute_Models/slurmlogs/fetch_full_11441912.err'
```
