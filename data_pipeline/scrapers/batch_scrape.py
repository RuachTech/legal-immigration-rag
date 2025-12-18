"""
Batch Scraper for GOV.UK Immigration Rules

This script orchestrates the ingestion of all Immigration Rules pages
by reading URLs from the JSON inventory and using the Jina scraper.

Pipeline Stage: Data Ingestion
    1. Load URL inventory from data/immigration_rules_urls.json
    2. Filter/select URLs to scrape (by type, specific slugs, etc.)
    3. Scrape each URL with rate limiting (20 RPM)
    4. Save raw markdown and parsed chunks to govuk-data/

Features:
    - Resume capability: Skip already-scraped URLs
    - Filtering: Scrape by type (appendix, part) or specific slugs
    - Progress tracking: Shows completion status
    - Error handling: Logs failures, continues with remaining URLs
    - Dry-run mode: Preview what would be scraped

Usage:
    # Scrape all URLs
    python batch_scrape.py

    # Scrape only appendices
    python batch_scrape.py --type appendix

    # Scrape specific pages
    python batch_scrape.py --slugs appendix-fm,appendix-skilled-worker

    # Resume (skip already scraped)
    python batch_scrape.py --resume

    # Dry run (preview only)
    python batch_scrape.py --dry-run

    # Limit number of pages
    python batch_scrape.py --limit 5

Environment Variables:
    JINA_API_KEY: Required. Your Jina Reader API key.

Output:
    data/govuk-data/raw/{slug}.md      - Raw markdown from Jina
    data/govuk-data/chunks/{slug}.json - Parsed chunks with metadata
    data/govuk-data/index.json         - Summary of all scraped content
    data/govuk-data/scrape_log.json    - Scrape history for resume capability
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from govuk_jina_scraper import GovUKJinaScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
GOVUK_DATA_DIR = DATA_DIR / "govuk-data"
URLS_FILE = DATA_DIR / "immigration_rules_urls.json"
SCRAPE_LOG_FILE = GOVUK_DATA_DIR / "scrape_log.json"


@dataclass
class ScrapeResult:
    """Result of scraping a single URL."""

    url: str
    slug: str
    title: str
    status: str  # 'success', 'failed', 'skipped'
    chunk_count: int
    error: Optional[str]
    scraped_at: str
    duration_seconds: float


@dataclass
class BatchScrapeReport:
    """Summary report for a batch scrape operation."""

    started_at: str
    completed_at: str
    total_urls: int
    scraped: int
    failed: int
    skipped: int
    total_chunks: int
    results: List[dict]


class ScrapeLog:
    """
    Tracks scraping history for resume capability.

    Persists to govuk-data/scrape_log.json
    """

    def __init__(self, log_file: Path = SCRAPE_LOG_FILE):
        self.log_file = log_file
        self.scraped_urls: Set[str] = set()
        self.history: List[dict] = []
        self._load()

    def _load(self):
        """Load existing log from disk."""
        if self.log_file.exists():
            try:
                data = json.loads(self.log_file.read_text())
                self.scraped_urls = set(data.get("scraped_urls", []))
                self.history = data.get("history", [])
                logger.info(f"Loaded scrape log: {len(self.scraped_urls)} previously scraped URLs")
            except Exception as e:
                logger.warning(f"Failed to load scrape log: {e}")

    def _save(self):
        """Save log to disk."""
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "scraped_urls": list(self.scraped_urls),
            "history": self.history,
            "last_updated": datetime.now().isoformat(),
        }
        self.log_file.write_text(json.dumps(data, indent=2))

    def is_scraped(self, url: str) -> bool:
        """Check if URL has been successfully scraped."""
        return url in self.scraped_urls

    def mark_scraped(self, result: ScrapeResult):
        """Mark a URL as scraped and save."""
        if result.status == "success":
            self.scraped_urls.add(result.url)

        self.history.append(asdict(result))
        self._save()

    def get_stats(self) -> dict:
        """Get scraping statistics."""
        return {"total_scraped": len(self.scraped_urls), "history_entries": len(self.history)}


def load_urls(
    urls_file: Path = URLS_FILE,
    url_types: Optional[List[str]] = None,
    slugs: Optional[List[str]] = None,
    exclude_slugs: Optional[List[str]] = None,
) -> List[dict]:
    """
    Load and filter URLs from the JSON inventory.

    Args:
        urls_file: Path to immigration_rules_urls.json
        url_types: Filter by type(s): 'part', 'appendix', 'introduction', etc.
        slugs: Only include these specific slugs
        exclude_slugs: Exclude these specific slugs

    Returns:
        List of URL entries (dict with url, title, type, slug)
    """
    if not urls_file.exists():
        raise FileNotFoundError(
            f"URL inventory not found: {urls_file}\n"
            f"Run 'python get_govuk_urls.py' first to generate it."
        )

    data = json.loads(urls_file.read_text())
    urls = data.get("urls", [])

    logger.info(f"Loaded {len(urls)} URLs from inventory")

    # Filter by type
    if url_types:
        urls = [u for u in urls if u.get("type") in url_types]
        logger.info(f"Filtered to {len(urls)} URLs by type: {url_types}")

    # Filter by specific slugs
    if slugs:
        slugs_set = set(slugs)
        urls = [u for u in urls if u.get("slug") in slugs_set]
        logger.info(f"Filtered to {len(urls)} URLs by slugs")

    # Exclude specific slugs
    if exclude_slugs:
        exclude_set = set(exclude_slugs)
        urls = [u for u in urls if u.get("slug") not in exclude_set]
        logger.info(f"Excluded {len(exclude_slugs)} slugs, {len(urls)} remaining")

    return urls


async def scrape_url(
    scraper: GovUKJinaScraper, url_entry: dict, scrape_log: ScrapeLog, resume: bool = False
) -> ScrapeResult:
    """
    Scrape a single URL and record the result.

    Args:
        scraper: GovUKJinaScraper instance
        url_entry: Dict with url, title, type, slug
        scrape_log: ScrapeLog for tracking
        resume: If True, skip already-scraped URLs

    Returns:
        ScrapeResult with status and details
    """
    url = url_entry["url"]
    slug = url_entry["slug"]
    title = url_entry["title"]

    # Check if already scraped (resume mode)
    if resume and scrape_log.is_scraped(url):
        logger.info(f"Skipping (already scraped): {slug}")
        return ScrapeResult(
            url=url,
            slug=slug,
            title=title,
            status="skipped",
            chunk_count=0,
            error=None,
            scraped_at=datetime.now().isoformat(),
            duration_seconds=0.0,
        )

    # Scrape the URL
    start_time = datetime.now()

    try:
        chunks = await scraper.scrape_page(url, part_name=title)

        duration = (datetime.now() - start_time).total_seconds()

        result = ScrapeResult(
            url=url,
            slug=slug,
            title=title,
            status="success",
            chunk_count=len(chunks),
            error=None,
            scraped_at=datetime.now().isoformat(),
            duration_seconds=duration,
        )

        logger.info(f"✓ Scraped {slug}: {len(chunks)} chunks ({duration:.1f}s)")

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()

        result = ScrapeResult(
            url=url,
            slug=slug,
            title=title,
            status="failed",
            chunk_count=0,
            error=str(e),
            scraped_at=datetime.now().isoformat(),
            duration_seconds=duration,
        )

        logger.error(f"✗ Failed {slug}: {e}")

    # Record result
    scrape_log.mark_scraped(result)

    return result


async def batch_scrape(
    api_key: str,
    url_types: Optional[List[str]] = None,
    slugs: Optional[List[str]] = None,
    exclude_slugs: Optional[List[str]] = None,
    resume: bool = False,
    limit: Optional[int] = None,
    dry_run: bool = False,
) -> BatchScrapeReport:
    """
    Scrape multiple URLs from the inventory.

    Args:
        api_key: Jina Reader API key
        url_types: Filter by type(s)
        slugs: Only scrape these slugs
        exclude_slugs: Skip these slugs
        resume: Skip already-scraped URLs
        limit: Maximum number of URLs to scrape
        dry_run: If True, only preview what would be scraped

    Returns:
        BatchScrapeReport with summary and results
    """
    started_at = datetime.now().isoformat()

    # Load URLs
    urls = load_urls(url_types=url_types, slugs=slugs, exclude_slugs=exclude_slugs)

    # Apply limit
    if limit:
        urls = urls[:limit]
        logger.info(f"Limited to {len(urls)} URLs")

    # Initialize scrape log
    scrape_log = ScrapeLog()

    # Filter out already scraped if resuming
    if resume:
        original_count = len(urls)
        urls = [u for u in urls if not scrape_log.is_scraped(u["url"])]
        skipped = original_count - len(urls)
        if skipped:
            logger.info(f"Resume mode: skipping {skipped} already-scraped URLs")

    # Dry run - just preview
    if dry_run:
        logger.info("\n=== DRY RUN - Preview Only ===")
        logger.info(f"Would scrape {len(urls)} URLs:\n")

        for i, url_entry in enumerate(urls, 1):
            logger.info(f"  {i:3}. [{url_entry['type']:12}] {url_entry['slug']}")

        return BatchScrapeReport(
            started_at=started_at,
            completed_at=datetime.now().isoformat(),
            total_urls=len(urls),
            scraped=0,
            failed=0,
            skipped=len(urls),
            total_chunks=0,
            results=[],
        )

    # Scrape URLs
    results: List[ScrapeResult] = []
    total_chunks = 0

    logger.info(f"\n{'='*60}")
    logger.info(f"Starting batch scrape of {len(urls)} URLs")
    logger.info("Rate limit: 20 RPM (3 seconds between requests)")
    logger.info(f"Estimated time: ~{len(urls) * 3 / 60:.1f} minutes")
    logger.info(f"{'='*60}\n")

    async with GovUKJinaScraper(
        api_key=api_key, save_results=True, data_dir=GOVUK_DATA_DIR
    ) as scraper:

        for i, url_entry in enumerate(urls, 1):
            logger.info(f"[{i}/{len(urls)}] Scraping: {url_entry['slug']}")

            result = await scrape_url(
                scraper=scraper, url_entry=url_entry, scrape_log=scrape_log, resume=resume
            )

            results.append(result)

            if result.status == "success":
                total_chunks += result.chunk_count

    # Generate report
    completed_at = datetime.now().isoformat()

    scraped_count = sum(1 for r in results if r.status == "success")
    failed_count = sum(1 for r in results if r.status == "failed")
    skipped_count = sum(1 for r in results if r.status == "skipped")

    report = BatchScrapeReport(
        started_at=started_at,
        completed_at=completed_at,
        total_urls=len(urls),
        scraped=scraped_count,
        failed=failed_count,
        skipped=skipped_count,
        total_chunks=total_chunks,
        results=[asdict(r) for r in results],
    )

    # Save report
    report_file = GOVUK_DATA_DIR / f"batch_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    report_file.write_text(json.dumps(asdict(report), indent=2))
    logger.info(f"Saved report: {report_file}")

    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info("BATCH SCRAPE COMPLETE")
    logger.info(f"{'='*60}")
    logger.info(f"  Total URLs:    {report.total_urls}")
    logger.info(f"  Scraped:       {report.scraped}")
    logger.info(f"  Failed:        {report.failed}")
    logger.info(f"  Skipped:       {report.skipped}")
    logger.info(f"  Total Chunks:  {report.total_chunks}")
    logger.info(f"{'='*60}\n")

    # List failures if any
    if failed_count > 0:
        logger.warning("Failed URLs:")
        for r in results:
            if r.status == "failed":
                logger.warning(f"  - {r.slug}: {r.error}")

    return report


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Batch scrape GOV.UK Immigration Rules pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Scrape all URLs
    python batch_scrape.py

    # Scrape only appendices
    python batch_scrape.py --type appendix

    # Scrape specific pages
    python batch_scrape.py --slugs appendix-fm,appendix-skilled-worker

    # Resume interrupted scrape
    python batch_scrape.py --resume

    # Preview what would be scraped
    python batch_scrape.py --dry-run

    # Scrape first 5 pages only
    python batch_scrape.py --limit 5
        """,
    )

    parser.add_argument(
        "--type",
        "-t",
        dest="types",
        action="append",
        choices=["part", "appendix", "introduction", "index", "updates", "other"],
        help="Filter by URL type (can specify multiple times)",
    )

    parser.add_argument("--slugs", "-s", type=str, help="Comma-separated list of slugs to scrape")

    parser.add_argument(
        "--exclude", "-e", type=str, help="Comma-separated list of slugs to exclude"
    )

    parser.add_argument("--resume", "-r", action="store_true", help="Skip already-scraped URLs")

    parser.add_argument("--limit", "-l", type=int, help="Maximum number of URLs to scrape")

    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Preview what would be scraped without actually scraping",
    )

    return parser.parse_args()


async def main():
    """Main entry point."""
    args = parse_args()

    # Get API key
    api_key = os.environ.get("JINA_API_KEY")
    if not api_key:
        logger.error("JINA_API_KEY environment variable not set")
        logger.error("Usage: JINA_API_KEY='your_key' python batch_scrape.py")
        sys.exit(1)

    # Parse slug filters
    slugs = args.slugs.split(",") if args.slugs else None
    exclude_slugs = args.exclude.split(",") if args.exclude else None

    # Run batch scrape
    try:
        report = await batch_scrape(
            api_key=api_key,
            url_types=args.types,
            slugs=slugs,
            exclude_slugs=exclude_slugs,
            resume=args.resume,
            limit=args.limit,
            dry_run=args.dry_run,
        )

        # Exit with error code if any failures
        if report.failed > 0:
            sys.exit(1)

    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user. Progress has been saved.")
        logger.info("Run with --resume to continue from where you left off.")
        sys.exit(130)


if __name__ == "__main__":
    asyncio.run(main())
