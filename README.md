# Legal Immigration RAG System

A Retrieval-Augmented Generation (RAG) system designed to make UK immigration information accessible through natural language conversation.

## Project Structure

```
legal-immigration-rag/
├── frontend/                    # React application
│   ├── src/
│   │   ├── components/         # UI components
│   │   ├── hooks/              # Custom React hooks
│   │   ├── services/           # API client
│   │   └── types/              # TypeScript types
│   └── package.json
│
├── backend/                     # FastAPI application
│   ├── api/                    # API routes
│   ├── core/                   # Core business logic
│   └── main.py
│
├── rag_pipeline/               # RAG implementation
│   ├── retrieval/              # Hybrid retrieval system
│   ├── generation/             # Query rewriting and generation
│   ├── memory/                 # Conversation memory
│   └── chain.py                # Main RAG chain
│
├── data_pipeline/              # Data ingestion
│   ├── scrapers/               # GOV.UK scraper
│   ├── processing/             # Chunking and embedding
│   └── indexer.py
│
├── storage/                    # Storage adapters
│   ├── vector/                 # Vector store interface and implementations
│   └── session/                # Session store interface and implementations
│
├── evaluation/                 # Testing and evaluation
│   ├── metrics/                # RAGAS evaluator
│   ├── datasets/               # Gold standard dataset
│   └── benchmarks/
│
├── tests/                      # Test suites
│   ├── unit/
│   ├── integration/
│   └── property/              # Property-based tests
│
├── scripts/                    # Utility scripts
└── docs/                       # Documentation
```

## Setup

### Python Environment

1. Install dependencies with uv (automatically creates venv):
```bash
uv sync
```

2. Run commands with uv:
```bash
uv run python scripts/verify_setup.py
uv run pytest
```

Or activate the virtual environment:
```bash
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### Frontend

1. Install dependencies:
```bash
cd frontend
npm install
```

2. Run development server:
```bash
npm run dev
```

## Architecture

The system follows a modular architecture with clean interfaces:

- **Vector Store**: Abstract interface allows swapping between ChromaDB (development) and Weaviate (production)
- **Session Store**: Abstract interface supports Redis, MongoDB, or other backends
- **RAG Pipeline**: LangChain-based conversational RAG with hybrid retrieval
- **Data Pipeline**: Continuous ingestion from GOV.UK with Summary-Augmented Chunking

## Key Features

- **Hybrid Retrieval**: Combines vector search with keyword matching (BM25)
- **Summary-Augmented Chunking**: Prepends document summaries to chunks to prevent retrieval mismatch
- **Rationale-Driven Selection**: Generates explicit explanations for evidence selection
- **Grounded Generation**: All answers cite source documents with GOV.UK links
- **Conversational Memory**: Multi-turn conversations with context preservation

## Testing

The system uses both unit tests and property-based tests (Hypothesis):

```bash
# Run all tests
pytest

# Run property-based tests only
pytest tests/property/

# Run with coverage
pytest --cov=. --cov-report=html
```

## Indexing Pipeline

The indexing pipeline transforms GOV.UK Immigration Rules into a searchable vector database:

### Quick Start

```bash
# Set required API keys
export JINA_API_KEY="your_jina_key"
export GEMINI_API_KEY="your_gemini_key"
export VOYAGE_API_KEY="your_voyage_key"

# Run full indexing pipeline
uv run python scripts/index_pipeline.py --mode full

# Run incremental updates (only changed documents)
uv run python scripts/index_pipeline.py --mode incremental

# Test with limited documents
uv run python scripts/index_pipeline.py --mode full --limit 5
```

### Pipeline Stages

1. **Scraping**: Fetch and parse GOV.UK pages (via `govuk_jina_scraper.py`)
2. **SAC Enhancement**: Generate summaries and augmented text for embedding
3. **Embedding**: Create vector representations using voyage-law-2
4. **Vector Store Loading**: Index chunks in ChromaDB or Weaviate

### Individual Scripts

Run stages independently:

```bash
# Scraping
uv run python data_pipeline/scrapers/batch_scrape.py

# SAC Enhancement
uv run python data_pipeline/processing/enhance_chunks_with_sac.py --in-place

# Embedding
uv run python scripts/embed_chunks.py --model voyage-law-2

# Vector Store Loading
uv run python scripts/load_to_vectorstore.py --vector-store chromadb
```

### Vector Store Support

Switch between ChromaDB (development) and Weaviate (production):

```bash
# ChromaDB (default)
uv run python scripts/index_pipeline.py --vector-store chromadb

# Weaviate (requires docker-compose up -d)
uv run python scripts/index_pipeline.py --vector-store weaviate
```

See [docs/indexing-pipeline.md](docs/indexing-pipeline.md) for complete documentation.

## Documentation

### Project Specifications

See the `.kiro/specs/legal-immigration-rag/` directory for:
- `requirements.md`: Detailed requirements with acceptance criteria
- `design.md`: System architecture and correctness properties
- `tasks.md`: Implementation plan and task list

### Implementation Guides

- [Indexing Pipeline](docs/indexing-pipeline.md): Complete pipeline documentation
- [Data Pipeline](docs/data-pipeline.md): Data ingestion overview
- [SAC Implementation](docs/sac-implementation-learnings.md): Summary-Augmented Chunking
- [Embedder Usage](docs/embedder-usage.md): Embedding generation
- [Storage Implementation](docs/storage-implementation-summary.md): Vector and session stores
