# Survival Analysis for Wikipedia Dispute Resolution

## Why Survival Analysis?

A dispute doesn't just end — it ends *eventually*, or it doesn't. Standard classification tells you whether a case resulted in sanctions. Survival analysis tells you **how long it took**, accounts for **cases that are still open**, and lets you ask whether a factor makes resolution faster or slower.

Three properties make this the right tool here:

1. **Time matters.** A case that escalates in two weeks is qualitatively different from one that drags through ANI for six months before ArbCom accepts it. Duration is signal.

2. **Right censoring is real.** Some cases in our dataset are still open (`outcome_status = "open"` or `"unknown"`). We can't just drop them — they contribute information up to the observation date. KM and Cox handle this correctly; logistic regression doesn't.

3. **Escalation is sequential.** The dispute pathway Talk → DRN → ANI → ArbCom has multiple transitions, each with its own hazard. A multi-state model captures each stage's dynamics independently.

---

## The Three Questions

### Q1: How long until an ArbCom case closes?

**Event:** case formally closed
**Duration:** days from case filing to closure
**Censoring:** cases still open as of observation date (use today as right-censor)

This is the simplest analysis and can be run on current data once we extract timestamps from the raw JSON revision history.

**Expected result:** median ~120–200 days based on Wikipedia ArbCom historical records, with high variance. Cases involving sanctions likely take longer (more deliberation required).

### Q2: What factors speed up or slow down resolution?

**Cox proportional hazards model** with the following covariates (all known before outcome):

| Covariate | Expected direction | Rationale |
|---|---|---|
| `participants_count` | HR < 1 (slower) | More parties → harder to reach consensus |
| `total_revisions` | HR < 1 (slower) | Higher volume → more complex case |
| `participants_with_blocks` | HR < 1 (slower) | Prior sanctions → more contentious dispute |
| `main_content_length` | ambiguous | Longer filings could go either way |
| `ani_mentions` | HR > 1 (faster) | ANI involvement → conduct case → faster resolution path |
| `has_evidence_page` | HR < 1 (slower) | Formal evidence phase added → more deliberate process |
| `has_workshop_page` | HR < 1 (slower) | Workshop phase added → more deliberate process |

Interpret hazard ratios:
- HR = 1.5 → factor associated with resolving 50% faster
- HR = 0.7 → factor associated with resolving 43% slower

### Q3: What predicts escalation between stages?

**This is the most interesting question and requires data we don't yet have.**

See §"Selection Bias" below. Answering this requires disputes that *did not* escalate as a comparison group.

---

## Data Structure

### What we have

```
data/raw/arbitration/<CaseName>.json
  └── pages.main.revisions[]
        ├── timestamp     ← case_opened (first revision)
        └── ...           ← case_closed (last revision, approximation)
```

The `scripts/survival_analysis.py` script extracts these timestamps directly from the raw JSON. Using last-revision as case_closed is an approximation — the actual closure date would come from parsing the `{{ArbCom case closed}}` template or equivalent, which is a future improvement.

### What's still needed for escalation analysis

For modeling Talk → DRN → ANI → ArbCom transitions, you need:

- **Talk page entry timestamp:** first edit to the article's talk page that triggered dispute
- **DRN filing date:** opening post of the DRN thread
- **ANI report date:** opening post of the ANI thread
- **ArbCom acceptance date:** when the committee formally accepted the case

The `scripts/fetch_dispute_lifecycle.py` script fetches the raw pages; extracting structured timestamps from them requires parsing the wikitext headers of each venue's thread.

---

## Kaplan-Meier: Descriptive Curves

KM estimates the survival function S(t) = P(case still open at time t) non-parametrically. No model assumptions needed.

**Useful group comparisons:**

```python
from lifelines import KaplanMeierFitter
from lifelines.statistics import logrank_test

# Overall curve
kmf = KaplanMeierFitter()
kmf.fit(df["duration_days"], event_observed=df["event_observed"])
print(f"Median resolution time: {kmf.median_survival_time_:.0f} days")

# Compare sanctioned vs unsanctioned cases
T_s = df.loc[df["was_sanctioned"] == 1, "duration_days"]
E_s = df.loc[df["was_sanctioned"] == 1, "event_observed"]
T_u = df.loc[df["was_sanctioned"] == 0, "duration_days"]
E_u = df.loc[df["was_sanctioned"] == 0, "event_observed"]

result = logrank_test(T_s, T_u, event_observed_A=E_s, event_observed_B=E_u)
print(f"Log-rank p-value: {result.p_value:.4f}")
```

**Other useful groupings:**
- By whether an evidence page was created (procedural complexity)
- By number of participants (binned: <20, 20–50, >50)
- By decade (2005–2010 vs 2011–2015 vs 2016–2020) — has ArbCom gotten faster?
- By topic area (if we add topic classification from article categories)

---

## Cox Proportional Hazards: Inferential Model

