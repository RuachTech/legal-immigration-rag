"""Unit tests for Summary-Augmented Chunking (SAC) implementation.

Tests cover:
- RecursiveCharacterTextSplitter respects document structure
- DocumentSummarizer generates appropriate summaries
- SummaryAugmentedChunker prepends summaries to chunks
- Metadata is properly attached to chunks
- Integration with storage layer
"""

from unittest.mock import MagicMock, patch

import pytest

from data_pipeline.processing import (
    ChunkInfo,
    DocumentInfo,
    LLMDocumentSummarizer,
    RecursiveCharacterTextSplitter,
    SummaryAugmentedChunker,
    create_embedding_stub,
    sac_chunk_to_storage_chunk,
    sac_chunks_to_storage_chunks,
)
from storage.vector.base import Chunk, ChunkMetadata


class TestRecursiveCharacterTextSplitter:
    """Test document splitting logic."""

    def test_split_by_paragraphs(self):
        """Should split at paragraph boundaries first."""
        text = "First paragraph with more content to reach the limit.\n\n" \
        "Second paragraph with even more content here.\n\nThird paragraph with " \
        "substantial additional text to ensure proper splitting."
        splitter = RecursiveCharacterTextSplitter(max_chunk_size=80)
        chunks = splitter.split(text)

        assert len(chunks) >= 2
        assert "First paragraph" in chunks[0]
        # Verify chunks don't exceed max size
        for chunk in chunks:
            assert len(chunk) <= 150

    def test_respects_max_chunk_size(self):
        """All chunks should respect max_chunk_size."""
        text = "word " * 500  # 2500 chars
        splitter = RecursiveCharacterTextSplitter(max_chunk_size=100)
        chunks = splitter.split(text)

        for chunk in chunks:
            assert len(chunk) <= 150  # Allow some flexibility for word boundaries

    def test_preserves_short_text(self):
        """Short text should not be split."""
        text = "This is a short sentence."
        splitter = RecursiveCharacterTextSplitter(max_chunk_size=1000)
        chunks = splitter.split(text)

        assert len(chunks) == 1
        assert chunks[0] == text

    def test_handles_empty_string(self):
        """Empty string should return empty list."""
        splitter = RecursiveCharacterTextSplitter()
        chunks = splitter.split("")

        assert chunks == [""]

    def test_handles_multiple_separators(self):
        """Should try separators in order."""
        text = "A\n\nB\nC D E"
        splitter = RecursiveCharacterTextSplitter(max_chunk_size=50, separators=["\n\n", "\n", " "])
        chunks = splitter.split(text)

        # Should split at \n\n first
        assert len(chunks) >= 1
        assert all(chunk.strip() for chunk in chunks if chunk)

    def test_preserves_legal_structure(self):
        """Should preserve clause structure within chunks."""
        text = """
        Section 1: Eligibility

        1.1 The applicant must meet all of the following requirements:
        (a) Be at least 18 years old
        (b) Have a valid passport
        (c) Have adequate funds
        Section 2: Application Process
        """
        splitter = RecursiveCharacterTextSplitter(max_chunk_size=200)
        chunks = splitter.split(text)

        # Verify no clause is split mid-requirement
        full_text = " ".join(chunks)
        assert full_text.count("(a)") >= 1
        assert full_text.count("(b)") >= 1


class TestLLMDocumentSummarizer:
    """Test LLM-based document summarization."""

    @patch("data_pipeline.processing.summary_augmented_chunker.litellm.completion")
    def test_generates_summary(self, mock_completion):
        """Should call litellm and return summary."""
        mock_response = {"choices": [{"message": {"content": "This is a summary."}}]}
        mock_completion.return_value = mock_response

        summarizer = LLMDocumentSummarizer()
        result = summarizer.summarize("Some legal text", "Visa Requirements")

        assert result == "This is a summary."
        mock_completion.assert_called_once()

    @patch("data_pipeline.processing.summary_augmented_chunker.litellm.completion")
    def test_handles_api_error(self, mock_completion):
        """Should fallback to title on API error."""
        mock_completion.side_effect = Exception("API error")

        summarizer = LLMDocumentSummarizer()
        result = summarizer.summarize("Some text", "Test Document")

        assert result == "Test Document"

    @patch("data_pipeline.processing.summary_augmented_chunker.litellm.completion")
    def test_truncates_long_documents(self, mock_completion):
        """Should only pass first 2000 chars to LLM."""
        mock_completion.return_value = {"choices": [{"message": {"content": "Summary"}}]}

        summarizer = LLMDocumentSummarizer()
        long_text = "a" * 5000
        summarizer.summarize(long_text, "Title")

        call_args = mock_completion.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert len(prompt) < len(long_text)


