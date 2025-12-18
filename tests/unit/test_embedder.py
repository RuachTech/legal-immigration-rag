"""Unit tests for the legal domain embedder.

These tests verify the embedding functionality with mocked API calls
to avoid costs and ensure reliability.
"""

from unittest.mock import Mock, patch

from data_pipeline.processing.embedder import LegalEmbedder
from data_pipeline.processing.embedding_providers import (
    LegalBERTProvider,
    VoyageAIProvider,
)


class TestEmbeddingProviders:
    """Test the embedding provider implementations."""

    @patch("voyageai.Client")
    def test_voyage_ai_provider_initialization(self, mock_client_class):
        """Test VoyageAIProvider initializes correctly."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        provider = VoyageAIProvider(model_name="voyage-law-2", api_key="test_key")

        assert provider.model_name == "voyage-law-2"
        assert provider.get_dimension() == 1024
        assert provider.get_model_name() == "voyage-law-2"
        mock_client_class.assert_called_once_with(api_key="test_key")

    @patch("voyageai.Client")
    def test_voyage_ai_provider_embed_single(self, mock_client_class):
        """Test VoyageAIProvider embeds single text correctly."""
        mock_client = Mock()
        mock_result = Mock()
        mock_result.embeddings = [[0.1] * 1024]
        mock_client.embed.return_value = mock_result
        mock_client_class.return_value = mock_client

        provider = VoyageAIProvider(api_key="test_key")
        embedding = provider.embed("test text")

        assert len(embedding) == 1024
        assert embedding[0] == 0.1
        mock_client.embed.assert_called_once_with(["test text"], model="voyage-law-2")

    @patch("voyageai.Client")
    def test_voyage_ai_provider_embed_batch(self, mock_client_class):
        """Test VoyageAIProvider embeds batch correctly."""
        mock_client = Mock()
        mock_result = Mock()
        mock_result.embeddings = [[0.1] * 1024, [0.2] * 1024, [0.3] * 1024]
        mock_client.embed.return_value = mock_result
        mock_client_class.return_value = mock_client

        provider = VoyageAIProvider(api_key="test_key")
        texts = ["text1", "text2", "text3"]
        embeddings = provider.embed_batch(texts)

        assert len(embeddings) == 3
        assert len(embeddings[0]) == 1024
        assert embeddings[0][0] == 0.1
        assert embeddings[1][0] == 0.2
        mock_client.embed.assert_called_once_with(texts, model="voyage-law-2")

    @patch("sentence_transformers.SentenceTransformer")
    def test_legal_bert_provider_initialization(self, mock_st):
        """Test LegalBERTProvider initializes correctly."""
        mock_model = Mock()
        mock_st.return_value = mock_model

        provider = LegalBERTProvider()

        assert provider.model_name == "nlpaueb/legal-bert-base-uncased"
        assert provider.get_dimension() == 768
        mock_st.assert_called_once_with("nlpaueb/legal-bert-base-uncased")

    @patch("sentence_transformers.SentenceTransformer")
    def test_legal_bert_provider_embed_single(self, mock_st):
        """Test LegalBERTProvider embeds single text correctly."""
        mock_model = Mock()
        mock_embedding = Mock()
        mock_embedding.tolist.return_value = [0.5] * 768
        mock_model.encode.return_value = mock_embedding
        mock_st.return_value = mock_model

        provider = LegalBERTProvider()
        embedding = provider.embed("test text")

        assert len(embedding) == 768
        assert embedding[0] == 0.5
        mock_model.encode.assert_called_once_with("test text", convert_to_numpy=True)

    @patch("sentence_transformers.SentenceTransformer")
    def test_legal_bert_provider_embed_batch(self, mock_st):
        """Test LegalBERTProvider embeds batch correctly."""
        mock_model = Mock()
        mock_embeddings = Mock()
        mock_embeddings.tolist.return_value = [[0.5] * 768, [0.6] * 768]
        mock_model.encode.return_value = mock_embeddings
        mock_st.return_value = mock_model

        provider = LegalBERTProvider()
        texts = ["text1", "text2"]
        embeddings = provider.embed_batch(texts)

        assert len(embeddings) == 2
        assert len(embeddings[0]) == 768
        mock_model.encode.assert_called_once()


class TestLegalEmbedder:
    """Test the main LegalEmbedder class."""

    @patch("data_pipeline.processing.embedder.VoyageAIProvider")
    @patch("data_pipeline.processing.embedder.LegalBERTProvider")
    def test_embedder_initialization_with_voyage(self, mock_legal_bert, mock_voyage):
        """Test LegalEmbedder initializes with VoyageAI as primary."""
        mock_voyage_instance = Mock()
        mock_voyage.return_value = mock_voyage_instance
        mock_legal_bert_instance = Mock()
        mock_legal_bert.return_value = mock_legal_bert_instance

        embedder = LegalEmbedder(model_name="voyage-law-2", api_key="test_key")

        assert embedder.model_name == "voyage-law-2"
        assert embedder.batch_size == 128
        assert embedder.primary_provider == mock_voyage_instance
        assert embedder.fallback_provider == mock_legal_bert_instance
        mock_voyage.assert_called_once_with(model_name="voyage-law-2", api_key="test_key")
        mock_legal_bert.assert_called_once()

    @patch("data_pipeline.processing.embedder.LegalBERTProvider")
    def test_embedder_initialization_with_legal_bert(self, mock_legal_bert):
        """Test LegalEmbedder initializes with LEGAL-BERT as primary."""
        mock_instance = Mock()
        mock_legal_bert.return_value = mock_instance

        embedder = LegalEmbedder(model_name="nlpaueb/legal-bert-base-uncased", use_fallback=False)

        assert embedder.primary_provider == mock_instance
        assert embedder.fallback_provider is None

    @patch("data_pipeline.processing.embedder.VoyageAIProvider")
    def test_embed_text_success(self, mock_voyage):
        """Test embedding single text successfully."""
        mock_provider = Mock()
        mock_provider.embed.return_value = [0.1] * 1024
        mock_voyage.return_value = mock_provider

        embedder = LegalEmbedder(api_key="test_key", use_fallback=False)
        embedding = embedder.embed_text("test text")

        assert len(embedding) == 1024
        assert embedding[0] == 0.1
        mock_provider.embed.assert_called_once_with("test text")

    @patch("data_pipeline.processing.embedder.VoyageAIProvider")
    @patch("data_pipeline.processing.embedder.LegalBERTProvider")
    def test_embed_text_fallback(self, mock_legal_bert, mock_voyage):
        """Test fallback to LEGAL-BERT when VoyageAI fails."""
        mock_voyage_provider = Mock()
        mock_voyage_provider.embed.side_effect = Exception("API Error")
        mock_voyage.return_value = mock_voyage_provider

        mock_bert_provider = Mock()
        mock_bert_provider.embed.return_value = [0.5] * 768
        mock_legal_bert.return_value = mock_bert_provider

        embedder = LegalEmbedder(api_key="test_key", use_fallback=True)
        embedding = embedder.embed_text("test text")

        assert len(embedding) == 768
        assert embedding[0] == 0.5
        mock_bert_provider.embed.assert_called_once_with("test text")

    @patch("data_pipeline.processing.embedder.VoyageAIProvider")
    def test_embed_batch_success(self, mock_voyage):
        """Test embedding batch successfully."""
        mock_provider = Mock()
        mock_provider.embed_batch.return_value = [[0.1] * 1024, [0.2] * 1024]
        mock_voyage.return_value = mock_provider

        embedder = LegalEmbedder(api_key="test_key", use_fallback=False)
        embeddings, failed = embedder.embed_batch(["text1", "text2"])

        assert len(embeddings) == 2
        assert len(failed) == 0
        assert embeddings[0][0] == 0.1

    @patch("data_pipeline.processing.embedder.VoyageAIProvider")
    def test_embed_chunks_success(self, mock_voyage):
        """Test embedding chunks successfully."""
        mock_provider = Mock()
        mock_provider.embed_batch.return_value = [[0.1] * 1024, [0.2] * 1024]
        mock_voyage.return_value = mock_provider

        chunks = [
            {
                "augmented_text": "text1",
                "metadata": {"section_id": "chunk1"},
            },
            {
                "augmented_text": "text2",
                "metadata": {"section_id": "chunk2"},
            },
        ]

        embedder = LegalEmbedder(api_key="test_key", use_fallback=False)
        embedded_chunks, failed_ids = embedder.embed_chunks(chunks)

        assert len(embedded_chunks) == 2
        assert len(failed_ids) == 0
        assert "embedding" in embedded_chunks[0]
        assert len(embedded_chunks[0]["embedding"]) == 1024
        assert embedded_chunks[0]["embedding"][0] == 0.1

    @patch("data_pipeline.processing.embedder.VoyageAIProvider")
    def test_embed_chunks_with_missing_field(self, mock_voyage):
        """Test embedding chunks with missing text field."""
        mock_provider = Mock()
        mock_provider.embed_batch.return_value = [[0.1] * 1024]
        mock_voyage.return_value = mock_provider

        chunks = [
            {
                "augmented_text": "text1",
                "metadata": {"section_id": "chunk1"},
            },
            {
                # Missing augmented_text field
                "metadata": {"section_id": "chunk2"},
            },
        ]

        embedder = LegalEmbedder(api_key="test_key", use_fallback=False)
        embedded_chunks, failed_ids = embedder.embed_chunks(chunks)

        assert len(embedded_chunks) == 1
        assert len(failed_ids) == 1
        assert "chunk2" in failed_ids

    @patch("data_pipeline.processing.embedder.VoyageAIProvider")
    def test_embed_chunks_batch_processing(self, mock_voyage):
        """Test chunks are processed in batches."""
        mock_provider = Mock()
        # Return different embeddings for each batch call
        mock_provider.embed_batch.side_effect = [
            [[0.1] * 1024, [0.2] * 1024],  # First batch
            [[0.3] * 1024],  # Second batch
        ]
        mock_voyage.return_value = mock_provider

        chunks = [
            {"augmented_text": f"text{i}", "metadata": {"section_id": f"chunk{i}"}}
            for i in range(3)
        ]

        embedder = LegalEmbedder(api_key="test_key", batch_size=2, use_fallback=False)
        embedded_chunks, failed_ids = embedder.embed_chunks(chunks)

        assert len(embedded_chunks) == 3
        assert len(failed_ids) == 0
        # Should have been called twice (2 batches)
        assert mock_provider.embed_batch.call_count == 2

    @patch("data_pipeline.processing.embedder.VoyageAIProvider")
    def test_get_embedding_dimension(self, mock_voyage):
        """Test getting embedding dimension."""
        mock_provider = Mock()
        mock_provider.get_dimension.return_value = 1024
        mock_voyage.return_value = mock_provider

        embedder = LegalEmbedder(api_key="test_key", use_fallback=False)
        dimension = embedder.get_embedding_dimension()

        assert dimension == 1024

    @patch("data_pipeline.processing.embedder.VoyageAIProvider")
    @patch("data_pipeline.processing.embedder.LegalBERTProvider")
    def test_get_model_info(self, mock_legal_bert, mock_voyage):
        """Test getting model information."""
        mock_voyage_provider = Mock()
        mock_voyage_provider.get_model_name.return_value = "voyage-law-2"
        mock_voyage_provider.get_dimension.return_value = 1024
        mock_voyage.return_value = mock_voyage_provider

        mock_bert_provider = Mock()
        mock_bert_provider.get_model_name.return_value = "nlpaueb/legal-bert-base-uncased"
        mock_legal_bert.return_value = mock_bert_provider

        embedder = LegalEmbedder(api_key="test_key", use_fallback=True)
        info = embedder.get_model_info()

        assert info["primary_model"] == "voyage-law-2"
        assert info["fallback_model"] == "nlpaueb/legal-bert-base-uncased"
        assert info["embedding_dimension"] == 1024
        assert info["batch_size"] == 128
