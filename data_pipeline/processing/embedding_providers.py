"""Abstract interface and implementations for embedding providers.

This module provides a clean abstraction for different embedding models,
allowing the system to switch between voyage-law-2 (primary) and LEGAL-BERT
(fallback) without changing application code.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import List, Optional

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers.

    This interface allows swapping between different embedding models
    (voyage-law-2, LEGAL-BERT, etc.) without changing application code.
    """

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: The text to embed

        Returns:
            List of floats representing the embedding vector
        """
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors, one per input text
        """
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Get the dimensionality of embeddings produced by this provider.

        Returns:
            Integer dimension of embedding vectors
        """
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the name of the embedding model.

        Returns:
            String name of the model
        """
        pass


class VoyageAIProvider(EmbeddingProvider):
    """Embedding provider using Voyage AI's voyage-law-2 model.

    This is the primary embedding model for the legal immigration RAG system,
    specifically trained on legal text for superior performance on legal domain tasks.
    """

    def __init__(self, model_name: str = "voyage-law-2", api_key: Optional[str] = None):
        """Initialize Voyage AI provider.

        Args:
            model_name: Name of the Voyage AI model to use
            api_key: Voyage AI API key (defaults to VOYAGE_API_KEY env var)
        """
        try:
            import voyageai
        except ImportError:
            raise ImportError("voyageai package not installed. Install with: uv add voyageai")

        self.model_name = model_name
        self.api_key = api_key or os.getenv("VOYAGE_API_KEY")

        if not self.api_key:
            raise ValueError(
                "Voyage AI API key not provided. Set VOYAGE_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.client = voyageai.Client(api_key=self.api_key)
        logger.info(f"Initialized VoyageAIProvider with model: {model_name}")

    def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text using voyage-law-2.

        Args:
            text: The text to embed

        Returns:
            1024-dimensional embedding vector
        """
        result = self.client.embed([text], model=self.model_name)
        return result.embeddings[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts using voyage-law-2.

        Args:
            texts: List of texts to embed

        Returns:
            List of 1024-dimensional embedding vectors
        """
        if not texts:
            return []

        result = self.client.embed(texts, model=self.model_name)
        return result.embeddings

    def get_dimension(self) -> int:
        """Get embedding dimension for voyage-law-2.

        Returns:
            1024 (voyage-law-2 embedding dimension)
        """
        return 1024

    def get_model_name(self) -> str:
        """Get the model name.

        Returns:
            Model name string
        """
        return self.model_name


class LegalBERTProvider(EmbeddingProvider):
    """Embedding provider using LEGAL-BERT model.

    This is an optional fallback provider that uses the open-source LEGAL-BERT model
    from sentence-transformers. It's useful for:
    - Development and testing (no API costs)
    - Fallback when Voyage AI is unavailable
    - Offline operation
    """

    def __init__(self, model_name: str = "nlpaueb/legal-bert-base-uncased"):
        """Initialize LEGAL-BERT provider.

        Args:
            model_name: Name of the sentence-transformers model to use
        """
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        logger.info(f"Loading LEGAL-BERT model: {model_name}")
        self.model = SentenceTransformer(model_name)
        logger.info(f"Initialized LegalBERTProvider with model: {model_name}")

    def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text using LEGAL-BERT.

        Args:
            text: The text to embed

        Returns:
            768-dimensional embedding vector
        """
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts using LEGAL-BERT.

        Args:
            texts: List of texts to embed

        Returns:
            List of 768-dimensional embedding vectors
        """
        if not texts:
            return []

        embeddings = self.model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
        return embeddings.tolist()

    def get_dimension(self) -> int:
        """Get embedding dimension for LEGAL-BERT.

        Returns:
            768 (LEGAL-BERT embedding dimension)
        """
        return 768

    def get_model_name(self) -> str:
        """Get the model name.

        Returns:
            Model name string
        """
        return self.model_name
