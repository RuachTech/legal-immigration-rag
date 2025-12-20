# Indexing Pipeline Documentation

## Overview

The indexing pipeline orchestrates the complete process of transforming GOV.UK Immigration Rules into a searchable vector database for the RAG system. It connects four key stages:

1. **Scraping** - Fetch and parse GOV.UK pages
2. **SAC Enhancement** - Generate summaries and augmented text
3. **Embedding** - Create vector representations
4. **Vector Store Loading** - Index chunks for retrieval

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Indexing Pipeline                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌────────┐│
│  │ Scraping │───▶│   SAC    │───▶│Embedding │───▶│ Vector ││
│  │          │    │Enhancement│    │          │    │ Store  ││
│  └──────────┘    └──────────┘    └──────────┘    └────────┘│
│       │               │                │              │     │
│       ▼               ▼                ▼              ▼     │
│   chunks/         chunks/        chunks-embedded/  ChromaDB │
│                 (in-place)                        /Weaviate │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│  Incremental Indexer: Tracks state, detects changes         │
│  Progress Tracker: Real-time progress, logging, metrics     │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Full Indexing (First Time)

Process all Immigration Rules documents:

```bash
# Set required API keys
export JINA_API_KEY="your_jina_key"
export GEMINI_API_KEY="your_gemini_key"  # or OPENAI_API_KEY
export VOYAGE_API_KEY="your_voyage_key"

# Run full pipeline
uv run python scripts/index_pipeline.py --mode full
```

### Incremental Updates

Process only changed documents:

```bash
uv run python scripts/index_pipeline.py --mode incremental
```

### Testing with Limited Documents

```bash
# Process only first 5 documents
uv run python scripts/index_pipeline.py --mode full --limit 5
```

## Pipeline Stages

### Stage 1: Scraping

**Purpose**: Fetch Immigration Rules from GOV.UK and parse into structured chunks.

**Implementation**: `data_pipeline/scrapers/govuk_jina_scraper.py`

**Output**: `data/govuk-data/chunks/*.json`

**Note**: Currently run separately. Future versions will integrate into pipeline.

```bash
# Manual scraping (if needed)
uv run python data_pipeline/scrapers/batch_scrape.py
```

### Stage 2: SAC Enhancement

**Purpose**: Generate chunk-level summaries and create augmented text for embedding.

**Implementation**: `data_pipeline/processing/enhance_chunks_with_sac.py`

**What it does**:
- Generates 2-3 sentence summary for each chunk using LLM
- Creates metadata header (source, part, section, topic)
- Combines metadata + summary + original text = `augmented_text`
- Adds `summary` and `augmented_text` fields to chunks

**Output**: Updates chunks in-place in `data/govuk-data/chunks/*.json`

**Configuration**:
```bash
# Use different LLM for summaries
uv run python scripts/index_pipeline.py --sac-model gpt-4o-mini
```

### Stage 3: Embedding

**Purpose**: Generate vector embeddings for semantic search.

**Implementation**: `scripts/embed_chunks.py`

**What it does**:
- Embeds `augmented_text` field using voyage-law-2 (or LEGAL-BERT)
- Processes in batches for efficiency
- Adds `embedding` field to chunks

**Output**: `data/govuk-data/chunks-embedded/*.json`

**Configuration**:
```bash
# Use different embedding model
uv run python scripts/index_pipeline.py --embedding-model voyage-law-2

# Or use LEGAL-BERT (no API key needed)
uv run python scripts/index_pipeline.py --embedding-model nlpaueb/legal-bert-base-uncased
```

### Stage 4: Vector Store Loading

**Purpose**: Load embedded chunks into vector database for retrieval.

**Implementation**: `scripts/load_to_vectorstore.py`

**What it does**:
- Converts chunk JSON to `Chunk` objects
- Loads into ChromaDB or Weaviate
- Supports batch loading for efficiency

**Output**: Indexed chunks in vector store

**Configuration**:
```bash
# Use Weaviate instead of ChromaDB
uv run python scripts/index_pipeline.py --vector-store weaviate
```

## Incremental Indexing

The pipeline tracks which documents have been processed and can detect changes for efficient updates.

### How It Works

