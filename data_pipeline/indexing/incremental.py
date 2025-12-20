"""Incremental indexing logic for detecting and processing document changes.

This module provides functionality to track which documents have been processed
and detect changes to enable efficient incremental updates.
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class DocumentState:
    """State information for a single document."""

    url: str
    part_name: str
    last_scraped_at: str
    content_hash: str
    chunk_count: int
    last_indexed_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class IndexState:
    """Overall state of the indexing pipeline."""

    version: str = "1.0"
    last_full_index: Optional[str] = None
    last_incremental_index: Optional[str] = None
    documents: Dict[str, DocumentState] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "last_full_index": self.last_full_index,
            "last_incremental_index": self.last_incremental_index,
            "documents": {url: asdict(doc) for url, doc in self.documents.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "IndexState":
        """Create IndexState from dictionary."""
        documents = {
            url: DocumentState(**doc_data) for url, doc_data in data.get("documents", {}).items()
        }
        return cls(
            version=data.get("version", "1.0"),
            last_full_index=data.get("last_full_index"),
            last_incremental_index=data.get("last_incremental_index"),
            documents=documents,
        )


class IncrementalIndexer:
    """Manages incremental indexing state and change detection.

    This class tracks which documents have been processed and identifies
    new, updated, and deleted documents for efficient incremental updates.
    """

    def __init__(self, state_file: Path):
        """Initialize incremental indexer.

        Args:
            state_file: Path to the index state JSON file
        """
        self.state_file = state_file
        self.state = self._load_state()

    def _load_state(self) -> IndexState:
        """Load index state from file."""
        if not self.state_file.exists():
            logger.info(f"No existing state file found at {self.state_file}")
            return IndexState()

        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            state = IndexState.from_dict(data)
            logger.info(
                f"Loaded index state: {len(state.documents)} documents, "
                f"last full index: {state.last_full_index}"
            )
            return state
        except Exception as e:
            logger.error(f"Failed to load state file: {e}")
            logger.warning("Starting with empty state")
            return IndexState()

    def save_state(self) -> None:
        """Save current state to file."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(self.state.to_dict(), f, indent=2)
            logger.info(f"Saved index state to {self.state_file}")
        except Exception as e:
            logger.error(f"Failed to save state file: {e}")
            raise

    def compute_content_hash(self, chunk_file: Path) -> str:
        """Compute hash of chunk file content.

        Args:
            chunk_file: Path to chunk JSON file

        Returns:
            SHA256 hash of file content
        """
        try:
            content = chunk_file.read_text(encoding="utf-8")
            return hashlib.sha256(content.encode("utf-8")).hexdigest()
        except Exception as e:
            logger.error(f"Failed to compute hash for {chunk_file}: {e}")
            return ""

    def detect_changes(
        self, chunk_files: List[Path]
    ) -> tuple[List[Path], List[Path], List[str]]:
        """Detect new, updated, and deleted documents.

        Args:
            chunk_files: List of current chunk file paths

        Returns:
            Tuple of (new_files, updated_files, deleted_urls)
        """
        new_files: List[Path] = []
        updated_files: List[Path] = []
        deleted_urls: List[str] = []

        # Build mapping of current files
        current_urls: Set[str] = set()

        for chunk_file in chunk_files:
            try:
                # Load chunk file to get URL
                with open(chunk_file, "r") as f:
                    data = json.load(f)

                url = data.get("url", "")
                if not url:
                    logger.warning(f"No URL found in {chunk_file.name}, skipping")
                    continue

                current_urls.add(url)

                # Check if document exists in state
                if url not in self.state.documents:
                    new_files.append(chunk_file)
                    logger.debug(f"New document: {url}")
                else:
                    # Check if content has changed
                    current_hash = self.compute_content_hash(chunk_file)
                    previous_hash = self.state.documents[url].content_hash

                    if current_hash != previous_hash:
                        updated_files.append(chunk_file)
                        logger.debug(f"Updated document: {url}")

            except Exception as e:
                logger.error(f"Error processing {chunk_file.name}: {e}")
                continue

        # Find deleted documents
        previous_urls = set(self.state.documents.keys())
        deleted_urls = list(previous_urls - current_urls)

        logger.info(
            f"Change detection: {len(new_files)} new, "
            f"{len(updated_files)} updated, {len(deleted_urls)} deleted"
        )

        return new_files, updated_files, deleted_urls

    def update_document_state(
        self, url: str, part_name: str, chunk_file: Path, chunk_count: int
    ) -> None:
        """Update state for a processed document.

        Args:
            url: Document URL
            part_name: Part/Appendix name
            chunk_file: Path to chunk file
            chunk_count: Number of chunks in document
        """
        content_hash = self.compute_content_hash(chunk_file)

        # Get scraped_at timestamp from chunk file if available
        try:
            with open(chunk_file, "r") as f:
                data = json.load(f)
            scraped_at = data.get("scraped_at", datetime.now().isoformat())
        except Exception:
            scraped_at = datetime.now().isoformat()

        self.state.documents[url] = DocumentState(
            url=url,
            part_name=part_name,
            last_scraped_at=scraped_at,
            content_hash=content_hash,
            chunk_count=chunk_count,
            last_indexed_at=datetime.now().isoformat(),
        )

    def mark_full_index_complete(self) -> None:
        """Mark that a full index has completed."""
        self.state.last_full_index = datetime.now().isoformat()
        self.save_state()
        logger.info("Marked full index as complete")

    def mark_incremental_index_complete(self) -> None:
        """Mark that an incremental index has completed."""
        self.state.last_incremental_index = datetime.now().isoformat()
        self.save_state()
        logger.info("Marked incremental index as complete")

    def remove_document(self, url: str) -> None:
        """Remove a document from the index state.

        Args:
            url: Document URL to remove
        """
        if url in self.state.documents:
            del self.state.documents[url]
            logger.info(f"Removed document from state: {url}")

    def get_document_state(self, url: str) -> Optional[DocumentState]:
        """Get state for a specific document.

        Args:
            url: Document URL

        Returns:
            DocumentState if found, None otherwise
        """
        return self.state.documents.get(url)

    def get_statistics(self) -> Dict:
        """Get statistics about the current index state.

        Returns:
            Dictionary with statistics
        """
        total_chunks = sum(doc.chunk_count for doc in self.state.documents.values())

        return {
            "total_documents": len(self.state.documents),
            "total_chunks": total_chunks,
            "last_full_index": self.state.last_full_index,
            "last_incremental_index": self.state.last_incremental_index,
            "oldest_document": (
                min(
                    (doc.last_indexed_at for doc in self.state.documents.values()),
                    default=None,
                )
            ),
            "newest_document": (
                max(
                    (doc.last_indexed_at for doc in self.state.documents.values()),
                    default=None,
                )
            ),
        }
