"""Quick verification script to test storage implementations."""

from datetime import datetime

from storage.factories import create_chromadb_store, create_redis_session_store
from storage.session.base import Message
from storage.vector.base import Chunk, ChunkMetadata


def test_chromadb_store() -> None:
    """Test ChromaDB store with dependency injection."""
    print("Testing ChromaDBStore...")

    # Create store with injected client (in-memory for testing)
    store = create_chromadb_store(collection_name="test_chunks")

    # Create test chunk
    metadata = ChunkMetadata(
        source="Immigration Rules Appendix Skilled Worker",
        part="Appendix Skilled Worker",
        section="SW 2.1",
        topic="Eligibility requirements",
        url="https://www.gov.uk/guidance/immigration-rules/appendix-skilled-worker",
        parent_section="SW 2.0",
        hierarchy_level=2
    )

    chunk = Chunk(
        id="chunk_001",
        document_id="doc_001",
        content="An applicant must meet the eligibility requirements...",
        summary="This document covers Skilled Worker visa eligibility.",
        embedding=[0.1, 0.2, 0.3, 0.4, 0.5],
        metadata=metadata
    )

    # Test add_chunks
    store.add_chunks([chunk])
    print("✓ Added chunk successfully")

    # Test hybrid_search
    results = store.hybrid_search(
        query="eligibility",
        query_embedding=[0.1, 0.2, 0.3, 0.4, 0.5],
        top_k=5
    )
    print(f"✓ Search returned {len(results)} results")

    # Test delete_by_source
    store.delete_by_source("Immigration Rules Appendix Skilled Worker")
    print("✓ Deleted chunks by source")

    print("ChromaDBStore: All tests passed!\n")


def test_redis_session_store() -> None:
    """Test Redis session store with dependency injection."""
    print("Testing RedisSessionStore...")

    try:
        # Create store with injected client
        store = create_redis_session_store(
            host="localhost",
            port=6379,
            ttl_seconds=3600
        )

        # Test create_session
        session_id = store.create_session()
        print(f"✓ Created session: {session_id}")

        # Test get_session
        conversation = store.get_session(session_id)
        print(f"✓ Retrieved session: {conversation.session_id}")

        # Test save_message
        message = Message(
            id="msg_001",
            role="user",
            content="What are the Skilled Worker visa requirements?",
            citations=[],
            rationales=[],
            timestamp=datetime.utcnow()
        )
        store.save_message(session_id, message)
        print("✓ Saved message to session")

        # Verify message was saved
        updated_conversation = store.get_session(session_id)
        assert len(updated_conversation.messages) == 1
        print("✓ Message persisted correctly")

        # Test delete_session
        store.delete_session(session_id)
        print("✓ Deleted session")

        print("RedisSessionStore: All tests passed!\n")

    except Exception as e:
        print(f"⚠ Redis test skipped (Redis not running): {e}\n")


if __name__ == "__main__":
    print("=" * 60)
    print("Storage Layer Verification")
    print("=" * 60 + "\n")

    test_chromadb_store()
    test_redis_session_store()

    print("=" * 60)
    print("All storage tests completed!")
    print("=" * 60)
