"""Data pipeline processing module.

Contains implementations for:
- Summary-Augmented Chunking (SAC)
- Document splitting with structure awareness
- LLM-based summarization
- Integration with storage layer
"""

from .chunk_converter import (
    create_embedding_stub,
    sac_chunk_to_storage_chunk,
    sac_chunks_to_storage_chunks,
)
from .summary_augmented_chunker import (
    ChunkInfo,
    DocumentInfo,
    DocumentSplitter,
    DocumentSummarizer,
    LLMDocumentSummarizer,
    RecursiveCharacterTextSplitter,
    SummaryAugmentedChunker,
)

__all__ = [
    # SAC components
    "DocumentInfo",
    "ChunkInfo",
    "DocumentSplitter",
    "RecursiveCharacterTextSplitter",
    "DocumentSummarizer",
    "LLMDocumentSummarizer",
    "SummaryAugmentedChunker",
    # Converters
    "create_embedding_stub",
    "sac_chunk_to_storage_chunk",
    "sac_chunks_to_storage_chunks",
]
