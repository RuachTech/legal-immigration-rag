# Legal Domain Embedder Usage Guide

## Overview

The Legal Domain Embedder provides a clean abstraction for generating embeddings from legal immigration documents. It supports two embedding models that can be easily switched via configuration:

- **voyage-law-2** (Recommended) - Legal domain-specific model
- **LEGAL-BERT** (Alternative) - Open-source general legal model

## Why voyage-law-2?

We chose **voyage-law-2** as the default embedding model for several critical reasons:

### 1. **Legal Domain Specialization**
- Specifically trained on legal text corpora including case law, statutes, and regulations
- Superior understanding of legal terminology, citations, and document structure
- Better semantic representation of legal concepts compared to general-purpose models

### 2. **Higher Embedding Dimension (1024 vs 768)**
- voyage-law-2 produces 1024-dimensional embeddings vs LEGAL-BERT's 768 dimensions
- More expressive representations capture nuanced legal distinctions
- Better performance on retrieval tasks for complex legal queries

### 3. **Optimized for Retrieval**
- Designed specifically for semantic search and retrieval tasks
- Outperforms LEGAL-BERT on legal document retrieval benchmarks
- Better handles the Document-Level Retrieval Mismatch (DRM) problem in legal text

### 4. **Production-Ready Performance**
- Hosted API with high availability and low latency
- Efficient batch processing capabilities
- Regular model updates and improvements

### When to Use LEGAL-BERT

LEGAL-BERT is a viable alternative for:
- **Development/Testing**: No API costs, runs locally
- **Offline Operation**: No internet connection required
- **Budget Constraints**: Open-source with no usage fees
- **Custom Fine-tuning**: Can be fine-tuned on specific legal domains

However, for production use with UK immigration law, voyage-law-2's superior legal domain knowledge and retrieval performance make it the recommended choice.

## Features

- **Flexible Model Selection**: Easy switching between voyage-law-2 and LEGAL-BERT
- **Batch Processing**: Efficient batch embedding with configurable batch sizes
- **Error Handling**: Automatic retry with exponential backoff for API failures
- **Clean Architecture**: Abstract interface allows seamless model migration

## Installation

Dependencies are already installed via `pyproject.toml`:

```bash
uv sync
```

Required packages:
- `voyageai` - Voyage AI API client
- `sentence-transformers` - For LEGAL-BERT fallback
- `tenacity` - Retry logic with exponential backoff

## Configuration

Set your Voyage AI API key in `.env`:

```bash
VOYAGE_API_KEY=your_voyage_api_key_here
EMBEDDING_MODEL=voyage-law-2
EMBEDDING_BATCH_SIZE=128
FALLBACK_EMBEDDING_MODEL=nlpaueb/legal-bert-base-uncased
```

## Basic Usage

### Initialize the Embedder

```python
from data_pipeline.processing.embedder import LegalEmbedder

# With Voyage AI (recommended for production)
embedder = LegalEmbedder(
    model_name="voyage-law-2",
    batch_size=128,
    use_fallback=True,  # Enable LEGAL-BERT fallback
    api_key="your_api_key"  # Or set VOYAGE_API_KEY env var
)

# With LEGAL-BERT only (for development/testing)
embedder = LegalEmbedder(
    model_name="nlpaueb/legal-bert-base-uncased",
    use_fallback=False
)
```

### Embed Single Text

```python
text = "A person applying for a Skilled Worker visa must meet the salary threshold."
embedding = embedder.embed_text(text)

print(f"Embedding dimension: {len(embedding)}")  # 1024 for voyage-law-2
```

### Embed Batch of Texts

```python
texts = [
    "Skilled Worker visa requirements",
    "Student visa eligibility criteria",
    "Family visa application process"
]

embeddings, failed_indices = embedder.embed_batch(texts)

print(f"Successfully embedded: {len(embeddings)} texts")
print(f"Failed: {len(failed_indices)} texts")
```

### Embed Chunks (Main Use Case)

```python
import json

# Load chunks from JSON file
with open("data/govuk-data/chunks/appendix-skilled-worker.json", "r") as f:
    data = json.load(f)
    chunks = data["chunks"]

# Embed all chunks
embedded_chunks, failed_ids = embedder.embed_chunks(
    chunks,
    text_field="augmented_text"  # Field containing text to embed
)

print(f"Embedded {len(embedded_chunks)} chunks")
print(f"Failed: {len(failed_ids)} chunks")

# Save embedded chunks
output_data = {
    "document_id": data["document_id"],
    "chunks": embedded_chunks,
    "embedding_model": embedder.get_model_info()
}

with open("data/govuk-data/chunks-embedded/appendix-skilled-worker.json", "w") as f:
    json.dump(output_data, f, indent=2)
```

