"""
Extract all Immigration Rules URLs from GOV.UK

This script fetches the main immigration rules index page and extracts
all links to individual Parts and Appendices, saving them to a JSON file.

Usage:
    python get_govuk_urls.py

    # With custom API key
    JINA_API_KEY="your_key" python get_govuk_urls.py

Output:
    data/immigration_rules_urls.json
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

import httpx

# Constants
# Two source pages contain comprehensive link listings
IMMIGRATION_RULES_SOURCES = [
    "https://www.gov.uk/guidance/immigration-rules",  # Main rules landing page
    "https://www.gov.uk/guidance/immigration-rules/immigration-rules-index",  # Detailed index
]
IMMIGRATION_RULES_PREFIX = "https://www.gov.uk/guidance/immigration-rules"
JINA_READER_BASE = "https://r.jina.ai"

# Output directory
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def fetch_page_with_jina(url: str, api_key: str) -> Dict[str, Any]:
    """
    Fetch a page using Jina Reader API and return links.

    Args:
        url: URL to fetch
        api_key: Jina API key

    Returns:
        Dict with content and links
    """
    jina_url = f"{JINA_READER_BASE}/{url}"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/markdown",  # Request markdown format
        "X-Return-Format": "markdown",
    }

    print(f"Fetching: {url}")

    with httpx.Client(timeout=60.0) as client:
        response = client.get(jina_url, headers=headers)
        response.raise_for_status()

        # Return content as markdown text
        return {"content": response.text, "links": []}


def extract_immigration_rules_links(content: str, include_anchors: bool = False) -> Dict[str, str]:
    """
    Extract immigration rules links from markdown content.

    Args:
        content: Markdown content from Jina
        include_anchors: Whether to include links with anchor fragments (#section)

    Returns:
        Dict mapping anchor text to URL
    """
    links = {}

    # Pattern for markdown links: [text](url)
    link_pattern = r"\[([^\]]+)\]\((https://www\.gov\.uk/guidance/immigration-rules[^\)]*)\)"

    for match in re.finditer(link_pattern, content):
        anchor_text = match.group(1).strip()
        url = match.group(2).strip().rstrip("/")

        # Handle anchor fragments - extract base URL for deduplication
        base_url = url.split("#")[0] if "#" in url else url
        has_anchor = "#" in url

        # Skip anchor links unless explicitly included
        if has_anchor and not include_anchors:
            continue

        # Skip if it's just the base immigration rules page
        if base_url == IMMIGRATION_RULES_PREFIX:
            continue

        # Clean up anchor text
        anchor_text = anchor_text.replace("\n", " ").strip()
        if anchor_text:  # Skip empty anchor texts
            # Use base URL as key to avoid duplicates
            if base_url not in links:
                links[base_url] = anchor_text

    return links


def categorize_url(url: str, title: str) -> Dict[str, Any]:
    """
    Categorize a URL into type and extract metadata.

    Args:
        url: The URL
        title: The anchor text/title

    Returns:
        Dict with url, title, type, and slug
    """
    path = urlparse(url).path
    slug = path.split("/")[-1]

    # Remove common prefix
    if slug.startswith("immigration-rules-"):
        slug = slug[len("immigration-rules-") :]

    # Determine type
    if "appendix" in slug.lower():
        url_type = "appendix"
    elif "part-" in slug.lower():
        url_type = "part"
    elif slug == "index":
        url_type = "index"
    elif slug == "introduction":
        url_type = "introduction"
    elif slug == "updates":
        url_type = "updates"
    else:
        url_type = "other"

    return {"url": url, "title": title, "type": url_type, "slug": slug}


def get_all_immigration_rules_urls(api_key: str) -> Dict[str, Any]:
    """
    Fetch and extract all immigration rules URLs from multiple source pages.

    Args:
        api_key: Jina API key

    Returns:
        Dict with metadata and list of URLs
    """
    all_links = {}  # url -> title mapping for deduplication

    # Fetch from all source pages
    for source_url in IMMIGRATION_RULES_SOURCES:
        print(f"\nFetching from: {source_url}")
        result = fetch_page_with_jina(source_url, api_key)

        # Extract links from content
        content = result.get("content", "")
        links = extract_immigration_rules_links(content)

        print(f"  Found {len(links)} unique immigration rules links")

        # Merge into all_links (first seen title wins)
        for url, title in links.items():
            if url not in all_links:
                all_links[url] = title

    print(f"\nTotal unique URLs after merging: {len(all_links)}")

    # Categorize and structure the URLs
    urls_list = []
    for url, title in all_links.items():
        entry = categorize_url(url, title)
        urls_list.append(entry)

    # Sort by type then title
    type_order = {"index": 0, "introduction": 1, "part": 2, "appendix": 3, "other": 4, "updates": 5}
    urls_list.sort(key=lambda x: (type_order.get(x["type"], 99), x["title"]))

    # Build summary
    type_counts = {}
    for entry in urls_list:
        url_type = entry["type"]
        type_counts[url_type] = type_counts.get(url_type, 0) + 1

    return {
        "source_urls": IMMIGRATION_RULES_SOURCES,
        "fetched_at": datetime.now().isoformat(),
        "total_count": len(urls_list),
        "by_type": type_counts,
        "urls": urls_list,
    }


def save_urls(data: Dict[str, Any], output_path: Path):
    """Save URLs to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved {data['total_count']} URLs to {output_path}")


def main():
    """Main entry point."""
    # Get API key from environment
    api_key = os.environ.get("JINA_API_KEY")

    if not api_key:
        print("Error: JINA_API_KEY environment variable not set")
        print("Usage: JINA_API_KEY='your_key' python get_govuk_urls.py")
        return 1

    # Fetch and extract URLs
    print("Fetching immigration rules from multiple source pages...")
    data = get_all_immigration_rules_urls(api_key)

    # Save to file
    output_path = DATA_DIR / "immigration_rules_urls.json"
    save_urls(data, output_path)

    # Print summary
    print("\nSummary:")
    print(f"  Total URLs: {data['total_count']}")
    print("  By type:")
    for url_type, count in data["by_type"].items():
        print(f"    - {url_type}: {count}")

    return 0


if __name__ == "__main__":
    exit(main())
