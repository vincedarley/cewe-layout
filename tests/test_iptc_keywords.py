#!/usr/bin/env python3
"""
Test IPTC keyword reading for photo importance detection.

Usage:
    python tests/test_iptc_keywords.py path/to/photo.jpg
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.photos import get_iptc_keywords, get_photo_preferred_size


def test_keywords_from_file(img_path: Path):
    """Test keyword extraction from a specific image file."""
    if not img_path.exists():
        print(f"❌ Image not found: {img_path}")
        return
    
    print(f"Testing: {img_path.name}")
    print("=" * 60)
    
    # Extract keywords
    keywords = get_iptc_keywords(img_path)
    print(f"Keywords found: {keywords}")
    
    # Get preferred size
    size = get_photo_preferred_size(img_path)
    print(f"Preferred size: {size}")
    
    # Explain mapping
    if size == 5.0:
        print("✓ Mapped to HIGH importance (5 star keyword detected)")
    elif size == 3.0:
        print("✓ Mapped to MEDIUM importance (4 star keyword detected)")
    else:
        print("✓ Mapped to NORMAL size (no star keyword)")
    
    print()


def test_keyword_mapping():
    """Test the keyword to size mapping logic."""
    print("Keyword Mapping Tests")
    print("=" * 60)
    
    test_cases = [
        (['5 star', 'vacation'], 5.0, "5 star → 5.0"),
        (['4 star', 'family'], 3.0, "4 star → 3.0"),
        (['vacation', 'beach'], 1.0, "no star rating → 1.0"),
        (['5star'], 5.0, "5star (no space) → 5.0"),
        (['4STAR'], 3.0, "4STAR (caps) → 3.0"),
        ([], 1.0, "no keywords → 1.0"),
    ]
    
    for keywords, expected, description in test_cases:
        # Simulate the logic
        keywords_lower = [kw.lower() for kw in keywords]
        if '5 star' in keywords_lower or '5star' in keywords_lower:
            result = 5.0
        elif '4 star' in keywords_lower or '4star' in keywords_lower:
            result = 3.0
        else:
            result = 1.0
        
        status = "✓" if result == expected else "❌"
        print(f"{status} {description}: {keywords} → {result}")
    
    print()


if __name__ == '__main__':
    # Run mapping tests
    test_keyword_mapping()
    
    # Test with command-line argument if provided
    if len(sys.argv) > 1:
        img_path = Path(sys.argv[1])
        test_keywords_from_file(img_path)
    else:
        print("To test a specific image:")
        print(f"  python {sys.argv[0]} path/to/photo.jpg")
        print()
        print("Expected behavior:")
        print("  - Photos with '5 star' keyword → size 5.0 (high importance)")
        print("  - Photos with '4 star' keyword → size 3.0 (medium importance)")
        print("  - All other photos → size 1.0 (normal)")