Cox regression estimates which covariates accelerate or delay the event, without assuming a specific baseline hazard shape (semi-parametric).

```python
from lifelines import CoxPHFitter

cph = CoxPHFitter()
cph.fit(
    df[["duration_days", "event_observed"] + COVARIATES],
    duration_col="duration_days",
    event_col="event_observed",
)
cph.print_summary()
cph.plot_covariate_groups("participants_count", values=[10, 30, 60, 100])
```

**Checking the proportional hazards assumption:**

Cox assumes the hazard ratio between any two cases is constant over time (the "parallel curves" assumption). Test it:

```python
from lifelines.statistics import proportional_hazard_test
result = proportional_hazard_test(cph, df, time_transform="rank")
# p < 0.05 → violation → consider time-varying covariates or stratified Cox
```

If `participants_count` violates the assumption, try stratifying on a binned version:

```python
df["participant_tier"] = pd.cut(df["participants_count"], bins=[0, 20, 50, 300], labels=["small", "medium", "large"])
cph.fit(..., strata=["participant_tier"])
```

---

## Multi-State Model: Full Escalation Pathway

The full lifecycle is a multi-state process where each transition has its own hazard:

```
[Talk] --h₁--> [DRN]  --h₃--> [ANI] --h₄--> [ArbCom] --h₅--> [Closed]
         └-----h₂----> [ANI]
         └-----h₂'---> [ArbCom] (direct skip)
```

Each arrow is a separate hazard function. You fit one Cox model per transition.

```python
# Transition: Talk → DRN
t1_df = df[df["reached_talk"]].copy()
t1_df["event"] = df["reached_drn"].astype(int)
cph_t1 = CoxPHFitter().fit(t1_df, duration_col="days_at_talk", event_col="event")

# Transition: DRN → ANI
t2_df = df[df["reached_drn"]].copy()
t2_df["event"] = df["reached_ani"].astype(int)
cph_t2 = CoxPHFitter().fit(t2_df, duration_col="days_at_drn", event_col="event")
# ... etc.
```

`lifelines` doesn't have native multi-state support, but each transition can be modeled independently since Wikipedia disputes are non-recurrent within a single dispute (a case doesn't go backwards from ArbCom to DRN).

---

## Selection Bias: The Central Limitation

**Every case in `data/raw/arbitration/` reached ArbCom.**

This creates a fundamental selection bias for escalation modeling:

- All our ArbCom cases were contentious enough to escalate all the way up.
- We have no cases that were resolved at Talk, DRN, or ANI without further escalation.
- Any model trained on this data cannot learn "what makes a dispute escalate?" — it can only learn "within cases that already escalated, what predicts the outcome?"

**To answer "did it escalate?" you need:**

| Positive class | Negative class |
|---|---|
| DRN cases that escalated to ANI/ArbCom | DRN cases resolved without escalation |
| ANI reports that escalated to ArbCom | ANI reports closed without referral |

**How to get the negative class:**

```python
# Fetch DRN cases closed as "resolved" or "declined" (never went to ANI)
make fetch-drn            # fetches DRN archives
# Parse DRN thread outcomes: "resolved", "declined", "no consensus"
# Cases with outcome="resolved" and no subsequent ANI report = non-escalated
```

This data is partially available via `scripts/fetch_drn_archived_cases.py` — the DRN outcome parsing is the gap.

---

## Implementation Sequence

1. **Run now (works with current data):**
   ```bash
   python scripts/survival_analysis.py --demo   # synthetic validation
   python scripts/survival_analysis.py          # real timestamps from raw JSON
   ```

2. **Next: extract structured dates**
   Add `case_opened_date` and `case_closed_date` to `scripts/build_dataset.py` by parsing the first/last revision timestamps from each case's main page.

3. **Then: add topic classification**
   Fetch article WikiProject banners to categorize disputes by topic area (geopolitics, science, biography, etc.). This enables KM stratification by topic.

4. **Then: collect the comparison group**
   Parse DRN archived case outcomes to identify disputes resolved without ANI/ArbCom escalation. This unlocks the escalation classifier.

5. **Finally: multi-state model**
   Once per-stage timestamps exist across the full Talk→DRN→ANI→ArbCom pathway, fit per-transition Cox models and compare hazard ratios across stages.

---

## Quick Reference

| Tool | Use case | lifelines class |
|---|---|---|
| Kaplan-Meier | Describe time-to-event distribution | `KaplanMeierFitter` |
| Log-rank test | Compare KM curves between groups | `logrank_test` |
| Cox PH | Which covariates predict time-to-event | `CoxPHFitter` |
| PH assumption test | Check Cox model validity | `proportional_hazard_test` |
| Competing risks | Cases can close as "dismissed" OR "sanctioned" | `AalenJohansenFitter` |
| Multi-state | Full Talk→DRN→ANI→ArbCom pathway | Multiple `CoxPHFitter` per transition |

See `scripts/survival_analysis.py` for runnable code using all of these.
