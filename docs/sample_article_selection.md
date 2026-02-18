# Sample Article Selection

This document describes the rationale for selecting Wikipedia articles used in the dispute analysis.

## Selection Criteria

To study edit wars and dispute escalation, we need both:

1. **High-conflict articles** — Known for edit wars, content disputes, and potential arbitration
2. **Low-conflict articles** — Stable, well-maintained articles as a control group

This balanced approach allows us to:

- Compare revert ratios between contentious and stable topics
- Identify behavioral patterns unique to disputed content
- Build predictive models with meaningful baseline comparisons

---

## High-Conflict Articles

These articles were selected based on:

- History of edit wars or page protection
- Presence in Wikipedia arbitration cases
- Politically, religiously, or scientifically contentious topics

| Article | Category | Why Selected |
|---------|----------|--------------|
| **Climate change** | Science | Persistent disputes over scientific consensus framing |
| **Donald Trump** | Politics/BLP | One of the most edited/reverted articles on Wikipedia |
| **Israeli–Palestinian conflict** | Geopolitics | Long-running, deeply polarized edit wars |
| **Abortion** | Social issues | Moral/political disputes, multiple ArbCom cases |
| **COVID-19 pandemic** | Science/Health | Misinformation battles, rapidly evolving content |

### Expected Characteristics

- High revert ratios (>10%)
- Multiple 3RR (Three-Revert Rule) violations
- Frequent page protection
- Concentrated conflict between specific user pairs
- Talk page disputes

---

## Low-Conflict Articles (Control Group)

These articles were selected based on:

- Minimal edit warring history
- Non-controversial subject matter
- Stable content over time
- Collaborative editing patterns

| Article | Category | Why Selected |
|---------|----------|--------------|
| **Speed of light** | Physics | Settled science, fundamental constant |
| **Pythagorean theorem** | Mathematics | Pure math, universally accepted proof |
| **Mount Everest** | Geography | Physical facts, minimal political disputes |
| **Photosynthesis** | Biology | Fundamental biology, well-established science |
| **Mona Lisa** | Art history | Cultural artifact, non-political subject |

### Expected Characteristics

- Low revert ratios (<5%)
- Collaborative editing patterns
- No significant user conflicts
- Rare or no page protection
- Constructive talk page discussions

---

## Data Collection

Article selection is configured in `artifacts/sample_articles.yaml`. Edit this file to add or remove articles.

### Quick Start

```bash
make fetch-small      # Fetch all articles from config
make fetch-small-dry  # Preview what would be fetched
```

This fetches:

- Revisions for each article (default: 500 per article)
- Edit war analysis (revert detection, user conflicts, 3RR checks)
- Arbitration cases (default: 5)
- Current DRN cases

### Individual Commands

```bash
# Fetch revisions for a specific article
uv run python scripts/fetch_all.py --revisions "Article Name" --limit 500

# Run edit war analysis
uv run python scripts/fetch_all.py --editwar "Article Name"

# Fetch from config with options
uv run python scripts/fetch_from_config.py --skip-arb  # Skip arbitration
uv run python scripts/fetch_from_config.py --dry-run   # Preview only
```

---

## Analysis Goals

By comparing high-conflict and low-conflict articles, we can answer:

### 1. What revert ratio indicates an edit war?

Compare distributions between groups to establish thresholds.

### 2. Do specific user pairs drive conflicts?

Network analysis of reverter relationships—are disputes driven by a few users or broadly distributed?

### 3. Can we predict escalation?

Identify features (revert velocity, user diversity, talk page activity) that distinguish stable vs. disputed articles.

### 4. What precedes arbitration?

Timeline analysis of edit patterns in the weeks/months before formal dispute resolution.

---

## Future Expansion

### Additional High-Conflict Topics

- `Gamergate (harassment campaign)` — Harassment/BLP issues
- `Brexit` — UK/EU political dispute
- `Russo-Ukrainian War` — Ongoing geopolitical conflict
- `Vaccine hesitancy` — Public health misinformation
- `Muhammad` — Religious sensitivity

### Additional Low-Conflict Topics

- `Transistor` — Electronics fundamentals
- `Roman Empire` — Ancient history
- `Chess` — Game rules and history
- `Periodic table` — Chemistry standard
- `Ancient Egypt` — Distant historical period

---

## References

- [Wikipedia:Lamest edit wars](https://en.wikipedia.org/wiki/Wikipedia:Lamest_edit_wars) — Documented edit war examples
- [Wikipedia:Edit warring](https://en.wikipedia.org/wiki/Wikipedia:Edit_warring) — Policy on edit wars
- [Wikipedia:Three-revert rule](https://en.wikipedia.org/wiki/Wikipedia:Three-revert_rule) — 3RR policy
- [Wikipedia:Arbitration Committee](https://en.wikipedia.org/wiki/Wikipedia:Arbitration_Committee) — ArbCom overview