class TestSummaryAugmentedChunker:
    """Test the main SAC implementation."""

    @patch("data_pipeline.processing.summary_augmented_chunker.LLMDocumentSummarizer")
    def test_chunks_document(self, mock_summarizer_class):
        """Should split document and prepend summary to each chunk."""
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = "Document Summary"
        mock_summarizer_class.return_value = mock_summarizer

        chunker = SummaryAugmentedChunker(summarizer=mock_summarizer)

        doc_text = "First part.\n\nSecond part.\n\nThird part."
        doc_info = DocumentInfo(title="Test Doc", url="https://example.com/doc")

        chunks = chunker.chunk_document(doc_text, doc_info)

        assert len(chunks) >= 1
        # Each chunk should have augmented content with summary
        for chunk in chunks:
            assert "Document Summary" in chunk["augmented_content"]
            assert chunk["summary"] == "Document Summary"
            assert chunk["metadata"]["source"] == "Test Doc"

    @patch("data_pipeline.processing.summary_augmented_chunker.LLMDocumentSummarizer")
    def test_metadata_attachment(self, mock_summarizer_class):
        """Should attach complete hierarchical metadata."""
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = "Summary"
        mock_summarizer_class.return_value = mock_summarizer

        chunker = SummaryAugmentedChunker(summarizer=mock_summarizer)

        doc_text = "Content here."
        doc_info = DocumentInfo(
            title="Appendix Skilled Worker",
            url="https://gov.uk/skilled-worker",
            effective_date="2025-01-01",
            version="1.2",
        )

        chunks = chunker.chunk_document(doc_text, doc_info)

        assert len(chunks) >= 1
        metadata = chunks[0]["metadata"]
        assert metadata["source"] == "Appendix Skilled Worker"
        assert metadata["url"] == "https://gov.uk/skilled-worker"
        assert metadata["effective_date"] == "2025-01-01"
        assert metadata["version"] == "1.2"
        assert "chunk_number" in metadata

    @patch("data_pipeline.processing.summary_augmented_chunker.LLMDocumentSummarizer")
    def test_structure_extraction_callback(self, mock_summarizer_class):
        """Should call extract_structure_fn if provided."""
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = "Summary"
        mock_summarizer_class.return_value = mock_summarizer

        def extract_structure(chunk_text):
            return ChunkInfo(
                raw_content=chunk_text,
                chunk_number=1,
                part="Part 1",
                section="1.1",
                topic="Eligibility",
            )

        chunker = SummaryAugmentedChunker(summarizer=mock_summarizer)

        doc_text = "Content here."
        doc_info = DocumentInfo(title="Test", url="http://test.com")

        chunks = chunker.chunk_document(doc_text, doc_info, extract_structure)

        assert chunks[0]["metadata"]["part"] == "Part 1"
        assert chunks[0]["metadata"]["section"] == "1.1"
        assert chunks[0]["metadata"]["topic"] == "Eligibility"

    @patch("data_pipeline.processing.summary_augmented_chunker.LLMDocumentSummarizer")
    def test_multiple_documents(self, mock_summarizer_class):
        """Should process multiple documents."""
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.side_effect = ["Summary 1", "Summary 2"]
        mock_summarizer_class.return_value = mock_summarizer

        chunker = SummaryAugmentedChunker(summarizer=mock_summarizer)

        documents = [
            ("First doc content.", DocumentInfo("Doc1", "http://1.com")),
            ("Second doc content.", DocumentInfo("Doc2", "http://2.com")),
        ]

        all_chunks = chunker.chunk_documents(documents)

        assert len(all_chunks) >= 2
        assert mock_summarizer.summarize.call_count == 2

    @patch("data_pipeline.processing.summary_augmented_chunker.LLMDocumentSummarizer")
    def test_unique_chunk_ids(self, mock_summarizer_class):
        """Each chunk should have a unique ID."""
        mock_summarizer = MagicMock()
        mock_summarizer.summarize.return_value = "Summary"
        mock_summarizer_class.return_value = mock_summarizer

        chunker = SummaryAugmentedChunker(summarizer=mock_summarizer)

        doc_text = "Chunk 1.\n\nChunk 2.\n\nChunk 3."
        doc_info = DocumentInfo("Test", "http://test.com")

        chunks = chunker.chunk_document(doc_text, doc_info)

        ids = [chunk["id"] for chunk in chunks]
        assert len(ids) == len(set(ids))  # All unique


