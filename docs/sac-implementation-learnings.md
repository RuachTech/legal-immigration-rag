# Summary-Augmented Chunking (SAC) Implementation Learnings

**Date:** December 6, 2025  
**Task:** Task 3.3 - Summary-Augmented Chunking  
**Status:** ✅ Complete

## Executive Summary

Successfully implemented Summary-Augmented Chunking (SAC) for 2,775 legal immigration chunks across 117 files. The system uses **chunk-level summaries** (not document-level) with **structured metadata headers** to prevent Document-Level Retrieval Mismatch (DRM). Key finding: **Quality control is critical** - 1.3% of chunks flagged for review, with 3 files (100% flagged) requiring exclusion.

## Architecture Decisions

### 1. Chunk-Level vs Document-Level Summaries

**Decision:** Generate summaries for EVERY individual chunk, not one summary per document.

**Rationale:**
- Legal documents are long (50-200 sections per appendix)
- Users ask specific questions about subsections (e.g., "What is the salary requirement for Skilled Worker visa?")
- Document-level summary would be too generic for precise retrieval
- Chunk-level summaries capture specific legal provision intent

**Implementation:**
```python
# data_pipeline/processing/enhance_chunks_with_sac.py
async def generate_chunk_summary(chunk_text: str, metadata: dict) -> str:
    """Generate legal-focused summary for a single chunk."""
    prompt = f"""Summarize this legal immigration text in 2-3 sentences.
    Focus on: eligibility requirements, application processes, definitions...
    Text: {chunk_text}"""
    response = await litellm.acompletion(model="gpt-4o-mini", messages=[...])
```

**Trade-offs:**
- ✅ More precise retrieval (summary matches user query intent)
- ✅ Better for conversational follow-ups (chunk context is specific)
- ❌ Higher API costs (2,775 API calls vs 117 for document-level)
- ❌ Slower processing (mitigated with async batching)

### 2. LLM Provider Selection

**Tested Models:**
| Model | Status | Issue | Solution |
|-------|--------|-------|----------|
| `gemini-2.5-flash` | ❌ Failed | Returned `null` for content field | Switched provider |
| `gemini-2.0-flash-thinking-exp` | ❌ Rate limited | Hit quota too quickly | Switched provider |
| `gpt-4o-mini` | ✅ Production | Stable, 1000 req/min | **Final choice** |

**Decision:** Use `gpt-4.1-mini` or nano via litellm for provider abstraction.

**Why litellm:**
```python
# Single interface across providers
import litellm

# Async support for concurrent requests
response = await litellm.acompletion(
    model="gpt-4o-mini",  # Can swap to "claude-3-5-sonnet" easily
    messages=[{"role": "user", "content": prompt}]
)
```

**Production Config:**
- Rate limit: 0.1s delay between requests (1000 req/min for gpt-4o-mini)
- Retry logic: litellm handles transient failures automatically
- Cost: ~$0.15 per 1M tokens (gpt-4o-mini input), ~$2.70 for 2,775 summaries

### 3. Augmented Text Format

**Evolution:**

**Version 1 (Initial):** Simple concatenation
```
Summary: [LLM-generated summary]

[Original chunk text]
```

**Version 2 (Final):** Structured metadata headers
```
Document: Immigration Rules Appendix Skilled Worker
Part: Appendix Skilled Worker
Section ID: SW 15.1
Section: Requirements for Skilled Worker
Topic: Eligibility for indefinite leave to remain

Summary: This provision sets out the requirements for Skilled Worker 
route applicants seeking indefinite leave to remain in the UK.

[Original chunk text]
```

**Rationale for Version 2:**
- Metadata filtering is **critical** for DRM prevention in legal text
- Embedding model sees complete context (source + hierarchy + topic)
- Retrieval can use metadata to constrain searches to relevant sections
- Debugging easier (can see chunk provenance at a glance)

**Implementation:**
```python
def build_augmented_text(chunk: dict) -> str:
    """Build augmented text with metadata header + summary + original text."""
    metadata = chunk.get("metadata", {})
    summary = chunk.get("summary", "")
    text = chunk.get("text", "")
    
    return f"""Document: {metadata.get('source', 'Unknown')}
Part: {metadata.get('part', 'N/A')}
Section ID: {metadata.get('section_id', 'N/A')}
Section: {metadata.get('section_title', 'N/A')}
Topic: {metadata.get('topic', 'N/A')}

Summary: {summary}

{text}"""
```

## Quality Control: The Critical Discovery

### Problem: Source Data Quality Issues

After processing all chunks, quality review revealed **source data problems**:

**3 files with 100% chunks flagged:**
1. **`introduction.json`** - Entire immigration glossary as single 91KB chunk
2. **`appendix-eu.json`** - Massive 155KB definitions table as single chunk
3. **`appendix-eu-family-permit.json`** - 79KB chunk

