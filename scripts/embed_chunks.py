#!/usr/bin/env python3
"""Batch embedding script for legal immigration chunks.

This script processes all chunks in the chunks directory and generates
embeddings using voyage-law-2 (recommended) or LEGAL-BERT.

Usage:
    uv run python scripts/embed_chunks.py
    uv run python scripts/embed_chunks.py --model voyage-law-2 --batch-size 128
    uv run python scripts/embed_chunks.py --model nlpaueb/legal-bert-base-uncased
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_pipeline.processing.embedder import LegalEmbedder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Embed legal immigration chunks using voyage-law-2 or LEGAL-BERT"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="voyage-law-2",
        help="Embedding model to use (default: voyage-law-2)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=128,
        help="Batch size for embedding (default: 128)"
    )
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        default=Path("data/govuk-data/chunks"),
        help="Directory containing chunk files (default: data/govuk-data/chunks)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/govuk-data/chunks-embedded"),
        help="Output directory for embedded chunks (default: data/govuk-data/chunks-embedded)"
    )
    parser.add_argument(
        "--text-field",
        type=str,
        default="augmented_text",
        help="Field name containing text to embed (default: augmented_text)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of files to process (for testing)"
    )

    return parser.parse_args()


def embed_all_chunks(
    embedder: LegalEmbedder,
    chunks_dir: Path,
    output_dir: Path,
    text_field: str = "augmented_text",
    limit: int = None
) -> Dict[str, any]:
    """Embed all chunks in the chunks directory.

    Args:
        embedder: LegalEmbedder instance
        chunks_dir: Directory containing chunk JSON files
        output_dir: Output directory for embedded chunks
        text_field: Field name containing text to embed
        limit: Optional limit on number of files to process

    Returns:
        Dictionary with embedding statistics
    """
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get all chunk files
    chunk_files = sorted(chunks_dir.glob("*.json"))

    if limit:
        chunk_files = chunk_files[:limit]
        logger.info(f"Processing limited to {limit} files")

    logger.info(f"Found {len(chunk_files)} chunk files to process")

    # Statistics
    stats = {
        "total_files": len(chunk_files),
        "processed_files": 0,
        "skipped_files": 0,
        "total_chunks": 0,
        "embedded_chunks": 0,
        "failed_chunks": 0,
        "failed_chunk_ids": []
    }

    # Process each file
    for i, chunk_file in enumerate(chunk_files, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"Processing {i}/{len(chunk_files)}: {chunk_file.name}")
        logger.info(f"{'='*60}")

        try:
            # Load chunks
            with open(chunk_file, "r") as f:
                data = json.load(f)

            if "chunks" not in data or not data["chunks"]:
                logger.warning("  Skipping (no chunks found)")
                stats["skipped_files"] += 1
                continue

            chunks = data["chunks"]
            stats["total_chunks"] += len(chunks)

            logger.info(f"  Loaded {len(chunks)} chunks")

            # Embed chunks
            embedded_chunks, failed_ids = embedder.embed_chunks(
                chunks,
                text_field=text_field
            )

            stats["embedded_chunks"] += len(embedded_chunks)
            stats["failed_chunks"] += len(failed_ids)
            stats["failed_chunk_ids"].extend(failed_ids)

            logger.info(
                f"  ✓ Embedded: {len(embedded_chunks)}/{len(chunks)} chunks "
                f"({len(embedded_chunks)/len(chunks)*100:.1f}%)"
            )

            if failed_ids:
                logger.warning(f"  ✗ Failed chunk IDs: {failed_ids}")

            # Save embedded chunks
            output_data = {
                **data,
                "chunks": embedded_chunks,
                "embedding_metadata": embedder.get_model_info()
            }

            output_file = output_dir / chunk_file.name
            with open(output_file, "w") as f:
                json.dump(output_data, f, indent=2)

            logger.info(f"  💾 Saved to: {output_file}")
            stats["processed_files"] += 1

        except Exception as e:
            logger.error(f"  ✗ Error processing {chunk_file.name}: {e}")
            stats["skipped_files"] += 1
            continue

    return stats


def print_summary(stats: Dict[str, any], embedder: LegalEmbedder):
    """Print embedding summary statistics.

    Args:
        stats: Statistics dictionary
        embedder: LegalEmbedder instance
    """
    logger.info(f"\n{'='*60}")
    logger.info("EMBEDDING SUMMARY")
    logger.info(f"{'='*60}")

    # Model info
    model_info = embedder.get_model_info()
    logger.info("\nModel Configuration:")
    logger.info(f"  Primary Model: {model_info['primary_model']}")
    logger.info(f"  Fallback Model: {model_info.get('fallback_model', 'None')}")
    logger.info(f"  Embedding Dimension: {model_info['embedding_dimension']}")
    logger.info(f"  Batch Size: {model_info['batch_size']}")

    # File statistics
    logger.info("\nFile Statistics:")
    logger.info(f"  Total Files: {stats['total_files']}")
    logger.info(f"  Processed: {stats['processed_files']}")
    logger.info(f"  Skipped: {stats['skipped_files']}")

    # Chunk statistics
    success_rate = (
        (stats['embedded_chunks'] / stats['total_chunks'] * 100)
        if stats['total_chunks'] > 0 else 0
    )
    logger.info("\nChunk Statistics:")
    logger.info(f"  Total Chunks: {stats['total_chunks']}")
    logger.info(f"  Successfully Embedded: {stats['embedded_chunks']}")
    logger.info(f"  Failed: {stats['failed_chunks']}")
    logger.info(f"  Success Rate: {success_rate:.2f}%")

    if stats['failed_chunk_ids']:
        logger.warning(f"\nFailed Chunk IDs ({len(stats['failed_chunk_ids'])}):")
        for chunk_id in stats['failed_chunk_ids'][:10]:  # Show first 10
            logger.warning(f"  - {chunk_id}")
        if len(stats['failed_chunk_ids']) > 10:
            logger.warning(f"  ... and {len(stats['failed_chunk_ids']) - 10} more")

    logger.info(f"\n{'='*60}")
    logger.info("✓ Embedding complete!")
    logger.info(f"{'='*60}\n")


def main():
    """Main entry point."""
    args = parse_args()

    logger.info("Legal Immigration Chunk Embedder")
    logger.info(f"Chunks Directory: {args.chunks_dir}")
    logger.info(f"Output Directory: {args.output_dir}")
    logger.info(f"Model: {args.model}")
    logger.info(f"Batch Size: {args.batch_size}")

    # Validate chunks directory
    if not args.chunks_dir.exists():
        logger.error(f"Chunks directory not found: {args.chunks_dir}")
        sys.exit(1)

    # Initialize embedder
    try:
        logger.info("\nInitializing embedder...")
        embedder = LegalEmbedder(
            model_name=args.model,
            batch_size=args.batch_size
        )
        logger.info("✓ Embedder initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize embedder: {e}")
        sys.exit(1)

    # Embed all chunks
    try:
        stats = embed_all_chunks(
            embedder=embedder,
            chunks_dir=args.chunks_dir,
            output_dir=args.output_dir,
            text_field=args.text_field,
            limit=args.limit
        )
    except KeyboardInterrupt:
        logger.warning("\n\nEmbedding interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        sys.exit(1)

    # Print summary
    print_summary(stats, embedder)

    # Exit with error code if there were failures
    if stats['failed_chunks'] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
