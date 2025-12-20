"""Progress tracking utilities for the indexing pipeline.

Provides real-time progress tracking with rich console output and detailed logging.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Pipeline stages for progress tracking."""

    SCRAPING = "Scraping"
    SAC_ENHANCEMENT = "SAC Enhancement"
    EMBEDDING = "Embedding"
    VECTOR_STORE_LOADING = "Vector Store Loading"


@dataclass
class StageProgress:
    """Progress information for a single pipeline stage."""

    stage: PipelineStage
    total_items: int
    processed_items: int = 0
    failed_items: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    errors: List[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        """Check if stage is complete."""
        return self.processed_items + self.failed_items >= self.total_items

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        total = self.processed_items + self.failed_items
        if total == 0:
            return 0.0
        return (self.processed_items / total) * 100

    @property
    def elapsed_time(self) -> Optional[float]:
        """Get elapsed time in seconds."""
        if self.start_time is None:
            return None
        end = self.end_time if self.end_time else time.time()
        return end - self.start_time

    @property
    def items_per_second(self) -> Optional[float]:
        """Calculate processing rate."""
        elapsed = self.elapsed_time
        if elapsed is None or elapsed == 0:
            return None
        return self.processed_items / elapsed

    @property
    def estimated_time_remaining(self) -> Optional[float]:
        """Estimate time remaining in seconds."""
        rate = self.items_per_second
        if rate is None or rate == 0:
            return None
        remaining_items = self.total_items - (self.processed_items + self.failed_items)
        return remaining_items / rate


class ProgressTracker:
    """Tracks progress across all pipeline stages.

    Provides real-time progress updates, statistics, and logging.
    """

    def __init__(self):
        """Initialize progress tracker."""
        self.stages: Dict[PipelineStage, StageProgress] = {}
        self.pipeline_start_time: Optional[float] = None
        self.pipeline_end_time: Optional[float] = None

    def start_pipeline(self) -> None:
        """Mark the start of the pipeline."""
        self.pipeline_start_time = time.time()
        logger.info("=" * 60)
        logger.info("INDEXING PIPELINE STARTED")
        logger.info(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)

    def end_pipeline(self) -> None:
        """Mark the end of the pipeline."""
        self.pipeline_end_time = time.time()
        logger.info("=" * 60)
        logger.info("INDEXING PIPELINE COMPLETED")
        logger.info(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        if self.pipeline_start_time:
            elapsed = self.pipeline_end_time - self.pipeline_start_time
            logger.info(f"Total time: {self._format_duration(elapsed)}")
        logger.info("=" * 60)

    def init_stage(self, stage: PipelineStage, total_items: int) -> None:
        """Initialize a new stage.

        Args:
            stage: The pipeline stage
            total_items: Total number of items to process
        """
        self.stages[stage] = StageProgress(stage=stage, total_items=total_items)
        logger.info("")
        logger.info(f"{'=' * 60}")
        logger.info(f"STAGE: {stage.value}")
        logger.info(f"Total items: {total_items}")
        logger.info(f"{'=' * 60}")

    def start_stage(self, stage: PipelineStage) -> None:
        """Mark the start of a stage.

        Args:
            stage: The pipeline stage
        """
        if stage not in self.stages:
            raise ValueError(f"Stage {stage} not initialized")

        self.stages[stage].start_time = time.time()
        logger.info(f"Starting {stage.value}...")

    def update_stage(
        self, stage: PipelineStage, processed: int = 0, failed: int = 0, error: Optional[str] = None
    ) -> None:
        """Update progress for a stage.

        Args:
            stage: The pipeline stage
            processed: Number of successfully processed items to add
            failed: Number of failed items to add
            error: Optional error message to log
        """
        if stage not in self.stages:
            raise ValueError(f"Stage {stage} not initialized")

        progress = self.stages[stage]
        progress.processed_items += processed
        progress.failed_items += failed

        if error:
            progress.errors.append(error)
            logger.error(f"[{stage.value}] {error}")

        # Log progress update
        total_done = progress.processed_items + progress.failed_items
        percentage = (total_done / progress.total_items * 100) if progress.total_items > 0 else 0

        logger.info(
            f"[{stage.value}] Progress: {total_done}/{progress.total_items} "
            f"({percentage:.1f}%) - Success: {progress.processed_items}, "
            f"Failed: {progress.failed_items}"
        )

        # Show rate and ETA if available
        if progress.items_per_second:
            eta = progress.estimated_time_remaining
            eta_str = self._format_duration(eta) if eta else "N/A"
            logger.info(
                f"[{stage.value}] Rate: {progress.items_per_second:.2f} items/sec, "
                f"ETA: {eta_str}"
            )

    def end_stage(self, stage: PipelineStage) -> None:
        """Mark the end of a stage.

        Args:
            stage: The pipeline stage
        """
        if stage not in self.stages:
            raise ValueError(f"Stage {stage} not initialized")

        progress = self.stages[stage]
        progress.end_time = time.time()

        logger.info("")
        logger.info(f"{'=' * 60}")
        logger.info(f"STAGE COMPLETE: {stage.value}")
        logger.info(f"Processed: {progress.processed_items}/{progress.total_items}")
        logger.info(f"Failed: {progress.failed_items}")
        logger.info(f"Success rate: {progress.success_rate:.1f}%")

        if progress.elapsed_time:
            logger.info(f"Duration: {self._format_duration(progress.elapsed_time)}")

        if progress.errors:
            logger.warning(f"Errors encountered: {len(progress.errors)}")

        logger.info(f"{'=' * 60}")

    def get_stage_progress(self, stage: PipelineStage) -> Optional[StageProgress]:
        """Get progress for a specific stage.

        Args:
            stage: The pipeline stage

        Returns:
            StageProgress if stage exists, None otherwise
        """
        return self.stages.get(stage)

    def get_summary(self) -> Dict:
        """Get summary statistics for all stages.

        Returns:
            Dictionary with summary statistics
        """
        total_processed = sum(s.processed_items for s in self.stages.values())
        total_failed = sum(s.failed_items for s in self.stages.values())
        total_items = sum(s.total_items for s in self.stages.values())

        pipeline_duration = None
        if self.pipeline_start_time:
            end = self.pipeline_end_time if self.pipeline_end_time else time.time()
            pipeline_duration = end - self.pipeline_start_time

        return {
            "total_stages": len(self.stages),
            "total_items": total_items,
            "total_processed": total_processed,
            "total_failed": total_failed,
            "overall_success_rate": (
                (total_processed / (total_processed + total_failed) * 100)
                if (total_processed + total_failed) > 0
                else 0
            ),
            "pipeline_duration": pipeline_duration,
            "stages": {
                stage.value: {
                    "total": progress.total_items,
                    "processed": progress.processed_items,
                    "failed": progress.failed_items,
                    "success_rate": progress.success_rate,
                    "duration": progress.elapsed_time,
                }
                for stage, progress in self.stages.items()
            },
        }

    def print_summary(self) -> None:
        """Print a formatted summary of the pipeline execution."""
        summary = self.get_summary()

        logger.info("")
        logger.info("=" * 60)
        logger.info("PIPELINE SUMMARY")
        logger.info("=" * 60)

        if summary["pipeline_duration"]:
            logger.info(f"Total Duration: {self._format_duration(summary['pipeline_duration'])}")

        logger.info(f"Total Items Processed: {summary['total_processed']}")
        logger.info(f"Total Items Failed: {summary['total_failed']}")
        logger.info(f"Overall Success Rate: {summary['overall_success_rate']:.1f}%")

        logger.info("")
        logger.info("Stage Breakdown:")
        logger.info("-" * 60)

        for stage_name, stage_data in summary["stages"].items():
            logger.info(f"\n{stage_name}:")
            logger.info(f"  Processed: {stage_data['processed']}/{stage_data['total']}")
            logger.info(f"  Failed: {stage_data['failed']}")
            logger.info(f"  Success Rate: {stage_data['success_rate']:.1f}%")
            if stage_data["duration"]:
                logger.info(f"  Duration: {self._format_duration(stage_data['duration'])}")

        logger.info("")
        logger.info("=" * 60)

    @staticmethod
    def _format_duration(seconds: Optional[float]) -> str:
        """Format duration in human-readable format.

        Args:
            seconds: Duration in seconds

        Returns:
            Formatted duration string
        """
        if seconds is None:
            return "N/A"

        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"
