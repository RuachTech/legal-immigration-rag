"""
GOV.UK Immigration Rules Scraper using Jina Reader

This scraper uses Jina Reader (r.jina.ai) to fetch and convert GOV.UK pages to clean Markdown,
then parses the hierarchical structure for the RAG pipeline.

Key features:
- Uses Jina Reader API for HTML-to-Markdown conversion
- Rate limiting at 20 RPM (Jina's current limit)
- Hierarchical section parsing (Part/Appendix -> Section -> Subsection)
- Metadata capture for Document-Level Retrieval Mismatch (DRM) prevention
- Support for multiple section ID formats (GEN.1.1, SW 1.1, paragraph numbers)

Usage:
    scraper = GovUKJinaScraper(api_key="your_jina_api_key")
    chunks = await scraper.scrape_all()
    
    # Or scrape a single page
    chunks = await scraper.scrape_page(url)
"""

import re
import time
import json
import asyncio
import httpx
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Dict, Tuple, Any
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
GOVUK_BASE_URL = "https://www.gov.uk"
IMMIGRATION_RULES_URL = "https://www.gov.uk/guidance/immigration-rules"
IMMIGRATION_RULES_PREFIX = "https://www.gov.uk/guidance/immigration-rules"
JINA_READER_BASE = "https://r.jina.ai"

# Jina rate limit: 20 requests per minute = 3 seconds between requests
JINA_RATE_LIMIT_RPM = 20
JINA_MIN_INTERVAL = 60.0 / JINA_RATE_LIMIT_RPM  # 3 seconds

# Default data directory for saving scraped content
DEFAULT_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "govuk-data"


@dataclass
class ChunkMetadata:
    """Metadata for a scraped chunk following Summary-Augmented Chunking (SAC)."""
    source: str                    # e.g., "Immigration Rules Appendix FM"
    part: str                      # e.g., "Appendix FM" or "Part 1"
    section_id: str                # e.g., "GEN.1.1" or "SW 1.1"
    section_title: str             # Human-readable section title
    parent_section: Optional[str] = None  # e.g., "GEN.1" for "GEN.1.1"
    hierarchy_level: int = 1       # 1=Part, 2=Section, 3=Subsection, 4+=Deeper
    topic: Optional[str] = None    # Topic category if identifiable
    url: str = ""                  # Source URL for citations
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ScrapedChunk:
    """A chunk of content with hierarchical metadata."""
    metadata: ChunkMetadata
    text: str  # Body content in Markdown format
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "metadata": asdict(self.metadata),
            "text": self.text
        }


