"""Legal domain embedder with batch processing and error handling.

This module provides the main LegalEmbedder class that orchestrates embedding
generation for legal immigration documents. Supports voyage-law-2 (recommended)
or LEGAL-BERT models via simple configuration.
"""

import logging
import os
from typing import Dict, List, Optional, Tuple

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from data_pipeline.processing.embedding_providers import (
    EmbeddingProvider,
    LegalBERTProvider,
    VoyageAIProvider,
)

logger = logging.getLogger(__name__)


class LegalEmbedder:
    """Main embedder class for legal immigration documents.

    This class orchestrates embedding generation with:
    - voyage-law-2 (recommended) - Legal domain-specific, 1024-dim
    - LEGAL-BERT (alternative) - Open-source, 768-dim
    - Batch processing for efficiency
    - Retry logic with exponential backoff for API failures

    To switch models, simply change the model_name parameter.

    Example:
        >>> # Using voyage-law-2 (recommended)
        >>> embedder = LegalEmbedder(model_name="voyage-law-2", batch_size=128)
        >>>
        >>> # Using LEGAL-BERT (for development/testing)
        >>> embedder = LegalEmbedder(model_name="nlpaueb/legal-bert-base-uncased")
        >>>
        >>> chunks = [{"text": "...", "id": "1"}, ...]
        >>> embedded_chunks, failed_ids = embedder.embed_chunks(chunks)
    """

    def __init__(
        self,
        model_name: str = "voyage-law-2",
        batch_size: int = 128,
        api_key: Optional[str] = None,
    ):
        """Initialize the legal embedder.

        Args:
            model_name: Name of the embedding model to use (default: voyage-law-2)
            batch_size: Number of texts to embed in each batch (default: 128)
            api_key: Voyage AI API key (defaults to VOYAGE_API_KEY env var)
        """
        self.model_name = model_name
        self.batch_size = batch_size

        # Initialize provider based on model name
        if model_name == "voyage-law-2" or model_name.startswith("voyage-"):
            if api_key is None:
                api_key = os.getenv("VOYAGE_API_KEY")
            self.provider = VoyageAIProvider(model_name=model_name, api_key=api_key)
        else:
            # Assume it's a sentence-transformers model (e.g., LEGAL-BERT)
            self.provider = LegalBERTProvider(model_name=model_name)

        logger.info(
            f"Initialized LegalEmbedder with model: {model_name}, " f"batch_size: {batch_size}"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _embed_with_retry(self, texts: List[str], provider: EmbeddingProvider) -> List[List[float]]:
        """Embed texts with retry logic.

        Args:
            texts: List of texts to embed
            provider: Embedding provider to use

        Returns:
            List of embedding vectors

        Raises:
            Exception: If all retry attempts fail
        """
        return provider.embed_batch(texts)

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text.

        Args:
            text: The text to embed

        Returns:
            Embedding vector as list of floats
        """
        return self.provider.embed(text)

    def embed_batch(self, texts: List[str]) -> Tuple[List[List[float]], List[int]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of texts to embed

        Returns:
            Tuple of (embeddings, failed_indices)
            - embeddings: List of embedding vectors
            - failed_indices: List of indices that failed to embed
        """
        if not texts:
            return [], []

        try:
            result = self._embed_with_retry(texts, self.provider)
            return result, []
        except Exception as e:
            logger.error(f"Failed to embed batch of {len(texts)} texts: {e}")
            # Return None for all embeddings and mark all as failed
            return [None] * len(texts), list(range(len(texts)))

    def embed_chunks(
        self, chunks: List[Dict], text_field: str = "augmented_text"
    ) -> Tuple[List[Dict], List[str]]:
        """Embed a list of chunks in batches.

        This method processes chunks in batches for efficiency and adds
        the 'embedding' field to each chunk.

        Args:
            chunks: List of chunk dictionaries
            text_field: Field name containing text to embed (default: augmented_text)

        Returns:
            Tuple of (embedded_chunks, failed_chunk_ids)
            - embedded_chunks: Chunks with 'embedding' field added
            - failed_chunk_ids: List of chunk IDs that failed to embed
        """
        if not chunks:
            return [], []

        logger.info(f"Embedding {len(chunks)} chunks in batches of {self.batch_size}")

        embedded_chunks = []
        failed_chunk_ids = []

        # Process in batches
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            batch_texts = []
            batch_chunk_map = []  # Map from batch index to chunk

            # Extract texts from chunks
            for chunk in batch:
                if text_field in chunk and chunk[text_field]:
                    batch_texts.append(chunk[text_field])
                    batch_chunk_map.append(chunk)
                else:
                    logger.warning(
                        f"Chunk missing '{text_field}' field: {chunk.get('metadata', {}).get('section_id', 'unknown')}"
                    )
                    failed_chunk_ids.append(
                        chunk.get("metadata", {}).get("section_id", f"chunk_{i}")
                    )

            if not batch_texts:
                continue

            # Embed batch
            embeddings, failed_indices = self.embed_batch(batch_texts)

            # Add embeddings to chunks
            for idx, (chunk, embedding) in enumerate(zip(batch_chunk_map, embeddings)):
                if embedding is not None:
                    chunk_copy = chunk.copy()
                    chunk_copy["embedding"] = embedding
                    embedded_chunks.append(chunk_copy)
                else:
                    chunk_id = chunk.get("metadata", {}).get("section_id", f"chunk_{i + idx}")
                    failed_chunk_ids.append(chunk_id)
                    logger.error(f"Failed to embed chunk: {chunk_id}")

            logger.info(
                f"Processed batch {i // self.batch_size + 1}/{(len(chunks) + self.batch_size - 1) // self.batch_size}: "
                f"{len(embeddings) - len(failed_indices)}/{len(batch_texts)} successful"
            )

        success_rate = (len(embedded_chunks) / len(chunks)) * 100 if chunks else 0
        logger.info(
            f"Embedding complete: {len(embedded_chunks)}/{len(chunks)} chunks embedded "
            f"({success_rate:.1f}% success rate)"
        )

        if failed_chunk_ids:
            logger.warning(f"Failed to embed {len(failed_chunk_ids)} chunks")

        return embedded_chunks, failed_chunk_ids

    def get_embedding_dimension(self) -> int:
        """Get the dimensionality of embeddings.

        Returns:
            Integer dimension of embedding vectors
        """
        return self.provider.get_dimension()

    def get_model_info(self) -> Dict[str, any]:
        """Get information about the embedding model.

        Returns:
            Dictionary with model information
        """
        return {
            "model_name": self.provider.get_model_name(),
            "batch_size": self.batch_size,
            "embedding_dimension": self.provider.get_dimension(),
        }
