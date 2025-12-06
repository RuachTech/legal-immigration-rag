"""Summary-Augmented Chunking (SAC) for legal documents.

This module implements SAC to prevent Document-Level Retrieval Mismatch (DRM)
by prepending document-level summaries to every chunk before embedding.

SAC addresses the problem that similar legal text from different documents
can cause retrieval mismatches. By including the document summary, we ensure
each chunk is contextualized within its source document.

Architecture:
1. Split document into chunks respecting legal structure (clauses, sections)
2. Generate document-level summary describing the content
3. Prepend summary to EVERY chunk before embedding
4. Attach hierarchical metadata (source, part, section, topic, url)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)

# litellm is optional at import time; provide a stub so tests can patch without dependency errors.
try:  # pragma: no cover - import guard
    import litellm
except ImportError:  # pragma: no cover
    class _LitellmStub:
        def completion(self, *args, **kwargs):
            raise ImportError("litellm not installed; run `uv add litellm`.")

    litellm = _LitellmStub()  # type: ignore


@dataclass
class DocumentInfo:
    """Information about a source document."""
    title: str
    url: str
    effective_date: Optional[str] = None
    version: Optional[str] = None


@dataclass
class ChunkInfo:
    """Information extracted during chunking."""
    raw_content: str  # Original chunk text without summary
    chunk_number: int  # Position in document (1-based)
    part: Optional[str] = None
    section: Optional[str] = None
    parent_section: Optional[str] = None
    hierarchy_level: int = 0
    topic: Optional[str] = None


class DocumentSplitter(ABC):
    """Abstract base class for document splitting strategies."""

    @abstractmethod
    def split(self, text: str) -> list[str]:
        """Split document into chunks respecting structure.
        
        Args:
            text: The document text to split
            
        Returns:
            List of chunk texts
        """
        pass


class RecursiveCharacterTextSplitter(DocumentSplitter):
    """Splits documents by semantic boundaries while preserving structure.
    
    This splitter respects legal document structure by preferring to split:
    1. At section boundaries (highest priority)
    2. At paragraph boundaries
    3. At sentence boundaries
    4. At character boundaries (fallback)
    
    This ensures clauses are not split mid-sentence, preserving legal meaning.
    """

    def __init__(
        self,
        max_chunk_size: int = 1000,
        overlap: int = 100,
        separators: Optional[list[str]] = None
    ):
        """Initialize the splitter.
        
        Args:
            max_chunk_size: Target chunk size in characters
            overlap: Overlap between chunks for context preservation
            separators: List of separators to try in order
        """
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
        self.separators = separators or [
            "\n\n",  # Section boundaries
            "\n",    # Paragraph boundaries
            ". ",    # Sentence boundaries
            " ",     # Word boundaries
            ""       # Character fallback
        ]

    def split(self, text: str) -> list[str]:
        """Split text into chunks respecting structure.
        
        Uses a recursive approach: tries to split at the first separator,
        then recursively splits each piece if it exceeds max_chunk_size.
        """
        chunks = []
        good_splits = []

        # Try each separator in order
        for separator in self.separators:
            if separator == "":
                splits = list(text)
            else:
                splits = text.split(separator)

            # Keep only non-empty splits
            good_splits = [s for s in splits if s]

            if len(good_splits) > 1:
                break

        if not good_splits:
            return [text]

        # Merge splits, respecting max_chunk_size
        merged_splits = self._merge_splits(good_splits, separator)
        chunks = [s for s in merged_splits if s]

        return chunks

    def _merge_splits(self, splits: list[str], separator: str) -> list[str]:
        """Merge splits while respecting max_chunk_size.
        
        Args:
            splits: List of text segments
            separator: The separator used
            
        Returns:
            List of merged chunks
        """
        chunks = []
        current_chunk = ""
        separator_size = len(separator)

        for split in splits:
            if not split:
                continue

            split_size = len(split)

            # If adding this split would exceed max size
            if len(current_chunk) + split_size + separator_size > self.max_chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                    # Add overlap from the end of current chunk
                    if self.overlap > 0:
                        current_chunk = split[-self.overlap:] if len(split) > self.overlap else split
                    else:
                        current_chunk = ""
                else:
                    # Split is itself too large, add it anyway
                    chunks.append(split)
                    current_chunk = ""
            else:
                # Add to current chunk
                if current_chunk:
                    current_chunk += separator + split
                else:
                    current_chunk = split

        if current_chunk:
            chunks.append(current_chunk)

        return chunks


class DocumentSummarizer(ABC):
    """Abstract base class for document summarization."""

    @abstractmethod
    def summarize(self, text: str, doc_title: str) -> str:
        """Generate a summary of the document.
        
        Args:
            text: The document text to summarize
            doc_title: Title of the document
            
        Returns:
            Summary text (typically 1-2 sentences)
        """
        pass


class LLMDocumentSummarizer(DocumentSummarizer):
    """Generates summaries using litellm-compatible LLMs.

    Defaults to litellm.completion so callers can swap any provider via
    environment (OpenAI, Anthropic, etc.) while keeping one interface.
    """

    def __init__(self, client=None, model: str = "deepseek/deepseek-chat"):
        """Initialize the summarizer.

        Args:
            client: Optional callable matching litellm.completion signature
            model: Model to use for summarization
        """
        self.client = client
        self.model = model

    def summarize(self, text: str, doc_title: str) -> str:
        """Generate a document summary using the configured LLM.

        Args:
            text: The document text (first 2000 chars are used)
            doc_title: Title of the document

        Returns:
            Summary (1-2 sentences)
        """
        prompt = f"""Given this legal document titled "{doc_title}", provide a very brief 1-2 sentence summary that captures what this document is about. Be specific about the visa type, requirements, or guidance.