1. **State Tracking**: Maintains `data/govuk-data/index_state.json` with:
   - Document URLs
   - Content hashes
   - Last indexed timestamps
   - Chunk counts

2. **Change Detection**: Compares current chunks against state to find:
   - **New documents**: Not in state
   - **Updated documents**: Content hash changed
   - **Deleted documents**: In state but not in current chunks

3. **Incremental Processing**: Only processes changed documents

### Usage

```bash
# First run: full indexing
uv run python scripts/index_pipeline.py --mode full

# Subsequent runs: incremental updates
uv run python scripts/index_pipeline.py --mode incremental
```

### Index State File

Location: `data/govuk-data/index_state.json`

Structure:
```json
{
  "version": "1.0",
  "last_full_index": "2025-12-19T15:30:00",
  "last_incremental_index": "2025-12-19T16:45:00",
  "documents": {
    "https://www.gov.uk/guidance/...": {
      "url": "...",
      "part_name": "Appendix Skilled Worker",
      "last_scraped_at": "2025-12-19T15:30:00",
      "content_hash": "abc123...",
      "chunk_count": 45,
      "last_indexed_at": "2025-12-19T15:30:00"
    }
  }
}
```

## Progress Tracking

The pipeline provides real-time progress tracking with detailed logging.

### Console Output

```
============================================================
INDEXING PIPELINE STARTED
Start time: 2025-12-19 15:30:00
============================================================

Pipeline Mode: full
Data Directory: data/govuk-data
Vector Store: chromadb
Embedding Model: voyage-law-2

============================================================
STAGE: SAC Enhancement
Total items: 100
============================================================
Starting SAC Enhancement...
[SAC Enhancement] Progress: 25/100 (25.0%) - Success: 25, Failed: 0
[SAC Enhancement] Rate: 2.50 items/sec, ETA: 30.0s
...
```

### Log Files

Detailed logs saved to: `data/govuk-data/pipeline_logs/pipeline_YYYYMMDD_HHMMSS.log`

Includes:
- Timestamp for each operation
- Success/failure status
- Error messages with stack traces
- Performance metrics

## Command-Line Options

### Mode Selection

```bash
--mode {full,incremental}    # Indexing mode (default: full)
```

### Stage Control

Skip stages to resume from a specific point:

```bash
--skip-scrape     # Skip scraping (use existing chunks)
--skip-sac        # Skip SAC enhancement
--skip-embed      # Skip embedding
--skip-load       # Skip vector store loading
```

**Example**: Resume from embedding after SAC completed:
```bash
uv run python scripts/index_pipeline.py --skip-scrape --skip-sac
```

### Configuration

```bash
--data-dir PATH                  # Data directory (default: data/govuk-data)
--vector-store {chromadb,weaviate}  # Vector store backend
--embedding-model MODEL          # Embedding model name
--sac-model MODEL               # LLM for SAC summaries
```

### Options

```bash
--dry-run        # Validate without loading to vector store
--limit N        # Process only first N documents (testing)
```

## Vector Store Support

The pipeline supports multiple vector store backends through the abstract `VectorStore` interface.

### ChromaDB (Development)

**Default for local development**

```bash
uv run python scripts/index_pipeline.py --vector-store chromadb
```

**Pros**:
- Easy setup, no external services
- Good for development and testing
- Persistent storage

**Cons**:
- No native BM25 keyword search
- Limited scalability

### Weaviate (Production)

**Recommended for production**

```bash
# Start Weaviate
docker-compose up -d

# Run pipeline with Weaviate
uv run python scripts/index_pipeline.py --vector-store weaviate
```

**Pros**:
- Native hybrid search (vector + BM25)
- Highly scalable
- Production-ready

**Cons**:
- Requires external service
- More complex setup

## Error Handling

### Automatic Recovery

The pipeline is designed to be resilient:

1. **Stage Independence**: Each stage can be run separately
2. **Checkpoint Files**: State saved after each document
3. **Retry Logic**: Transient failures automatically retried
4. **Graceful Degradation**: Failed chunks logged but don't block pipeline

### Manual Recovery

If pipeline fails mid-execution:

