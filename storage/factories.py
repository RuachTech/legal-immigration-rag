"""Factory functions for creating storage instances with dependency injection.

This module demonstrates proper dependency injection patterns for the storage layer.
Use these factories in production code to create properly configured storage instances.

Example usage:
    >>> from storage.factories import create_chromadb_store, create_redis_session_store
    >>>
    >>> # Create vector store with injected ChromaDB client
    >>> vector_store = create_chromadb_store(collection_name="immigration_chunks")
    >>>
    >>> # Create session store with injected Redis client
    >>> session_store = create_redis_session_store(
    ...     host="localhost",
    ...     port=6379,
    ...     ttl_seconds=86400
    ... )
"""

from typing import Optional

import chromadb
import redis

from storage.session.redis_session_store import RedisSessionStore
from storage.vector.chromadb_store import ChromaDBStore


def create_chromadb_store(
    collection_name: str = "chunks",
    persist_directory: Optional[str] = None
) -> ChromaDBStore:
    """Create a ChromaDB vector store with dependency injection.

    Args:
        collection_name: Name of the ChromaDB collection
        persist_directory: Optional path for persistent storage (None = in-memory)

    Returns:
        ChromaDBStore instance with injected client

    Example:
        >>> store = create_chromadb_store(
        ...     collection_name="legal_docs",
        ...     persist_directory="./chroma_data"
        ... )
    """
    if persist_directory:
        client = chromadb.PersistentClient(path=persist_directory)
    else:
        client = chromadb.Client()

    return ChromaDBStore(client=client, collection_name=collection_name)


def create_redis_session_store(
    host: str = "localhost",
    port: int = 6379,
    db: int = 0,
    ttl_seconds: int = 86400,
    password: Optional[str] = None
) -> RedisSessionStore:
    """Create a Redis session store with dependency injection.

    Args:
        host: Redis server host
        port: Redis server port
        db: Redis database number
        ttl_seconds: Session time-to-live in seconds (default: 24 hours)
        password: Optional Redis password

    Returns:
        RedisSessionStore instance with injected client

    Example:
        >>> store = create_redis_session_store(
        ...     host="localhost",
        ...     port=6379,
        ...     ttl_seconds=3600  # 1 hour
        ... )
    """
    client = redis.Redis(
        host=host,
        port=port,
        db=db,
        password=password,
        decode_responses=True  # Required for string responses
    )

    return RedisSessionStore(client=client, ttl_seconds=ttl_seconds)


__all__ = [
    "create_chromadb_store",
    "create_redis_session_store",
]
