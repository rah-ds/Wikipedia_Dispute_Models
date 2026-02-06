# Wikipedia Dispute Resolution Data Collection

This project collects and analyzes data from Wikipedia's dispute resolution processes, including arbitration cases and requests for comments (RfCs).

## Features

- **Fetch Arbitration Cases**: Retrieves all arbitration cases from English Wikipedia
- **Fetch Requests for Comments**: Retrieves all RfCs from Meta-Wiki (resolved, unsuccessful, invalid, inactive)
- **Relationship Analysis**: Maps arbitration cases to RfCs and analyzes dispute resolution methods used

## Project Structure

```
wikipedia-disputes/
├── data/
│   ├── raw/              # Raw API responses
│   │   ├── arbitration/  # Arbitration case data
│   │   ├── rfc/          # Request for comment data
│   │   └── analysis/     # Analysis results
│   ├── processed/        # Cleaned datasets (for future use)
│   └── external/         # Third-party data (for future use)
├── docs/                 # Documentation
├── scripts/              # Data collection and analysis scripts
│   ├── fetch_arbitration_cases.py
│   ├── fetch_requests_for_comments.py
│   └── analyze_case_rfc_relationships.py
├── src/                  # Source code modules
│   ├── wiki.py          # Wikipedia API client
│   └── io.py            # Input/output utilities
├── .env                 # Your credentials (create from .env.example)
├── .env.example         # Template for environment variables
├── .gitignore          # Git ignore file
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Setup

### 1. Install Dependencies

```bash
cd wikipedia-disputes
pip install -r requirements.txt
```

### 2. Configure API Credentials

Wikipedia's API has rate limits. Using OAuth authentication provides higher limits and is recommended.

#### Option A: Using OAuth Access Token (Recommended)

1. Go to https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration
2. Register a new OAuth consumer for "personal use"
3. Get your access token
4. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```
5. Add your access token to `.env`:
   ```
   WIKIPEDIA_ACCESS_TOKEN=your_token_here
   ```

#### Option B: Anonymous Access (Lower Rate Limits)

If you don't set an access token, the scripts will work but with lower rate limits (200 requests per hour vs. 5000 with authentication).

### 3. About Rate Limits

**Without authentication:**
- 200 requests per hour per IP address

**With OAuth authentication:**
- 5,000 requests per hour
- No hard limit on continuation requests

The scripts include built-in rate limiting and respect Wikipedia's usage policies.

## Usage

### Step 1: Fetch Arbitration Cases

Retrieves all arbitration cases from the "Wikipedia arbitration cases" category:

```bash
python scripts/fetch_arbitration_cases.py
```

**What it does:**
- Fetches all ~485 arbitration cases
- Retrieves full page content for each case
- Saves to `data/raw/arbitration/all_arbitration_cases_TIMESTAMP.json`

**Output includes:**
- Case title and page ID
- Full wikitext content
- Last revision metadata
- Timestamps

### Step 2: Fetch Requests for Comments

Retrieves all RfCs from Meta-Wiki across multiple categories:

```bash
python scripts/fetch_requests_for_comments.py
```

**What it does:**
- Fetches RfCs from 4 categories:
  - Resolved (~200 pages)
  - Unsuccessful
  - Invalid
  - Inactive
- Retrieves full content for each RfC
- Saves to `data/raw/rfc/all_requests_for_comments_TIMESTAMP.json`

**Output includes:**
- RfC title and category
- Full wikitext content
- Last revision metadata
- Timestamps

### Step 3: Analyze Relationships

Analyzes relationships between arbitration cases and RfCs:

```bash
python scripts/analyze_case_rfc_relationships.py
```

**What it does:**
1. **Maps cases to RfCs**: Finds all RfC references in arbitration cases
2. **Extracts dispute resolution methods**: Identifies and categorizes prior DR methods mentioned:
   - Formal methods (DRN, AN/I, ArbCom, etc.)
   - Informal methods (talk pages, third opinion, etc.)
   - Frequency of each venue type
3. **Generates statistics**: Summary stats and rankings

**Output includes:**
- Per-case analysis with RfC references
- Dispute resolution method categorization
- Summary statistics:
  - Cases with RfC references
  - Most common DR venues
  - Top cases by DR activity
- Saves to `data/raw/analysis/arb_rfc_relationships_TIMESTAMP.json`

## Output Data Format

### Arbitration Cases Data