**5 chunks with 404 errors** (scraper hit dead links):
- `appendix-statelessness.json` (2/4 chunks)
- `appendix-domestic-workers-who-is-a-victim-of-modern-slavery.json` (2/4 chunks)
- `part-14-stateless-persons.json` (1 chunk)

**Root Cause:** Bad input data, NOT SAC failure
- Scraper preserved glossaries/definition tables without semantic chunking
- Some GOV.UK pages returned 404 errors
- Massive chunks (>50KB) are structural content, not legal provisions

### Solution: Automated Quality Flagging

Created `flag_chunks_for_review.py` to programmatically identify problematic chunks:

**Quality Indicators:**
```python
def should_flag_for_review(chunk: dict) -> tuple[bool, list[str]]:
    reasons = []
    
    # 404 errors from scraping
    if "404" in text and "Page not found" in text:
        reasons.append("404_error")
    
    # Massive chunks (likely unprocessed glossaries)
    if len(text) > 50_000:
        reasons.append(f"very_long_text_{len(text)}_chars")
    
    # Empty or too-short summaries
    if len(summary) < 50:
        reasons.append("short_summary")
    
    # Generic legal phrases + short summary = low quality
    generic_phrases = ["this provision applies to", "the provision in"]
    if any(p in summary.lower() for p in generic_phrases) and len(summary) < 150:
        reasons.append("generic_summary")
    
    return (len(reasons) > 0, reasons)
```

**Results:**
- Total chunks: 2,775
- Flagged: 36 (1.3%)
- Breakdown:
  - Generic summaries: 28 (acceptable - complex legal language)
  - 404 errors: 5 (need re-scraping)
  - Very long text: 3 (exclude from vector store)

**Recommendation:** Exclude 3 files with 100% flagged chunks before indexing.

## Implementation Details

### File Structure
```
data_pipeline/processing/
├── summary_augmented_chunker.py      # Core SAC abstractions
├── enhance_chunks_with_sac.py        # Main enhancement script
├── reformat_augmented_text.py        # One-time metadata header migration
├── rechunk_empty_files.py            # Re-chunk files with 0 chunks
├── flag_chunks_for_review.py         # Quality control automation
└── chunk_converter.py                # SAC → storage Chunk conversion
```

### Key Scripts

#### `enhance_chunks_with_sac.py`
**Purpose:** Main production script to add summaries to existing chunks.

**Features:**
- Async processing with litellm.acompletion
- Resume capability (--skip-existing flag)
- Rate limiting (0.1s delay)
- Structured metadata headers
- Progress tracking

**Usage:**
```bash
export OPENAI_API_KEY="sk-..."
uv run python data_pipeline/processing/enhance_chunks_with_sac.py

# Resume interrupted run
uv run python data_pipeline/processing/enhance_chunks_with_sac.py --skip-existing
```

**Output:** All 116 chunk files enhanced with `summary` and `augmented_text` fields.

#### `flag_chunks_for_review.py`
**Purpose:** Identify problematic chunks for exclusion/re-scraping.

**Usage:**
```bash
uv run python data_pipeline/processing/flag_chunks_for_review.py
```

**Output:** Adds `needs_review` (bool) and `review_reasons` (array) to chunks.

### Testing

**Unit Tests:** 18 tests in `tests/unit/test_summary_augmented_chunker.py`
- RecursiveCharacterTextSplitter logic
- LLMDocumentSummarizer with mocked API
- SummaryAugmentedChunker.chunk_document()
- ChunkConverter transformation

**Property Tests:** `tests/property/test_sac_property.py`
- **Property 5:** Summary-Augmented Chunking prepends summaries (Requirement 2.3)
- Uses Hypothesis for exhaustive testing
- Validates augmented_text format invariants

**Status:** ✅ All tests passing

## Operational Metrics

| Metric | Value |
|--------|-------|
| Total chunks processed | 2,775 |
| Files processed | 117 |
| Avg chunks per file | 23.7 |
| Flagged chunks | 36 (1.3%) |
| Files to exclude | 3 (2.6%) |
| API calls | ~2,775 |
| Processing time | ~8 minutes (async) |
| Estimated cost | ~$2.70 (gpt-4o-mini) |

## Key Learnings

### 1. Quality Control is Non-Negotiable
**Learning:** Always validate output, even when the algorithm is correct.

**Evidence:** SAC worked perfectly, but revealed upstream data quality issues (404 errors, massive glossaries). Without automated flagging, these would pollute retrieval results.

**Takeaway:** Build quality checks into every pipeline stage.

### 2. Chunk-Level Summaries for Legal Text
**Learning:** Document-level summaries are insufficient for legal domain.

