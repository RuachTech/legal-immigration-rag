# Hierarchical Legal Parsing: GOV.UK Immigration Rules via Markdown Extraction

## Overview

This document describes our approach for parsing GOV.UK Immigration Rules using **Jina Reader** to extract clean Markdown content. This replaces the previous HTML-based parsing approach (see `semi-structured-legal-parsing.md` for legacy reference).

**Key Insight:** Jina Reader converts web pages to well-structured Markdown that preserves document hierarchy, making it ideal for LLM consumption and RAG pipelines.

## Why Markdown Over HTML?

| Aspect | HTML Parsing | Markdown Extraction |
|--------|--------------|---------------------|
| **Complexity** | Parse `<h2>`, `<h3>`, `<p>`, `<ol>`, `<ul>` tags | Parse `#`, `##`, `###` headings and lists |
| **Noise** | Cookie banners, navigation, scripts | Clean content only |
| **Maintenance** | Breaks when GOV.UK changes layout | Resilient to cosmetic changes |
| **LLM Compatibility** | Requires HTML stripping | Native LLM-friendly format |
| **Structure Preservation** | Manual extraction required | Automatic via Jina |

## Jina Reader API

### Endpoint
```bash
curl "https://r.jina.ai/{url}" \
  -H "Authorization: Bearer {api_key}"
```

### Rate Limiting
- **Current limit**: 20 requests per minute (RPM)
- **Enforced interval**: 3 seconds minimum between requests
- **Parallel scraping**: Use `max_concurrent=1` (default) for safety; rate limiter handles concurrent requests but sequential is more predictable

### Response Format
Jina returns markdown with a header:
```
Title: Immigration Rules - Appendix FM: family members

URL Source: https://www.gov.uk/guidance/immigration-rules/...

Markdown Content:
[actual content here]
```

## Source: Jina Reader Output

Jina Reader (`r.jina.ai` or MCP tool `mcp_jina-mcp-serv_read_url`) returns structured Markdown:

```markdown
Title: Immigration Rules - Immigration Rules Appendix FM: family members

URL Source: https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-fm-family-members

Markdown Content:
Immigration Rules Appendix FM: family members
=============================================

Family members

General, Show
-------------

### Section GEN: General

### Purpose

GEN.1.1. This route is for those seeking to enter or remain in the UK...

### Definitions

1.   GEN.1.2. For the purposes of this Appendix "partner" means the applicant's- 
    1.   (i) spouse; or
    2.   (ii) civil partner; or
    ...
```

## Section ID Patterns in Immigration Rules

GOV.UK Immigration Rules use several section ID formats:

### Pattern 1: Dot-Notation IDs (Appendix FM style)
```
GEN.1.1     → Section "GEN", major=1, minor=1
GEN.1.2     → Section "GEN", major=1, minor=2
E-ECP.3.1   → Section "E-ECP", major=3, minor=1
R-LTRP.1.1  → Section "R-LTRP", major=1, minor=1
D-ILRP.1.2  → Section "D-ILRP", major=1, minor=2
```

### Pattern 2: Space-Notation IDs (Appendix Skilled Worker style)
```
SW 1.1      → Section "SW", major=1, minor=1
SW 2.3A     → Section "SW", major=2, minor=3, suffix=A
SW A1.1     → Section "SW", special prefix, major=1, minor=1
```

### Pattern 3: Simple Paragraph Numbers (Part 1 style)
```
7           → Paragraph 7
10A         → Paragraph 10A (variant)
11B         → Paragraph 11B (variant)
```

### Pattern 4: Nested List References
```
(a), (b), (c)           → Top-level list items
(i), (ii), (iii)        → Sub-list items (roman numerals)
(1), (2), (3)           → Alternative sub-numbering
```

## Architecture

### Data Model: `ScrapedChunk`

```python
@dataclass
class ChunkMetadata:
    """Metadata for a scraped chunk following Summary-Augmented Chunking (SAC)."""
    source: str                    # e.g., "Immigration Rules Appendix FM"
    part: str                      # e.g., "Appendix FM" or "Part 1"
    section_id: str                # e.g., "GEN.1.1" or "SW 1.1"
    section_title: str             # Human-readable title
    parent_section: Optional[str]  # e.g., "GEN.1" for "GEN.1.1"
    hierarchy_level: int           # 1=Part, 2=Section, 3=Subsection, 4+=Deeper
    topic: Optional[str]           # Topic category if identifiable
    url: str                       # Source URL for citations
    scraped_at: str                # ISO timestamp


@dataclass
class ScrapedChunk:
    """A chunk of content with hierarchical metadata."""
    metadata: ChunkMetadata
    text: str  # Body content in Markdown format
```

