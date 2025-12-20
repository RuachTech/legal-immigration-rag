"""Unit tests for incremental indexing logic."""

import json
import tempfile
from pathlib import Path

import pytest

from data_pipeline.indexing.incremental import (
    DocumentState,
    IncrementalIndexer,
    IndexState,
)


class TestDocumentState:
    """Tests for DocumentState dataclass."""

    def test_document_state_creation(self):
        """Test creating a DocumentState."""
        state = DocumentState(
            url="https://example.com/doc",
            part_name="Test Part",
            last_scraped_at="2025-12-19T15:00:00",
            content_hash="abc123",
            chunk_count=10,
        )

        assert state.url == "https://example.com/doc"
        assert state.part_name == "Test Part"
        assert state.chunk_count == 10
        assert state.content_hash == "abc123"


class TestIndexState:
    """Tests for IndexState dataclass."""

    def test_index_state_creation(self):
        """Test creating an IndexState."""
        state = IndexState()

        assert state.version == "1.0"
        assert state.last_full_index is None
        assert state.last_incremental_index is None
        assert len(state.documents) == 0

    def test_index_state_to_dict(self):
        """Test converting IndexState to dictionary."""
        doc_state = DocumentState(
            url="https://example.com/doc",
            part_name="Test Part",
            last_scraped_at="2025-12-19T15:00:00",
            content_hash="abc123",
            chunk_count=10,
        )

        state = IndexState(
            last_full_index="2025-12-19T15:00:00",
            documents={"https://example.com/doc": doc_state},
        )

        state_dict = state.to_dict()

        assert state_dict["version"] == "1.0"
        assert state_dict["last_full_index"] == "2025-12-19T15:00:00"
        assert "https://example.com/doc" in state_dict["documents"]

    def test_index_state_from_dict(self):
        """Test creating IndexState from dictionary."""
        data = {
            "version": "1.0",
            "last_full_index": "2025-12-19T15:00:00",
            "documents": {
                "https://example.com/doc": {
                    "url": "https://example.com/doc",
                    "part_name": "Test Part",
                    "last_scraped_at": "2025-12-19T15:00:00",
                    "content_hash": "abc123",
                    "chunk_count": 10,
                    "last_indexed_at": "2025-12-19T15:00:00",
                }
            },
        }

        state = IndexState.from_dict(data)

        assert state.version == "1.0"
        assert state.last_full_index == "2025-12-19T15:00:00"
        assert len(state.documents) == 1
        assert "https://example.com/doc" in state.documents


