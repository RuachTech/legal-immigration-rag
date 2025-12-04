# GitHub Copilot Instructions - Legal Immigration RAG System

## Project Overview

This is a specialized RAG (Retrieval-Augmented Generation) system for UK immigration information. The architecture prioritizes **Document-Level Retrieval Mismatch (DRM) prevention** through Summary-Augmented Chunking (SAC), hybrid retrieval, and rationale-driven evidence selection. Every answer must be grounded in source documents with precise citations.

**🎯 Start Here:** Read `.kiro/specs/legal-immigration-rag/design.md` for complete system architecture and design philosophy.

## Project Specifications in .kiro/ Directory

The `.kiro/specs/legal-immigration-rag/` directory contains the **driving specifications** for this project:

- **`design.md`** - System architecture, design philosophy, data flows, correctness properties. **Read this first** for context.
- **`requirements.md`** - User stories with acceptance criteria. Each requirement has numbered acceptance criteria (e.g., Requirement 3.1, 3.4).
- **`tasks.md`** - Implementation plan with tasks mapped to requirements. Each task references which requirement(s) it fulfills.

### Critical Workflow Rule:

**When asked to work on a task from `tasks.md`, you MUST:**

1. Read the task description and note which requirements it references (e.g., "_Requirements: 3.1, 3.4_")
2. Open `requirements.md` and read those specific requirements
3. Ensure your implementation satisfies ALL acceptance criteria for those requirements
4. If implementing a property-based test, refer to the correctness properties in `design.md`

**Example:**
```markdown
Task 4.1: Create hybrid retriever combining vector and keyword search
  _Requirements: 3.1, 3.3, 3.4_
```

You must:
- Check Requirement 3.1 acceptance criteria (hybrid retrieval combines dense + sparse search)
- Check Requirement 3.3 acceptance criteria (exact keyword matches rank highly)
- Check Requirement 3.4 acceptance criteria (metadata filtering prevents DRM)
- Implement features that satisfy ALL of these

## Critical Architecture Patterns

### 1. Abstract Interfaces for Storage Backends

**All storage dependencies use abstract base classes for swappable implementations:**

```python
from storage import VectorStore, SessionStore  # Import from storage package
from storage import Chunk, ChunkMetadata, Conversation, Message
```

- **Vector Store**: `storage/vector/base.py` defines `VectorStore` ABC. Start with ChromaDB, migrate to Weaviate for production.
- **Session Store**: `storage/session/base.py` defines `SessionStore` ABC. Use Redis for fast in-memory sessions, MongoDB for persistence.

**When creating new storage integrations:** Implement the abstract interface, never couple directly to a specific backend. See `storage/vector/base.py` and `storage/session/base.py` for method contracts.

### 2. Summary-Augmented Chunking (SAC) for Legal Text

Legal documents have **Document-Level Retrieval Mismatch** risk—similar text from wrong documents gets retrieved. SAC prevents this:

1. Generate document-level summary (e.g., "Requirements for UK Skilled Worker visa as of Oct 2025")
2. Prepend summary to EVERY chunk from that document before embedding
3. Tag chunks with hierarchical metadata: `source`, `part`, `section`, `topic`, `url`

**When implementing chunking:** Always preserve document structure boundaries. Use semantic chunking + structure-based chunking. Never split mid-clause.

### 3. Data Models Are Defined in Storage Abstractions

The canonical data models live in `storage/`:
- `Chunk`, `ChunkMetadata` → `storage/vector/base.py`
- `Message`, `Citation`, `Rationale`, `Conversation` → `storage/session/base.py`

**Import these types from the storage package, not from implementations.**

## Developer Workflows

### Package Management with UV

This project uses **UV** (not pip) for dependency management:

```bash
# Install dependencies (creates .venv automatically)
uv sync

# Add new dependency
uv add langchain-anthropic

# Add dev dependency
uv add --dev pytest-mock

# Run scripts/tests
uv run python scripts/verify_setup.py
uv run pytest

# Update dependencies
uv sync --upgrade
```

**Never use `pip install` directly.** All dependencies are in `pyproject.toml`. UV is 10-100x faster than pip and ensures reproducible builds.

### Makefile Commands

```bash
make install        # Install dependencies with uv
make test           # Run pytest suite
make dev-services   # Start Redis + Weaviate via Docker
make frontend       # Start Vite dev server (React)
make backend        # Start FastAPI with uvicorn --reload
make clean          # Remove build artifacts
```

### Testing Strategy

**Three test types** (all in `tests/` directory):

1. **Unit tests** (`tests/unit/`) - Fast, isolated component tests
2. **Integration tests** (`tests/integration/`) - Test component interactions
3. **Property-based tests** (`tests/property/`) - Use Hypothesis for exhaustive testing

**Run tests with markers:**
```bash
uv run pytest -m unit              # Unit tests only
uv run pytest -m property          # Property-based tests
uv run pytest --cov=. --cov-report=html  # Coverage report
```

**Property-based testing** is critical for this domain—use Hypothesis to test invariants like "all citations must have valid URLs" or "retrieval must never return chunks from wrong documents."

### Service Dependencies

**Start external services before running backend:**

```bash
docker-compose up -d  # Starts Redis (port 6379) + Weaviate (port 8080)
```

- **Redis**: Session storage (conversations, message history)
- **Weaviate**: Vector database for hybrid search (ChromaDB for dev, Weaviate for prod)

Check services with:
```bash
redis-cli ping        # Should return PONG
curl http://localhost:8080/v1/.well-known/ready  # Weaviate health
```