### Section ID Extraction

**Combined Regex Pattern:**

```python
def parse_section_id(text: str) -> Tuple[Optional[str], Optional[str], int]:
    """
    Parse section ID from text. Supports multiple GOV.UK formats.
    
    Returns:
        Tuple of (section_id, parent_section_id, hierarchy_level)
    """
    text = text.strip()
    
    # Pattern 1: Dot-notation (GEN.1.1, E-ECP.3.1, R-LTRP.1.1)
    dot_pattern = r'^([A-Z](?:-[A-Z]+)?[A-Z]*)\.(\d+)(?:\.(\d+))?([A-Z]*)'
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
    
    # Pattern 3: Simple paragraph (7, 10A, 11B)
    para_pattern = r'^(\d+[A-Z]?)(?:\.|$)'
    match = re.match(para_pattern, text)
    if match:
        return match.group(1), None, 1
    
    return None, None, 0
```

### Hierarchy Inference

From the markdown structure, hierarchy is determined by:

1. **Heading Level**: `#` = Part, `##` = Section, `###` = Subsection
2. **Section ID Depth**: `GEN.1` = Level 1, `GEN.1.1` = Level 2, `GEN.1.1.1` = Level 3
3. **Parent Derivation**: Strip last numeric component to find parent

**Example Hierarchy for Appendix FM:**

```
Level 1: GEN (General)
├── Level 2: GEN.1 (Section GEN: General)
│   ├── Level 3: GEN.1.1 (Purpose)
│   ├── Level 3: GEN.1.2 (Definitions - partner)
│   ├── Level 3: GEN.1.3 (Definitions - application)
│   └── ...
├── Level 2: GEN.2 (Leave to enter)
│   ├── Level 3: GEN.2.1 (Requirements)
│   └── Level 3: GEN.2.2 (Refusal)
└── Level 2: GEN.3 (Exceptional circumstances)
    ├── Level 3: GEN.3.1 (Financial requirement exception)
    └── Level 3: GEN.3.2 (Other requirements exception)

Level 1: EC-P (Entry clearance as partner)
├── Level 2: EC-P.1.1 (Requirements)
└── ...
```

## Markdown Parsing Algorithm

### Input
- Markdown content from Jina Reader
- Source URL
- Part/Appendix name (derived from URL or title)

### Output
- List of `ScrapedChunk` objects with complete metadata

### Algorithm

```python
def parse_markdown_content(
    markdown_content: str,
    url: str,
    part_name: str
) -> List[ScrapedChunk]:
    """
    Parse Jina Markdown and extract hierarchical chunks.
    
    Strategy:
    1. Skip boilerplate (cookies, navigation) by finding main content
    2. Split on heading patterns (===, ---, #, ##, ###)
    3. For each section:
       - Extract section ID from heading or first line
       - Determine hierarchy level from heading depth
       - Capture content until next heading
       - Infer parent section from ID structure
    4. Create chunks with complete metadata
    """
    chunks = []
    
    # Find start of main content (after navigation boilerplate)
    content = _strip_boilerplate(markdown_content)
    
    # Parse using state machine
    current_heading_stack = []  # Track h1, h2, h3 context
    current_section = None
    current_content = []
    
    for line in content.split('\n'):
        heading_level = _detect_heading(line)
        
        if heading_level > 0:
            # Save previous section
            if current_section:
                chunk = _create_chunk(current_section, current_content, ...)
                chunks.append(chunk)
            
            # Start new section
            current_section = _parse_heading(line, heading_level)
            current_content = []
            
            # Update heading stack for parent tracking
            _update_heading_stack(current_heading_stack, heading_level, current_section)
        else:
            # Accumulate content
            current_content.append(line)
    
    # Don't forget last section
    if current_section:
        chunks.append(_create_chunk(current_section, current_content, ...))
    
    return chunks


def _detect_heading(line: str) -> int:
    """
    Detect heading level from markdown line.
    
    Returns:
        0 = not a heading
        1 = h1 (# or === underline)
        2 = h2 (## or --- underline)  
        3 = h3 (###)
        4+ = deeper headings
    """
    # ATX-style headings
    if line.startswith('# '):
        return 1
    if line.startswith('## '):
        return 2
    if line.startswith('### '):
        return 3
    if line.startswith('#### '):
        return 4
    
    # Setext-style headings (underlines) - check previous line
    if re.match(r'^=+$', line):
        return 1  # Previous line was h1
    if re.match(r'^-+$', line):
        return 2  # Previous line was h2
    
    return 0


def _strip_boilerplate(content: str) -> str:
    """
    Remove GOV.UK boilerplate from Jina output.
    
    Strips:
    - Cookie consent banners
    - Navigation menus
    - Footer content
    - "Skip to main content" links
    """
    # Find main content start markers
    main_content_markers = [
        'Immigration Rules\n=',           # Main title
        '# Immigration Rules',            # Alt title format
        'From:[Home Office]',             # Metadata section
    ]
    
    for marker in main_content_markers:
        idx = content.find(marker)
        if idx > 0:
            content = content[idx:]
            break
    
    # Remove footer content
    footer_markers = [
        'Is this page useful?',
        'Help us improve GOV.UK',
        'Services and information',
    ]
    
    for marker in footer_markers:
        idx = content.find(marker)
        if idx > 0:
            content = content[:idx]
            break
    
    return content.strip()
```

