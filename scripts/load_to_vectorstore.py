#!/usr/bin/env python3
"""Load embedded chunks into vector store (ChromaDB or Weaviate).

This script reads embedded chunk files and loads them into the configured
vector store. Supports both ChromaDB (development) and Weaviate (production).

Usage:
    # Load to ChromaDB (default)
    uv run python scripts/load_to_vectorstore.py

    # Load to Weaviate
    uv run python scripts/load_to_vectorstore.py --vector-store weaviate

    # Incremental loading (skip already indexed)
    uv run python scripts/load_to_vectorstore.py --incremental

    # Dry run (validate without loading)
    uv run python scripts/load_to_vectorstore.py --dry-run
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

import dotenv

# Load environment variables
dotenv.load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from storage import Chunk, ChunkMetadata
from storage.factories import create_vector_store

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Load embedded chunks into vector store"
    )
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        default=Path("data/govuk-data/chunks-embedded"),
        help="Directory containing embedded chunk files",
    )
    parser.add_argument(
        "--vector-store",
        type=str,
        choices=["chromadb", "weaviate"],
        default="chromadb",
        help="Vector store backend to use (default: chromadb)",
    )
    parser.add_argument(
        "--collection-name",
        type=str,
        default="immigration_chunks",
        help="Name of the vector store collection (default: immigration_chunks)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Batch size for loading chunks (default: 100)",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Skip chunks that are already indexed",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate chunks without loading to vector store",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of files to process (for testing)",
    )

    return parser.parse_args()


def load_chunk_file(chunk_file: Path) -> Optional[Dict]:
    """Load and validate a chunk file.

    Args:
        chunk_file: Path to chunk JSON file

    Returns:
        Chunk file data or None if invalid
    """
    try:
        with open(chunk_file, "r") as f:
            data = json.load(f)

        # Validate structure
        if "chunks" not in data:
            logger.warning(f"No 'chunks' field in {chunk_file.name}")
            return None

        if not data["chunks"]:
            logger.warning(f"Empty chunks array in {chunk_file.name}")
            return None

        return data

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {chunk_file.name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading {chunk_file.name}: {e}")
        return None


def convert_to_chunk_object(chunk_data: Dict, document_id: str) -> Optional[Chunk]:
    """Convert chunk data to Chunk object.

    Args:
        chunk_data: Raw chunk data from JSON
        document_id: Document identifier

    Returns:
        Chunk object or None if conversion fails
    """
    try:
        metadata_dict = chunk_data.get("metadata", {})
        
        # Create ChunkMetadata (ensure no None values for ChromaDB)
        chunk_metadata = ChunkMetadata(
            source=metadata_dict.get("source") or "",
            part=metadata_dict.get("part") or "",
            section=metadata_dict.get("section_id") or metadata_dict.get("section") or "",
            topic=metadata_dict.get("topic") or "",
            url=metadata_dict.get("url") or "",
            parent_section=metadata_dict.get("parent_section") or None,  # None is OK here
            hierarchy_level=int(metadata_dict.get("hierarchy_level") or 0),
        )

        # Generate unique chunk ID from document_id, section, and index
        section_id = metadata_dict.get("section_id", "unknown")
        # Use a hash of the content to ensure uniqueness within the same section
        import hashlib
        content_hash = hashlib.md5(chunk_data.get("text", "").encode()).hexdigest()[:8]
        chunk_id = f"{document_id}_{section_id}_{content_hash}".replace(" ", "_").replace("/", "_")

        # Get embedding
        embedding = chunk_data.get("embedding")
        if not embedding:
            logger.warning(f"No embedding found for chunk {chunk_id}")
            return None

        # Create Chunk object
        chunk = Chunk(
            id=chunk_id,
            document_id=document_id,
            content=chunk_data.get("text", ""),
            summary=chunk_data.get("summary", ""),
            embedding=embedding,
            metadata=chunk_metadata,
        )

        return chunk

    except Exception as e:
        logger.error(f"Error converting chunk to object: {e}")
        return None


def load_chunks_to_vectorstore(
    chunks_dir: Path,
    vector_store_type: str,
    collection_name: str,
    batch_size: int,
    incremental: bool,
    dry_run: bool,
    limit: Optional[int] = None,
) -> Dict:
    """Load all chunks into vector store.

    Args:
        chunks_dir: Directory containing chunk files
        vector_store_type: Type of vector store (chromadb or weaviate)
        collection_name: Name of the collection
        batch_size: Batch size for loading
        incremental: Whether to skip already-indexed chunks
        dry_run: If True, validate without loading
        limit: Optional limit on number of files

    Returns:
        Statistics dictionary
    """
    # Get all chunk files
    chunk_files = sorted(chunks_dir.glob("*.json"))

    if limit:
        chunk_files = chunk_files[:limit]
        logger.info(f"Processing limited to {limit} files")

    logger.info(f"Found {len(chunk_files)} chunk files")

    # Initialize vector store (unless dry run)
    vector_store = None
    if not dry_run:
        try:
            logger.info(f"Initializing {vector_store_type} vector store...")
            vector_store = create_vector_store(
                store_type=vector_store_type, collection_name=collection_name
            )
            logger.info(f"✓ Vector store initialized: {vector_store_type}")
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            raise

    # Statistics
    stats = {
        "total_files": len(chunk_files),
        "processed_files": 0,
        "skipped_files": 0,
        "total_chunks": 0,
        "loaded_chunks": 0,
        "failed_chunks": 0,
        "validation_errors": [],
    }

    # Process files in batches
    batch_chunks: List[Chunk] = []

    for i, chunk_file in enumerate(chunk_files, 1):
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Processing {i}/{len(chunk_files)}: {chunk_file.name}")
        logger.info(f"{'=' * 60}")

        # Load chunk file
        data = load_chunk_file(chunk_file)
        if not data:
            stats["skipped_files"] += 1
            continue

        chunks_data = data["chunks"]
        document_id = chunk_file.stem
        url = data.get("url", "")

        logger.info(f"  Document: {url}")
        logger.info(f"  Chunks: {len(chunks_data)}")

        stats["total_chunks"] += len(chunks_data)

        # Convert chunks to Chunk objects
        for idx, chunk_data in enumerate(chunks_data):
            chunk_obj = convert_to_chunk_object(chunk_data, document_id)

            if chunk_obj is None:
                stats["failed_chunks"] += 1
                section_id = chunk_data.get("metadata", {}).get("section_id", f"index_{idx}")
                has_embedding = "embedding" in chunk_data
                stats["validation_errors"].append(
                    f"{chunk_file.name}:{section_id} - embedding={'yes' if has_embedding else 'NO'}"
                )
                continue

            batch_chunks.append(chunk_obj)

            # Load batch when it reaches batch_size
            if len(batch_chunks) >= batch_size:
                if not dry_run:
                    try:
                        vector_store.add_chunks(batch_chunks)
                        logger.info(f"  ✓ Loaded batch of {len(batch_chunks)} chunks")
                        stats["loaded_chunks"] += len(batch_chunks)
                    except Exception as e:
                        logger.error(f"  ✗ Failed to load batch: {e}")
                        stats["failed_chunks"] += len(batch_chunks)
                else:
                    logger.info(f"  [DRY RUN] Would load {len(batch_chunks)} chunks")
                    stats["loaded_chunks"] += len(batch_chunks)

                batch_chunks = []

        stats["processed_files"] += 1

    # Load remaining chunks
    if batch_chunks:
        if not dry_run:
            try:
                vector_store.add_chunks(batch_chunks)
                logger.info(f"  ✓ Loaded final batch of {len(batch_chunks)} chunks")
                stats["loaded_chunks"] += len(batch_chunks)
            except Exception as e:
                logger.error(f"  ✗ Failed to load final batch: {e}")
                stats["failed_chunks"] += len(batch_chunks)
        else:
            logger.info(f"  [DRY RUN] Would load {len(batch_chunks)} chunks")
            stats["loaded_chunks"] += len(batch_chunks)

    return stats


def print_summary(stats: Dict, dry_run: bool):
    """Print loading summary.

    Args:
        stats: Statistics dictionary
        dry_run: Whether this was a dry run
    """
    logger.info(f"\n{'=' * 60}")
    logger.info("LOADING SUMMARY" if not dry_run else "VALIDATION SUMMARY (DRY RUN)")
    logger.info(f"{'=' * 60}")

    logger.info(f"\nFile Statistics:")
    logger.info(f"  Total Files: {stats['total_files']}")
    logger.info(f"  Processed: {stats['processed_files']}")
    logger.info(f"  Skipped: {stats['skipped_files']}")

    success_rate = (
        (stats["loaded_chunks"] / stats["total_chunks"] * 100)
        if stats["total_chunks"] > 0
        else 0
    )

    logger.info(f"\nChunk Statistics:")
    logger.info(f"  Total Chunks: {stats['total_chunks']}")
    logger.info(
        f"  {'Loaded' if not dry_run else 'Valid'}: {stats['loaded_chunks']}"
    )
    logger.info(f"  Failed: {stats['failed_chunks']}")
    logger.info(f"  Success Rate: {success_rate:.2f}%")

    if stats["validation_errors"]:
        logger.warning(f"\nValidation Errors ({len(stats['validation_errors'])}):")
        for error in stats["validation_errors"][:10]:  # Show first 10
            logger.warning(f"  - {error}")
        if len(stats["validation_errors"]) > 10:
            logger.warning(
                f"  ... and {len(stats['validation_errors']) - 10} more"
            )

    logger.info(f"\n{'=' * 60}")
    if not dry_run:
        logger.info("✓ Loading complete!")
    else:
        logger.info("✓ Validation complete!")
    logger.info(f"{'=' * 60}\n")


def main():
    """Main entry point."""
    args = parse_args()

    logger.info("Vector Store Loader")
    logger.info(f"Chunks Directory: {args.chunks_dir}")
    logger.info(f"Vector Store: {args.vector_store}")
    logger.info(f"Collection: {args.collection_name}")
    logger.info(f"Batch Size: {args.batch_size}")
    logger.info(f"Incremental: {args.incremental}")
    logger.info(f"Dry Run: {args.dry_run}")

    # Validate chunks directory
    if not args.chunks_dir.exists():
        logger.error(f"Chunks directory not found: {args.chunks_dir}")
        sys.exit(1)

    # Load chunks
    try:
        stats = load_chunks_to_vectorstore(
            chunks_dir=args.chunks_dir,
            vector_store_type=args.vector_store,
            collection_name=args.collection_name,
            batch_size=args.batch_size,
            incremental=args.incremental,
            dry_run=args.dry_run,
            limit=args.limit,
        )
    except KeyboardInterrupt:
        logger.warning("\n\nLoading interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Loading failed: {e}")
        sys.exit(1)

    # Print summary
    print_summary(stats, args.dry_run)

    # Exit with error code if there were failures
    if stats["failed_chunks"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
