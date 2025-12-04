# Design Document: Legal Immigration RAG System

## Overview

The Legal Immigration RAG System is a specialized Retrieval-Augmented Generation application designed to make UK immigration information accessible through natural language conversation. The system addresses the critical challenge of Document-Level Retrieval Mismatch (DRM) in legal text through advanced techniques including Summary-Augmented Chunking (SAC), hybrid retrieval, and rationale-driven evidence selection.

The system operates as a full-stack web application with three core subsystems:

1. **Data Ingestion Pipeline**: Continuously scrapes, processes, and indexes UK immigration documents from GOV.UK
2. **Query Processing Pipeline**: Handles user queries through conversational memory, query rewriting, hybrid retrieval, and grounded generation
3. **Evaluation Framework**: Provides quantitative metrics and benchmarking against a gold standard dataset

The architecture prioritizes transparency, verifiability, and safety—every generated answer must be grounded in source documents with precise citations, and the system must explicitly communicate uncertainty when confidence is low.

## Architecture

### Design Philosophy: Clean Interfaces and Swappable Implementations

The system is designed with **dependency inversion** and **interface segregation** principles to enable seamless migration between storage backends:

- **Vector Store**: Start with ChromaDB for rapid development, migrate to Weaviate for production scale
- **Session Store**: Use Redis for fast in-memory session management, with option to switch to MongoDB for persistence
- **Embedding Models**: Abstract embedding interface allows switching between voyage-law-2, LEGAL-BERT, or other models
- **LLM Providers**: Support multiple LLM backends (OpenAI, Anthropic, local models) through unified interface

All storage and external service dependencies are accessed through abstract base classes, with concrete implementations injected at runtime via configuration. This enables:
- Zero-downtime migrations between backends
- A/B testing of different implementations
- Easy mocking for unit tests
- Future-proof architecture

### System Components

The system follows a modular, microservices-inspired architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
│  - Chat Interface  - Citation Display  - Session Management │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTPS/REST API
┌────────────────────────▼────────────────────────────────────┐
│                   Backend (FastAPI)                          │
│  - API Gateway  - Authentication  - Pipeline Orchestration  │
└─────┬──────────────────┬──────────────────┬─────────────────┘
      │                  │                  │
      │                  │                  │
┌─────▼─────┐   ┌────────▼────────┐   ┌────▼──────────────┐
│  Session  │   │  RAG Pipeline   │   │  Vector Store     │
│  Store    │   │   (LangChain +  │   │  (ChromaDB →      │
│  (Redis)  │   │   LlamaIndex)   │   │   Weaviate)       │
└───────────┘   └─────────────────┘   └───────────────────┘
```

### Project Structure

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
│   │   ├── chat.py
│   │   ├── sessions.py
│   │   └── health.py
│   ├── core/                   # Core business logic
│   │   ├── config.py
│   │   └── security.py
│   └── main.py
│
├── rag_pipeline/               # RAG implementation
│   ├── retrieval/
│   │   ├── hybrid_retriever.py
│   │   ├── rationale_generator.py
│   │   └── vector_store.py     # Abstract interface
│   ├── generation/
│   │   ├── query_rewriter.py
│   │   └── grounded_generator.py
│   ├── memory/
│   │   └── conversation_memory.py
│   └── chain.py                # Main RAG chain
│
├── data_pipeline/              # Data ingestion
│   ├── scrapers/
│   │   ├── govuk_scraper.py
│   │   └── parser.py
│   ├── processing/
│   │   ├── chunker.py          # SAC implementation
│   │   └── embedder.py
│   └── indexer.py
│
├── storage/                    # Storage adapters
│   ├── vector/
│   │   ├── base.py            # Abstract VectorStore
│   │   ├── chroma_store.py    # ChromaDB implementation
│   │   └── weaviate_store.py  # Weaviate implementation
│   └── session/
│       ├── base.py            # Abstract SessionStore
│       ├── redis_store.py     # Redis implementation
│       └── mongo_store.py     # MongoDB implementation (future)
│
├── evaluation/                 # Testing and evaluation
│   ├── metrics/
│   │   └── ragas_evaluator.py
│   ├── datasets/
│   │   └── gold_standard.json
│   └── benchmarks/
│
├── tests/                      # Test suites
│   ├── unit/
│   ├── integration/
│   └── property/              # Property-based tests
│
├── scripts/                    # Utility scripts
│   ├── run_scraper.py
│   ├── run_evaluation.py
│   └── migrate_vector_db.py
│
├── docs/                       # Documentation
│   └── api.md
│
├── docker-compose.yml          # Local development setup
├── requirements.txt
└── README.md
```



