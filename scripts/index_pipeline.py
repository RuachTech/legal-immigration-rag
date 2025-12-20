#!/usr/bin/env python3
"""Main indexing pipeline orchestrator for legal immigration RAG system.

This script orchestrates the complete indexing pipeline:
1. Scraping GOV.UK Immigration Rules
2. SAC Enhancement (Summary-Augmented Chunking)
3. Embedding generation
4. Vector store loading

Supports both full and incremental indexing modes.

Usage:
    # Full indexing (all stages)
    uv run python scripts/index_pipeline.py --mode full

    # Incremental indexing (only changed documents)
    uv run python scripts/index_pipeline.py --mode incremental

    # Skip specific stages (resume from embedding)
    uv run python scripts/index_pipeline.py --skip-scrape --skip-sac

    # Dry run (validate without loading to vector store)
    uv run python scripts/index_pipeline.py --dry-run

    # Use Weaviate instead of ChromaDB
    uv run python scripts/index_pipeline.py --vector-store weaviate
"""

import argparse
import asyncio
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import dotenv

# Load environment variables
dotenv.load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_pipeline.indexing import IncrementalIndexer, ProgressTracker
from data_pipeline.indexing.progress_tracker import PipelineStage

# Configure logging
log_dir = Path("data/govuk-data/pipeline_logs")
log_dir.mkdir(parents=True, exist_ok=True)

log_file = log_dir / f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Indexing pipeline for legal immigration RAG system"
    )

    # Mode selection
    parser.add_argument(
        "--mode",
        type=str,
        choices=["full", "incremental"],
        default="full",
        help="Indexing mode: full (process all) or incremental (only changes)",
    )

    # Stage control
    parser.add_argument(
        "--skip-scrape",
        action="store_true",
        help="Skip scraping stage (use existing chunks)",
    )
    parser.add_argument(
        "--skip-sac",
        action="store_true",
        help="Skip SAC enhancement stage",
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="Skip embedding stage",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Skip vector store loading stage",
    )

    # Configuration
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/govuk-data"),
        help="Data directory (default: data/govuk-data)",
    )
    parser.add_argument(
        "--vector-store",
        type=str,
        choices=["chromadb", "weaviate"],
        default="chromadb",
        help="Vector store backend (default: chromadb)",
    )
    parser.add_argument(
        "--embedding-model",
        type=str,
        default="voyage-law-2",
        help="Embedding model (default: voyage-law-2)",
    )
    parser.add_argument(
        "--sac-model",
        type=str,
        default="gpt-4o-mini",
        help="LLM model for SAC summaries (default: gpt-4o-mini)",
    )

    # Options
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate pipeline without loading to vector store",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of documents to process (for testing)",
    )

    return parser.parse_args()


