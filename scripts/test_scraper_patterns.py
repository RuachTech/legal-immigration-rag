#!/usr/bin/env python3
"""
Test scraper pattern matching against sample data from real GOV.UK pages.

This script validates that the parsing regex and chunk creation logic
correctly identifies section IDs from the 3 sampled immigration rules pages.
"""

import sys
import re
from typing import Optional, Tuple

sys.path.insert(0, '/Users/olamide/Documents/ruach-projects/immigranta')

from data_pipeline.scrapers.govuk_jina_scraper import GovUKScraperJina


# Sample section ID patterns discovered from the 3 sampled pages
PATTERN_TEST_CASES = {
    "Appendix Skilled Worker - Main Sections": [
        ("# SW 1", "SW 1", "SW 1", 1),  # Main section
        ("# SW 2", "SW 2", "SW 2", 1),
        ("# SW 3", "SW 3", "SW 3", 1),
    ],
    "Appendix Skilled Worker - Subsections": [
        ("# SW 1.1", "SW 1.1", "SW 1", 2),  # Subsection
        ("# SW 1.2", "SW 1.2", "SW 1", 2),
        ("# SW 1.5", "SW 1.5", "SW 1", 2),
        ("# SW 2.1", "SW 2.1", "SW 2", 2),
        ("# SW 2.3", "SW 2.3", "SW 2", 2),
    ],
    "Appendix Skilled Worker - Variants with Suffixes": [
        ("# SW 1.1A", "SW 1.1A", "SW 1", 2),  # Variant with letter
        ("# SW 2.3ZA", "SW 2.3ZA", "SW 2", 2),  # Variant with ZA
        ("# SW 3.5Z", "SW 3.5Z", "SW 3", 2),  # Variant with Z
    ],
    "Appendix Skilled Worker - Special Sections": [
        ("# SW A1.1", "SW A1.1", "SW A1", 2),  # Special format (Health and Care)
        ("# SW A2.1", "SW A2.1", "SW A2", 2),
    ],
    "Part 1 - Paragraph Numbers": [
        ("# 7", "7", None, None),  # Part 1 uses simple paragraph numbers
        ("# 10", "10", None, None),
        ("# 10A", "10A", None, None),
        ("# 11B", "11B", None, None),
    ],
}


def test_section_id_parsing():
    """Test section ID parsing against known patterns."""
    scraper = GovUKScraperJina()
    
    all_passed = True
    total_tests = 0
    passed_tests = 0
    
    for category, test_cases in PATTERN_TEST_CASES.items():
        print(f"\n{'='*60}")
        print(f"Testing: {category}")
        print('='*60)
        
        for test_input, expected_id, expected_parent, expected_level in test_cases:
            total_tests += 1
            
            # Extract heading text (remove "# " prefix)
            heading_text = test_input.lstrip('# ').strip()
            
            # Parse section ID
            section_id, parent_section, hierarchy_level = scraper._parse_section_id(heading_text)
            
            # Check results
            id_match = section_id == expected_id
            parent_match = parent_section == expected_parent
            level_match = hierarchy_level == expected_level
            
            all_match = id_match and parent_match and level_match
            
            if all_match:
                passed_tests += 1
                status = "✓ PASS"
            else:
                status = "✗ FAIL"
                all_passed = False
            
            print(f"\n{status}: {test_input}")
            print(f"  Input: '{heading_text}'")
            
            if not id_match:
                print(f"  Section ID: Expected '{expected_id}', Got '{section_id}' ✗")
            else:
                print(f"  Section ID: '{section_id}' ✓")
            
            if expected_parent is not None and not parent_match:
                print(f"  Parent: Expected '{expected_parent}', Got '{parent_section}' ✗")
            elif expected_parent is not None:
                print(f"  Parent: '{parent_section}' ✓")
            else:
                print(f"  Parent: Not applicable (paragraph number)")
            
            if expected_level is not None and not level_match:
                print(f"  Level: Expected {expected_level}, Got {hierarchy_level} ✗")
            elif expected_level is not None:
                print(f"  Level: {hierarchy_level} ✓")
            else:
                print(f"  Level: Not applicable (paragraph number)")
    
    # Summary
    print(f"\n{'='*60}")
    print("TEST SUMMARY")
    print('='*60)
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
    
    if all_passed:
        print("\n✓ ALL TESTS PASSED!")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED - Review patterns above")
        return 1


def test_url_parsing():
    """Test URL to part name extraction."""
    scraper = GovUKScraperJina()
    
    test_urls = [
        (
            "https://www.gov.uk/guidance/immigration-rules/immigration-rules-appendix-skilled-worker",
            "Appendix Skilled Worker"
        ),
        (
            "https://www.gov.uk/guidance/immigration-rules/immigration-rules-part-1-leave-to-enter-or-stay-in-the-uk",
            "Part 1: Leave to Enter or Stay in the UK"
        ),
        (
            "https://www.gov.uk/guidance/immigration-rules/immigration-rules-introduction",
            "Introduction"
        ),
    ]
    
    print(f"\n{'='*60}")
    print("URL to Part Name Extraction Tests")
    print('='*60)
    
    all_passed = True
    for url, expected_name in test_urls:
        actual_name = scraper._extract_part_name_from_url(url)
        match = actual_name == expected_name
        
        status = "✓" if match else "✗"
        print(f"\n{status} {url}")
        print(f"  Expected: {expected_name}")
        print(f"  Got: {actual_name}")
        
        if not match:
            all_passed = False
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    print("\n" + "="*60)
    print("SCRAPER PATTERN VALIDATION TEST SUITE")
    print("="*60)
    
    # Run tests
    test1_result = test_section_id_parsing()
    test2_result = test_url_parsing()
    
    sys.exit(max(test1_result, test2_result))
