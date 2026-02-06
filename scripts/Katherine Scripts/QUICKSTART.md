# Quick Start Guide

## Get Up and Running in 3 Steps

### Step 1: Install Dependencies

```bash
cd wikipedia-disputes
pip install -r requirements.txt
```

### Step 2: (Optional but Recommended) Set Up Authentication

Create a `.env` file with your Wikipedia OAuth token:

```bash
cp .env.example .env
# Edit .env and add your WIKIPEDIA_ACCESS_TOKEN
```

**To get an OAuth token:**
1. Visit: https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration
2. Click "Propose an OAuth 2.0 consumer"
3. Fill in:
   - Application name: "Wikipedia Dispute Research"
   - OAuth callback URL: (not needed for personal use)
   - Applicable grants: Check "High-volume editing"
4. Get your access token and add it to `.env`

**Without a token:** The scripts will work but with lower rate limits (200 vs 5000 requests/hour)

### Step 3: Run the Scripts

#### Option A: Run Everything at Once (Recommended)

```bash
python run_all.py
```

This will:
1. Fetch all ~485 arbitration cases (~5-10 min)
2. Fetch all ~345 RfCs from Meta-Wiki (~5-8 min)
3. Analyze relationships and generate statistics (~1 min)

#### Option B: Run Scripts Individually

```bash
# 1. Fetch arbitration cases
python scripts/fetch_arbitration_cases.py

# 2. Fetch requests for comments
python scripts/fetch_requests_for_comments.py

# 3. Analyze relationships
python scripts/analyze_case_rfc_relationships.py
```

## What You'll Get

After running, check `data/raw/` for:

```
data/raw/
├── arbitration/
│   └── all_arbitration_cases_[timestamp].json
├── rfc/
│   └── all_requests_for_comments_[timestamp].json
└── analysis/
    └── arb_rfc_relationships_[timestamp].json
```

## Understanding the Results

### Summary Statistics

The analysis produces statistics like:

- **Total cases analyzed**: 485
- **Cases with RfC references**: ~40-50
- **Most common dispute resolution venues**:
  - Dispute Resolution Noticeboard (DRN)
  - Administrator's Noticeboard (AN/I)
  - Request for Comments (RfC)
  - 3RR/Edit War resolution
  - Mediation

### Per-Case Analysis

For each arbitration case, you'll get:
- List of RfC references found
- All dispute resolution methods mentioned
- Categorization (formal vs informal)
- Frequency counts for each venue type

## Common Use Cases

### Research Question: "What dispute resolution was attempted before arbitration?"

```python
import json

# Load the analysis results
with open('data/raw/analysis/arb_rfc_relationships_[timestamp].json') as f:
    data = json.load(f)

# Print cases with high DR activity
for case in data['case_relationships']:
    total_dr = case['formal_dr_count'] + case['informal_dr_count']
    if total_dr > 5:
        print(f"{case['case_title']}: {total_dr} DR mentions")
```

### Research Question: "Which cases referenced RfCs?"

```python
import json

with open('data/raw/analysis/arb_rfc_relationships_[timestamp].json') as f:
    data = json.load(f)

# Find cases with RfC references
for case in data['case_relationships']:
    if case['rfc_count'] > 0:
        print(f"{case['case_title']}:")
        for rfc in case['rfc_references']:
            print(f"  - {rfc}")
```

## Troubleshooting

### "No module named 'dotenv'"

```bash
pip install python-dotenv requests
```

### "Data files not found" when running analysis

Run the fetch scripts first:
```bash
python scripts/fetch_arbitration_cases.py
python scripts/fetch_requests_for_comments.py
```

### Rate limit errors

1. Add your OAuth token to `.env` (see Step 2)
2. Wait a few minutes and try again
3. The scripts already include built-in rate limiting

## Next Steps

Once you have the data:

1. **Explore the JSON files**: Use `jq` or Python to explore
2. **Build visualizations**: Create network graphs of case→RfC relationships
3. **Time series analysis**: Track dispute resolution patterns over time
4. **Process mining**: Map common paths through the dispute resolution system
5. **Statistical analysis**: Compare effectiveness of different DR methods

## Need Help?

- Check the full [README.md](README.md) for detailed documentation
- Look at the script comments for implementation details
- Review the data format examples in the README

## Example Commands

```bash
# Run everything
python run_all.py

# Skip fetching if you already have data, just re-run analysis
python run_all.py --analyze-only

# Only fetch arbitration cases
python scripts/fetch_arbitration_cases.py

# View summary statistics
python -c "import json; d=json.load(open('data/raw/analysis/arb_rfc_relationships_*.json')); print(d['summary_statistics'])"
```
