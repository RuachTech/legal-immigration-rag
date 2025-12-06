# GOV.UK Immigration Rules - Sample Analysis Report

**Date:** 5 December 2025  
**Samples Analyzed:** 3 different immigration rules pages

## Sample Overview

We analyzed three different types of immigration rules pages to understand the exact structure and metadata patterns:

### Sample 1: Introduction Page
- **URL:** https://www.gov.uk/guidance/immigration-rules/immigration-rules-introduction
- **Type:** Definitions and interpretations section
- **Characteristics:** Dictionary-style with definitions

### Sample 2: Appendix Skilled Worker
- **URL:** https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-skilled-worker
- **Type:** Complex appendix with detailed subsections
- **Characteristics:** Highly hierarchical, many requirements and conditions

### Sample 3: Part 1 - Leave to Enter or Stay
- **URL:** https://www.gov.uk/guidance/immigration-rules/immigration-rules-part-1-leave-to-enter-or-stay-in-the-uk
- **Type:** Main part with general provisions
- **Characteristics:** Various sections covering entry procedures

---

## Key Patterns Discovered

### 1. **Section ID Patterns**

From Appendix Skilled Worker, we identified clear section ID patterns:

```
Pattern Type 1: Main sections with subsections
- Format: "XX N.M" where:
  - XX = 2-3 letter prefix (e.g., "SW" for Skilled Worker)
  - N = main section number (1, 2, 3, etc.)
  - M = subsection number (1, 2, 3, etc.)
  
Examples:
  SW 1.1 - Validity requirements part 1
  SW 1.2 - Validity requirements part 2
  SW 2.1 - Suitability requirements part 1
  SW 3.1 - Entry requirements part 1
  SW 4.1 - Points requirement part 1
  SW 5.1 through SW 5.7 - Points for sponsorship (mandatory)

Pattern Type 2: Subsections with letter suffixes
- Format: "XX N.M[A-Z]" 
  
Examples:
  SW 1.5ZA - Variation with "ZA" suffix
  SW 6.1A - Sub-variation
  SW 14A.1 - Separate numbering scheme

Pattern Type 3: Special sections
- Format: "SW A1.1" (Health and Care ASHE salary jobs)
- Format: "SW 14.5(c)" (Reference to earlier section)
```

### 2. **Hierarchy Levels**

**Level 1 - Part/Appendix** (Top level)
- Example: "Appendix Skilled Worker"
- Contains multiple main sections
- URL slug: "immigration-rules-appendix-skilled-worker"

**Level 2 - Main Sections** (Section groups)
- Example: "Validity requirements for a Skilled Worker"
- Multiple numbered subsections below
- Pattern: "SW 1.x", "SW 2.x", etc.

**Level 3 - Numbered Subsections** (Individual requirements)
- Example: "SW 1.1 - A person applying for entry clearance..."
- Contains detailed content
- Pattern: "SW N.M"

**Level 4 - Sub-subsections** (Lettered requirements)
- Example: "SW 1.2(a)" - "any fee and Immigration Health Charge must have been paid"
- Nested requirements with letters (a), (b), (c), etc.
- Can go very deep: "(a)(i)", "(a)(ii)", etc.

### 3. **Content Structure Patterns**

#### Introduction Page:
```
Content Type: Definitions
Format: "**Term**" definition text
Pattern: Alphabetically organized definitions
No hierarchical sections - single flat structure
```

#### Appendix Skilled Worker:
```
Content Type: Rules with conditions
Structure:
  - Main heading (markdown # level)
  - Numbered section (SW 1.1, SW 1.2, etc.)
  - Nested content with lettered lists (a), (b), (c)
  - Tables for complex information (options A-K)
  - Lists with bullet points
```

#### Part 1 - Leave to Enter:
```
Content Type: General procedural rules
Structure:
  - Section headings (markdown ## level)
  - Paragraph numbers (7, 8, 9, etc.)
  - Content with lettered references
  - Multiple categories of rules
```

