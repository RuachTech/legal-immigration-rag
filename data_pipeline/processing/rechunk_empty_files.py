"""Re-chunk empty chunk files from their raw markdown sources.

This script identifies chunk JSON files with 0 chunks, reads the corresponding
raw markdown files, and generates properly chunked + SAC-enhanced output.
"""

import argparse
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import litellm
except ImportError:
    raise ImportError("litellm required: uv add litellm")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

RATE_LIMIT_DELAY = 0.1  # seconds between calls


def extract_sections_from_markdown(markdown_text: str, source_name: str) -> List[Dict[str, Any]]:
    """Split markdown into sections based on headers.
    
    Returns list of chunks with metadata and text.
    """
    lines = markdown_text.split('\n')
    chunks = []
    current_chunk_lines = []
    current_section_title = None
    current_section_id = None
    current_level = 0
    
    for line in lines:
        # Check for headers (### Title or ## Title)
        if line.startswith('###'):
            # Save previous chunk if exists
            if current_chunk_lines:
                chunk_text = '\n'.join(current_chunk_lines).strip()
                if chunk_text:
                    chunks.append({
                        'section_title': current_section_title,
                        'section_id': current_section_id,
                        'hierarchy_level': current_level,
                        'text': chunk_text
                    })
            
            # Start new chunk
            current_section_title = line.replace('###', '').strip()
            current_section_id = current_section_title
            current_level = 3
            current_chunk_lines = [line]
            
        elif line.startswith('##'):
            # Save previous chunk if exists
            if current_chunk_lines:
                chunk_text = '\n'.join(current_chunk_lines).strip()
                if chunk_text:
                    chunks.append({
                        'section_title': current_section_title,
                        'section_id': current_section_id,
                        'hierarchy_level': current_level,
                        'text': chunk_text
                    })
            
            # Start new chunk
            current_section_title = line.replace('##', '').strip()
            current_section_id = current_section_title
            current_level = 2
            current_chunk_lines = [line]
        else:
            current_chunk_lines.append(line)
    
    # Save last chunk
    if current_chunk_lines:
        chunk_text = '\n'.join(current_chunk_lines).strip()
        if chunk_text:
            chunks.append({
                'section_title': current_section_title,
                'section_id': current_section_id,
                'hierarchy_level': current_level,
                'text': chunk_text
            })
    
    return chunks


async def generate_chunk_summary(
    chunk_text: str,
    metadata: Dict[str, Any],
    model: str = "gpt-4o-mini",
    max_retries: int = 3,
) -> str:
    """Generate a legal-focused summary for a single chunk."""
    source = metadata.get("source", "Unknown document")
    section_id = metadata.get("section_id")
    section_title = metadata.get("section_title")
    
    context_parts = [f"Document: {source}"]
    if section_id:
        context_parts.append(f"Section: {section_id}")
    if section_title:
        context_parts.append(f"Title: {section_title}")
    
    context = " | ".join(context_parts)
    
    prompt = f"""You are analyzing a chunk from UK Immigration Rules. Generate a concise 2-3 sentence summary (under 100 tokens) that captures:

1. Who or what this provision applies to (e.g., "Skilled Workers", "applicants", "sponsors")
2. The key requirement, right, obligation, or process being described
3. Any critical conditions, exceptions, or thresholds

Context: {context}

Chunk text:
{chunk_text[:1500]}

Legal summary:"""

    for attempt in range(max_retries):
        try:
            await asyncio.sleep(RATE_LIMIT_DELAY)
            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
            )
            
            summary = getattr(
                getattr(response, "choices", [None])[0],
                "message",
                None,
            )
            summary = getattr(summary, "content", "") if summary else ""
            
            return (summary or "").strip()
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt+1} failed: {e}, retrying...")
                await asyncio.sleep(1)
            else:
                logger.error(f"LLM summarization failed: {e}")
                return ""
    
    return ""


def build_augmented_text(metadata: Dict[str, Any], summary: str, text: str) -> str:
    """Build augmented text with metadata header + summary + original text."""
    source = metadata.get("source", "")
    part = metadata.get("part", "")
    section_id = metadata.get("section_id", "")
    section_title = metadata.get("section_title", "")
    topic = metadata.get("topic", "")
    
    metadata_lines = []
    if source:
        metadata_lines.append(f"Document: {source}")
    if part:
        metadata_lines.append(f"Part: {part}")
    if section_id:
        metadata_lines.append(f"Section ID: {section_id}")
    if section_title:
        metadata_lines.append(f"Section: {section_title}")
    if topic:
        metadata_lines.append(f"Topic: {topic}")
    
    metadata_header = "\n".join(metadata_lines)
    
    # Build augmented text with proper structure
    parts = []
    if metadata_header:
        parts.append(metadata_header)
    if summary:
        parts.append(f"\nSummary: {summary}")
    parts.append(f"\n{text}")
    
    return "\n".join(parts) if parts else text


