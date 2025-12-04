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

## Documentation

See the `.kiro/specs/legal-immigration-rag/` directory for:
- `requirements.md`: Detailed requirements with acceptance criteria
- `design.md`: System architecture and correctness properties
- `tasks.md`: Implementation plan and task list