### Data Flow

**Ingestion Flow:**
1. Scraper monitors GOV.UK for Immigration Rules and Statements of Changes
2. Parser extracts hierarchical structure (Parts, Sections, Paragraphs) with metadata
3. Chunker applies SAC: generates document summary, chunks text, prepends summary to each chunk
4. Embedder converts chunks to vectors using legal domain-specific model (voyage-law-2)
5. Indexer stores vectors in Weaviate with rich metadata (source, section, topic)

**Query Flow:**
1. User submits query through React frontend
2. Backend retrieves conversation history from MongoDB using session ID
3. LangChain agent rewrites query into standalone question using conversation context
4. Hybrid retriever searches Weaviate (vector + BM25) and returns top 10 chunks
5. Rationale generator (METEORA) creates explicit explanations for each chunk's relevance
6. Evidence selector filters chunks based on rationale quality
7. Generator LLM produces grounded answer with citations
8. Response with citations and rationales returned to frontend

## Components and Interfaces

### Frontend Component (React)

**Responsibilities:**
- Render conversational chat interface with message history
- Display generated answers with inline citations and expandable rationales
- Manage session state and handle WebSocket connections for streaming responses
- Show prominent disclaimer modal on first access

**Key Interfaces:**
```typescript
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  rationales?: Rationale[];
  timestamp: Date;
}

interface Citation {
  source: string;        // "Immigration Rules, Appendix Skilled Worker"
  section: string;       // "SW 8.1"
  url: string;          // GOV.UK link
  excerpt: string;      // Relevant text snippet
}

interface Rationale {
  chunkId: string;
  explanation: string;  // Why this chunk is relevant
  confidence: number;   // 0-1 score
}
```



### Backend API (FastAPI)

**Responsibilities:**
- Expose REST endpoints for chat, session management, and health checks
- Authenticate requests and manage rate limiting
- Orchestrate RAG pipeline execution
- Handle error cases and return appropriate HTTP status codes

**Key Endpoints:**
```python
POST /api/chat
  Request: { session_id: str, message: str }
  Response: { answer: str, citations: List[Citation], rationales: List[Rationale] }

GET /api/sessions/{session_id}
  Response: { messages: List[ChatMessage], created_at: datetime }

POST /api/sessions
  Response: { session_id: str }

GET /api/health
  Response: { status: str, components: Dict[str, bool] }
```

### RAG Pipeline (LangChain + LlamaIndex)

**Responsibilities:**
- Manage conversation memory using RunnableWithMessageHistory
- Rewrite ambiguous queries into standalone questions
- Execute hybrid retrieval across vector and keyword indexes
- Generate rationales and select evidence
- Prompt generator LLM with strict grounding instructions

**Key Classes:**
```python
class ConversationalRAGChain:
    def __init__(self, retriever, memory, llm):
        self.retriever = retriever
        self.memory = memory
        self.llm = llm
    
    def invoke(self, query: str, session_id: str) -> Response:
        # 1. Load conversation history
        # 2. Rewrite query with context
        # 3. Retrieve chunks
        # 4. Generate rationales
        # 5. Select evidence
        # 6. Generate grounded answer
        pass

class HybridRetriever:
    def retrieve(self, query: str, top_k: int = 10) -> List[Chunk]:
        # Combine vector search + BM25
        # Apply metadata filtering
        pass

class RationaleGenerator:
    def generate_rationales(self, query: str, chunks: List[Chunk]) -> List[Rationale]:
        # Use LLM to explain relevance
        pass
```



### Data Ingestion Pipeline (LlamaIndex)

**Responsibilities:**
- Scrape Immigration Rules from GOV.UK with rate limiting
- Parse HTML to extract hierarchical structure and metadata
- Implement Summary-Augmented Chunking (SAC)
- Generate embeddings using voyage-law-2 model
- Index chunks in Weaviate with metadata

**Key Classes:**
```python
class ImmigrationRulesScraper:
    def scrape(self, url: str) -> List[Document]:
        # Parse HTML structure
        # Extract Parts, Sections, Paragraphs
        # Capture metadata (part_number, section_id, hierarchy)
        pass

class SummaryAugmentedChunker:
    def chunk(self, document: Document) -> List[Chunk]:
        # 1. Generate document-level summary using LLM
        # 2. Split document by semantic boundaries
        # 3. Prepend summary to each chunk
        # 4. Attach metadata to each chunk
        pass

class LegalEmbedder:
    def __init__(self, model_name: str = "voyage-law-2"):
        self.model = VoyageAIEmbeddings(model=model_name)
    
    def embed(self, chunks: List[Chunk]) -> List[Vector]:
        pass
```

