# Wikipedia Dispute Data Collection

A comprehensive toolkit for collecting and analyzing Wikipedia arbitration cases and requests for comment (RfCs).

## Features

- **Arbitration Case Collection**: Fetches all arbitration cases from Wikipedia's arbitration category (485+ cases)
- **RFC Collection**: Fetches all requests for comment from Meta-Wiki across all status categories
- **Relationship Mapping**: Links arbitration cases to related RfCs
- **Dispute Resolution Analysis**: Identifies and categorizes all prior dispute resolution methods mentioned in arbitration cases
- **No Rate Limits**: Uses Wikipedia API with optional authentication token (no 250 hit limit)

## Setup

### 1. Environment Configuration

Create a `.env` file in your project root:

```bash
# Optional: Wikipedia OAuth token for higher rate limits
WIKIPEDIA_ACCESS_TOKEN=your_access_token_here
```

**Note**: The scripts work without an access token, but having one provides higher rate limits and better reliability for large collections.

### 2. Install Dependencies

```bash
pip install requests python-dotenv --break-system-packages
```

Or if using a virtual environment:

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install requests python-dotenv
```

### 3. Set Execute Permissions

```bash
chmod +x run_dispute_collection.py
chmod +x fetch_all_arbitration.py
chmod +x fetch_all_rfc.py
chmod +x analyze_arb_rfc_mapping.py
```

## Usage

### Quick Start - Run Everything

Collect all data and run analysis:

```bash
python run_dispute_collection.py --all
```

### Collect Data Only

```bash
# Collect both arbitration cases and RfCs
python run_dispute_collection.py --collect

# Just arbitration cases
python run_dispute_collection.py --arb

# Just RfCs
python run_dispute_collection.py --rfc
```

### Limited Collection (for testing)

```bash
# Fetch first 50 arbitration cases and 20 RfCs per category
python run_dispute_collection.py --arb --rfc --limit 50
```

### Analyze Existing Data

If you already have collected data:

```bash
python run_dispute_collection.py --analyze
```

### Individual Scripts

You can also run scripts individually:

```bash
# Fetch arbitration cases
python fetch_all_arbitration.py --limit 100 --output arb_cases.json

# Fetch RfCs
python fetch_all_rfc.py --limit 50 --output rfcs.json

# Analyze mapping
python analyze_arb_rfc_mapping.py \
    --arb arb_cases.json \
    --rfc rfcs.json \
    --output mapping.json \
    --report report.txt
```

## Output Files

The scripts generate the following files:

### Data Files

- **`arbitration_cases_full.json`**: All arbitration cases with full content and metadata
  - Case names, status, dates
  - Full wikitext content
  - Parties involved
  - Arbitrators
  - Prior dispute resolution mentions

- **`requests_for_comment_full.json`**: All RfCs organized by status
  - Resolved, unsuccessful, invalid, inactive RfCs
  - Full content and metadata

### Analysis Files

- **`arb_rfc_mapping.json`**: Detailed mapping analysis
  - Case-by-case RfC references
  - Matched RfCs with status
  - Dispute resolution type counts
  - Statistical analysis

- **`arb_rfc_report.txt`**: Human-readable summary report
  - Overview statistics
  - Dispute resolution type breakdown
  - Most referenced RfCs

## Data Structure

### Arbitration Case

```json
{
  "pageid": 12345,
  "title": "Wikipedia:Arbitration/Requests/Case/Example",
  "url": "https://en.wikipedia.org/wiki/...",
  "content": "Full wikitext content...",
  "timestamp": "2024-01-01T00:00:00Z",
  "categories": ["Category:Wikipedia arbitration cases"],
  "metadata": {
    "case_name": "Example",
    "status": "Closed",
    "opened": "January 1, 2024",
    "closed": "February 1, 2024",
    "parties": ["User1", "User2"],
    "prior_dispute_resolution": {
      "drn": [...],
      "rfc": [...],
      "an": [...]
    }
  }
}
```

### Analysis Output

```json
{
  "statistics": {
    "total_cases_analyzed": 485,
    "cases_with_rfc_reference": 123,
    "cases_with_matched_rfc": 98,
    "cases_with_prior_dispute_resolution": 412,
    "dispute_resolution_type_counts": {
      "drn": 234,
      "rfc": 123,
      "ani": 189,
      "an": 156,
      ...
    }
  },
  "case_analyses": [...]
}
```

## Dispute Resolution Types Detected

The analysis identifies these dispute resolution venues:

- **DRN**: Dispute Resolution Noticeboard
- **RFC**: Requests for Comment
- **AN**: Administrators' Noticeboard
- **ANI**: Administrators' Noticeboard/Incidents
- **AN/EW**: Administrators' Noticeboard/Edit Warring
- **Mediation**: Formal mediation processes
- **Third Opinion**: 3O requests
- **Talk Page**: Article/user talk page discussions

## API Rate Limits

### Without Token
- ~100 requests/minute (varies by endpoint)
- May encounter throttling with large collections

### With OAuth Token
- Significantly higher limits
- More reliable for collecting all 485+ arbitration cases
- Recommended for production use

## Project Structure Integration

Place these scripts in your existing project:

```
your-project/
├── .env                              # Your credentials
├── scripts/
│   ├── run_dispute_collection.py     # Unified CLI
│   ├── fetch_all_arbitration.py      # Arbitration collector
│   ├── fetch_all_rfc.py              # RFC collector
│   └── analyze_arb_rfc_mapping.py    # Analysis script
├── data/
│   ├── raw/
│   │   ├── arbitration_cases_full.json
│   │   └── requests_for_comment_full.json
│   └── processed/
│       ├── arb_rfc_mapping.json
│       └── arb_rfc_report.txt
└── README.md
```

## Examples

### Example 1: Full Collection for Research

```bash
# Collect everything (may take 30-60 minutes)
python run_dispute_collection.py --all
```

### Example 2: Sample for Testing

```bash
# Quick test with limited data
python run_dispute_collection.py --all --limit 10
```

### Example 3: Update Analysis

```bash
# Re-analyze without re-fetching
python run_dispute_collection.py --analyze
```

## Troubleshooting

### "Rate limit exceeded"
- Add `WIKIPEDIA_ACCESS_TOKEN` to `.env`
- Reduce `--limit` for testing
- Add delays between requests (already implemented)

### "Module not found"
```bash
pip install requests python-dotenv --break-system-packages
```

### "No data found"
- Check internet connection
- Verify Wikipedia API is accessible
- Try with `--limit 5` first

## Citation

If you use this data in research, please cite Wikipedia appropriately and note the collection date.

## License

This code is provided as-is for research purposes. Wikipedia content is under CC BY-SA license.
