# Implementation Plan

- [x] 1. Set up project structure and core interfaces
  - Create directory structure for frontend, backend, rag_pipeline, data_pipeline, storage, evaluation, and tests
  - Set up Python virtual environment(with uv) and install base dependencies (FastAPI, LangChain, LlamaIndex, Hypothesis)
  - Create abstract base classes for VectorStore and SessionStore interfaces
  - Set up TypeScript project for React frontend
  - _Requirements: 10.1, 10.2_

- [ ] 2. Implement storage layer with clean interfaces
- [ ] 2.1 Create abstract storage interfaces
  - Write VectorStore ABC with methods: add_chunks, hybrid_search, delete_by_source
  - Write SessionStore ABC with methods: create_session, get_session, save_message, delete_session
  - Define Chunk, Document, and Conversation data models
  - _Requirements: 10.1_

- [ ] 2.2 Implement ChromaDB vector store adapter
  - Create ChromaDBStore class implementing VectorStore interface
  - Implement add_chunks with metadata storage
  - Implement hybrid_search combining vector similarity and keyword matching
  - _Requirements: 3.1, 3.4_

- [ ] 2.3 Write property test for vector store interface
  - **Property 6: All Chunks Have Complete Metadata**
  - **Validates: Requirements 2.5, 5.3, 5.4**

- [ ] 2.4 Implement Redis session store adapter
  - Create RedisSessionStore class implementing SessionStore interface
  - Implement session creation with unique ID generation
  - Implement message persistence with TTL configuration
  - _Requirements: 7.1_

- [ ] 2.5 Write property test for session persistence
  - **Property 15: Session Persistence Round-Trip**
  - **Validates: Requirements 7.1, 7.4**


- [ ] 3. Build data ingestion pipeline for GOV.UK Immigration Rules
- [ ] 3.1 Implement GOV.UK scraper
  - Write scraper to fetch Immigration Rules from GOV.UK (start with Appendix Skilled Worker)
  - Parse HTML structure to extract Parts, Sections, and Paragraphs
  - Extract hierarchical metadata (part_number, section_id, parent-child relationships)
  - Implement rate limiting and respect robots.txt
  - _Requirements: 2.1, 2.2_

- [ ] 3.2 Write property test for metadata extraction
  - **Property 4: Scraper Extracts Complete Hierarchical Metadata**
  - **Validates: Requirements 2.1, 2.2**

- [ ] 3.3 Implement Summary-Augmented Chunking (SAC)
  - Create chunker that splits documents by semantic boundaries
  - Generate document-level summary using LLM
  - Prepend summary to every chunk before embedding
  - Attach complete metadata to each chunk
  - _Requirements: 2.3, 2.5_

- [ ] 3.4 Write property test for SAC implementation
  - **Property 5: Summary-Augmented Chunking Prepends Summaries**
  - **Validates: Requirements 2.3**

- [ ] 3.5 Write property test for structure preservation
  - **Property 14: Structure-Aware Chunking Preserves Clauses**
  - **Validates: Requirements 5.1, 5.2**

- [ ] 3.6 Implement legal domain embedder
  - Create embedder using voyage-law-2 or LEGAL-BERT model
  - Implement batch embedding for efficiency
  - Add error handling for API failures
  - _Requirements: 3.2_

- [ ] 3.7 Create indexing pipeline
  - Connect scraper → chunker → embedder → vector store
  - Implement incremental indexing for updates
  - Add logging and progress tracking
  - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [ ] 3.8 Write unit tests for scraper edge cases
  - Test handling of malformed HTML
  - Test rate limiting behavior
  - Test error recovery
  - _Requirements: 2.1_


- [ ] 4. Implement hybrid retrieval system
- [ ] 4.1 Create hybrid retriever combining vector and keyword search
  - Implement dense vector search using ChromaDB
  - Implement sparse keyword search (BM25)
  - Combine and rank results from both methods
  - Apply metadata filtering to prevent DRM
  - _Requirements: 3.1, 3.3, 3.4_

