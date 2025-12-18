"""Enhance existing chunk files with Summary-Augmented Chunking (SAC).

This script reads your existing chunk JSON files, generates LLM summaries for
EACH chunk (not document-level), enriches null metadata fields, and creates
augmented_text for embedding while preserving all original structure.

Usage:
    export GEMINI_API_KEY=your_key_here
    uv run python data_pipeline/processing/enhance_chunks_with_sac.py
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import litellm
    from litellm import RateLimitError
except ImportError:
    raise ImportError("litellm required: uv add litellm")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Rate limiting - gemini-2.0-flash-thinking-exp has 1000 req/min
RATE_LIMIT_DELAY = 0.1  # seconds between calls (for 1000 req/min limit)


async def generate_chunk_summary(
    chunk_text: str,
    metadata: Dict[str, Any],
    model: str = "gpt-4o-mini",
    max_retries: int = 3,
) -> str:
    """Generate a legal-focused summary for a single chunk.

    Prompt captures:
    - Who/what the provision applies to
    - Key requirement, right, or obligation
    - Critical conditions or exceptions
    - 2-3 sentences, under 100 tokens
    """
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

1. Who or what this provision applies to (e.g., "Skilled Workers", "applicants", "sponsors", students)
2. The key requirement, right, obligation, or process being described
3. Any critical conditions, exceptions, or thresholds

Context: {context}

Chunk text:
{chunk_text[:1500]}

Legal summary:"""

    for attempt in range(max_retries):
        try:
            await asyncio.sleep(RATE_LIMIT_DELAY)  # Rate limiting
            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=120,
            )

            if isinstance(response, dict):
                summary = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                summary = getattr(
                    getattr(response, "choices", [None])[0],
                    "message",
                    None,
                )
                summary = getattr(summary, "content", "") if summary else ""

            return (summary or "").strip()
        except RateLimitError as e:
            if attempt < max_retries - 1:
                wait_time = 20  # Gemini suggests 18s retry delay
                logger.warning(
                    f"Rate limit hit, waiting {wait_time}s... (attempt {attempt+1}/{max_retries})"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Rate limit exceeded after {max_retries} attempts: {e}")
                return ""
        except Exception as e:
            logger.error(f"LLM summarization failed: {e}")
            return ""

    return ""


async def enrich_metadata_fields(
    chunk_text: str,
    metadata: Dict[str, Any],
    model: str = "gpt-4o-mini",
    max_retries: int = 3,
) -> Dict[str, Optional[str]]:
    """Use LLM to infer missing section_id, section_title, or topic if null."""
    section_id = metadata.get("section_id")
    section_title = metadata.get("section_title")
    topic = metadata.get("topic")

    # Only call LLM if at least one field is missing
    if section_id and section_title and topic:
        return {"section_id": section_id, "section_title": section_title, "topic": topic}

    prompt = f"""Analyze this UK Immigration Rules chunk and extract:

1. section_id: The rule/paragraph reference (e.g., "SW 3.1", "AD 1.2")
2. section_title: A brief heading describing the section (e.g., "Entry requirements for students")
3. topic: A single category word (e.g., "eligibility", "financial", "points", "sponsorship", "english-language")

Chunk text:
{chunk_text[:1000]}

Respond ONLY in this JSON format:
{{"section_id": "value", "section_title": "value", "topic": "value"}}"""

    for attempt in range(max_retries):
        try:
            await asyncio.sleep(RATE_LIMIT_DELAY)
            response = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=80,
                response_format={"type": "json_object"},
            )

            if isinstance(response, dict):
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            else:
                msg = getattr(getattr(response, "choices", [None])[0], "message", None)
                content = getattr(msg, "content", "{}") if msg else "{}"

            parsed = json.loads(content)
            return {
                "section_id": parsed.get("section_id") or section_id,
                "section_title": parsed.get("section_title") or section_title,
                "topic": parsed.get("topic") or topic,
            }
        except RateLimitError:
            if attempt < max_retries - 1:
                wait_time = 20
                logger.warning(f"Rate limit hit, waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.warning("Metadata enrichment rate limited, using originals")
                return {"section_id": section_id, "section_title": section_title, "topic": topic}
        except Exception as e:
            logger.warning(f"Metadata enrichment failed: {e}")
            return {"section_id": section_id, "section_title": section_title, "topic": topic}

    return {"section_id": section_id, "section_title": section_title, "topic": topic}


async def enhance_chunk_file(
    input_path: Path,
    output_path: Path,
    model: str,
    enrich_metadata: bool,
    skip_existing: bool = True,
) -> None:
    """Process one chunk JSON file: add summaries and augmented_text."""
    data = json.loads(input_path.read_text(encoding="utf-8"))
    chunks = data.get("chunks", [])

    if not chunks:
        logger.warning(f"No chunks in {input_path.name}, skipping")
        return

    # Check if file already processed (resume capability)
    if skip_existing and output_path.exists():
        existing_data = json.loads(output_path.read_text(encoding="utf-8"))
        existing_chunks = existing_data.get("chunks", [])
        if existing_chunks and "summary" in existing_chunks[0]:
            logger.info(f"⏭️  Skipping {input_path.name} (already enhanced)")
            return

    enhanced_chunks = []
    for i, chunk in enumerate(chunks, 1):
        text = chunk.get("text", "")
        metadata = chunk.get("metadata", {})

        # Generate chunk-specific summary
        logger.info(f"  Chunk {i}/{len(chunks)}: generating summary...")
        summary = await generate_chunk_summary(text, metadata, model)

        # Enrich null metadata if requested
        if enrich_metadata:
            enriched = await enrich_metadata_fields(text, metadata, model)
            metadata["section_id"] = enriched["section_id"]
            metadata["section_title"] = enriched["section_title"]
            metadata["topic"] = enriched["topic"]

        # Create metadata header for augmented text
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

        # Create augmented text: metadata header + summary + original text
        parts = []
        if metadata_header:
            parts.append(metadata_header)
        if summary:
            parts.append(f"\nSummary: {summary}")
        parts.append(f"\n{text}")

        augmented_text = "\n".join(parts) if parts else text

        # Build enhanced chunk preserving all original fields
        enhanced_chunk = {
            "metadata": metadata,
            "text": text,
            "summary": summary,
            "augmented_text": augmented_text,
        }

        enhanced_chunks.append(enhanced_chunk)

    # Write output with same top-level structure
    output_data = {
        "url": data.get("url"),
        "part_name": data.get("part_name"),
        "scraped_at": data.get("scraped_at"),
        "chunk_count": len(enhanced_chunks),
        "chunks": enhanced_chunks,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        f"✓ Enhanced {input_path.name} → {output_path.name} ({len(enhanced_chunks)} chunks)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enhance chunk files with SAC (chunk-level summaries)"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/govuk-data/chunks"),
        help="Directory with existing chunk JSON files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/govuk-data/chunks-sac"),
        help="Directory to write SAC-enhanced chunks",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4.1-nano",
        help="LLM model for litellm",
    )
    parser.add_argument(
        "--enrich-metadata",
        action="store_true",
        help="Use LLM to fill null section_id/section_title/topic fields",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only first N files (for testing)",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Modify chunk files in place instead of creating new output directory",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip files that already have summaries (resume capability)",
    )

    args = parser.parse_args()

    input_dir: Path = args.input_dir
    output_dir: Path = args.output_dir if not args.in_place else args.input_dir
    model: str = args.model
    enrich_metadata: bool = args.enrich_metadata
    limit: Optional[int] = args.limit
    skip_existing: bool = args.skip_existing

    files = sorted([p for p in input_dir.glob("*.json") if p.stem != "index"])
    if not files:
        raise SystemExit(f"No JSON files in {input_dir}")

    if limit:
        files = files[:limit]
        logger.info(f"Processing {len(files)} files (limit={limit})")
    else:
        logger.info(f"Processing {len(files)} files")

    if args.in_place:
        logger.info(f"⚠️  IN-PLACE MODE: Files will be modified directly in {input_dir}")

    async def process_all_files():
        for path in files:
            logger.info(f"\n📄 {path.name}")
            out_path = output_dir / path.name
            await enhance_chunk_file(path, out_path, model, enrich_metadata, skip_existing)

    asyncio.run(process_all_files())

    mode_msg = "in place" if args.in_place else f"in {output_dir}"
    logger.info(f"\n✅ Done! Enhanced chunks {mode_msg}")


if __name__ == "__main__":
    main()