### 4. **Metadata Extraction Points**

**Part/Appendix Name** - Extracted from URL slug:
```
URL: immigration-rules-appendix-skilled-worker
→ Part: "Appendix Skilled Worker"

URL: immigration-rules-part-1-leave-to-enter-or-stay-in-the-uk
→ Part: "Part 1: Leave to Enter or Stay in the UK"

URL: immigration-rules-introduction
→ Part: "Introduction"
```

**Section ID** - From heading text:
```
Heading: "SW 1.1. A person applying for entry clearance..."
→ Section ID: "SW 1.1"
→ Main section: "SW 1"
→ Subsection: ".1"
```

**Hierarchy Level** - Determined by section ID format:
```
"SW 1" = Level 1 (main section)
"SW 1.1" = Level 2 (subsection)
"SW 1.1A" = Level 2 (variation of subsection)
"SW A1.1" = Level 1 (special section)
```

**Parent Section** - Derived from section ID:
```
"SW 1.1" → parent: "SW 1"
"SW 1.2" → parent: "SW 1"
"SW 5.7" → parent: "SW 5"
```

### 5. **Content Boundaries**

**Natural chunk boundaries** are at:
1. Main section level (SW 1, SW 2, etc.)
2. Heading breaks with markdown (### headings in Jina output)
3. Tabular content (should be treated as atomic units)
4. Lists that form coherent requirements

**Example chunking strategy:**
```
Chunk 1: SW 1.1 content (single section)
Chunk 2: SW 1.2 content (next section)
Chunk 3: Table data for SW 4.1 (Points requirement table)
Chunk 4: SW 5 group (all sponsorship points)
```

---

## Metadata Schema for Chunks

Based on analysis, each chunk should capture:

```python
@dataclass
class ChunkMetadata:
    source: str              # "Appendix Skilled Worker"
    part: str                # "Appendix Skilled Worker"
    section_id: str          # "SW 1.1"
    section_title: str       # "Application for entry clearance..."
    parent_section: str      # "SW 1" (for SW 1.1)
    hierarchy_level: int     # 1, 2, 3, 4
    topic: Optional[str]     # "Validity requirements"
    url: str                 # Source URL
    scraped_at: str          # ISO timestamp
```

---

## Implementation Priorities

### Priority 1: Core Parsing (High confidence from samples)
- ✅ Extract part name from URL slug
- ✅ Parse section IDs using regex pattern: `^([A-Z]{1,3})\s+(\d+)(?:\.(\d+))?([A-Z]*)`
- ✅ Determine hierarchy level from section ID format
- ✅ Extract parent section ID
- ✅ Split content at main section boundaries

### Priority 2: Advanced Features (Medium confidence)
- Handle special section formats (SW A1.1)
- Preserve tables as atomic units
- Track lettered subsections (a), (b), (c)
- Flatten deeply nested content appropriately

### Priority 3: Refinements (Lower priority initially)
- Extract topic from section heading
- Handle cross-references within content
- Track effective dates (not visible in samples)
- Handle amendments/deletions (DELETED sections)

---

## Jina Tool Integration Notes

**Advantages observed:**
- Converts HTML to clean Markdown automatically
- Preserves hierarchical structure via markdown headings
- Maintains table formatting as markdown tables
- Removes navigation/UI clutter
- Produces consistent output across different page types

**Important consideration:**
- The Jina output includes ALL links found on page (navigation, footer, etc.)
- We filter by URL prefix matching: `https://www.gov.uk/guidance/immigration-rules`

---

## Recommended Next Steps

1. **Refine `_parse_section_id()` method** with tested regex
2. **Implement content splitting** at section boundaries
3. **Create comprehensive test cases** for each pattern type
4. **Build integration test** fetching one appendix and chunking it end-to-end
5. **Profile performance** on full immigration rules dataset