## Collapsible Sections Handling

GOV.UK uses "Show/Hide" collapsible sections in the HTML, which Jina renders as:

```markdown
General, Show
-------------

### Section GEN: General
```

The `, Show` suffix indicates a collapsible section. Our parser handles this by:

```python
def _clean_section_title(title: str) -> str:
    """Remove 'Show'/'Hide' suffixes from collapsible section titles."""
    return re.sub(r',\s*(Show|Hide)\s*$', '', title).strip()
```

## Nested Lists Preservation

Immigration Rules heavily use nested lists for legal requirements. Jina preserves the structure:

```markdown
1.   GEN.1.2. For the purposes of this Appendix "partner" means the applicant's- 
    1.   (i) spouse; or
    2.   (ii) civil partner; or
    3.   (iii) fiancé(e) or proposed civil partner; or
    4.   (iv) unmarried partner, where the couple have been in a relationship...
```

**Preservation Strategy:**
- Keep markdown list formatting intact in chunk text
- Do NOT flatten lists - they contain hierarchical legal logic
- Store the raw markdown for LLM consumption

## Cross-Reference Detection

Immigration Rules contain extensive cross-references:

```markdown
GEN.1.8. Paragraphs 277-280, 289AA, 295AA and 296 of Part 8 of these Rules shall apply...

...the applicant satisfies the requirements in paragraph R-LTRP.1.1.(a), (b) and (d)...
```

**Extraction Pattern:**

```python
def extract_cross_references(text: str) -> List[str]:
    """Extract section/paragraph cross-references from text."""
    patterns = [
        r'[Pp]aragraph[s]?\s+([\d\w\-\.]+(?:\s*[-–]\s*[\d\w\-\.]+)?)',  # Paragraphs 277-280
        r'[Ss]ection\s+([A-Z\-]+\.[\d\.]+)',                            # Section GEN.1.1
        r'(?:paragraph|section)\s+([A-Z\-]+[\.\s][\d\.]+\([a-z]\))',    # R-LTRP.1.1.(a)
        r'Appendix\s+([A-Z][A-Z\-]*)',                                   # Appendix FM
        r'Part\s+(\d+[A-Z]?)',                                           # Part 8
    ]
    
    refs = []
    for pattern in patterns:
        refs.extend(re.findall(pattern, text))
    
    return list(set(refs))
```

## URL to Part Name Mapping

```python
def extract_part_name_from_url(url: str) -> str:
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
    
    if parts[0] == 'appendix':
        # Handle appendix naming
        appendix_id = parts[1].upper()  # "fm", "skilled" -> "FM", "SKILLED"
        
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
        part_num = parts[1]
        if len(parts) > 2:
            description = ' '.join(p.capitalize() for p in parts[2:])
            return f"Part {part_num}: {description}"
        return f"Part {part_num}"
    
    else:
        return slug.replace('-', ' ').title()
```

## Output Format

### JSON Serialization

