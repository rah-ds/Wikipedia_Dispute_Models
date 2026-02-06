# Wikipedia Dispute Resolution Research - Getting Started

## 📦 What You Have

A complete, production-ready system for collecting and analyzing Wikipedia dispute resolution data.

## 🚀 Quick Start (3 Steps)

### 1. Install Dependencies
```bash
cd wikipedia-disputes
pip install -r requirements.txt
```

### 2. (Optional) Add Your Wikipedia OAuth Token
```bash
cp .env.example .env
# Edit .env and add: WIKIPEDIA_ACCESS_TOKEN=your_token_here
```

Get a token here: https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration

### 3. Run Everything
```bash
python run_all.py
```

That's it! The script will:
- ✅ Fetch all ~485 arbitration cases (5-10 min)
- ✅ Fetch all ~345 RfCs from Meta-Wiki (5-8 min)  
- ✅ Analyze relationships and generate statistics (<1 min)

## 📊 What You'll Get

After running, you'll have three JSON files in `data/raw/`:

1. **Arbitration Cases** (`data/raw/arbitration/`)
   - All 485 arbitration cases with full content
   - Page metadata and timestamps
   - Last revision information

2. **Requests for Comments** (`data/raw/rfc/`)
   - All 345 RfCs across 4 categories
   - Full content and metadata
   - Category classifications

3. **Analysis Results** (`data/raw/analysis/`)
   - Case → RfC relationship mappings
   - Dispute resolution method categorization
   - Summary statistics and rankings

## 🔍 Key Features

### No Rate Limit Issues
- With OAuth: 5,000 requests/hour ✅
- Without OAuth: 200 requests/hour (still works)
- Automatic pagination - fetches ALL data, not just 250 items

### Comprehensive Analysis
Automatically detects and categorizes:
- RfC references in arbitration cases
- Formal DR venues (DRN, AN/I, ArbCom, etc.)
- Informal methods (talk pages, third opinion, etc.)
- Frequency statistics for each venue type

### Well-Organized Output
```
data/raw/
├── arbitration/all_arbitration_cases_[timestamp].json
├── rfc/all_requests_for_comments_[timestamp].json
└── analysis/arb_rfc_relationships_[timestamp].json
```

## 📖 Documentation

- **QUICKSTART.md** - Get up and running fast
- **README.md** - Complete documentation
- **PROJECT_OVERVIEW.md** - Technical details and use cases

## 💡 Example Use Cases

### Find cases with high DR activity
```python
import json

with open('data/raw/analysis/arb_rfc_relationships_[timestamp].json') as f:
    data = json.load(f)

# Print cases with >5 DR mentions
for case in data['case_relationships']:
    total = case['formal_dr_count'] + case['informal_dr_count']
    if total > 5:
        print(f"{case['case_title']}: {total} DR attempts")
```

### List all RfC references
```python
for case in data['case_relationships']:
    if case['rfc_count'] > 0:
        print(f"\n{case['case_title']}:")
        for rfc in case['rfc_references']:
            print(f"  → {rfc}")
```

### View summary statistics
```python
stats = data['summary_statistics']
print(f"Total cases: {stats['total_cases_analyzed']}")
print(f"Cases with RfCs: {stats['cases_with_rfc_refs']}")
print(f"\nTop DR venues:")
for venue, count in list(stats['venue_type_totals'].items())[:5]:
    print(f"  {venue}: {count}")
```

## 🛠️ Individual Scripts

You can also run scripts separately:

```bash
# Fetch arbitration cases only
python scripts/fetch_arbitration_cases.py

# Fetch RfCs only
python scripts/fetch_requests_for_comments.py

# Run analysis only (requires existing data)
python scripts/analyze_case_rfc_relationships.py
```

## 🔐 About Authentication

### With OAuth Token (Recommended)
- 5,000 requests per hour
- Faster data collection
- No interruptions

### Without OAuth Token
- 200 requests per hour
- Still works, just slower
- Scripts handle rate limiting automatically

### Getting an OAuth Token
1. Go to https://meta.wikimedia.org/wiki/Special:OAuthConsumerRegistration
2. Click "Propose an OAuth 2.0 consumer"
3. Application name: "Wikipedia Dispute Research"
4. Check "High-volume editing" under grants
5. Copy your access token to `.env`

## ⚠️ Troubleshooting

### "No module named 'requests'"
```bash
pip install requests python-dotenv
```

### "Data files not found" error
Run the fetch scripts first:
```bash
python scripts/fetch_arbitration_cases.py
python scripts/fetch_requests_for_comments.py
```

### Rate limit errors
Add your OAuth token to `.env` or wait a few minutes

## 📚 Research Applications

This data is perfect for:
- Process mining and workflow analysis
- Network analysis of dispute relationships
- Temporal analysis of dispute patterns
- Effectiveness studies of DR methods
- Content analysis of dispute topics
- Machine learning classification

## 🎯 Next Steps

1. **Run the scripts** to collect your data
2. **Explore the JSON** files to understand the structure
3. **Build analysis tools** using the provided data
4. **Create visualizations** of dispute resolution patterns
5. **Publish research** using this comprehensive dataset

## 📄 Files Included

```
wikipedia-disputes/
├── scripts/                    # 3 main scripts
├── src/                        # Core modules
├── run_all.py                 # Master script
├── requirements.txt           # Dependencies
├── .env.example              # Token template
├── README.md                 # Full docs
├── QUICKSTART.md            # Quick guide
└── PROJECT_OVERVIEW.md      # Technical details
```

## 💬 Questions?

Check the documentation:
- Quick answers → `QUICKSTART.md`
- Full details → `README.md`
- Technical info → `PROJECT_OVERVIEW.md`

---

**Ready to start?**

```bash
cd wikipedia-disputes
pip install -r requirements.txt
python run_all.py
```

That's all it takes! 🚀
