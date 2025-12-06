#!/usr/bin/env python3
"""
Flag chunks that need manual review based on quality indicators.

Quality issues detected:
- 404 errors in source content
- Extremely long text (> 50,000 chars)
- Empty or very short summaries
- Generic/low-quality summaries
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set


def should_flag_for_review(chunk: Dict, part_name: str) -> tuple[bool, List[str]]:
    """
    Determine if a chunk needs review.
    
    Returns:
        (should_flag, reasons) - boolean and list of reason strings
    """
    reasons = []
    
    # Check for 404 errors
    if "404" in chunk.get("text", "") or "Page not found" in chunk.get("text", ""):
        reasons.append("404_error")
    
    # Check for extremely long text (likely unprocessed definitions/glossaries)
    text_length = len(chunk.get("text", ""))
    if text_length > 50000:
        reasons.append(f"very_long_text_{text_length}_chars")
    
    # Check for empty or very short summaries
    summary = chunk.get("summary", "").strip()
    if not summary:
        reasons.append("empty_summary")
    elif len(summary) < 50:
        reasons.append("very_short_summary")
    
    # Check for generic summaries (common phrases that indicate low quality)
    generic_phrases = [
        "this provision applies to",
        "the provision in",
        "this section outlines",
        "this document provides",
    ]
    if any(phrase in summary.lower() for phrase in generic_phrases):
        if len(summary) < 200:  # Only flag if both generic AND short
            reasons.append("generic_summary")
    
    # Check metadata quality
    metadata = chunk.get("metadata", {})
    if not metadata.get("source"):
        reasons.append("missing_source")
    
    # Check for known problematic files
    problematic_files = [
        "appendix-statelessness",
        "appendix-eu-family-permit"
    ]
    if any(prob in part_name.lower() for prob in problematic_files):
        if "404" in chunk.get("text", "") or not chunk.get("summary"):
            reasons.append("known_problematic_file")
    
    return len(reasons) > 0, reasons


def flag_chunks_in_file(file_path: Path, dry_run: bool = False) -> Dict:
    """
    Add needs_review flag to chunks that need review.
    
    Returns summary stats.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    total_chunks = data.get("chunk_count", 0)
    flagged_count = 0
    reasons_summary = {}
    
    for chunk in data.get("chunks", []):
        should_flag, reasons = should_flag_for_review(chunk, data.get("part_name", ""))
        
        if should_flag:
            chunk["needs_review"] = True
            chunk["review_reasons"] = reasons
            flagged_count += 1
            
            # Track reasons
            for reason in reasons:
                reasons_summary[reason] = reasons_summary.get(reason, 0) + 1
        else:
            # Ensure flag is explicitly false if not flagged
            chunk["needs_review"] = False
            chunk.pop("review_reasons", None)  # Remove if exists
    
    # Write back if not dry run
    if not dry_run:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    
    return {
        "file": file_path.name,
        "total_chunks": total_chunks,
        "flagged_chunks": flagged_count,
        "reasons": reasons_summary
    }


def main():
    chunks_dir = Path("data/govuk-data/chunks")
    
    if not chunks_dir.exists():
        print(f"Error: {chunks_dir} not found")
        sys.exit(1)
    
    # Process all chunk files
    all_stats = []
    total_flagged = 0
    total_chunks = 0
    all_reasons = {}
    
    chunk_files = sorted(chunks_dir.glob("*.json"))
    
    print(f"Processing {len(chunk_files)} chunk files...")
    print("-" * 80)
    
    for chunk_file in chunk_files:
        stats = flag_chunks_in_file(chunk_file, dry_run=False)
        all_stats.append(stats)
        
        total_chunks += stats["total_chunks"]
        total_flagged += stats["flagged_chunks"]
        
        # Merge reasons
        for reason, count in stats["reasons"].items():
            all_reasons[reason] = all_reasons.get(reason, 0) + count
        
        # Print files with flagged chunks
        if stats["flagged_chunks"] > 0:
            pct = (stats["flagged_chunks"] / stats["total_chunks"] * 100) if stats["total_chunks"] > 0 else 0
            print(f"  {stats['file']}: {stats['flagged_chunks']}/{stats['total_chunks']} chunks flagged ({pct:.1f}%)")
            for reason, count in stats["reasons"].items():
                print(f"    - {reason}: {count}")
    
    print("-" * 80)
    print(f"\nSummary:")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Flagged for review: {total_flagged} ({total_flagged/total_chunks*100:.1f}%)")
    print(f"\nReasons breakdown:")
    for reason, count in sorted(all_reasons.items(), key=lambda x: x[1], reverse=True):
        print(f"  {reason}: {count}")
    
    # Print files that should be excluded entirely
    print(f"\nFiles with >50% flagged chunks (consider excluding):")
    for stats in all_stats:
        if stats["total_chunks"] > 0:
            pct = stats["flagged_chunks"] / stats["total_chunks"]
            if pct > 0.5:
                print(f"  - {stats['file']} ({pct*100:.1f}% flagged)")


if __name__ == "__main__":
    main()
