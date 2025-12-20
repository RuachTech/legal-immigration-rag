# Indexing Pipeline Quick Start Guide

## Prerequisites

### Required API Keys

Set these in your `.env` file or export as environment variables:

```bash
# For scraping GOV.UK pages
export JINA_API_KEY="your_jina_api_key"

# For SAC summaries (choose one)
export GEMINI_API_KEY="your_gemini_key"
# OR
export OPENAI_API_KEY="your_openai_key"

# For embeddings
export VOYAGE_API_KEY="your_voyage_key"
```

### External Services

For Weaviate (production):
```bash
docker-compose up -d
```

## Common Commands

### Full Indexing (First Time)

Process all Immigration Rules documents:

```bash
uv run python scripts/index_pipeline.py --mode full
```

### Incremental Updates

Process only changed documents:

```bash
uv run python scripts/index_pipeline.py --mode incremental
```

### Testing with Sample Data

Process only 5 documents for testing:

```bash
uv run python scripts/index_pipeline.py --mode full --limit 5
```

### Dry Run (Validation Only)

Validate pipeline without loading to vector store:

```bash
uv run python scripts/index_pipeline.py --dry-run
```

### Using Weaviate Instead of ChromaDB

```bash
# Ensure Weaviate is running
docker-compose up -d

# Run pipeline with Weaviate
uv run python scripts/index_pipeline.py --vector-store weaviate
```

## Stage-by-Stage Execution

### Run Individual Stages

If you need to run stages separately:

#### 1. Scraping Only

```bash
# Scrape all Immigration Rules
uv run python data_pipeline/scrapers/batch_scrape.py

# Or scrape specific URLs
uv run python data_pipeline/scrapers/govuk_jina_scraper.py --scrape
```

#### 2. SAC Enhancement Only

```bash
# Enhance all chunks with summaries
uv run python data_pipeline/processing/enhance_chunks_with_sac.py --in-place

# Use specific model
uv run python data_pipeline/processing/enhance_chunks_with_sac.py \
  --in-place \
  --model gpt-4o-mini
```

#### 3. Embedding Only

```bash
# Embed all chunks
uv run python scripts/embed_chunks.py

# Use specific model
uv run python scripts/embed_chunks.py --model voyage-law-2

# Or use LEGAL-BERT (no API key needed)
uv run python scripts/embed_chunks.py --model nlpaueb/legal-bert-base-uncased
```

#### 4. Vector Store Loading Only

```bash
# Load to ChromaDB
uv run python scripts/load_to_vectorstore.py

# Load to Weaviate
uv run python scripts/load_to_vectorstore.py --vector-store weaviate

# Dry run (validate without loading)
uv run python scripts/load_to_vectorstore.py --dry-run
```

### Resume from Specific Stage

Skip completed stages:

```bash
# Resume from embedding (skip scraping and SAC)
uv run python scripts/index_pipeline.py --skip-scrape --skip-sac

# Resume from vector store loading
uv run python scripts/index_pipeline.py --skip-scrape --skip-sac --skip-embed
```

## Configuration Options

### Change Models

```bash
# Use different embedding model
uv run python scripts/index_pipeline.py \
  --embedding-model voyage-law-2

# Use different SAC model
uv run python scripts/index_pipeline.py \
  --sac-model gpt-4o-mini
```

### Change Data Directory

```bash
uv run python scripts/index_pipeline.py \
  --data-dir /path/to/custom/data
```

### Adjust Batch Sizes

For embedding:
```bash
uv run python scripts/embed_chunks.py --batch-size 256
```

For vector store loading:
```bash
uv run python scripts/load_to_vectorstore.py --batch-size 200
```

## Monitoring Progress

### View Logs

Logs are saved to `data/govuk-data/pipeline_logs/`:

```bash
# View latest log
tail -f data/govuk-data/pipeline_logs/pipeline_*.log

# Search for errors
grep ERROR data/govuk-data/pipeline_logs/pipeline_*.log
```

### Check Index State

View current indexing state:

```bash
cat data/govuk-data/index_state.json | jq
```

## Troubleshooting

### Pipeline Failed Mid-Execution

Resume from the failed stage:

```bash
# Check logs for which stage failed
cat data/govuk-data/pipeline_logs/pipeline_*.log | grep ERROR

# Resume from that stage
uv run python scripts/index_pipeline.py --skip-scrape --skip-sac
```

### API Rate Limits

The pipeline has built-in retry logic. If you hit rate limits:

1. Wait a few minutes
2. Resume from the failed stage
3. Pipeline will continue from where it left off

### Vector Store Connection Issues

For ChromaDB:
```bash
# ChromaDB is embedded, no external service needed
# Check if data directory is writable
ls -la data/govuk-data/
```

For Weaviate:
```bash
# Check if Weaviate is running
docker ps | grep weaviate

# Restart if needed
docker-compose restart weaviate

# Check health
curl http://localhost:8080/v1/.well-known/ready
```

### Missing Chunks

If chunks are missing after scraping:

```bash
# Check chunk files
ls -la data/govuk-data/chunks/

# Re-run scraping for specific URLs
uv run python data_pipeline/scrapers/batch_scrape.py
```

## Performance Tips

### 1. Use Incremental Mode

After initial full indexing, always use incremental mode:

```bash
# Daily updates
uv run python scripts/index_pipeline.py --mode incremental
```

### 2. Test with Limited Data First

Before processing all documents:

```bash
uv run python scripts/index_pipeline.py --mode full --limit 5
```

### 3. Monitor Resource Usage

```bash
# Watch memory and CPU
htop

# Check disk space
df -h data/govuk-data/
```

### 4. Optimize Batch Sizes

Adjust based on your system:

- **High memory**: Increase batch sizes (256-512)
- **Low memory**: Decrease batch sizes (64-128)

## Scheduled Updates

### Set Up Cron Job

For daily incremental updates:

```bash
# Edit crontab
crontab -e

# Add this line (runs at 2 AM daily)
0 2 * * * cd /path/to/project && uv run python scripts/index_pipeline.py --mode incremental >> /var/log/indexing-pipeline.log 2>&1
```

### Manual Scheduled Run

```bash
# Create a script
cat > run_incremental_update.sh << 'EOF'
#!/bin/bash
cd /path/to/project
source .venv/bin/activate
python scripts/index_pipeline.py --mode incremental
EOF

chmod +x run_incremental_update.sh

# Run manually
./run_incremental_update.sh
```

## Next Steps

After indexing is complete:

1. **Verify indexed chunks**:
   ```bash
   uv run python scripts/verify_storage.py
   ```

2. **Test retrieval**:
   ```python
   from storage.factories import create_vector_store
   
   store = create_vector_store(store_type="chromadb")
   results = store.hybrid_search(
       query="Skilled Worker visa requirements",
       query_embedding=embedder.embed_text(query),
       top_k=10
   )
   ```

3. **Build RAG pipeline** (Task 4.x in tasks.md)

## Additional Resources

- [Full Pipeline Documentation](./indexing-pipeline.md)
- [SAC Implementation Guide](./sac-implementation-learnings.md)
- [Embedder Usage](./embedder-usage.md)
- [Storage Implementation](./storage-implementation-summary.md)
