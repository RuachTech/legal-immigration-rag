"""Abstract base class for vector store implementations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ChunkMetadata:
    """Metadata associated with a document chunk."""
    source: str
    part: str
    section: str
    topic: str
    url: str
    parent_section: Optional[str] = None
    hierarchy_level: int = 0


@dataclass
class Chunk:
    """A chunk of a document with embeddings and metadata."""
    id: str
    document_id: str
    content: str
    summary: str
    embedding: list[float]
    metadata: ChunkMetadata


class VectorStore(ABC):
    """Abstract interface for vector database operations.

    This interface allows swapping between different vector database
    implementations (ChromaDB, Weaviate, etc.) without changing
    application code.
    """

    @abstractmethod
    def add_chunks(self, chunks: list[Chunk]) -> None:
        """Store chunks with embeddings and metadata.

        Args:
            chunks: List of Chunk objects to store
        """
        pass

    @abstractmethod
    def hybrid_search(
        self,
        query: str,
        query_embedding: list[float],
        top_k: int = 10,
        filters: Optional[dict[str, Any]] = None
    ) -> list[Chunk]:
        """Perform hybrid vector + keyword search.

        Args:
            query: The search query text
            query_embedding: Embedding of the query
            top_k: Number of top results to return
            filters: Optional metadata filters
        Returns:
            List of relevant Chunk objects
        """
        pass

    @abstractmethod
    def delete_by_source(self, source: str) -> None:
        """Delete all chunks from a given source document.

        Args:
            source: Source document identifier
        """
        pass