- [ ] 4.2 Write property test for hybrid retrieval
  - **Property 7: Hybrid Retrieval Combines Search Methods**
  - **Validates: Requirements 3.1**

- [ ] 4.3 Write property test for keyword ranking
  - **Property 8: Keyword Matches Rank Highly**
  - **Validates: Requirements 3.3**

- [ ] 4.4 Write property test for DRM prevention
  - **Property 9: Document-Level Retrieval Mismatch Prevention**
  - **Validates: Requirements 3.4**

- [ ] 4.5 Implement rationale-driven selection (METEORA)
  - Create rationale generator that explains chunk relevance
  - Use fast LLM (GPT-3.5 or Haiku) to generate rationales
  - Filter chunks based on rationale quality
  - _Requirements: 3.5_

- [ ] 4.6 Write property test for rationale generation
  - **Property 10: Rationales Generated for All Retrievals**
  - **Validates: Requirements 3.5, 4.5**

- [ ] 5. Build conversational RAG chain with LangChain
- [ ] 5.1 Implement query rewriting for conversational context
  - Create query rewriter that uses conversation history
  - Transform ambiguous follow-ups into standalone questions
  - Resolve pronouns and references to previous messages
  - _Requirements: 1.2, 1.3_

- [ ] 5.2 Write property test for query rewriting
  - **Property 1: Query Rewriting Produces Standalone Questions**
  - **Validates: Requirements 1.3**

- [ ] 5.3 Write property test for pronoun resolution
  - **Property 3: Pronoun Resolution in Conversations**
  - **Validates: Requirements 1.2**

- [ ] 5.4 Implement grounded generator with citation enforcement
  - Create generator prompt that enforces grounding in context
  - Extract citations from generated responses
  - Format citations with document name, section, and URL
  - _Requirements: 1.4, 4.1, 4.2, 4.3_

- [ ] 5.5 Write property test for citation completeness
  - **Property 2: All Generated Responses Include Citations**
  - **Validates: Requirements 1.4, 4.2**

- [ ] 5.6 Write property test for faithfulness
  - **Property 11: Faithfulness to Retrieved Context**
  - **Validates: Requirements 4.1**

- [ ] 5.7 Write property test for citation URLs
  - **Property 12: Citations Include Valid URLs**
  - **Validates: Requirements 4.3**

- [ ] 5.8 Implement uncertainty communication
  - Detect low confidence scenarios (no relevant context, low scores)
  - Generate explicit uncertainty statements
  - Suggest alternative actions (rephrase, consult official sources)
  - _Requirements: 1.5, 4.4_

- [ ] 5.9 Write property test for uncertainty handling
  - **Property 13: Uncertainty Communication**
  - **Validates: Requirements 4.4, 1.5**

- [ ] 5.10 Assemble complete RAG chain with memory
  - Integrate query rewriter, retriever, rationale generator, and grounded generator
  - Use LangChain's RunnableWithMessageHistory for conversation memory
  - Connect to Redis session store
  - _Requirements: 1.1, 1.2, 7.5_


- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Build FastAPI backend
- [ ] 7.1 Create API endpoints
  - Implement POST /api/chat endpoint with request validation
  - Implement GET /api/sessions/{session_id} endpoint
  - Implement POST /api/sessions endpoint for session creation
  - Implement GET /api/health endpoint with component status checks
  - _Requirements: 10.2_

- [ ] 7.2 Add authentication and security
  - Implement API key authentication
  - Add rate limiting middleware
  - Configure CORS for frontend
  - _Requirements: 8.2_

- [ ] 7.3 Write property test for data encryption
  - **Property 16: Data Encryption in Storage and Transit**
  - **Validates: Requirements 8.2**

- [ ] 7.4 Implement error handling and logging
  - Add structured error logging with context
  - Implement error response formatting
  - Add monitoring for critical failures
  - _Requirements: Error Handling section_