```json
{
  "metadata": {
    "source": "Immigration Rules Appendix FM",
    "part": "Appendix FM",
    "section_id": "GEN.1.2",
    "section_title": "Definitions",
    "parent_section": "GEN.1",
    "hierarchy_level": 2,
    "topic": "definitions",
    "url": "https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-fm-family-members",
    "scraped_at": "2025-12-05T10:30:00Z"
  },
  "text": "GEN.1.2. For the purposes of this Appendix \"partner\" means the applicant's-\n1.   (i) spouse; or\n2.   (ii) civil partner; or\n..."
}
```

## DRM Prevention Through Metadata

**Document-Level Retrieval Mismatch (DRM)** occurs when similar text from different documents gets retrieved. Prevention strategies:

### 1. Source Filtering
```python
# Query about partner visa? Filter to Appendix FM
filter = {"source": "Appendix FM"}
results = vector_store.search(query, filter=filter)
```

### 2. Section ID Namespace
```python
# Retrieve only from GEN (General) sections
filter = {"section_id": {"$startswith": "GEN"}}
```

### 3. Hierarchy Level Bounds
```python
# Get main sections and subsections, not deep details
filter = {"hierarchy_level": {"$lte": 2}}
```

## Integration with RAG Pipeline

```
Jina Reader (mcp_jina-mcp-serv_read_url)
    ↓
GovUKScraperJina.parse_markdown_content()
    ↓
List[ScrapedChunk] with complete metadata
    ↓
SummaryAugmentedChunker.chunk()
    ↓
List[Chunk] with document summaries prepended
    ↓
VectorStore.add_chunks() (with metadata indexing)
    ↓
HybridRetriever with metadata filtering
    ↓
LLM Generation with citations
```

## Testing Strategy

### Property Tests

```python
from hypothesis import given, strategies as st

@given(st.text())
def test_section_id_parsing_never_crashes(text):
    """Parser should handle any input without exceptions."""
    result = parse_section_id(text)
    assert result is not None
    assert len(result) == 3  # (section_id, parent, level)


def test_hierarchy_consistency():
    """Child sections must have higher level than parents."""
    chunks = scraper.parse_markdown_content(sample_content, url, part)
    
    for chunk in chunks:
        if chunk.metadata.parent_section:
            parent_chunk = find_chunk_by_id(chunks, chunk.metadata.parent_section)
            assert parent_chunk.metadata.hierarchy_level < chunk.metadata.hierarchy_level


def test_all_chunks_have_complete_metadata():
    """Every chunk must have all required metadata fields."""
    chunks = scraper.parse_markdown_content(sample_content, url, part)
    
    for chunk in chunks:
        assert chunk.metadata.source
        assert chunk.metadata.section_id
        assert chunk.metadata.url.startswith("https://www.gov.uk")
        assert chunk.metadata.hierarchy_level >= 1
        assert len(chunk.text.strip()) > 0
```

### Sample-Based Tests

```python
# Test with real Appendix FM content
APPENDIX_FM_SAMPLE = """
Immigration Rules Appendix FM: family members
=============================================

General, Show
-------------

### Section GEN: General

### Purpose

GEN.1.1. This route is for those seeking to enter or remain in the UK...

### Definitions

1.   GEN.1.2. For the purposes of this Appendix "partner" means...
"""

def test_appendix_fm_parsing():
    """Test parsing of Appendix FM structure."""
    chunks = scraper.parse_markdown_content(
        APPENDIX_FM_SAMPLE,
        "https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-fm-family-members",
        "Appendix FM"
    )
    
    # Should extract GEN.1.1 and GEN.1.2
    section_ids = [c.metadata.section_id for c in chunks]
    assert "GEN.1.1" in section_ids or any("GEN" in s for s in section_ids)
```

## Migration from HTML Parsing

### Deprecation Plan

1. **Phase 1 (Current)**: Implement Jina-based scraper alongside HTML scraper
2. **Phase 2**: Run both in parallel, compare outputs
3. **Phase 3**: Switch primary ingestion to Jina scraper
4. **Phase 4**: Deprecate and remove HTML scraper

### Compatibility

The output format (`ScrapedChunk`) is compatible with the existing pipeline. The downstream `SummaryAugmentedChunker` accepts chunks with the same metadata structure.

## References

- Jina Reader: https://r.jina.ai
- GOV.UK Immigration Rules: https://www.gov.uk/guidance/immigration-rules
- Appendix FM (Family Members): https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-fm-family-members
- MCP Jina Tool: `mcp_jina-mcp-serv_read_url`
- Legacy HTML Parsing: `docs/semi-structured-legal-parsing.md`