### Vector Database (Abstracted Interface)

**Implementation Strategy:**
- Start with **ChromaDB** for development and prototyping
- Design clean interface to allow migration to **Weaviate** for production
- Use adapter pattern to isolate vector database implementation details

**Responsibilities:**
- Store document embeddings with rich metadata
- Support hybrid search (vector + BM25)
- Enable metadata filtering to prevent DRM
- Provide horizontal scalability

**Abstract Interface:**
```python
class VectorStore(ABC):
    @abstractmethod
    def add_chunks(self, chunks: List[Chunk]) -> None:
        """Store chunks with embeddings and metadata"""
        pass
    
    @abstractmethod
    def hybrid_search(self, query: str, query_embedding: List[float], 
                     top_k: int = 10, filters: Dict = None) -> List[Chunk]:
        """Perform hybrid vector + keyword search"""
        pass
    
    @abstractmethod
    def delete_by_source(self, source: str) -> None:
        """Remove all chunks from a specific source"""
        pass

class ChromaDBStore(VectorStore):
    """ChromaDB implementation for development"""
    pass

class WeaviateStore(VectorStore):
    """Weaviate implementation for production"""
    pass
```

**Schema Design (Database-Agnostic):**
```python
{
  "content": str,              # Chunk text
  "summary": str,              # Document summary
  "source": str,               # "Immigration Rules"
  "part": str,                 # "Appendix Skilled Worker"
  "section": str,              # "SW 8.1"
  "topic": str,                # "Salary Requirements"
  "url": str,                  # GOV.UK link
  "parent_section": str,       # Parent in hierarchy
  "last_updated": datetime     # Update timestamp
}
```



## Data Models

### Document Model
```python
@dataclass
class Document:
    id: str
    source: str              # "Immigration Rules"
    part: str                # "Appendix Skilled Worker"
    url: str                 # GOV.UK URL
    content: str             # Full text
    metadata: Dict[str, Any] # Hierarchical structure
    last_updated: datetime
```

### Chunk Model
```python
@dataclass
class Chunk:
    id: str
    document_id: str
    content: str             # Actual chunk text
    summary: str             # Document-level summary (prepended)
    embedding: List[float]   # Vector representation
    metadata: ChunkMetadata
    
@dataclass
class ChunkMetadata:
    source: str
    part: str
    section: str
    topic: str
    url: str
    parent_section: Optional[str]
    hierarchy_level: int
```

### Conversation Model
```python
@dataclass
class Conversation:
    session_id: str
    user_id: Optional[str]
    messages: List[Message]
    created_at: datetime
    last_active: datetime

@dataclass
class Message:
    id: str
    role: Literal["user", "assistant"]
    content: str
    citations: List[Citation]
    rationales: List[Rationale]
    timestamp: datetime
```

### Storage Interfaces

**Session Store Interface:**
```python
class SessionStore(ABC):
    @abstractmethod
    def create_session(self) -> str:
        """Create new session and return session_id"""
        pass
    
    @abstractmethod
    def get_session(self, session_id: str) -> Optional[Conversation]:
        """Retrieve session by ID"""
        pass
    
    @abstractmethod
    def save_message(self, session_id: str, message: Message) -> None:
        """Add message to session"""
        pass
    
    @abstractmethod
    def delete_session(self, session_id: str) -> None:
        """Remove session"""
        pass

class RedisSessionStore(SessionStore):
    """Redis implementation for development and production"""
    pass

class MongoSessionStore(SessionStore):
    """MongoDB implementation (future alternative)"""
    pass
```

### Evaluation Model
```python
@dataclass
class EvaluationResult:
    query: str
    generated_answer: str
    ground_truth: str
    retrieved_chunks: List[Chunk]
    metrics: EvaluationMetrics

@dataclass
class EvaluationMetrics:
    context_precision: float    # 0-1
    context_recall: float       # 0-1
    faithfulness: float         # 0-1
    answer_relevancy: float     # 0-1
    answer_correctness: float   # 0-1
```



## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Query Rewriting Produces Standalone Questions

*For any* conversation history and ambiguous follow-up query, the rewritten query should be self-contained and interpretable without access to the conversation history.

**Validates: Requirements 1.3**

### Property 2: All Generated Responses Include Citations

