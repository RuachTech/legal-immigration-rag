# Data Ingestion Pipeline: GOV.UK Immigration Rules

This document describes the complete data ingestion pipeline for scraping and processing GOV.UK Immigration Rules into the RAG system.

**Pipeline Overview:**
```
URL Discovery
    ↓
get_govuk_urls.py → data/immigration_rules_urls.json (122 URLs)
    ↓
Batch Scraping
    ↓
batch_scrape.py + govuk_jina_scraper.py → data/govuk-data/
    ↓
Raw Markdown & Parsed Chunks with Metadata
    ↓
Ready for Summary-Augmented Chunking (SAC) → Vector Store Ingestion
```

## Stage 1: URL Discovery (`get_govuk_urls.py`)

**Purpose:** Extract all Immigration Rules URLs from GOV.UK index pages.

**Sources:**
- `https://www.gov.uk/guidance/immigration-rules` (main landing page)
- `https://www.gov.uk/guidance/immigration-rules/immigration-rules-index` (detailed index)

**Output:**
```json
data/immigration_rules_urls.json
{
  "source_urls": [...],
  "total_count": 122,
  "by_type": {
    "part": 16,
    "appendix": 103,
    "introduction": 1,
    "index": 1,
    "updates": 1
  },
  "urls": [
    {
      "url": "https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-fm-family-members",
      "title": "Immigration Rules Appendix FM: family members",
      "type": "appendix",
      "slug": "appendix-fm-family-members"
    },
    ...
  ]
}
```

**Usage:**

```bash
# Generate or regenerate URL inventory
export JINA_API_KEY="your_jina_api_key"
cd /Users/olamide/Documents/ruach-projects/immigranta

python data_pipeline/scrapers/get_govuk_urls.py
```

**Features:**
- Fetches from both source pages and deduplicates URLs
- Categorizes by type (parts, appendices, etc.)
- Saves structured JSON for batch scraping
- No dependencies on existing data

**Rate Limit:** 20 RPM (Jina limit)

---

## Stage 2: Batch Scraping (`batch_scrape.py`)

**Purpose:** Orchestrate scraping of all (or filtered) Immigration Rules pages using the Jina scraper.

**Components:**
1. **`batch_scrape.py`** - Main orchestration script (you are here)
2. **`govuk_jina_scraper.py`** - Core scraper class
3. **`scrape_log.json`** - Tracks scraped URLs for resume capability

### Core Classes

#### `GovUKJinaScraper`

Handles individual page scraping with:
- Jina Reader API integration
- Rate limiting (20 RPM)
- Markdown parsing into hierarchical chunks
- Section ID extraction (GEN.1.1, SW 1.1, paragraph numbers)
- Metadata capture for DRM prevention

**Key Methods:**

```python
# Single page
chunks = await scraper.scrape_page(url, part_name="Appendix FM")

# Fetch index and scrape all
chunks = await scraper.scrape_all()

# Multiple pages with rate limiting
chunks = await scraper.scrape_multiple(
    urls={"Appendix FM": "https://...", "Part 1": "https://..."},
    max_concurrent=1  # Sequential for safety
)
```

**Data Saved:**

```
data/govuk-data/
├── raw/{slug}.md              # Raw markdown from Jina
├── chunks/{slug}.json         # Parsed chunks with metadata
└── index.json                 # Summary of scraped content
```

#### `ScrapeLog`

Persistent tracker for resume capability:

```json
{
  "scraped_urls": [
    "https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-fm-family-members",
    "https://www.gov.uk/guidance/immigration-rules/immigration-rules-part-11-asylum",
    ...
  ],
  "history": [
    {
      "url": "https://...",
      "slug": "appendix-fm-family-members",
      "title": "Immigration Rules Appendix FM: family members",
      "status": "success",
      "chunk_count": 1200,
      "error": null,
      "scraped_at": "2025-12-06T17:18:29.441948",
      "duration_seconds": 3.172965
    },
    ...
  ]
}
```

### CLI Usage

**Basic scraping (all 122 URLs):**

```bash
export JINA_API_KEY="your_jina_api_key"
python data_pipeline/scrapers/batch_scrape.py

# Estimated time: ~6 minutes (122 pages × 3 seconds per request)
```

**Filter by type:**

```bash
# Scrape only appendices (103 pages)
python data_pipeline/scrapers/batch_scrape.py --type appendix

# Scrape only parts (16 pages)
python data_pipeline/scrapers/batch_scrape.py --type part

# Multiple types
python data_pipeline/scrapers/batch_scrape.py --type part --type introduction
```

**Scrape specific pages:**

```bash
# Only Appendix FM and Skilled Worker
python data_pipeline/scrapers/batch_scrape.py \
  --slugs appendix-fm-family-members,appendix-skilled-worker

# Exclude specific pages
python data_pipeline/scrapers/batch_scrape.py \
  --exclude appendix-visitor-visa-national-list,appendix-eta-national-list
```

**Resume interrupted scrape:**

```bash
# Skip URLs that have already been scraped
python data_pipeline/scrapers/batch_scrape.py --resume

# Combine with other filters
python data_pipeline/scrapers/batch_scrape.py --resume --type appendix
```

