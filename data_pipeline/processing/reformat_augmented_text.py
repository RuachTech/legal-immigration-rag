"""Reformat augmented_text fields to include metadata header.

This script updates existing chunk files to add structured metadata headers
to the augmented_text field, following the format:

Document: [source]
Part: [part]
Section ID: [section_id]
Section: [section_title]
Topic: [topic]

Summary: [summary]

[original text]
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


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


def reformat_chunk_file(file_path: Path, in_place: bool = True) -> None:
    """Reformat augmented_text in a single chunk file."""
    data = json.loads(file_path.read_text(encoding="utf-8"))
    chunks = data.get("chunks", [])

    if not chunks:
        logger.warning(f"No chunks in {file_path.name}, skipping")
        return

    # Check if chunks have summary field (already enhanced)
    if "summary" not in chunks[0]:
        logger.warning(f"No summary field in {file_path.name}, skipping (not enhanced yet)")
        return

    reformatted_chunks = []
    for chunk in chunks:
        metadata = chunk.get("metadata", {})
        text = chunk.get("text", "")
        summary = chunk.get("summary", "")

        # Build new augmented text with metadata header
        augmented_text = build_augmented_text(metadata, summary, text)

        # Update chunk with new augmented_text
        reformatted_chunk = {
            "metadata": metadata,
            "text": text,
            "summary": summary,
            "augmented_text": augmented_text,
        }
        reformatted_chunks.append(reformatted_chunk)

    # Write updated file
    output_data = {
        "url": data.get("url"),
        "part_name": data.get("part_name"),
        "scraped_at": data.get("scraped_at"),
        "chunk_count": len(reformatted_chunks),
        "chunks": reformatted_chunks,
    }

    if in_place:
        file_path.write_text(
            json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"✓ Reformatted {file_path.name} ({len(reformatted_chunks)} chunks)")
    else:
        output_path = file_path.parent / f"reformatted_{file_path.name}"
        output_path.write_text(
            json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"✓ Reformatted {file_path.name} → reformatted_{file_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reformat augmented_text fields to include metadata headers"
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path("data/govuk-data/chunks"),
        help="Directory with chunk JSON files to reformat",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        default=True,
        help="Modify files in place (default: True)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Process only first N files (for testing)",
    )

    args = parser.parse_args()

    input_dir: Path = args.input_dir
    in_place: bool = args.in_place
    limit: int = args.limit

    files = sorted([p for p in input_dir.glob("*.json") if p.stem != "index"])
    if not files:
        raise SystemExit(f"No JSON files in {input_dir}")

    if limit:
        files = files[:limit]
        logger.info(f"Processing {len(files)} files (limit={limit})")
    else:
        logger.info(f"Processing {len(files)} files")

    if in_place:
        logger.info(f"⚠️  IN-PLACE MODE: Files will be modified directly in {input_dir}")

    for file_path in files:
        logger.info(f"\n📄 {file_path.name}")
        reformat_chunk_file(file_path, in_place)

    logger.info(f"\n✅ Done! Reformatted {len(files)} files")


if __name__ == "__main__":
    main()