class TestIncrementalIndexer:
    """Tests for IncrementalIndexer."""

    @pytest.fixture
    def temp_state_file(self):
        """Create a temporary state file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            state_file = Path(f.name)
        yield state_file
        if state_file.exists():
            state_file.unlink()

    @pytest.fixture
    def temp_chunk_file(self):
        """Create a temporary chunk file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            chunk_data = {
                "url": "https://example.com/doc",
                "part_name": "Test Part",
                "scraped_at": "2025-12-19T15:00:00",
                "chunks": [
                    {
                        "metadata": {"section_id": "1.1"},
                        "text": "Test content",
                    }
                ],
            }
            json.dump(chunk_data, f)
            chunk_file = Path(f.name)
        yield chunk_file
        if chunk_file.exists():
            chunk_file.unlink()

    def test_indexer_initialization_no_state(self, temp_state_file):
        """Test initializing indexer with no existing state."""
        indexer = IncrementalIndexer(temp_state_file)

        assert indexer.state_file == temp_state_file
        assert len(indexer.state.documents) == 0

    def test_indexer_save_and_load_state(self, temp_state_file):
        """Test saving and loading state."""
        # Create indexer and add document
        indexer = IncrementalIndexer(temp_state_file)

        doc_state = DocumentState(
            url="https://example.com/doc",
            part_name="Test Part",
            last_scraped_at="2025-12-19T15:00:00",
            content_hash="abc123",
            chunk_count=10,
        )
        indexer.state.documents["https://example.com/doc"] = doc_state

        # Save state
        indexer.save_state()

        # Create new indexer and verify it loads the state
        new_indexer = IncrementalIndexer(temp_state_file)

        assert len(new_indexer.state.documents) == 1
        assert "https://example.com/doc" in new_indexer.state.documents
        assert new_indexer.state.documents["https://example.com/doc"].chunk_count == 10

    def test_compute_content_hash(self, temp_state_file, temp_chunk_file):
        """Test computing content hash."""
        indexer = IncrementalIndexer(temp_state_file)

        hash1 = indexer.compute_content_hash(temp_chunk_file)
        hash2 = indexer.compute_content_hash(temp_chunk_file)

        # Same file should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 produces 64 hex characters

    def test_detect_new_files(self, temp_state_file, temp_chunk_file):
        """Test detecting new files."""
        indexer = IncrementalIndexer(temp_state_file)

        new_files, updated_files, deleted_urls = indexer.detect_changes([temp_chunk_file])

        assert len(new_files) == 1
        assert temp_chunk_file in new_files
        assert len(updated_files) == 0
        assert len(deleted_urls) == 0

    def test_detect_updated_files(self, temp_state_file, temp_chunk_file):
        """Test detecting updated files."""
        indexer = IncrementalIndexer(temp_state_file)

        # Add document to state with different hash
        indexer.state.documents["https://example.com/doc"] = DocumentState(
            url="https://example.com/doc",
            part_name="Test Part",
            last_scraped_at="2025-12-19T15:00:00",
            content_hash="old_hash",
            chunk_count=10,
        )

        new_files, updated_files, deleted_urls = indexer.detect_changes([temp_chunk_file])

        assert len(new_files) == 0
        assert len(updated_files) == 1
        assert temp_chunk_file in updated_files
        assert len(deleted_urls) == 0

    def test_detect_deleted_documents(self, temp_state_file):
        """Test detecting deleted documents."""
        indexer = IncrementalIndexer(temp_state_file)

        # Add document to state that doesn't exist in files
        indexer.state.documents["https://example.com/deleted"] = DocumentState(
            url="https://example.com/deleted",
            part_name="Deleted Part",
            last_scraped_at="2025-12-19T15:00:00",
            content_hash="abc123",
            chunk_count=5,
        )

        new_files, updated_files, deleted_urls = indexer.detect_changes([])

        assert len(new_files) == 0
        assert len(updated_files) == 0
        assert len(deleted_urls) == 1
        assert "https://example.com/deleted" in deleted_urls

    def test_update_document_state(self, temp_state_file, temp_chunk_file):
        """Test updating document state."""
        indexer = IncrementalIndexer(temp_state_file)

        indexer.update_document_state(
            url="https://example.com/doc",
            part_name="Test Part",
            chunk_file=temp_chunk_file,
            chunk_count=5,
        )

        assert "https://example.com/doc" in indexer.state.documents
        doc_state = indexer.state.documents["https://example.com/doc"]
        assert doc_state.chunk_count == 5
        assert doc_state.part_name == "Test Part"
        assert len(doc_state.content_hash) == 64

    def test_mark_full_index_complete(self, temp_state_file):
        """Test marking full index as complete."""
        indexer = IncrementalIndexer(temp_state_file)

        assert indexer.state.last_full_index is None

        indexer.mark_full_index_complete()

        assert indexer.state.last_full_index is not None

    def test_mark_incremental_index_complete(self, temp_state_file):
        """Test marking incremental index as complete."""
        indexer = IncrementalIndexer(temp_state_file)

        assert indexer.state.last_incremental_index is None

        indexer.mark_incremental_index_complete()

        assert indexer.state.last_incremental_index is not None

    def test_remove_document(self, temp_state_file):
        """Test removing a document from state."""
        indexer = IncrementalIndexer(temp_state_file)

        # Add document
        indexer.state.documents["https://example.com/doc"] = DocumentState(
            url="https://example.com/doc",
            part_name="Test Part",
            last_scraped_at="2025-12-19T15:00:00",
            content_hash="abc123",
            chunk_count=10,
        )

        assert len(indexer.state.documents) == 1

        # Remove document
        indexer.remove_document("https://example.com/doc")

        assert len(indexer.state.documents) == 0

    def test_get_statistics(self, temp_state_file):
        """Test getting statistics."""
        indexer = IncrementalIndexer(temp_state_file)

        # Add some documents
        indexer.state.documents["https://example.com/doc1"] = DocumentState(
            url="https://example.com/doc1",
            part_name="Part 1",
            last_scraped_at="2025-12-19T15:00:00",
            content_hash="abc123",
            chunk_count=10,
        )
        indexer.state.documents["https://example.com/doc2"] = DocumentState(
            url="https://example.com/doc2",
            part_name="Part 2",
            last_scraped_at="2025-12-19T16:00:00",
            content_hash="def456",
            chunk_count=15,
        )

        stats = indexer.get_statistics()

        assert stats["total_documents"] == 2
        assert stats["total_chunks"] == 25
        assert stats["last_full_index"] is None