**Preview without scraping:**

```bash
# See what would be scraped (useful for testing filters)
python data_pipeline/scrapers/batch_scrape.py --dry-run

# Preview first 10 pages
python data_pipeline/scrapers/batch_scrape.py --dry-run --limit 10

# Preview only appendices
python data_pipeline/scrapers/batch_scrape.py --dry-run --type appendix
```

**Limit for testing:**

```bash
# Scrape only first 5 pages
python data_pipeline/scrapers/batch_scrape.py --limit 5

# Good for testing before full run
```

### Output Structure

```
data/
├── immigration_rules_urls.json              # URL inventory
└── govuk-data/
    ├── raw/
    │   ├── appendix-fm-family-members.md   # Raw markdown
    │   ├── part-11-asylum.md
    │   └── ...
    ├── chunks/
    │   ├── appendix-fm-family-members.json # Parsed chunks
    │   ├── part-11-asylum.json
    │   └── ...
    ├── index.json                          # Scrape summary
    ├── scrape_log.json                     # Resume state
    └── batch_report_20251206_171700.json   # Timestamped reports
```

### Chunk Output Format

Each `chunks/{slug}.json` contains:

```json
{
  "url": "https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-fm-family-members",
  "part_name": "Appendix FM: family members",
  "scraped_at": "2025-12-06T17:17:00.131926",
  "chunk_count": 1200,
  "chunks": [
    {
      "metadata": {
        "source": "Appendix FM: family members",
        "part": "Appendix FM: family members",
        "section_id": "GEN.1.1",
        "section_title": "Purpose",
        "parent_section": "GEN.1",
        "hierarchy_level": 2,
        "topic": "eligibility",
        "url": "https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-fm-family-members",
        "scraped_at": "2025-12-06T17:17:00.131926"
      },
      "text": "GEN.1.1. This route is for those seeking to enter or remain in the UK..."
    },
    ...
  ]
}
```

### Batch Report

Each run generates a timestamped report: `batch_report_20251206_171700.json`

```json
{
  "started_at": "2025-12-06T17:17:00.123456",
  "completed_at": "2025-12-06T17:17:10.654321",
  "total_urls": 122,
  "scraped": 120,
  "failed": 2,
  "skipped": 0,
  "total_chunks": 8543,
  "results": [
    {
      "url": "https://...",
      "slug": "appendix-fm-family-members",
      "title": "Immigration Rules Appendix FM: family members",
      "status": "success",
      "chunk_count": 1200,
      "error": null,
      "scraped_at": "2025-12-06T17:17:02.123456",
      "duration_seconds": 2.5
    },
    ...
  ]
}
```

---

## Complete Pipeline Workflow

### Scenario 1: Initial Full Ingestion

```bash
# 1. Generate URL inventory (one-time or periodic refresh)
export JINA_API_KEY="your_key"
python data_pipeline/scrapers/get_govuk_urls.py
# Output: data/immigration_rules_urls.json (122 URLs)

# 2. Preview what would be scraped
python data_pipeline/scrapers/batch_scrape.py --dry-run
# Output: List of 122 URLs

# 3. Scrape everything
python data_pipeline/scrapers/batch_scrape.py
# Output: 
#   - data/govuk-data/raw/*.md (122 files)
#   - data/govuk-data/chunks/*.json (122 files)
#   - data/govuk-data/scrape_log.json
#   - data/govuk-data/batch_report_*.json

# 4. Verify results
ls -la data/govuk-data/chunks/ | wc -l  # Should be ~125 (122 + summaries)
cat data/govuk-data/batch_report_*.json | jq '.total_chunks'  # Total chunk count
```

**Expected Results:**
- ~8,000-10,000 chunks across all pages
- ~90% success rate (index/intro pages may have 0 chunks)
- ~6 minutes total time

### Scenario 2: Incremental Ingestion (New Rules Added)

```bash
# 1. Refresh URL inventory to pick up new pages
python data_pipeline/scrapers/get_govuk_urls.py
# Updates: data/immigration_rules_urls.json

# 2. Resume scraping - only new URLs
python data_pipeline/scrapers/batch_scrape.py --resume
# Output: Only scrapes URLs not in scrape_log.json
```

### Scenario 3: Re-scrape Specific Section

```bash
# Example: Rules changed for Appendix FM, need fresh scrape

# Option A: Re-scrape just this page
python data_pipeline/scrapers/batch_scrape.py \
  --slugs appendix-fm-family-members

# Option B: Re-scrape whole category
python data_pipeline/scrapers/batch_scrape.py \
  --type appendix --resume
# (Skips already-scraped appendices except FM if you deleted it)

# Note: scrape_log.json is updated with new scrape timestamp
```

### Scenario 4: Testing/Development

```bash
# Quick test with first 3 pages
python data_pipeline/scrapers/batch_scrape.py --limit 3

# Test only appendices (smaller set)
python data_pipeline/scrapers/batch_scrape.py --type appendix --limit 5

# Dry run to verify filters
python data_pipeline/scrapers/batch_scrape.py --dry-run --type part

# Check existing data
cat data/govuk-data/scrape_log.json | jq '.scraped_urls | length'
cat data/govuk-data/index.json | jq '.total_chunks'
```

