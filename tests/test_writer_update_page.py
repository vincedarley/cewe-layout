"""Test update_page_layout function."""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.mcf_io.mcf_layout_change import update_page_layout
from cewe_layout.mcf_io.mcf_parser import parse_mcf_from_path, extract_pages_info


def test_update_page_layout():
    """Test updating a page layout and verify the changes."""
    # Use Test-album.xmcf as test data
    mcf_path = Path(__file__).parent.parent.parent / 'Test-album.xmcf' / 'data.mcf'
    
    if not mcf_path.exists():
        print(f"Test album not found at {mcf_path}")
        return
    
    # Parse original file to get a page
    root = parse_mcf_from_path(str(mcf_path))
    pages = extract_pages_info(root)
    
    if not pages:
        print("No pages found in test album")
        return
    
    # Get first page with photos
    test_pageno = None
    original_photos = None
    original_texts = None
    
    for pageno, info in pages:
        photos = info.get('photos', [])
        texts = info.get('texts', [])
        if photos:
            test_pageno = pageno
            original_photos = photos
            original_texts = texts
            break
    
    if test_pageno is None:
        print("No pages with photos found")
        return
    
    print(f"\nTesting page {test_pageno}")
    print(f"Original layout: {len(original_photos)} photos, {len(original_texts)} texts")
    
    # Create modified layout (shift all photos by 10 units)
    modified_photos = []
    for p in original_photos:
        modified = p.copy()
        modified['area_left'] = (modified.get('area_left', 0) or 0) + 10.0
        modified['area_top'] = (modified.get('area_top', 0) or 0) + 10.0
        modified_photos.append(modified)
    
    modified_texts = original_texts.copy()  # Keep texts unchanged
    
    print(f"\nWriting modified layout (photos shifted +10 units)...")
    
    # Write modified layout (will create backup)
    result = update_page_layout(
        str(mcf_path), test_pageno, modified_photos, modified_texts, make_backup=True
    )
    
    print(f"Write successful!")
    print(f"  Modified: {result['modified_photos']} photos, {result['modified_texts']} texts")
    print(f"  Backup: {result['backup_path']}")
    
    # Parse the updated file and verify changes
    root_updated = parse_mcf_from_path(str(mcf_path))
    pages_updated = extract_pages_info(root_updated)
    
    updated_page_info = None
    for pageno, info in pages_updated:
        if pageno == test_pageno:
            updated_page_info = info
            break
    
    if updated_page_info is None:
        print("ERROR: Could not find updated page")
        return
    
    updated_photos = updated_page_info.get('photos', [])
    
    print(f"\nVerifying changes...")
    if len(updated_photos) != len(original_photos):
        print(f"ERROR: Photo count changed ({len(original_photos)} → {len(updated_photos)})")
        return
    
    # Check first photo position
    orig_left = original_photos[0].get('area_left', 0) or 0
    updated_left = updated_photos[0].get('area_left', 0) or 0
    expected_left = orig_left + 10.0
    
    print(f"First photo position:")
    print(f"  Original: {orig_left:.2f}")
    print(f"  Expected: {expected_left:.2f}")
    print(f"  Updated:  {updated_left:.2f}")
    print(f"  Difference: {abs(updated_left - expected_left):.2f}")
    
    if abs(updated_left - expected_left) < 0.1:
        print("\n✓ Test PASSED: Layout was correctly updated")
    else:
        print("\n✗ Test FAILED: Layout update did not match expected values")
    
    print(f"\nNote: Original file backed up to {result['backup_path']}")
    print(f"To restore: mv {result['backup_path']} {mcf_path}")


if __name__ == '__main__':
    test_update_page_layout()