```json
{
  "category": "Wikipedia arbitration cases",
  "fetch_timestamp": "2024-01-15 14:30:00",
  "total_cases": 485,
  "cases": [
    {
      "title": "Wikipedia:Arbitration/Requests/Case/Example",
      "page_id": 12345,
      "timestamp": "2024-01-01T00:00:00Z",
      "content": "Full wikitext content...",
      "last_revision_user": "Username",
      "last_revision_comment": "Edit comment",
      "last_revision_timestamp": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### RfC Data

```json
{
  "source": "Meta-Wiki Requests for Comments",
  "fetch_timestamp": "2024-01-15 14:35:00",
  "categories_fetched": [...],
  "category_counts": {
    "Requests for comments (resolved)": 200,
    ...
  },
  "total_rfcs": 345,
  "rfcs": [
    {
      "title": "Requests for comment/Example",
      "page_id": 67890,
      "category": "Requests for comments (resolved)",
      "content": "Full wikitext content...",
      ...
    }
  ]
}
```

### Analysis Results

```json
{
  "analysis_timestamp": "2024-01-15 14:40:00",
  "summary_statistics": {
    "total_cases_analyzed": 485,
    "cases_with_rfc_refs": 42,
    "total_rfc_references": 67,
    "cases_with_formal_dr": 320,
    "cases_with_informal_dr": 405,
    "venue_type_totals": {
      "Dispute Resolution Noticeboard": 156,
      "Administrator's noticeboard": 142,
      ...
    },
    "top_cases_by_rfc_refs": [...],
    "top_cases_by_dr_mentions": [...]
  },
  "case_relationships": [
    {
      "case_title": "Wikipedia:Arbitration/Requests/Case/Example",
      "case_page_id": 12345,
      "rfc_references": ["Requests for comment/Some RfC"],
      "rfc_count": 1,
      "dispute_resolution_methods": {
        "formal_methods": ["DRN", "AN/I"],
        "informal_methods": ["Talk page discussion"],
        "venue_types": {
          "Dispute Resolution Noticeboard": 2,
          "Administrator's noticeboard": 1
        }
      },
      "formal_dr_count": 2,
      "informal_dr_count": 1,
      "venue_type_summary": {...}
    }
  ]
}
```

## Performance Notes

- **Arbitration cases**: ~485 pages, takes approximately 5-10 minutes
- **RfCs**: ~345 pages across 4 categories, takes approximately 5-8 minutes
- **Analysis**: Runs in under 1 minute on cached data

All scripts include:
- Progress indicators
- Rate limiting to respect Wikipedia's servers
- Error handling and recovery
- Automatic continuation for paginated results

## Troubleshooting

### Rate Limit Errors

If you see rate limit errors:
1. Use OAuth authentication (see Setup section)
2. The scripts already include rate limiting
3. Wait a few minutes and retry

### Missing Data Files

If the analysis script can't find data:
```bash
# Run the fetch scripts first:
python scripts/fetch_arbitration_cases.py
python scripts/fetch_requests_for_comments.py

# Then run analysis:
python scripts/analyze_case_rfc_relationships.py
```

### API Connection Issues

If you can't connect to Wikipedia:
1. Check your internet connection
2. Verify Wikipedia is accessible from your location
3. Check if your IP is blocked (unlikely but possible)

## Data Locations

All collected data is stored in `data/raw/` with timestamps:

```
data/raw/
├── arbitration/
│   └── all_arbitration_cases_20240115_143000.json
├── rfc/
│   └── all_requests_for_comments_20240115_143500.json
└── analysis/
    └── arb_rfc_relationships_20240115_144000.json
```

The analysis script automatically uses the most recent data files.

## Research Applications

This data can be used for:

1. **Dispute Resolution Research**: Study patterns in Wikipedia's dispute resolution
2. **Network Analysis**: Map relationships between cases and RfCs
3. **Process Improvement**: Identify common paths through DR processes
4. **Temporal Analysis**: Track how disputes evolve over time
5. **Effectiveness Studies**: Compare outcomes of different DR methods

## License

This project is for research purposes. All Wikipedia content is available under the Creative Commons Attribution-ShareAlike License.

## Contributing

Contributions are welcome! Please ensure:
- Code follows existing style
- Scripts include error handling
- Data collection respects Wikipedia's rate limits
- Documentation is updated

## Acknowledgments

- Wikimedia Foundation for providing the API
- Wikipedia community for maintaining dispute resolution records
- All contributors to Wikipedia's arbitration and RFC processes