class IndexingPipeline:
    """Orchestrates the complete indexing pipeline."""

    def __init__(
        self,
        mode: str,
        data_dir: Path,
        vector_store: str,
        embedding_model: str,
        sac_model: str,
        skip_stages: Dict[str, bool],
        dry_run: bool = False,
        limit: Optional[int] = None,
    ):
        """Initialize pipeline.

        Args:
            mode: Indexing mode (full or incremental)
            data_dir: Data directory path
            vector_store: Vector store type
            embedding_model: Embedding model name
            sac_model: SAC summary model name
            skip_stages: Dict of stages to skip
            dry_run: If True, skip vector store loading
            limit: Optional limit on documents to process
        """
        self.mode = mode
        self.data_dir = data_dir
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.sac_model = sac_model
        self.skip_stages = skip_stages
        self.dry_run = dry_run
        self.limit = limit

        # Paths
        self.chunks_dir = data_dir / "chunks"
        self.chunks_sac_dir = data_dir / "chunks"  # In-place SAC enhancement
        self.chunks_embedded_dir = data_dir / "chunks-embedded"
        self.state_file = data_dir / "index_state.json"

        # Components
        self.incremental_indexer = IncrementalIndexer(self.state_file)
        self.progress_tracker = ProgressTracker()

    def run(self) -> bool:
        """Run the complete pipeline.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.progress_tracker.start_pipeline()

            logger.info(f"Pipeline Mode: {self.mode}")
            logger.info(f"Data Directory: {self.data_dir}")
            logger.info(f"Vector Store: {self.vector_store}")
            logger.info(f"Embedding Model: {self.embedding_model}")
            logger.info(f"SAC Model: {self.sac_model}")
            logger.info(f"Dry Run: {self.dry_run}")

            # Determine which files to process
            files_to_process = self._get_files_to_process()

            if not files_to_process:
                logger.warning("No files to process")
                return True

            logger.info(f"Files to process: {len(files_to_process)}")

            # Stage 1: Scraping (if needed)
            if not self.skip_stages.get("scrape", False):
                success = self._run_scraping_stage(files_to_process)
                if not success:
                    logger.error("Scraping stage failed")
                    return False

            # Stage 2: SAC Enhancement
            if not self.skip_stages.get("sac", False):
                success = self._run_sac_stage(files_to_process)
                if not success:
                    logger.error("SAC enhancement stage failed")
                    return False

            # Stage 3: Embedding
            if not self.skip_stages.get("embed", False):
                success = self._run_embedding_stage(files_to_process)
                if not success:
                    logger.error("Embedding stage failed")
                    return False

            # Stage 4: Vector Store Loading
            if not self.skip_stages.get("load", False) and not self.dry_run:
                success = self._run_loading_stage(files_to_process)
                if not success:
                    logger.error("Loading stage failed")
                    return False

            # Update index state
            self._update_index_state(files_to_process)

            # Mark completion
            if self.mode == "full":
                self.incremental_indexer.mark_full_index_complete()
            else:
                self.incremental_indexer.mark_incremental_index_complete()

            self.progress_tracker.end_pipeline()
            self.progress_tracker.print_summary()

            logger.info(f"Pipeline log saved to: {log_file}")

            return True

        except KeyboardInterrupt:
            logger.warning("\n\nPipeline interrupted by user")
            return False
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return False

    def _get_files_to_process(self) -> List[Path]:
        """Determine which files to process based on mode.

        Returns:
            List of chunk file paths to process
        """
        chunk_files = sorted(self.chunks_dir.glob("*.json"))

        # Exclude index.json
        chunk_files = [f for f in chunk_files if f.stem != "index"]

        if self.limit:
            chunk_files = chunk_files[: self.limit]

        if self.mode == "incremental":
            # Detect changes
            new_files, updated_files, deleted_urls = self.incremental_indexer.detect_changes(
                chunk_files
            )

            # Process new and updated files
            files_to_process = new_files + updated_files

            # Handle deleted documents
            for url in deleted_urls:
                logger.info(f"Deleting document from vector store: {url}")
                # TODO: Implement deletion from vector store
                self.incremental_indexer.remove_document(url)

            logger.info(
                f"Incremental mode: {len(new_files)} new, "
                f"{len(updated_files)} updated, {len(deleted_urls)} deleted"
            )

            return files_to_process
        else:
            # Full mode: process all files
            return chunk_files

    def _run_scraping_stage(self, files: List[Path]) -> bool:
        """Run scraping stage (placeholder - assumes scraping already done).

        Args:
            files: Files to process

        Returns:
            True if successful
        """
        # Note: Scraping is typically done separately via govuk_jina_scraper.py
        # This stage is a placeholder for future integration
        logger.info("Scraping stage: Using existing chunk files")
        return True

    def _run_sac_stage(self, files: List[Path]) -> bool:
        """Run SAC enhancement stage.

        Args:
            files: Files to process

        Returns:
            True if successful
        """
        self.progress_tracker.init_stage(PipelineStage.SAC_ENHANCEMENT, len(files))
        self.progress_tracker.start_stage(PipelineStage.SAC_ENHANCEMENT)

        try:
            # Build command
            cmd = [
                "uv",
                "run",
                "python",
                "data_pipeline/processing/enhance_chunks_with_sac.py",
                "--in-place",
                "--model",
                self.sac_model,
                "--skip-existing",
            ]

            if self.limit:
                cmd.extend(["--limit", str(self.limit)])

            logger.info(f"Running SAC enhancement: {' '.join(cmd)}")

            # Run SAC enhancement
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"SAC enhancement failed: {result.stderr}")
                self.progress_tracker.update_stage(
                    PipelineStage.SAC_ENHANCEMENT,
                    failed=len(files),
                    error="SAC enhancement subprocess failed",
                )
                return False

            # Parse output for progress (simplified)
            self.progress_tracker.update_stage(
                PipelineStage.SAC_ENHANCEMENT, processed=len(files)
            )

            self.progress_tracker.end_stage(PipelineStage.SAC_ENHANCEMENT)
            return True

        except Exception as e:
            logger.error(f"SAC enhancement error: {e}")
            self.progress_tracker.update_stage(
                PipelineStage.SAC_ENHANCEMENT, failed=len(files), error=str(e)
            )
            return False

    def _run_embedding_stage(self, files: List[Path]) -> bool:
        """Run embedding stage.

        Args:
            files: Files to process

        Returns:
            True if successful
        """
        self.progress_tracker.init_stage(PipelineStage.EMBEDDING, len(files))
        self.progress_tracker.start_stage(PipelineStage.EMBEDDING)

        try:
            # Build command
            cmd = [
                "uv",
                "run",
                "python",
                "scripts/embed_chunks.py",
                "--model",
                self.embedding_model,
                "--chunks-dir",
                str(self.chunks_dir),
                "--output-dir",
                str(self.chunks_embedded_dir),
            ]

            if self.limit:
                cmd.extend(["--limit", str(self.limit)])

            logger.info(f"Running embedding: {' '.join(cmd)}")

            # Run embedding
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Embedding failed: {result.stderr}")
                self.progress_tracker.update_stage(
                    PipelineStage.EMBEDDING,
                    failed=len(files),
                    error="Embedding subprocess failed",
                )
                return False

            # Parse output for progress (simplified)
            self.progress_tracker.update_stage(PipelineStage.EMBEDDING, processed=len(files))

            self.progress_tracker.end_stage(PipelineStage.EMBEDDING)
            return True

        except Exception as e:
            logger.error(f"Embedding error: {e}")
            self.progress_tracker.update_stage(
                PipelineStage.EMBEDDING, failed=len(files), error=str(e)
            )
            return False

    def _run_loading_stage(self, files: List[Path]) -> bool:
        """Run vector store loading stage.

        Args:
            files: Files to process

        Returns:
            True if successful
        """
        self.progress_tracker.init_stage(PipelineStage.VECTOR_STORE_LOADING, len(files))
        self.progress_tracker.start_stage(PipelineStage.VECTOR_STORE_LOADING)

        try:
            # Build command
            cmd = [
                "uv",
                "run",
                "python",
                "scripts/load_to_vectorstore.py",
                "--vector-store",
                self.vector_store,
                "--chunks-dir",
                str(self.chunks_embedded_dir),
            ]

            if self.limit:
                cmd.extend(["--limit", str(self.limit)])

            logger.info(f"Running vector store loading: {' '.join(cmd)}")

            # Run loading
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Loading failed: {result.stderr}")
                self.progress_tracker.update_stage(
                    PipelineStage.VECTOR_STORE_LOADING,
                    failed=len(files),
                    error="Loading subprocess failed",
                )
                return False

            # Parse output for progress (simplified)
            self.progress_tracker.update_stage(
                PipelineStage.VECTOR_STORE_LOADING, processed=len(files)
            )

            self.progress_tracker.end_stage(PipelineStage.VECTOR_STORE_LOADING)
            return True

        except Exception as e:
            logger.error(f"Loading error: {e}")
            self.progress_tracker.update_stage(
                PipelineStage.VECTOR_STORE_LOADING, failed=len(files), error=str(e)
            )
            return False

    def _update_index_state(self, files: List[Path]) -> None:
        """Update index state for processed files.

        Args:
            files: Files that were processed
        """
        logger.info("Updating index state...")

        for chunk_file in files:
            try:
                # Load chunk file to get metadata
                with open(chunk_file, "r") as f:
                    data = json.load(f)

                url = data.get("url", "")
                part_name = data.get("part_name", "")
                chunk_count = len(data.get("chunks", []))

                if url:
                    self.incremental_indexer.update_document_state(
                        url=url,
                        part_name=part_name,
                        chunk_file=chunk_file,
                        chunk_count=chunk_count,
                    )

            except Exception as e:
                logger.error(f"Failed to update state for {chunk_file.name}: {e}")

        # Save state
        self.incremental_indexer.save_state()

        # Print statistics
        stats = self.incremental_indexer.get_statistics()
        logger.info(f"Index state updated: {stats['total_documents']} documents indexed")


def main():
    """Main entry point."""
    args = parse_args()

    logger.info("=" * 60)
    logger.info("LEGAL IMMIGRATION RAG - INDEXING PIPELINE")
    logger.info("=" * 60)

    # Build skip_stages dict
    skip_stages = {
        "scrape": args.skip_scrape,
        "sac": args.skip_sac,
        "embed": args.skip_embed,
        "load": args.skip_load,
    }

    # Initialize pipeline
    pipeline = IndexingPipeline(
        mode=args.mode,
        data_dir=args.data_dir,
        vector_store=args.vector_store,
        embedding_model=args.embedding_model,
        sac_model=args.sac_model,
        skip_stages=skip_stages,
        dry_run=args.dry_run,
        limit=args.limit,
    )

    # Run pipeline
    success = pipeline.run()

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