---

## Downstream Integration

### Next Steps: Summary-Augmented Chunking

The chunks from this pipeline feed into SAC (from `.kiro/specs/`):

```python
from data_pipeline.processing import SummaryAugmentedChunker
from storage import VectorStore

# 1. Load scraped chunks
chunks_dir = Path("data/govuk-data/chunks")
all_chunks = load_chunks_from_json(chunks_dir)

# 2. Apply SAC: prepend document summaries to each chunk
sac = SummaryAugmentedChunker(model="gpt-4", cache=True)
enhanced_chunks = await sac.process(all_chunks)
# Each chunk now has: [Document Summary] → [Chunk Text]

# 3. Embed and store in vector DB
vector_store = ChromaDB()  # or Weaviate for production
await vector_store.add_chunks(enhanced_chunks, metadata_index=True)
```

### Metadata for Retrieval

The chunks include rich metadata for filtering during retrieval:

```python
# RAG retrieval with filtering
results = vector_store.search(
    query="partner visa requirements",
    filters={
        "source": "Appendix FM",  # Exact source filtering
        "hierarchy_level": {"$lte": 2},  # Only main sections
        "topic": "eligibility"  # Topic-based filtering
    },
    top_k=10
)
```

---

## Troubleshooting

### Rate Limit Errors

```
429 Too Many Requests
```

**Solution:** Jina has a 20 RPM limit. The scraper automatically enforces 3-second intervals, but parallel requests may still hit it.

- Use `--limit` to test with fewer pages first
- Run with `max_concurrent=1` (default)
- If errors persist, check Jina API status

### Empty Chunks

```json
{"chunk_count": 0, "chunks": []}
```

**Expected for:**
- `immigration-rules-index` - Mostly navigation/TOC
- `immigration-rules-introduction` - High-level overview

**Investigation:**
```bash
# Check raw markdown
cat data/govuk-data/raw/appendix-fm-family-members.md | head -100

# If content exists but chunks empty, parsing may have failed
# Check logs for "Parsed 0 chunks" messages
```

### Resume State Issues

```bash
# View what's already scraped
cat data/govuk-data/scrape_log.json | jq '.scraped_urls | length'

# Reset resume state (start over)
rm data/govuk-data/scrape_log.json
python data_pipeline/scrapers/batch_scrape.py

# Or selectively reset
# Edit scrape_log.json to remove specific URLs, then run with --resume
```

### API Key Issues

```
Error: JINA_API_KEY environment variable not set
```

**Solution:**

```bash
export JINA_API_KEY="your_actual_key"
python data_pipeline/scrapers/batch_scrape.py

# Or inline
JINA_API_KEY="your_key" python data_pipeline/scrapers/batch_scrape.py
```

---

## Architecture Decisions

### Why Jina Reader?

- **Clean markdown output** vs HTML parsing complexity
- **Automatic boilerplate removal** (cookies, navigation, footer)
- **Structural preservation** (headings, lists, formatting)
- **20 RPM rate limit acceptable** for batch ingestion (not real-time)

### Why Batch Script?

- **Resume capability** for interrupted scrapes (important for 120+ pages)
- **Flexible filtering** (by type, slug, specific pages)
- **Centralized logging** (timestamps, error tracking)
- **Dry-run mode** for validation
- **Progress tracking** with batch reports

### Why Separate URL Discovery?

- **Independent from scraping** - URLs can be refreshed without re-scraping
- **Deduplication** - Combines multiple source pages
- **Categorization** - Enables filtering (parts vs appendices)
- **Inventory management** - Audit trail of what exists on GOV.UK

---

## Performance Metrics

**Current Pipeline (as of 2025-12-06):**

| Metric | Value |
|--------|-------|
| Total URLs | 122 |
| URL Discovery Time | ~8 seconds (2 Jina calls) |
| Average Chunk Count per URL | ~70 chunks |
| Total Chunks Expected | ~8,500-10,000 |
| Scrape Rate | 20 RPM (3 sec/page) |
| Total Scrape Time | ~6 minutes (122 pages) |
| Storage per Page | 50-150 KB (raw + chunks) |
| Total Storage | ~15-20 MB |

**Optimizations:**
- Sequential scraping (max_concurrent=1) for predictability
- Resume capability to avoid re-scraping
- Filtering for incremental updates

---

## References

- **Jina Reader:** https://r.jina.ai
- **GOV.UK Immigration Rules:** https://www.gov.uk/guidance/immigration-rules
- **Parsing Logic:** `docs/hierarchical-legal-parsing.md`
- **Source Code:**
  - `data_pipeline/scrapers/get_govuk_urls.py` - URL discovery
  - `data_pipeline/scrapers/batch_scrape.py` - Batch orchestration
  - `data_pipeline/scrapers/govuk_jina_scraper.py` - Core scraper
- **Specification:** `.kiro/specs/legal-immigration-rag/`