```bash
# Check logs
cat data/govuk-data/pipeline_logs/pipeline_*.log | grep ERROR

# Resume from failed stage
uv run python scripts/index_pipeline.py --skip-scrape --skip-sac
```

## Performance Optimization

### Batch Sizes

Adjust batch sizes for optimal performance:

**Embedding**:
```bash
# Default: 128 chunks per batch
uv run python scripts/embed_chunks.py --batch-size 256
```

**Vector Store Loading**:
```bash
# Default: 100 chunks per batch
uv run python scripts/load_to_vectorstore.py --batch-size 200
```

### Parallel Processing

Future enhancement: Process multiple documents in parallel while respecting API rate limits.

## Monitoring

### Real-Time Metrics

The pipeline tracks:
- **Processing rate**: Items per second
- **Success rate**: Percentage of successful operations
- **ETA**: Estimated time remaining
- **Error count**: Failed operations per stage

### Summary Report

At completion, displays:
```
============================================================
PIPELINE SUMMARY
============================================================
Total Duration: 15.5m

Total Items Processed: 450
Total Items Failed: 5
Overall Success Rate: 98.9%

Stage Breakdown:
------------------------------------------------------------

SAC Enhancement:
  Processed: 100/100
  Failed: 0
  Success Rate: 100.0%
  Duration: 5.2m

Embedding:
  Processed: 98/100
  Failed: 2
  Success Rate: 98.0%
  Duration: 8.1m

Vector Store Loading:
  Processed: 98/98
  Failed: 0
  Success Rate: 100.0%
  Duration: 2.2m
============================================================
```

## Troubleshooting

### Common Issues

**1. API Key Not Found**
```
Error: VOYAGE_API_KEY environment variable not set
```
**Solution**: Set required API keys in `.env` file

**2. Chunk Files Not Found**
```
Error: Chunks directory not found: data/govuk-data/chunks
```
**Solution**: Run scraping first or check data directory path

**3. Embedding Failures**
```
Error: Failed to embed batch: Rate limit exceeded
```
**Solution**: Pipeline will retry automatically. Check API quota.

**4. Vector Store Connection Failed**
```
Error: Failed to initialize vector store
```
**Solution**: Ensure ChromaDB/Weaviate is running (check `docker-compose up -d`)

### Debug Mode

Enable verbose logging:
```bash
# Set log level to DEBUG
export LOG_LEVEL=DEBUG
uv run python scripts/index_pipeline.py --mode full
```

## Best Practices

### 1. Test with Limited Data First

```bash
# Test with 5 documents
uv run python scripts/index_pipeline.py --mode full --limit 5
```

### 2. Use Dry Run for Validation

```bash
# Validate without loading to vector store
uv run python scripts/index_pipeline.py --dry-run
```

### 3. Monitor Logs

```bash
# Watch logs in real-time
tail -f data/govuk-data/pipeline_logs/pipeline_*.log
```

### 4. Regular Incremental Updates

```bash
# Set up cron job for daily updates
0 2 * * * cd /path/to/project && uv run python scripts/index_pipeline.py --mode incremental
```

### 5. Backup Index State

```bash
# Backup state file before major changes
cp data/govuk-data/index_state.json data/govuk-data/index_state.backup.json
```

## Integration with RAG System

Once indexing is complete, the vector store is ready for retrieval:

```python
from storage.factories import create_vector_store

# Initialize vector store
vector_store = create_vector_store(store_type="chromadb")

# Perform hybrid search
results = vector_store.hybrid_search(
    query="What are the salary requirements for Skilled Worker visa?",
    query_embedding=embedder.embed_text(query),
    top_k=10,
    filters={"part": "Appendix Skilled Worker"}
)
```

## Future Enhancements

- [ ] Integrate scraping into pipeline (currently manual)
- [ ] Parallel document processing
- [ ] Webhook support for automatic updates
- [ ] Metrics dashboard
- [ ] A/B testing for different chunking strategies
- [ ] Automatic quality validation

## Related Documentation

- [Data Pipeline Overview](./data-pipeline.md)
- [SAC Implementation Learnings](./sac-implementation-learnings.md)
- [Embedder Usage](./embedder-usage.md)
- [Storage Implementation](./storage-implementation-summary.md)