*For any* user query that receives a factual answer, the response should include at least one citation containing document name, section number, and source URL.

**Validates: Requirements 1.4, 4.2**

### Property 3: Pronoun Resolution in Conversations

*For any* conversation where a follow-up query contains pronouns or references, the query rewriting step should correctly resolve those references to their antecedents from the conversation history.

**Validates: Requirements 1.2**

### Property 4: Scraper Extracts Complete Hierarchical Metadata

*For any* Immigration Rules document scraped from GOV.UK, the resulting Document object should contain all required metadata fields: source, part, section, url, and hierarchical relationships.

**Validates: Requirements 2.1, 2.2**

### Property 5: Summary-Augmented Chunking Prepends Summaries

*For any* source document processed through the chunking pipeline, every resulting chunk should begin with the document-level summary text.

**Validates: Requirements 2.3**

### Property 6: All Chunks Have Complete Metadata

*For any* chunk stored in the vector database, the chunk should have all required metadata fields populated: source, part, section, topic, url, parent_section, and hierarchy_level.

**Validates: Requirements 2.5, 5.3, 5.4**

### Property 7: Hybrid Retrieval Combines Search Methods

*For any* query processed by the retrieval system, the final ranked results should include contributions from both dense vector search and sparse keyword search (BM25).

**Validates: Requirements 3.1**

### Property 8: Keyword Matches Rank Highly

*For any* query containing specific legal terms or visa codes, chunks containing exact matches for those terms should appear in the top 5 retrieved results.

**Validates: Requirements 3.3**



### Property 9: Document-Level Retrieval Mismatch Prevention

*For any* query about a specific visa type, all retrieved chunks should originate from documents about that visa type, not from similar but incorrect documents.

**Validates: Requirements 3.4**

### Property 10: Rationales Generated for All Retrievals

*For any* retrieval operation, each returned chunk should have an associated rationale explaining why it is relevant to the query.

**Validates: Requirements 3.5, 4.5**

### Property 11: Faithfulness to Retrieved Context

*For any* generated answer, all factual statements in the answer should be directly supported by text in the retrieved context chunks.

**Validates: Requirements 4.1**

### Property 12: Citations Include Valid URLs

*For any* citation in a generated response, the citation should include a url field containing a valid GOV.UK link.

**Validates: Requirements 4.3**

### Property 13: Uncertainty Communication

*For any* query where the retrieval confidence score is below a threshold or no relevant context is found, the generated response should explicitly state uncertainty or inability to answer.

**Validates: Requirements 4.4, 1.5**

### Property 14: Structure-Aware Chunking Preserves Clauses

*For any* legal document with cross-references or multi-sentence clauses, the chunking process should not split a complete clause across multiple chunks.

**Validates: Requirements 5.1, 5.2**

### Property 15: Session Persistence Round-Trip

*For any* conversation session with messages, storing the session to the database and then retrieving it should return an equivalent session with all messages preserved.

**Validates: Requirements 7.1, 7.4**

### Property 16: Data Encryption in Storage and Transit

*For any* user query or session data, the data should be encrypted when stored in the database and transmitted over TLS when sent between client and server.

**Validates: Requirements 8.2**

### Property 17: Dataset Entries Have Complete Citations

*For any* question-answer pair in the evaluation dataset, the entry should include citations to specific Immigration Rules sections.

**Validates: Requirements 9.3**

### Property 18: Fault Isolation Between Components

*For any* component failure (vector database, LLM API, session database), other components should continue operating and return appropriate error messages rather than cascading failures.

**Validates: Requirements 10.5**



## Error Handling

### Error Categories and Strategies

**1. Retrieval Failures**
- **Scenario**: Vector database unavailable or query timeout
- **Handling**: Return cached fallback response with disclaimer, log error for monitoring
- **User Message**: "We're experiencing technical difficulties. Please try again in a moment."

**2. LLM API Failures**
- **Scenario**: Rate limit exceeded, API timeout, or service unavailable
- **Handling**: Implement exponential backoff retry (max 3 attempts), fallback to alternative model if available
- **User Message**: "Our AI service is temporarily unavailable. Please try again shortly."

**3. No Relevant Context Found**
- **Scenario**: Retrieval returns no chunks above confidence threshold
- **Handling**: Generate response explicitly stating inability to answer, suggest rephrasing or consulting official sources
- **User Message**: "I couldn't find relevant information in the Immigration Rules to answer your question. Please try rephrasing or visit GOV.UK directly."