**Reason:** Legal documents are hierarchical (Parts → Sections → Paragraphs). Users need chunk-level precision ("What is SW 15.1?"), not document-level vagueness.

**Takeaway:** Match summarization granularity to retrieval granularity.

### 3. Structured Metadata Headers Critical for DRM
**Learning:** Prepending just summaries isn't enough - need full metadata context.

**Reason:** Legal text has high similarity across documents (similar language about "applications", "eligibility", "requirements"). Metadata filtering prevents retrieving wrong document chunks.

**Takeaway:** Embed complete provenance (source, part, section ID, topic) alongside summaries.

### 4. LLM Provider Abstraction is Essential
**Learning:** Use litellm for provider-agnostic interface.

**Evidence:** gemini-2.5-flash failed → switched to gpt-4o-mini in 2 lines. No refactoring needed.

**Takeaway:** Never couple to a single LLM provider in production systems.

### 5. Async Processing for API-Heavy Workloads
**Learning:** Synchronous API calls are unacceptable for 2,775 requests.

**Improvement:** Async with litellm.acompletion reduced processing time from ~46 minutes (sequential) to ~8 minutes (concurrent with rate limiting).

**Takeaway:** Use async for any API-heavy data pipeline.

### 6. Resume Capability for Long-Running Jobs
**Learning:** Always support --skip-existing for idempotent re-runs.

**Reason:** API failures, rate limits, or interruptions happen. Reprocessing from scratch wastes time and money.

**Implementation:**
```python
if skip_existing and "summary" in chunk and chunk["summary"]:
    continue  # Skip already processed chunks
```

## Common Pitfalls Avoided

### ❌ Pitfall 1: Document-Level Summaries
**Why it fails:** Too generic for legal Q&A. User asks "What is the salary requirement?" and gets summary of entire Skilled Worker appendix (200+ sections).

**Solution:** Chunk-level summaries capture specific provision intent.

### ❌ Pitfall 2: Unstructured Augmented Text
**Why it fails:** Embedding model has no context about document source/hierarchy. DRM risk increases.

**Solution:** Structured metadata headers provide complete provenance.

### ❌ Pitfall 3: No Quality Control
**Why it fails:** "Garbage in, garbage out." Bad source data (404s, glossaries) creates bad embeddings.

**Solution:** Automated flagging with `needs_review` + `review_reasons` fields.

### ❌ Pitfall 4: Tight Coupling to LLM Provider
**Why it fails:** Provider outages, pricing changes, or quality issues require refactoring.

**Solution:** litellm abstraction allows model switching in config, not code.

### ❌ Pitfall 5: Synchronous API Calls
**Why it fails:** 2,775 sequential API calls take 46+ minutes (0.1s delay each).

**Solution:** async/await with litellm.acompletion (8 minutes total).

## Next Steps

### Immediate: Handle Flagged Chunks
1. **Exclude 3 files** from vector indexing (introduction.json, appendix-eu.json, appendix-eu-family-permit.json)
2. **Re-scrape 2 files** with 404 errors (appendix-statelessness, appendix-domestic-workers)
3. **Accept generic summaries** (28 chunks scattered across files, not problematic)

### Implementation in Indexing Pipeline (Task 3.7):
```python
# data_pipeline/indexing/ingest_chunks.py
def filter_chunks_for_indexing(chunks: list[dict]) -> list[dict]:
    """Exclude flagged chunks from vector store ingestion."""
    return [
        chunk for chunk in chunks
        if not chunk.get("needs_review", False)
        or "generic_summary" in chunk.get("review_reasons", [])  # Allow these
    ]
```

### Monitoring in Production:
- Track % flagged chunks per batch
- Alert if >5% flagged (indicates scraper degradation)
- Log excluded chunks for manual review

## References

**Code:**
- Core SAC: `data_pipeline/processing/summary_augmented_chunker.py`
- Enhancement script: `data_pipeline/processing/enhance_chunks_with_sac.py`
- Quality flagging: `data_pipeline/processing/flag_chunks_for_review.py`

**Tests:**
- Unit tests: `tests/unit/test_summary_augmented_chunker.py`
- Property tests: `tests/property/test_sac_property.py`

**Specs:**
- Requirements: `.kiro/specs/legal-immigration-rag/requirements.md` (2.3, 2.5)
- Design: `.kiro/specs/legal-immigration-rag/design.md` (DRM prevention)
- Tasks: `.kiro/specs/legal-immigration-rag/tasks.md` (Task 3.3)

**Data:**
- Enhanced chunks: `data/govuk-data/chunks/*.json` (117 files, 2,775 chunks)
- Flagged chunks: 36 chunks with `needs_review: true`