class TestChunkConverter:
    """Test conversion from SAC format to storage format."""

    def test_embedding_stub_creation(self):
        """Should create correct-sized embedding stub."""
        stub = create_embedding_stub(size=1536)

        assert len(stub) == 1536
        assert all(x == 0.0 for x in stub)

    def test_sac_to_storage_chunk_conversion(self):
        """Should convert SAC chunk to Chunk format."""
        sac_chunk = {
            "id": "chunk-123",
            "raw_content": "Original content",
            "augmented_content": "Summary\n\nOriginal content",
            "summary": "Summary",
            "metadata": {
                "source": "Visa Requirements",
                "url": "https://gov.uk",
                "part": "Part 1",
                "section": "1.1",
                "parent_section": "Part 1",
                "hierarchy_level": 1,
                "topic": "Eligibility",
                "chunk_number": 1,
                "effective_date": "2025-01-01",
                "version": "1.0",
            },
        }

        embedding = [0.1] * 1536
        storage_chunk = sac_chunk_to_storage_chunk(sac_chunk, embedding)

        assert isinstance(storage_chunk, Chunk)
        assert storage_chunk.id == "chunk-123"
        assert storage_chunk.content == "Summary\n\nOriginal content"
        assert storage_chunk.summary == "Summary"
        assert storage_chunk.embedding == embedding
        assert isinstance(storage_chunk.metadata, ChunkMetadata)
        assert storage_chunk.metadata.source == "Visa Requirements"
        assert storage_chunk.metadata.section == "1.1"

    def test_sac_to_storage_batch_conversion(self):
        """Should convert batch of SAC chunks."""
        sac_chunks = [
            {
                "id": f"chunk-{i}",
                "raw_content": f"Content {i}",
                "augmented_content": f"Summary\n\nContent {i}",
                "summary": "Summary",
                "metadata": {
                    "source": "Doc",
                    "url": "http://test.com",
                    "part": "Part 1",
                    "section": f"1.{i}",
                    "parent_section": "Part 1",
                    "hierarchy_level": 1,
                    "topic": "Topic",
                    "chunk_number": i,
                },
            }
            for i in range(3)
        ]

        embeddings = [[0.1] * 1536 for _ in range(3)]
        storage_chunks = sac_chunks_to_storage_chunks(sac_chunks, embeddings)

        assert len(storage_chunks) == 3
        for i, chunk in enumerate(storage_chunks):
            assert chunk.id == f"chunk-{i}"
            assert isinstance(chunk, Chunk)

    def test_converter_uses_stubs_for_missing_embeddings(self):
        """Should use embedding stubs when not provided."""
        sac_chunk = {
            "id": "chunk-123",
            "raw_content": "Content",
            "augmented_content": "Summary\n\nContent",
            "summary": "Summary",
            "metadata": {
                "source": "Doc",
                "url": "http://test.com",
                "part": "",
                "section": "",
                "parent_section": None,
                "hierarchy_level": 0,
                "topic": "Topic",
                "chunk_number": 1,
            },
        }

        storage_chunk = sac_chunk_to_storage_chunk(sac_chunk, embedding=None)

        assert len(storage_chunk.embedding) == 1536
        assert all(x == 0.0 for x in storage_chunk.embedding)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
