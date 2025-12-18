"""ChromaDBStore: Implements VectorStore interface using ChromaDB backend."""

from typing import Any, Optional

from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.api.types import QueryResult

from storage.vector.base import Chunk, ChunkMetadata, VectorStore


class ChromaDBStore(VectorStore):
    """ChromaDB implementation of VectorStore interface.

    Supports vector similarity search with metadata filtering.
    Uses dependency injection for ChromaDB client.
    """

    def __init__(self, client: ClientAPI, collection_name: str = "chunks") -> None:
        """Initialize ChromaDB store with injected client.

        Args:
            client: ChromaDB client instance (injected)
            collection_name: Name of the collection to use
        """
        self._client = client
        self._collection: Collection = self._client.get_or_create_collection(name=collection_name)

    def add_chunks(self, chunks: list[Chunk]) -> None:
        """Store chunks with embeddings and metadata in ChromaDB.

        Args:
            chunks: List of Chunk objects to store
        """
        if not chunks:
            return

        ids: list[str] = []
        documents: list[str] = []
        embeddings: list[list[float]] = []
        metadatas: list[dict[str, Any]] = []

        for chunk in chunks:
            ids.append(chunk.id)
            documents.append(chunk.content)
            embeddings.append(chunk.embedding)
            # Convert metadata dataclass to dict
            metadata_dict = {
                "document_id": chunk.document_id,
                "summary": chunk.summary,
                "source": chunk.metadata.source,
                "part": chunk.metadata.part,
                "section": chunk.metadata.section,
                "topic": chunk.metadata.topic,
                "url": chunk.metadata.url,
                "parent_section": chunk.metadata.parent_section or "",
                "hierarchy_level": chunk.metadata.hierarchy_level,
            }
            metadatas.append(metadata_dict)

        self._collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,  # type: ignore[arg-type]
            metadatas=metadatas,  # type: ignore[arg-type]
        )

    def hybrid_search(
        self, query: str, query_embedding: list[float], top_k: int = 10, filters: Optional[dict[str, Any]] = None
    ) -> list[Chunk]:
        """Perform vector similarity search with optional metadata filtering.

        Note: ChromaDB doesn't natively support BM25 keyword search.
        For true hybrid search, consider using Weaviate in production.

        Args:
            query: The search query text (unused in current implementation)
            query_embedding: Embedding vector of the query
            top_k: Number of top results to return
            filters: Optional metadata filters (ChromaDB where clause)

        Returns:
              List of matching Chunk objects
        """
        results: QueryResult = self._collection.query(
            query_embeddings=[query_embedding],  # type: ignore[arg-type]
            n_results=top_k,
            where=filters if filters else None,
        )

        chunks: list[Chunk] = []

        # ChromaDB returns nested lists for batch queries
        if not results["ids"] or not results["ids"][0]:
            return chunks

        ids_list = results["ids"][0]
        documents_list = results["documents"][0] if results["documents"] else []
        metadatas_list = results["metadatas"][0] if results["metadatas"] else []

        for i, chunk_id in enumerate(ids_list):
            metadata_dict = metadatas_list[i] if i < len(metadatas_list) else {}

            # Reconstruct ChunkMetadata from dict
            # type: ignore[arg-type]
            chunk_metadata = ChunkMetadata(
                source=str(metadata_dict.get("source", "")),
                part=str(metadata_dict.get("part", "")),
                section=str(metadata_dict.get("section", "")),
                topic=str(metadata_dict.get("topic", "")),
                url=str(metadata_dict.get("url", "")),
                parent_section=(
                    str(metadata_dict.get("parent_section")) if metadata_dict.get("parent_section") else None
                ),
                hierarchy_level=(
                    int(metadata_dict.get("hierarchy_level", 0))
                    if isinstance(metadata_dict.get("hierarchy_level"), (int, float, str))
                    else 0
                ),
            )

            chunk = Chunk(
                id=str(chunk_id),
                document_id=str(metadata_dict.get("document_id", "")),
                content=str(documents_list[i]) if i < len(documents_list) else "",
                summary=str(metadata_dict.get("summary", "")),
                embedding=query_embedding,  # Note: actual chunk embeddings not returned
                metadata=chunk_metadata,
            )
            chunks.append(chunk)

        return chunks

    def delete_by_source(self, source: str) -> None:
        """Delete all chunks from a specific source document.

        Args:
            source: Source document identifier to match in metadata
        """
        self._collection.delete(where={"source": source})