## Advanced Usage

### Get Model Information

```python
info = embedder.get_model_info()
print(info)
# {
#     "primary_model": "voyage-law-2",
#     "fallback_model": "nlpaueb/legal-bert-base-uncased",
#     "batch_size": 128,
#     "embedding_dimension": 1024
# }
```

### Custom Batch Size

```python
# For rate-limited APIs or memory constraints
embedder = LegalEmbedder(
    model_name="voyage-law-2",
    batch_size=32,  # Smaller batches
    api_key="your_api_key"
)
```

### Error Handling

```python
try:
    embedding = embedder.embed_text("Sample text")
except RuntimeError as e:
    print(f"Embedding failed: {e}")
    # Handle fallback or retry logic
```

## Batch Embedding Script

For embedding all chunks in the data pipeline:

```python
import json
import glob
from pathlib import Path
from data_pipeline.processing.embedder import LegalEmbedder

def embed_all_chunks():
    """Embed all chunks in the chunks directory."""
    embedder = LegalEmbedder(
        model_name="voyage-law-2",
        batch_size=128,
        use_fallback=True
    )
    
    chunks_dir = Path("data/govuk-data/chunks")
    output_dir = Path("data/govuk-data/chunks-embedded")
    output_dir.mkdir(exist_ok=True)
    
    chunk_files = list(chunks_dir.glob("*.json"))
    
    for i, chunk_file in enumerate(chunk_files, 1):
        print(f"\nProcessing {i}/{len(chunk_files)}: {chunk_file.name}")
        
        # Load chunks
        with open(chunk_file, "r") as f:
            data = json.load(f)
        
        if "chunks" not in data or not data["chunks"]:
            print(f"  Skipping (no chunks)")
            continue
        
        # Embed chunks
        embedded_chunks, failed_ids = embedder.embed_chunks(
            data["chunks"],
            text_field="augmented_text"
        )
        
        print(f"  Embedded: {len(embedded_chunks)}/{len(data['chunks'])}")
        
        if failed_ids:
            print(f"  Failed: {failed_ids}")
        
        # Save embedded chunks
        output_data = {
            **data,
            "chunks": embedded_chunks,
            "embedding_metadata": embedder.get_model_info()
        }
        
        output_file = output_dir / chunk_file.name
        with open(output_file, "w") as f:
            json.dump(output_data, f, indent=2)
    
    print(f"\n✓ Embedding complete! Output: {output_dir}")

if __name__ == "__main__":
    embed_all_chunks()
```

## Performance Considerations

### Batch Size Optimization

- **voyage-law-2**: Recommended batch size 128-256
- **LEGAL-BERT**: Batch size depends on available GPU memory (32-128)

### Rate Limiting

The embedder includes automatic retry with exponential backoff:
- 3 retry attempts
- Initial wait: 2 seconds
- Maximum wait: 10 seconds

### Cost Optimization

- Use batch embedding instead of single-text embedding
- Enable fallback to LEGAL-BERT for development/testing
- Monitor API usage through Voyage AI dashboard

## Embedding Dimensions

- **voyage-law-2**: 1024 dimensions
- **LEGAL-BERT**: 768 dimensions

**Note**: If you switch models, you must re-index all chunks in the vector database.

## Troubleshooting

### API Key Not Found

```
ValueError: Voyage AI API key not provided
```

**Solution**: Set `VOYAGE_API_KEY` environment variable or pass `api_key` parameter.

### Import Error

```
ImportError: voyageai package not installed
```

**Solution**: Run `uv sync` to install dependencies.

### Timeout Errors

If embedding times out, try:
1. Reduce batch size
2. Check network connection
3. Verify API key is valid

### Fallback Activation

If you see "Using fallback provider" in logs, the primary provider failed. Check:
1. API key validity
2. Network connectivity
3. Voyage AI service status

## Integration with Vector Store

After embedding, chunks can be indexed in ChromaDB or Weaviate:

```python
from storage.vector import ChromaDBStore

# Initialize vector store
vector_store = ChromaDBStore(
    collection_name="immigration_rules",
    persist_directory="./chroma_data"
)

# Add embedded chunks
vector_store.add_chunks(embedded_chunks)
```

## Next Steps

- See `storage/vector/base.py` for vector store integration
- See `rag_pipeline/retrieval/hybrid_retriever.py` for retrieval usage
- See `.kiro/specs/legal-immigration-rag/design.md` for system architecture