**4. Session Database Failures**
- **Scenario**: MongoDB connection lost or write failure
- **Handling**: Continue processing query without saving history, log error, notify user of temporary memory loss
- **User Message**: "Your conversation history may not be saved due to a temporary issue."

**5. Scraper Failures**
- **Scenario**: GOV.UK structure changes, rate limiting, or network errors
- **Handling**: Log detailed error with page structure, send alert to administrators, continue with existing data
- **Alert**: "Scraper failed for [URL]: [error details]"

**6. Malformed User Input**
- **Scenario**: Empty queries, excessively long input, or injection attempts
- **Handling**: Validate and sanitize input, return clear error message
- **User Message**: "Please enter a valid question about UK immigration."

### Error Logging and Monitoring

All errors will be logged with structured data including:
- Timestamp
- Error type and severity
- User session ID (anonymized)
- Component that failed
- Stack trace (for system errors)
- Context (query, retrieved chunks, etc.)

Critical errors (database failures, API outages) will trigger alerts to the operations team.



## Testing Strategy

### Dual Testing Approach

The system will employ both unit testing and property-based testing to ensure comprehensive coverage. Unit tests verify specific examples and integration points, while property tests verify universal correctness properties across all inputs.

### Property-Based Testing

**Framework**: We will use **Hypothesis** for Python components, which is the leading property-based testing library with excellent support for generating complex test data.

**Configuration**: Each property test will run a minimum of 100 iterations to ensure statistical confidence in the results.

**Test Tagging**: Each property-based test will include a comment explicitly referencing the correctness property from this design document using the format:
```python
# Feature: legal-immigration-rag, Property 1: Query Rewriting Produces Standalone Questions
```

**Property Test Coverage**:

1. **Query Rewriting (Property 1, 3)**: Generate random conversation histories with pronouns and ambiguous references, verify rewritten queries are standalone
2. **Citation Completeness (Property 2, 12)**: Generate random queries, verify all responses have citations with required fields
3. **Metadata Extraction (Property 4, 6)**: Generate synthetic legal documents with known structure, verify parser extracts all metadata
4. **SAC Implementation (Property 5)**: Generate random documents, verify every chunk contains the summary prefix
5. **Hybrid Retrieval (Property 7, 8)**: Generate queries with legal terms, verify results include both vector and keyword contributions
6. **DRM Prevention (Property 9)**: Create similar documents about different visas, verify retrieval doesn't mix them
7. **Rationale Generation (Property 10)**: Generate random retrievals, verify each chunk has a rationale
8. **Faithfulness (Property 11)**: Generate answers, verify all statements can be traced to context
9. **Uncertainty Handling (Property 13)**: Generate out-of-domain queries, verify system communicates uncertainty
10. **Structure Preservation (Property 14)**: Generate documents with cross-references, verify chunks don't split clauses
11. **Session Persistence (Property 15)**: Generate random sessions, verify round-trip equality
12. **Encryption (Property 16)**: Verify stored data is encrypted and connections use TLS
13. **Dataset Validation (Property 17)**: Verify all dataset entries have required citation fields
14. **Fault Isolation (Property 18)**: Simulate component failures, verify other components continue operating

### Unit Testing

Unit tests will cover:

**Scraper Module**:
- Parsing specific GOV.UK page structures
- Handling rate limiting and retries
- Error cases (404, malformed HTML)

**Chunking Module**:
- Semantic boundary detection
- Metadata attachment
- Edge cases (very short/long documents)

**Retrieval Module**:
- Vector search integration
- BM25 scoring
- Metadata filtering logic

**API Endpoints**:
- Request validation
- Authentication
- Response formatting
- Error status codes

**Frontend Components**:
- Citation rendering
- Message display
- Session management

### Integration Testing

Integration tests will verify:
- End-to-end query flow from frontend to response
- Database connections and transactions
- LLM API integration
- Scraper to indexer pipeline

### Evaluation Metrics (RAGAS Framework)

The system will be continuously evaluated using the RAGAS framework with the following metrics:

- **Context Precision**: Proportion of retrieved chunks that are relevant
- **Context Recall**: Proportion of ground truth information successfully retrieved
- **Faithfulness**: Degree to which answers are grounded in context (hallucination detection)
- **Answer Relevancy**: Semantic alignment between query and answer
- **Answer Correctness**: Factual accuracy against gold standard dataset

**Baseline Comparison**: All metrics will be compared against a naive RAG baseline (fixed-size chunking, vector-only retrieval, no rationales) to demonstrate the value of advanced techniques.