class JinaRateLimiter:
    """
    Rate limiter for Jina Reader API.
    
    Jina currently limits to 20 requests per minute.
    This limiter ensures we don't exceed that, even with parallel requests.
    """
    
    def __init__(self, rpm: int = JINA_RATE_LIMIT_RPM):
        """
        Initialize rate limiter.
        
        Args:
            rpm: Requests per minute limit (default: 20)
        """
        self.min_interval = 60.0 / rpm
        self.last_request_time = 0.0
        self._lock = asyncio.Lock()
    
    async def wait(self):
        """Wait until we can make another request."""
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_request_time
            
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                logger.debug(f"Rate limiting: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)
            
            self.last_request_time = time.time()


class GovUKJinaScraper:
    """
    Scrapes GOV.UK Immigration Rules using Jina Reader for Markdown conversion.
    
    Architecture:
    1. Fetch index page to discover all Parts/Appendices
    2. Fetch each page via Jina Reader (respecting rate limits)
    3. Parse Markdown to extract hierarchical sections
    4. Return chunks with complete metadata for RAG pipeline
    
    Rate Limiting:
    Jina Reader limits to 20 requests per minute. When scraping multiple pages,
    the scraper automatically enforces a 3-second minimum interval between requests.
    """
    
    def __init__(
        self,
        api_key: str,
        timeout: float = 30.0,
        data_dir: Optional[Path] = None,
        save_results: bool = True
    ):
        """
        Initialize scraper.
        
        Args:
            api_key: Jina Reader API key
            timeout: HTTP request timeout in seconds
            data_dir: Directory to save scraped data (default: govuk-data/)
            save_results: Whether to save results to disk (default: True)
        """
        self.api_key = api_key
        self.timeout = timeout
        self.rate_limiter = JinaRateLimiter()
        self.client: Optional[httpx.AsyncClient] = None
        self.save_results = save_results
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        
        # Create data directories if saving is enabled
        if self.save_results:
            self._ensure_data_dirs()
    
    def _ensure_data_dirs(self):
        """Create data directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "raw").mkdir(exist_ok=True)
        (self.data_dir / "chunks").mkdir(exist_ok=True)
        logger.info(f"Data directory: {self.data_dir}")
    
    def _url_to_filename(self, url: str) -> str:
        """
        Convert URL to a safe filename.
        
        Example:
            ".../immigration-rules-appendix-fm-family-members"
            -> "appendix-fm-family-members"
        """
        path = urlparse(url).path
        slug = path.split('/')[-1]
        
        # Remove common prefix
        if slug.startswith('immigration-rules-'):
            slug = slug[len('immigration-rules-'):]
        
        # Ensure it's a valid filename
        slug = re.sub(r'[^\w\-]', '_', slug)
        return slug or "index"
    
    def _save_raw_markdown(self, url: str, content: str, part_name: str):
        """
        Save raw markdown content to disk.
        
        Creates: govuk-data/raw/{slug}.md
        """
        if not self.save_results:
            return
        
        filename = self._url_to_filename(url)
        filepath = self.data_dir / "raw" / f"{filename}.md"
        
        # Add metadata header
        header = f"""---
url: {url}
part_name: {part_name}
scraped_at: {datetime.now().isoformat()}
---

"""
        filepath.write_text(header + content, encoding='utf-8')
        logger.info(f"Saved raw markdown: {filepath}")
    
    def _save_chunks(self, url: str, chunks: List[ScrapedChunk], part_name: str):
        """
        Save parsed chunks to disk as JSON.
        
        Creates: govuk-data/chunks/{slug}.json
        """
        if not self.save_results:
            return
        
        filename = self._url_to_filename(url)
        filepath = self.data_dir / "chunks" / f"{filename}.json"
        
        data = {
            "url": url,
            "part_name": part_name,
            "scraped_at": datetime.now().isoformat(),
            "chunk_count": len(chunks),
            "chunks": [chunk.to_dict() for chunk in chunks]
        }
        
        filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        logger.info(f"Saved {len(chunks)} chunks: {filepath}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()
    
    async def fetch_with_jina(self, url: str) -> Dict[str, Any]:
        """
        Fetch a page using Jina Reader API.
        
        Args:
            url: URL to fetch
        
        Returns:
            Dict with 'content' (markdown), 'title', 'url' keys
        """
        await self.rate_limiter.wait()
        
        jina_url = f"{JINA_READER_BASE}/{url}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/markdown"
        }
        
        logger.info(f"Fetching: {url}")
        
        if not self.client:
            self.client = httpx.AsyncClient(timeout=self.timeout)
        
        try:
            response = await self.client.get(jina_url, headers=headers)
            response.raise_for_status()
            
            content = response.text
            
            # Extract title from content if present
            title = self._extract_title_from_markdown(content)
            
            return {
                "content": content,
                "title": title,
                "url": url
            }
        
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching {url}: {e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            raise
    
    def _extract_title_from_markdown(self, content: str) -> str:
        """Extract title from Jina markdown output."""
        # Jina format: "Title: <title>\n\nURL Source: <url>\n\nMarkdown Content:"
        match = re.search(r'^Title:\s*(.+?)(?:\n|$)', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        
        # Fallback: look for first H1
        match = re.search(r'^#\s+(.+?)$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        
        return "Untitled"
    
    async def fetch_index_links(self) -> Dict[str, str]:
        """
        Fetch the main immigration rules index and extract all rule links.
        
        Returns:
            Dict mapping page titles to URLs
        """
        result = await self.fetch_with_jina(IMMIGRATION_RULES_URL)
        content = result["content"]
        
        links = {}
        
        # Extract markdown links: [text](url)
        link_pattern = r'\[([^\]]+)\]\((https://www\.gov\.uk/guidance/immigration-rules[^\)]*)\)'
        
        for match in re.finditer(link_pattern, content):
            anchor_text = match.group(1).strip()
            url = match.group(2).strip().rstrip('/')
            
            # Skip the index page itself
            if url != IMMIGRATION_RULES_URL:
                links[anchor_text] = url
        
        logger.info(f"Found {len(links)} immigration rules links")
        return links
    
    async def scrape_page(self, url: str, part_name: Optional[str] = None) -> List[ScrapedChunk]:
        """
        Scrape a single GOV.UK immigration rules page.
        
        Args:
            url: URL to scrape
            part_name: Optional part name (derived from URL if not provided)
        
        Returns:
            List of ScrapedChunk objects
        """
        result = await self.fetch_with_jina(url)
        content = result["content"]
        
        if not part_name:
            part_name = self.extract_part_name_from_url(url)
        
        # Save raw markdown
        self._save_raw_markdown(url, content, part_name)
        
        # Parse into chunks
        chunks = self.parse_markdown_content(content, url, part_name)
        
        # Save parsed chunks
        self._save_chunks(url, chunks, part_name)
        
        return chunks
    
    async def scrape_multiple(
        self, 
        urls: Dict[str, str],
        max_concurrent: int = 1
    ) -> List[ScrapedChunk]:
        """
        Scrape multiple pages with rate limiting.
        
        Note: Due to Jina's 20 RPM limit, we process sequentially by default.
        Setting max_concurrent > 1 will still respect the rate limit but may
        help with network latency.
        
        Args:
            urls: Dict mapping part names to URLs
            max_concurrent: Max concurrent requests (default 1 for safety)
        
        Returns:
            All scraped chunks combined
        """
        all_chunks = []
        
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def scrape_with_semaphore(part_name: str, url: str) -> List[ScrapedChunk]:
            async with semaphore:
                try:
                    return await self.scrape_page(url, part_name)
                except Exception as e:
                    logger.error(f"Failed to scrape {part_name}: {e}")
                    return []
        
        # Process all URLs
        tasks = [
            scrape_with_semaphore(part_name, url)
            for part_name, url in urls.items()
        ]
        
        results = await asyncio.gather(*tasks)
        
        for chunks in results:
            all_chunks.extend(chunks)
        
        logger.info(f"Scraped {len(all_chunks)} total chunks from {len(urls)} pages")
        
        # Save index/summary
        self._save_index(urls, all_chunks)
        
        return all_chunks
    
    def _save_index(self, urls: Dict[str, str], all_chunks: List[ScrapedChunk]):
        """
        Save an index file summarizing all scraped content.
        
        Creates: govuk-data/index.json
        """
        if not self.save_results:
            return
        
        # Group chunks by part
        parts_summary = {}
        for part_name, url in urls.items():
            part_chunks = [c for c in all_chunks if c.metadata.part == part_name]
            parts_summary[part_name] = {
                "url": url,
                "chunk_count": len(part_chunks),
                "sections": list(set(c.metadata.section_id for c in part_chunks))
            }
        
        index_data = {
            "scraped_at": datetime.now().isoformat(),
            "total_pages": len(urls),
            "total_chunks": len(all_chunks),
            "parts": parts_summary
        }
        
        filepath = self.data_dir / "index.json"
        filepath.write_text(json.dumps(index_data, indent=2, ensure_ascii=False), encoding='utf-8')
        logger.info(f"Saved index: {filepath}")
    
    async def scrape_all(self) -> List[ScrapedChunk]:
        """
        Scrape all immigration rules pages.
        
        Returns:
            All scraped chunks
        """
        # First, get all links from the index
        links = await self.fetch_index_links()
        
        # Convert to {part_name: url} format
        urls = {
            self.extract_part_name_from_url(url): url
            for title, url in links.items()
        }
        
        return await self.scrape_multiple(urls)
    
    # =========================================================================
    # URL and Part Name Extraction
    # =========================================================================
    
    def extract_part_name_from_url(self, url: str) -> str:
        """
        Extract part/appendix name from GOV.UK URL.
        
        Examples:
        - ".../immigration-rules-appendix-fm-family-members" 
          → "Appendix FM: Family Members"
        - ".../immigration-rules-appendix-skilled-worker" 
          → "Appendix Skilled Worker"
        - ".../immigration-rules-part-1-leave-to-enter-or-stay-in-the-uk" 
          → "Part 1: Leave to Enter or Stay in the UK"
        """
        path = urlparse(url).path
        slug = path.split('/')[-1]
        
        # Remove common prefix
        if slug.startswith('immigration-rules-'):
            slug = slug[len('immigration-rules-'):]
        
        parts = slug.split('-')
        
        if not parts:
            return "Immigration Rules"
        
        if parts[0] == 'appendix':
            # Handle appendix naming
            if len(parts) < 2:
                return "Appendix"
            
            appendix_id = parts[1].upper()
            
            # Check if it's a short code (FM, ATAS) or full name
            if len(appendix_id) <= 4 and appendix_id.isalpha():
                # Short code: Appendix FM
                if len(parts) > 2:
                    description = ' '.join(p.capitalize() for p in parts[2:])
                    return f"Appendix {appendix_id}: {description}"
                return f"Appendix {appendix_id}"
            else:
                # Full name: Appendix Skilled Worker
                name = ' '.join(p.capitalize() for p in parts[1:])
                return f"Appendix {name}"
        
        elif parts[0] == 'part':
            if len(parts) < 2:
                return "Part"
            
            part_num = parts[1]
            if len(parts) > 2:
                description = ' '.join(p.capitalize() for p in parts[2:])
                return f"Part {part_num}: {description}"
            return f"Part {part_num}"
        
        elif parts[0] == 'introduction':
            return "Introduction"
        
        else:
            return slug.replace('-', ' ').title()
    
    # =========================================================================
    # Section ID Parsing
    # =========================================================================
    
    def parse_section_id(self, text: str) -> Tuple[Optional[str], Optional[str], int]:
        """
        Parse section ID from text. Supports multiple GOV.UK formats.
        
        Patterns supported:
        - Dot-notation: GEN.1.1, E-ECP.3.1, R-LTRP.1.1, D-ILRP.1.2
        - Space-notation: SW 1.1, PT 2.3, SW A1.1
        - Simple paragraphs: 7, 10A, 11B
        
        Returns:
            Tuple of (section_id, parent_section_id, hierarchy_level)
            Returns (None, None, 0) if no pattern matches
        """
        text = text.strip()
        
        # Pattern 1: Dot-notation with optional hyphenated prefix
        # Examples: GEN.1.1, E-ECP.3.1, R-LTRP.1.1, GEN.1.11A
        dot_pattern = r'^([A-Z](?:-[A-Z]+)*[A-Z]*)\.(\d+)(?:\.(\d+))?([A-Z]*)'
        match = re.match(dot_pattern, text)
        if match:
            prefix = match.group(1)      # "GEN", "E-ECP", "R-LTRP"
            major = match.group(2)       # "1", "3"
            minor = match.group(3)       # "1", "2" (optional)
            suffix = match.group(4)      # "A", "B" (optional)
            
            section_id = f"{prefix}.{major}"
            if minor:
                section_id += f".{minor}"
            if suffix:
                section_id += suffix
            
            parent = f"{prefix}.{major}" if minor else None
            level = 2 if minor else 1
            
            return section_id, parent, level
        
        # Pattern 2: Space-notation (SW 1.1, PT 2.3)
        # Examples: SW 1.1, PT 2.3, SW A1.1, SW 1.1A, SW 2.3ZA
        space_pattern = r'^([A-Z]{1,3})\s+([A-Z]?\d+)(?:\.(\d+))?([A-Z]*)'
        match = re.match(space_pattern, text)
        if match:
            prefix = match.group(1)      # "SW", "PT"
            major = match.group(2)       # "1", "A1"
            minor = match.group(3)       # "1" (optional)
            suffix = match.group(4)      # "A", "ZA" (optional)
            
            section_id = f"{prefix} {major}"
            if minor:
                section_id += f".{minor}"
            if suffix:
                section_id += suffix
            
            parent = f"{prefix} {major}" if minor else None
            level = 2 if minor else 1
            
            return section_id, parent, level
        
        # Pattern 3: Simple paragraph numbers (7, 10A, 11B)
        para_pattern = r'^(\d+[A-Z]?)(?:\.|$|\s)'
        match = re.match(para_pattern, text)
        if match:
            return match.group(1), None, 1
        
        return None, None, 0
    
    # =========================================================================
    # Markdown Parsing
    # =========================================================================
    
    def parse_markdown_content(
        self,
        markdown_content: str,
        url: str,
        part_name: str
    ) -> List[ScrapedChunk]:
        """
        Parse Jina Markdown and extract hierarchical chunks.
        
        Strategy:
        1. Strip boilerplate (cookies, navigation, footer)
        2. Split on heading patterns
        3. Extract section IDs from headings or content
        4. Track hierarchy through heading levels
        5. Create chunks with complete metadata
        
        Args:
            markdown_content: Raw markdown from Jina Reader
            url: Source URL
            part_name: Part/Appendix name
        
        Returns:
            List of ScrapedChunk objects
        """
        chunks = []
        
        # Strip boilerplate
        content = self._strip_boilerplate(markdown_content)
        
        if not content.strip():
            logger.warning(f"Empty content after stripping boilerplate for {url}")
            return chunks
        
        # Parse into sections
        sections = self._split_into_sections(content)
        
        for section in sections:
            chunk = self._create_chunk_from_section(
                section=section,
                part_name=part_name,
                url=url
            )
            if chunk:
                chunks.append(chunk)
        
        logger.info(f"Parsed {len(chunks)} chunks from {part_name}")
        return chunks
    
    def _strip_boilerplate(self, content: str) -> str:
        """
        Remove GOV.UK boilerplate from Jina output.
        
        Strips:
        - Title/URL header from Jina
        - Cookie consent banners
        - Navigation menus
        - Footer content
        """
        # Find main content start - look for the actual Immigration Rules content
        main_content_markers = [
            'Immigration Rules\n=',           # Setext H1
            '# Immigration Rules',            # ATX H1
            'From:[Home Office]',             # Metadata
            '=====================',           # Underline marker
        ]
        
        start_idx = 0
        for marker in main_content_markers:
            idx = content.find(marker)
            if idx > 0:
                start_idx = max(start_idx, idx)
        
        if start_idx > 0:
            content = content[start_idx:]
        
        # Remove Jina header if present
        if content.startswith('Title:'):
            # Find end of header (double newline)
            header_end = content.find('\n\n')
            if header_end > 0:
                content = content[header_end + 2:]
        
        # Remove footer content
        footer_markers = [
            'Is this page useful?',
            'Help us improve GOV.UK',
            'Services and information',
            'Departments',
            '[Skip to main content]',
        ]
        
        for marker in footer_markers:
            idx = content.find(marker)
            if idx > 0:
                content = content[:idx]
        
        return content.strip()
    
    def _split_into_sections(self, content: str) -> List[Dict[str, Any]]:
        """
        Split markdown content into sections based on headings.
        
        Returns list of dicts with:
        - 'heading_level': int (1-6)
        - 'heading_text': str
        - 'content': str (body text under this heading)
        """
        sections = []
        lines = content.split('\n')
        
        current_section: Optional[dict[str, Any]] = None
        current_content = []
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Check for ATX-style headings (# , ## , etc.)
            atx_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if atx_match:
                # Save previous section
                if current_section:
                    current_section['content'] = '\n'.join(current_content).strip()
                    if current_section['content'] or current_section['heading_text']:
                        sections.append(current_section)
                
                # Start new section
                level = len(atx_match.group(1))
                heading_text = atx_match.group(2).strip()
                
                current_section = {
                    'heading_level': level,
                    'heading_text': self._clean_heading_text(heading_text),
                    'content': ''
                }
                current_content = []
                i += 1
                continue
            
            # Check for Setext-style headings (underlines)
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                
                # H1: line followed by ===
                if re.match(r'^=+$', next_line) and line.strip():
                    if current_section:
                        current_section['content'] = '\n'.join(current_content).strip()
                        if current_section['content'] or current_section['heading_text']:
                            sections.append(current_section)
                    
                    current_section = {
                        'heading_level': 1,
                        'heading_text': self._clean_heading_text(line.strip()),
                        'content': ''
                    }
                    current_content = []
                    i += 2  # Skip both the heading and underline
                    continue
                
                # H2: line followed by ---
                if re.match(r'^-+$', next_line) and line.strip() and not line.startswith('-'):
                    if current_section:
                        current_section['content'] = '\n'.join(current_content).strip()
                        if current_section['content'] or current_section['heading_text']:
                            sections.append(current_section)
                    
                    current_section = {
                        'heading_level': 2,
                        'heading_text': self._clean_heading_text(line.strip()),
                        'content': ''
                    }
                    current_content = []
                    i += 2
                    continue
            
            # Regular content line
            current_content.append(line)
            i += 1
        
        # Don't forget the last section
        if current_section:
            current_section['content'] = '\n'.join(current_content).strip()
            if current_section['content'] or current_section['heading_text']:
                sections.append(current_section)
        
        return sections
    
    def _clean_heading_text(self, text: str) -> str:
        """
        Clean heading text by removing Show/Hide suffixes and extra whitespace.
        
        GOV.UK uses collapsible sections that Jina renders as "Section Name, Show"
        """
        # Remove ", Show" or ", Hide" suffixes
        text = re.sub(r',\s*(Show|Hide)\s*$', '', text)
        return text.strip()
    
    def _create_chunk_from_section(
        self,
        section: Dict[str, Any],
        part_name: str,
        url: str
    ) -> Optional[ScrapedChunk]:
        """
        Create a ScrapedChunk from a parsed section.
        
        Args:
            section: Dict with heading_level, heading_text, content
            part_name: Part/Appendix name
            url: Source URL
        
        Returns:
            ScrapedChunk or None if section should be skipped
        """
        heading_text = section.get('heading_text', '')
        content = section.get('content', '')
        heading_level = section.get('heading_level', 1)
        
        # Skip empty sections
        if not content.strip() and not heading_text.strip():
            return None
        
        # Skip navigation/boilerplate headings
        skip_headings = [
            'navigation menu',
            'services and information',
            'government activity',
            'search gov.uk',
            'cookies on gov.uk',
        ]
        if heading_text.lower() in skip_headings:
            return None
        
        # Try to extract section ID from heading
        section_id, parent_section, level = self.parse_section_id(heading_text)
        
        # If no section ID in heading, check first line of content
        if not section_id and content:
            first_line = content.split('\n')[0].strip()
            section_id, parent_section, level = self.parse_section_id(first_line)
        
        # Use heading text as section ID if still not found
        if not section_id:
            section_id = heading_text or "Unknown"
            level = heading_level
        
        # Combine heading and content for the chunk text
        full_text = content
        if heading_text and not content.startswith(heading_text):
            full_text = f"### {heading_text}\n\n{content}"
        
        # Infer topic from heading
        topic = self._infer_topic(heading_text, content)
        
        metadata = ChunkMetadata(
            source=part_name,
            part=part_name,
            section_id=section_id,
            section_title=heading_text or section_id,
            parent_section=parent_section,
            hierarchy_level=level if level > 0 else heading_level,
            topic=topic,
            url=url
        )
        
        return ScrapedChunk(metadata=metadata, text=full_text.strip())
    
    def _infer_topic(self, heading: str, content: str) -> Optional[str]:
        """
        Infer topic category from heading and content.
        
        Returns topic slug or None.
        """
        text = (heading + " " + content[:200]).lower()
        
        topic_keywords = {
            'eligibility': ['eligibility', 'eligible', 'requirements to be met'],
            'financial': ['financial', 'salary', 'income', 'maintenance', 'funds'],
            'english-language': ['english language', 'english requirement', 'language test'],
            'accommodation': ['accommodation', 'housing', 'adequate accommodation'],
            'suitability': ['suitability', 'refusal', 'exclusion', 'general grounds'],
            'definitions': ['definition', 'means', 'for the purposes of'],
            'leave-to-enter': ['leave to enter', 'entry clearance'],
            'leave-to-remain': ['leave to remain', 'extension'],
            'settlement': ['settlement', 'indefinite leave', 'ilr'],
            'family': ['partner', 'spouse', 'child', 'parent', 'family'],
            'points': ['points', 'point-based', 'tradeable'],
        }
        
        for topic, keywords in topic_keywords.items():
            if any(kw in text for kw in keywords):
                return topic
        
        return None
    
    # =========================================================================
    # Cross-Reference Extraction
    # =========================================================================
    
    def extract_cross_references(self, text: str) -> List[str]:
        """
        Extract section/paragraph cross-references from text.
        
        Patterns:
        - "Paragraphs 277-280"
        - "paragraph R-LTRP.1.1.(a)"
        - "Section GEN.1.1"
        - "Appendix FM"
        - "Part 8"
        """
        patterns = [
            r'[Pp]aragraph[s]?\s+([\d\w\-\.]+(?:\s*[-–]\s*[\d\w\-\.]+)?)',
            r'[Ss]ection\s+([A-Z\-]+\.[\d\.]+)',
            r'(?:paragraph|section)\s+([A-Z\-]+[\.\s][\d\.]+\([a-z]\))',
            r'Appendix\s+([A-Z][A-Z\-]*)',
            r'Part\s+(\d+[A-Z]?)',
        ]
        
        refs = []
        for pattern in patterns:
            refs.extend(re.findall(pattern, text))
        
        return list(set(refs))


# =============================================================================
# Convenience Functions
# =============================================================================

async def scrape_immigration_rules(
    api_key: str,
    save_results: bool = True,
    data_dir: Optional[Path] = None
) -> List[ScrapedChunk]:
    """
    Scrape all GOV.UK Immigration Rules pages.
    
    Args:
        api_key: Jina Reader API key
        save_results: Whether to save results to disk (default: True)
        data_dir: Directory to save data (default: govuk-data/)
    
    Returns:
        List of all scraped chunks
    """
    async with GovUKJinaScraper(
        api_key=api_key,
        save_results=save_results,
        data_dir=data_dir
    ) as scraper:
        return await scraper.scrape_all()


async def scrape_single_page(
    api_key: str,
    url: str,
    save_results: bool = True,
    data_dir: Optional[Path] = None
) -> List[ScrapedChunk]:
    """
    Scrape a single GOV.UK Immigration Rules page.
    
    Args:
        api_key: Jina Reader API key
        url: URL to scrape
        save_results: Whether to save results to disk (default: True)
        data_dir: Directory to save data (default: govuk-data/)
    
    Returns:
        List of scraped chunks from the page
    """
    async with GovUKJinaScraper(
        api_key=api_key,
        save_results=save_results,
        data_dir=data_dir
    ) as scraper:
        return await scraper.scrape_page(url)


# =============================================================================
# CLI / Testing
# =============================================================================

def run_unit_tests():
    """Run unit tests for section ID parsing and URL extraction."""
    print("Testing section ID parsing:")
    print("-" * 40)
    
    scraper = GovUKJinaScraper(api_key="test", save_results=False)
    
    test_cases = [
        # Dot-notation
        ("GEN.1.1", ("GEN.1.1", "GEN.1", 2)),
        ("GEN.1", ("GEN.1", None, 1)),
        ("E-ECP.3.1", ("E-ECP.3.1", "E-ECP.3", 2)),
        ("R-LTRP.1.1", ("R-LTRP.1.1", "R-LTRP.1", 2)),
        ("GEN.1.11A", ("GEN.1.11A", "GEN.1", 2)),
        
        # Space-notation
        ("SW 1.1", ("SW 1.1", "SW 1", 2)),
        ("SW 2.3A", ("SW 2.3A", "SW 2", 2)),
        ("PT 1", ("PT 1", None, 1)),
        
        # Simple paragraphs
        ("7.", ("7", None, 1)),
        ("10A.", ("10A", None, 1)),
        
        # Non-matching
        ("Some random text", (None, None, 0)),
    ]
    
    for input_text, expected in test_cases:
        result = scraper.parse_section_id(input_text)
        status = "✓" if result == expected else "✗"
        print(f"{status} '{input_text}' -> {result}")
        if result != expected:
            print(f"   Expected: {expected}")
    
    print()
    print("Testing URL to part name:")
    print("-" * 40)
    
    url_cases = [
        ("https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-fm-family-members",
         "Appendix FM: Family Members"),
        ("https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-skilled-worker",
         "Appendix Skilled Worker"),
        ("https://www.gov.uk/guidance/immigration-rules/immigration-rules-part-1-leave-to-enter-or-stay-in-the-uk",
         "Part 1: Leave To Enter Or Stay In The Uk"),
        ("https://www.gov.uk/guidance/immigration-rules/immigration-rules-introduction",
         "Introduction"),
    ]
    
    for url, expected in url_cases:
        result = scraper.extract_part_name_from_url(url)
        status = "✓" if result == expected else "✗"
        print(f"{status} {url.split('/')[-1][:40]}...")
        print(f"   Result: {result}")
        if result != expected:
            print(f"   Expected: {expected}")


async def run_scrape_test(api_key: str, url: str):
    """
    Test scraping a single page.
    
    Args:
        api_key: Jina Reader API key
        url: URL to scrape
    """
    print(f"\nScraping: {url}")
    print("-" * 60)
    
    chunks = await scrape_single_page(api_key=api_key, url=url, save_results=True)
    
    print(f"\nScraped {len(chunks)} chunks")
    for i, chunk in enumerate(chunks[:5]):  # Show first 5
        print(f"\n--- Chunk {i+1} ---")
        print(f"Section ID: {chunk.metadata.section_id}")
        print(f"Title: {chunk.metadata.section_title}")
        print(f"Level: {chunk.metadata.hierarchy_level}")
        print(f"Parent: {chunk.metadata.parent_section}")
        print(f"Text preview: {chunk.text[:150]}...")
    
    if len(chunks) > 5:
        print(f"\n... and {len(chunks) - 5} more chunks")

# asyncio.run(scrape_immigration_rules("jina_d990652876ed4bcdaef9a1160b287a17Aiu9H3-HGwmKL1c1W3QfXljLc21H"))
if __name__ == "__main__":
    import sys
    import os
    
    # Run unit tests
    run_unit_tests()
    
    # If API key is provided, run a live scrape test
    api_key = os.environ.get("JINA_API_KEY")
    
    if api_key and len(sys.argv) > 1 and sys.argv[1] == "--scrape":
        # Optional: specify URL as second argument
        url = sys.argv[2] if len(sys.argv) > 2 else \
            "https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-fm-family-members"
        
        asyncio.run(run_scrape_test(api_key, url))
    elif not api_key:
        print("\n" + "=" * 60)
        print("To run a live scrape test:")
        print("  export JINA_API_KEY='your_api_key'")
        print("  python govuk_jina_scraper.py --scrape [optional_url]")
        print("=" * 60)