Document excerpt:
{text[:2000]}

Summary:"""

        completion_fn = self.client or getattr(litellm, "completion", None)
        if completion_fn is None:
            logger.error("litellm completion not available; cannot summarize")
            return doc_title

        try:
            response = completion_fn(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
            )

            # Handle both dict and object response shapes
            if isinstance(response, dict):
                summary = (
                    response.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
            else:
                summary = getattr(
                    getattr(response, "choices", [None])[0],
                    "message",
                    None,
                )
                summary = getattr(summary, "content", "") if summary else ""

            summary = (summary or "").strip() or doc_title
            logger.info(f"Generated summary for '{doc_title}': {summary[:80]}...")
            return summary
        except Exception as e:  # pragma: no cover - network dependent
            logger.error(f"Failed to generate summary: {e}")
            return doc_title


class SummaryAugmentedChunker:
    """Main implementation of Summary-Augmented Chunking (SAC).
    
    SAC consists of:
    1. Document splitting respecting structure
    2. Document-level summary generation
    3. Summary prepending to every chunk
    4. Metadata attachment
    
    This prevents Document-Level Retrieval Mismatch by ensuring chunks
    from different documents are distinguishable even when text is similar.
    """

    def __init__(
        self,
        splitter: Optional[DocumentSplitter] = None,
        summarizer: Optional[DocumentSummarizer] = None,
        max_chunk_size: int = 1000,
        chunk_overlap: int = 100
    ):
        """Initialize the SAC chunker.
        
        Args:
            splitter: Custom DocumentSplitter (defaults to RecursiveCharacterTextSplitter)
            summarizer: Custom DocumentSummarizer (defaults to LLMDocumentSummarizer)
            max_chunk_size: Target size for chunks
            chunk_overlap: Overlap between chunks
        """
        self.splitter = splitter or RecursiveCharacterTextSplitter(
            max_chunk_size=max_chunk_size,
            overlap=chunk_overlap
        )
        self.summarizer = summarizer or LLMDocumentSummarizer()

    def chunk_document(
        self,
        text: str,
        doc_info: DocumentInfo,
        extract_structure_fn=None
    ) -> list[dict]:
        """Split and augment a document with SAC.
        
        Args:
            text: The document text
            doc_info: Metadata about the document
            extract_structure_fn: Optional function to extract hierarchical structure
                                 from chunk text. Should return ChunkInfo or dict.
        
        Returns:
            List of chunk dictionaries with:
            - raw_content: original chunk text
            - augmented_content: chunk with summary prepended
            - summary: the document summary
            - metadata: hierarchical metadata
            - id: unique chunk ID
        """
        logger.info(f"Starting SAC for document: {doc_info.title}")

        # Step 1: Generate document-level summary
        document_summary = self.summarizer.summarize(text, doc_info.title)
        logger.debug(f"Document summary: {document_summary}")

        # Step 2: Split document into chunks
        raw_chunks = self.splitter.split(text)
        logger.info(f"Split document into {len(raw_chunks)} chunks")

        # Step 3: Process each chunk
        processed_chunks = []
        for chunk_number, raw_chunk in enumerate(raw_chunks, 1):
            # Extract structure if function provided
            chunk_info = None
            if extract_structure_fn:
                chunk_info = extract_structure_fn(raw_chunk)
            
            if not chunk_info:
                chunk_info = ChunkInfo(
                    raw_content=raw_chunk,
                    chunk_number=chunk_number
                )

            # Step 3a: Prepend summary to chunk (SAC)
            augmented_content = f"{document_summary}\n\n{raw_chunk}"

            # Step 3b: Create metadata
            metadata = {
                "source": doc_info.title,
                "url": doc_info.url,
                "part": chunk_info.part,
                "section": chunk_info.section,
                "parent_section": chunk_info.parent_section,
                "hierarchy_level": chunk_info.hierarchy_level,
                "topic": chunk_info.topic or "General",
                "chunk_number": chunk_number,
                "effective_date": doc_info.effective_date,
                "version": doc_info.version
            }

            processed_chunks.append({
                "id": str(uuid.uuid4()),
                "raw_content": raw_chunk,
                "augmented_content": augmented_content,
                "summary": document_summary,
                "metadata": metadata
            })

        logger.info(f"Processed {len(processed_chunks)} chunks with SAC")
        return processed_chunks

    def chunk_documents(
        self,
        documents: list[tuple[str, DocumentInfo]],
        extract_structure_fn=None
    ) -> list[dict]:
        """Process multiple documents.
        
        Args:
            documents: List of (text, doc_info) tuples
            extract_structure_fn: Optional structure extraction function
            
        Returns:
            List of all processed chunks
        """
        all_chunks = []
        for text, doc_info in documents:
            chunks = self.chunk_document(text, doc_info, extract_structure_fn)
            all_chunks.extend(chunks)
        
        logger.info(f"Processed {len(documents)} documents into {len(all_chunks)} total chunks")
        return all_chunks
