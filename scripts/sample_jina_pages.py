"""
Sample test script to fetch and analyze 3 different immigration rules pages
to understand the exact structure and metadata patterns.
"""

import asyncio
import json
from data_pipeline.scrapers.govuk_jina_scraper import GovUKScraperJina

# We'll use the mcp_jina_mcp_serv read_url function directly
try:
    from mcp_jina_mcp_serv_read_url import read_url
except ImportError:
    # Create a mock for testing
    async def read_url(url, **kwargs):
        return {"content": "", "links": [], "url": url}


async def sample_pages():
    """Sample 3 different types of immigration rules pages."""
    
    # Sample URLs representing different page types
    sample_urls = [
        {
            "url": "https://www.gov.uk/guidance/immigration-rules/immigration-rules-introduction",
            "description": "Introduction page"
        },
        {
            "url": "https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-skilled-worker",
            "description": "Appendix Skilled Worker (complex with many subsections)"
        },
        {
            "url": "https://www.gov.uk/guidance/immigration-rules/immigration-rules-part-1-leave-to-enter-or-stay-in-the-uk",
            "description": "Part 1 (main part with general provisions)"
        }
    ]
    
    scraper = GovUKScraperJina(use_jina_api=True)
    
    for sample in sample_urls:
        url = sample["url"]
        description = sample["description"]
        
        print(f"\n{'='*80}")
        print(f"SAMPLE: {description}")
        print(f"URL: {url}")
        print(f"{'='*80}\n")
        
        try:
            # Try to fetch using the mcp_jina tool
            # NOTE: This uses a tool that might be available in the MCP environment
            print(f"Fetching content from Jina Reader...")
            # In a real scenario, this would be called through the MCP
            # For now, we'll note what would be fetched
            
            # Extract the part name from URL
            part_name = scraper._extract_part_name_from_url(url)
            print(f"Extracted Part Name: {part_name}\n")
            
            # Show what we expect to find
            print(f"Expected structure patterns:")
            print(f"  - Look for section IDs like 'SW 1.1', 'PT 2.3', etc.")
            print(f"  - Hierarchical headings with markdown (# , ## , ### )")
            print(f"  - Parent-child section relationships")
            print(f"\nTo fetch this page, use:")
            print(f"  mcp_jina_mcp_serv_read_url(url='{url}')")
            
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    print("GOV.UK Immigration Rules - Sample Analysis")
    print("=" * 80)
    print("\nThis script identifies the exact structure and patterns we need to parse.\n")
    
    # Run the async function
    asyncio.run(sample_pages())
    
    print("\n" + "="*80)
    print("NEXT STEPS:")
    print("="*80)
    print("""
1. Use the Jina Reader tool to fetch each URL above
2. Analyze the Markdown structure to identify:
   - Heading hierarchies (# , ## , ### , etc.)
   - Section ID patterns (e.g., SW 1.1, SW 2.3A)
   - Parent-child relationships
   - Metadata that can be extracted from the text

3. Based on the patterns found, refine the parsing logic in:
   - parse_markdown_content()
   - _parse_section_id()
   - _extract_part_name_from_url()

4. Create comprehensive test cases for the metadata extraction
    """)
