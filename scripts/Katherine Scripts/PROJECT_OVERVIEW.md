# Wikipedia Dispute Resolution Research - Project Overview

## Project Summary

This project provides automated tools to collect and analyze Wikipedia's dispute resolution data, specifically:

1. **Arbitration Cases** (~485 cases from English Wikipedia)
2. **Requests for Comments** (~345 RfCs from Meta-Wiki)
3. **Relationship Analysis** between cases and RfCs, including dispute resolution method categorization

## Key Features

### 1. Comprehensive Data Collection
- Fetches ALL arbitration cases (no manual limits)
- Retrieves complete page content (not just summaries)
- Collects from multiple RfC categories (resolved, unsuccessful, invalid, inactive)
- Built-in pagination handling (no 250-hit limit with proper auth)
- Automatic rate limiting and error recovery

### 2. Relationship Mapping
- Identifies RfC references in arbitration cases
- Extracts mentions of dispute resolution venues
- Categorizes DR methods (formal vs informal)
- Generates frequency statistics

### 3. Dispute Resolution Venue Detection
Automatically identifies and categorizes:

**Formal venues:**
- Arbitration Enforcement (AE)
- Arbitration Committee (ArbCom)
- Dispute Resolution Noticeboard (DRN)
- Administrator's Noticeboard (AN/I)
- Request for Comments (RfC)
- 3RR/Edit War resolution
- Mediation (MedCom)

**Informal methods:**
- Talk page discussions
- Third Opinion (3O)
- User talk conversations
- Article talk discussions
- Informal mediation

## File Structure

```
wikipedia-disputes/
├── scripts/                          # Executable scripts
│   ├── fetch_arbitration_cases.py   # Fetch ~485 arb cases
│   ├── fetch_requests_for_comments.py # Fetch ~345 RfCs
│   └── analyze_case_rfc_relationships.py # Analysis engine
├── src/                              # Core modules
│   ├── wiki.py                      # Wikipedia API client
│   └── io.py                        # Data I/O utilities
├── data/                             # Data storage (created on first run)
│   └── raw/
│       ├── arbitration/             # Arbitration case JSON files
│       ├── rfc/                     # RfC JSON files
│       └── analysis/                # Analysis results
├── run_all.py                       # Master script (runs everything)
├── requirements.txt                 # Python dependencies
├── .env.example                     # Template for credentials
├── .gitignore                       # Git ignore rules
├── README.md                        # Full documentation
└── QUICKSTART.md                    # Quick start guide
```

## Data Output

### Arbitration Cases Output
**File**: `data/raw/arbitration/all_arbitration_cases_[timestamp].json`

Contains:
- Complete list of all arbitration cases
- Full wikitext content for each case
- Metadata (page ID, timestamps, last editor)
- Total count: ~485 cases

### RfC Output
**File**: `data/raw/rfc/all_requests_for_comments_[timestamp].json`

Contains:
- All RfCs from 4 categories
- Full wikitext content
- Category classification
- Metadata and timestamps
- Total count: ~345 RfCs

### Analysis Output
**File**: `data/raw/analysis/arb_rfc_relationships_[timestamp].json`

Contains:
- **Summary statistics**:
  - Total cases analyzed
  - Cases with RfC references
  - Cases with formal/informal DR
  - Venue type frequency counts
  - Top cases by DR activity

- **Per-case analysis**:
  - List of RfC references
  - All DR methods mentioned
  - Formal vs informal categorization
  - Venue type breakdown

## API Rate Limits

### Without Authentication
- **Limit**: 200 requests per hour
- **Estimated time**: 
  - Arbitration: 12-15 minutes
  - RfCs: 10-12 minutes

### With OAuth Token (Recommended)
- **Limit**: 5,000 requests per hour
- **Estimated time**:
  - Arbitration: 5-8 minutes
  - RfCs: 5-7 minutes
  - Analysis: <1 minute

**Scripts automatically use continuation tokens**, so there's no hard limit on the number of results - you can fetch all available data.

## Usage Patterns

### Basic Usage
```bash
# Install dependencies
pip install -r requirements.txt

# Run everything
python run_all.py
```

### Advanced Usage
```bash
# Run only analysis (if data already exists)
python run_all.py --analyze-only

# Skip arbitration fetching
python run_all.py --skip-arb

# Run individual scripts
python scripts/fetch_arbitration_cases.py
python scripts/fetch_requests_for_comments.py
python scripts/analyze_case_rfc_relationships.py
```

## Research Applications

### 1. Process Mining
Map the typical path cases take through Wikipedia's dispute resolution system:
- Talk page → DRN → RfC → ArbCom?
- How many steps before arbitration?
- Which venues are most commonly used?

### 2. Network Analysis
Build graphs showing:
- Which cases reference which RfCs
- Clusters of related disputes
- Temporal patterns in dispute escalation

### 3. Effectiveness Studies
Analyze:
- Success rates of different DR venues
- Time to resolution by method
- Correlation between prior DR attempts and arbitration outcomes

### 4. Content Analysis
Study:
- Common topics in disputes
- Language patterns in successful vs unsuccessful resolutions
- Evolution of dispute resolution practices over time

## Key Advantages

1. **Complete Data**: Fetches ALL cases, not a sample
2. **No Manual Limits**: Uses pagination to get everything
3. **Rate Limit Aware**: Respects Wikipedia's servers
4. **Automated**: One command to run everything
5. **Well Documented**: Clear data formats and structure
6. **Extensible**: Easy to add new analysis methods
7. **Reproducible**: Timestamped outputs, clear provenance

## Technical Details

### Authentication
- Uses OAuth 2.0 access tokens
- Stored securely in `.env` file (gitignored)
- Falls back to anonymous access if not configured

### Data Collection
- Paginated requests with automatic continuation
- Error handling and retry logic
- Progress indicators
- Built-in rate limiting (0.5-1 second between requests)

### Analysis Engine
- Regular expression-based pattern matching
- Multiple detection patterns for each venue type
- Frequency counting and categorization
- Summary statistics generation

## Dependencies

- **Python 3.7+**
- **requests**: HTTP library for API calls
- **python-dotenv**: Environment variable management

## Data Format

All data is stored as JSON for:
- Easy parsing and analysis
- Human-readable format
- Standard interchange format
- Compatibility with analysis tools (Python, R, JavaScript, etc.)

## Future Enhancements

Potential additions:
- Time series analysis of dispute trends
- Network graph visualization
- Machine learning classification of dispute types
- Integration with other Wikipedia data sources
- Export to other formats (CSV, Excel, SQL)

## Credits

- **Wikipedia API**: Provided by Wikimedia Foundation
- **Data Source**: Wikipedia and Meta-Wiki communities
- **License**: All Wikipedia content CC BY-SA 3.0

## Support

- Full documentation: `README.md`
- Quick start: `QUICKSTART.md`
- Code comments: Inline in all scripts
- Examples: In documentation

---

**Version**: 1.0  
**Last Updated**: 2024  
**Status**: Production Ready