async def rechunk_file(
    chunk_file: Path,
    raw_file: Path,
    model: str,
    url: str
) -> None:
    """Re-chunk a single empty chunk file from its raw markdown."""
    logger.info(f"  Reading raw markdown from {raw_file.name}...")
    raw_text = raw_file.read_text(encoding="utf-8")
    
    # Read existing metadata from chunk file
    existing_data = json.loads(chunk_file.read_text(encoding="utf-8"))
    source_name = existing_data.get("part_name", raw_file.stem.replace("-", " ").title())
    
    # Extract sections from markdown
    section_chunks = extract_sections_from_markdown(raw_text, source_name)
    
    if not section_chunks:
        logger.warning(f"  No sections extracted from {raw_file.name}")
        return
    
    logger.info(f"  Extracted {len(section_chunks)} sections, generating summaries...")
    
    # Process each chunk with SAC
    enhanced_chunks = []
    for i, chunk_data in enumerate(section_chunks, 1):
        text = chunk_data['text']
        
        metadata = {
            "source": source_name,
            "part": source_name,
            "section_id": chunk_data.get('section_id'),
            "section_title": chunk_data.get('section_title'),
            "parent_section": None,
            "hierarchy_level": chunk_data.get('hierarchy_level', 1),
            "topic": None,
            "url": url,
            "scraped_at": datetime.utcnow().isoformat(),
        }
        
        logger.info(f"    Chunk {i}/{len(section_chunks)}: generating summary...")
        summary = await generate_chunk_summary(text, metadata, model)
        
        augmented_text = build_augmented_text(metadata, summary, text)
        
        enhanced_chunk = {
            "metadata": metadata,
            "text": text,
            "summary": summary,
            "augmented_text": augmented_text,
        }
        
        enhanced_chunks.append(enhanced_chunk)
    
    # Write updated chunk file
    output_data = {
        "url": url,
        "part_name": source_name,
        "scraped_at": datetime.utcnow().isoformat(),
        "chunk_count": len(enhanced_chunks),
        "chunks": enhanced_chunks,
    }
    
    chunk_file.write_text(
        json.dumps(output_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    logger.info(f"✓ Re-chunked {chunk_file.name} ({len(enhanced_chunks)} chunks)")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-chunk empty chunk files from raw markdown"
    )
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        default=Path("data/govuk-data/chunks"),
        help="Directory with chunk JSON files",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("data/govuk-data/raw"),
        help="Directory with raw markdown files",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="LLM model for litellm",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="https://www.gov.uk/guidance/immigration-rules/",
        help="Base URL for immigration rules",
    )
    
    args = parser.parse_args()
    
    chunks_dir: Path = args.chunks_dir
    raw_dir: Path = args.raw_dir
    model: str = args.model
    base_url: str = args.base_url
    
    # Find all empty chunk files
    empty_files = []
    for chunk_file in chunks_dir.glob("*.json"):
        if chunk_file.stem == "index":
            continue
        
        try:
            data = json.loads(chunk_file.read_text(encoding="utf-8"))
            chunk_count = len(data.get("chunks", []))
            if chunk_count == 0:
                empty_files.append(chunk_file)
        except Exception as e:
            logger.error(f"Error reading {chunk_file.name}: {e}")
    
    if not empty_files:
        logger.info("No empty chunk files found!")
        return
    
    logger.info(f"Found {len(empty_files)} empty chunk files to re-chunk")
    
    # Process each empty file
    async def process_all():
        for chunk_file in empty_files:
            # Find corresponding raw file
            raw_file = raw_dir / f"{chunk_file.stem}.md"
            
            if not raw_file.exists():
                logger.warning(f"⚠️  No raw file found for {chunk_file.name}, skipping")
                continue
            
            logger.info(f"\n📄 {chunk_file.name}")
            
            # Construct URL
            url = f"{base_url}{chunk_file.stem}"
            
            await rechunk_file(chunk_file, raw_file, model, url)
    
    await process_all()
    
    logger.info(f"\n✅ Done! Re-chunked {len(empty_files)} files")


if __name__ == "__main__":
    asyncio.run(main())