- [ ] 7.5 Write property test for fault isolation
  - **Property 18: Fault Isolation Between Components**
  - **Validates: Requirements 10.5**

- [ ] 7.6 Write unit tests for API endpoints
  - Test request validation
  - Test authentication
  - Test error status codes
  - _Requirements: 10.2_

- [ ] 8. Build React frontend
- [ ] 8.1 Create chat interface components
  - Build message list component with auto-scroll
  - Build message input component with loading states
  - Build citation display component with expandable rationales
  - Implement session management
  - _Requirements: 7.2, 7.3_

- [ ] 8.2 Implement disclaimer modal
  - Create modal that displays on first access
  - Include clear statement that system does not provide legal advice
  - Add "I understand" confirmation button
  - _Requirements: 8.1_

- [ ] 8.3 Connect frontend to backend API
  - Create API client service
  - Implement WebSocket or polling for streaming responses
  - Add error handling and retry logic
  - _Requirements: 7.1, 7.2, 7.3_

- [ ] 8.4 Write unit tests for React components
  - Test message rendering
  - Test citation display
  - Test session management
  - _Requirements: 7.2, 7.3_


- [ ] 9. Create evaluation framework
- [ ] 9.1 Build gold standard dataset
  - Create 50-100 question-answer pairs covering diverse immigration topics
  - Include ground truth answers with citations
  - Verify answers with legal experts or official sources
  - Store in structured JSON format
  - _Requirements: 9.1, 9.2, 9.3_

- [ ] 9.2 Write property test for dataset validation
  - **Property 17: Dataset Entries Have Complete Citations**
  - **Validates: Requirements 9.3**

- [ ] 9.3 Implement RAGAS evaluation metrics
  - Integrate RAGAS framework
  - Implement Context Precision calculation
  - Implement Context Recall calculation
  - Implement Faithfulness calculation
  - Implement Answer Relevancy calculation
  - Implement Answer Correctness calculation
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 9.4 Create naive RAG baseline for comparison
  - Implement simple fixed-size chunking
  - Implement vector-only retrieval (no hybrid search)
  - Implement generation without rationales
  - _Requirements: 6.5_

- [ ] 9.5 Build evaluation runner script
  - Run system on gold standard dataset
  - Calculate all RAGAS metrics
  - Compare against naive baseline
  - Generate evaluation report
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 9.6 Write unit tests for metric calculations
  - Test Context Precision calculation
  - Test Faithfulness detection
  - Test Answer Relevancy scoring
  - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [ ] 10. Implement Weaviate adapter for production migration
- [ ] 10.1 Create WeaviateStore implementing VectorStore interface
  - Implement add_chunks with Weaviate schema
  - Implement hybrid_search using Weaviate's native hybrid search
  - Implement metadata filtering
  - _Requirements: 3.1, 3.4_

- [ ] 10.2 Create migration script
  - Write script to export data from ChromaDB
  - Write script to import data into Weaviate
  - Add validation to ensure data integrity
  - _Requirements: 10.1_

- [ ] 10.3 Write integration tests for Weaviate adapter
  - Test hybrid search functionality
  - Test metadata filtering
  - Test data migration
  - _Requirements: 3.1, 3.4_

- [ ] 11. Add monitoring and observability
- [ ] 11.1 Implement structured logging
  - Add request/response logging
  - Add performance metrics (latency, token usage)
  - Add error tracking with context
  - _Requirements: Error Handling section_

- [ ] 11.2 Create health check dashboard
  - Monitor vector database connectivity
  - Monitor LLM API status
  - Monitor session store status
  - Display component health in /api/health endpoint
  - _Requirements: 10.5_

- [ ] 11.3 Write integration tests for monitoring
  - Test health check endpoint
  - Test error logging
  - Test metric collection
  - _Requirements: 10.5_

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