## Code Conventions

### Import Organization

```python
# 1. Standard library
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

# 2. Third-party packages
from langchain.chains import ConversationalRetrievalChain
from fastapi import FastAPI, HTTPException

# 3. Local imports - use absolute imports from project packages
from storage import VectorStore, SessionStore, Chunk
from rag_pipeline.retrieval import HybridRetriever
from data_pipeline.processing import SummaryAugmentedChunker
```

### Dataclass Patterns

Use `@dataclass` for data models (following existing pattern in `storage/`):

```python
@dataclass
class Citation:
    source: str
    section: str
    url: str
    excerpt: str
```

### Type Hints

**Always use type hints** (project uses mypy):
```python
def hybrid_search(
    self,
    query: str,
    query_embedding: List[float],
    top_k: int = 10,
    filters: Optional[Dict[str, Any]] = None
) -> List[Chunk]:
    ...
```

## Domain-Specific Guidance

### RAG Pipeline Structure

The RAG flow is **conversational with memory**:

1. **Query Rewriting** (`rag_pipeline/generation/query_rewriter.py`) - Converts follow-up questions into standalone queries using conversation history
2. **Hybrid Retrieval** (`rag_pipeline/retrieval/`) - Combines vector search (semantic) + BM25 (keyword) for legal terms
3. **Rationale Generation** - Generates explicit explanations for why each chunk is relevant (METEORA pattern)
4. **Grounded Generation** - LLM generates answer using ONLY retrieved context, with mandatory citations

**Never generate answers without citations.** If context is insufficient, explicitly state "I cannot answer this question based on available sources."

### Metadata Schema for Chunks

Every chunk must have complete metadata for DRM prevention:

```python
ChunkMetadata(
    source="Immigration Rules Appendix Skilled Worker",
    part="Appendix Skilled Worker",
    section="SW 2.1",
    topic="Eligibility requirements",
    url="https://www.gov.uk/guidance/immigration-rules/appendix-skilled-worker",
    parent_section="SW 2.0",
    hierarchy_level=2
)
```

**Metadata filtering during retrieval is critical**—use it to constrain searches to relevant document sections.

### Frontend-Backend Integration

- **Frontend**: React + Vite + TypeScript (`frontend/`)
- **Backend**: FastAPI (`backend/main.py`)
- **API Pattern**: REST endpoints in `backend/api/`

**Session management:** Frontend sends `session_id` with each request. Backend retrieves conversation history from SessionStore to maintain context.

## What to Avoid

- ❌ **Never bypass abstract interfaces** - Don't import ChromaDB or Weaviate clients directly
- ❌ **Never chunk without SAC** - All legal text must use Summary-Augmented Chunking
- ❌ **Never generate without citations** - Every factual claim needs source + section + URL
- ❌ **Don't use pip** - Use `uv` for all dependency operations
- ❌ **Don't ignore DRM** - Legal text similarity causes retrieval mismatch; always use metadata filtering
- ❌ **Don't split legal clauses** - Chunking must respect document structure boundaries

## Project Specifications in .kiro/ Directory

The `.kiro/specs/legal-immigration-rag/` directory contains the **driving specifications** for this project:

- **`design.md`** - System architecture, design philosophy, data flows, correctness properties. **Read this first** for context.
- **`requirements.md`** - User stories with acceptance criteria. Each requirement has numbered acceptance criteria (e.g., Requirement 3.1, 3.4).
- **`tasks.md`** - Implementation plan with tasks mapped to requirements. Each task references which requirement(s) it fulfills.

### Critical Workflow Rule:

**When asked to work on a task from `tasks.md`, you MUST:**

1. Read the task description and note which requirements it references (e.g., "_Requirements: 3.1, 3.4_")
2. Open `requirements.md` and read those specific requirements
3. Ensure your implementation satisfies ALL acceptance criteria for those requirements
4. If implementing a property-based test, refer to the correctness properties in `design.md`

**Example:**
```markdown
Task 4.1: Create hybrid retriever combining vector and keyword search
  _Requirements: 3.1, 3.3, 3.4_
```

You must:
- Check Requirement 3.1 acceptance criteria (hybrid retrieval combines dense + sparse search)
- Check Requirement 3.3 acceptance criteria (exact keyword matches rank highly)
- Check Requirement 3.4 acceptance criteria (metadata filtering prevents DRM)
- Implement features that satisfy ALL of these

### Specification Files Quick Reference

- `.kiro/specs/legal-immigration-rag/design.md` - Architecture context (707 lines)
- `.kiro/specs/legal-immigration-rag/requirements.md` - Acceptance criteria (145 lines)
- `.kiro/specs/legal-immigration-rag/tasks.md` - Implementation plan (309 lines)

## Key Code Files Reference

- `storage/vector/base.py` - VectorStore abstract interface
- `storage/session/base.py` - SessionStore abstract interface + conversation models
- `pyproject.toml` - Dependencies, test config, tool settings
- `Makefile` - Development task shortcuts
- `docker-compose.yml` - Redis + Weaviate service definitions
- `docs/uv-commands.md` - UV package manager reference

## Additional Context

The system addresses **information volatility**—UK immigration policy changes frequently through "Statements of Changes." The data pipeline must continuously monitor GOV.UK for updates. When modifying ingestion logic, ensure temporal awareness (track effective dates, version history).

**Target users:** Immigrants navigating complex legal requirements without legal expertise. All UX and generation patterns should prioritize clarity, verifiability, and explicit uncertainty communication.
