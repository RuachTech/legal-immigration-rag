"""Abstract base class for vector store implementations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


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
    embedding: List[float]
    metadata: ChunkMetadata


class VectorStore(ABC):
    """Abstract interface for vector database operations.
    
    This interface allows swapping between different vector database
    implementations (ChromaDB, Weaviate, etc.) without changing
    application code.
    """
    
    @abstractmethod
    def add_chunks(self, chunks: List[Chunk]) -> None:
        """Store chunks with embeddings and metadata.
        
        Args:
            chunks: List of Chunk objects to store
        """
        pass
    
    @abstractmethod
    def hybrid_search(
        self,
        query: str,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """Perform hybrid vector + keyword search.
        
        Args:
            query: The search query text
            query_embedding: Vector representation of the query
            top_k: Number of results to return
            filters: Optional metadata filters
            
        Returns:
            List of matching chunks ranked by relevance
        """
        pass
    
    @abstractmethod
    def delete_by_source(self, source: str) -> None:
        """Remove all chunks from a specific source.
        
        Args:
            source: The source identifier to delete
        """
        pass
