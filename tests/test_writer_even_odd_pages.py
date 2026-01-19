"""Test update_page_layout for even and odd pages (spread handling)."""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.mcf_io.mcf_layout_change import update_page_layout
from cewe_layout.mcf_io.mcf_parser import parse_mcf_from_path, extract_pages_info


def test_page(mcf_path, pageno, page_info):
    """Test a single page update."""
    photos = page_info.get('photos', [])
    texts = page_info.get('texts', [])
    origin_left = page_info.get('origin_left', 0.0)
    
    print(f"\n{'='*70}")
    print(f"Testing page {pageno}")
    print(f"{'='*70}")
    print(f"Original layout: {len(photos)} photos, {len(texts)} texts")
    print(f"Origin left: {origin_left:.2f} (page is on {'RIGHT' if origin_left > 0 else 'LEFT'} side of spread)")
    
    if not photos:
        print("Skipping: no photos on this page")
        return True
    
    # Show original positions
    print(f"\nOriginal photo positions:")
    for i, p in enumerate(photos[:3]):  # Show first 3
        print(f"  Photo {i+1}: left={p.get('area_left', 0):.2f}, top={p.get('area_top', 0):.2f}")
    if len(photos) > 3:
        print(f"  ... and {len(photos)-3} more")
    
    # Create modified layout (shift by 5 units to make change visible)
    modified_photos = []
    for p in photos:
        modified = p.copy()
        modified['area_left'] = (modified.get('area_left', 0) or 0) + 5.0
        modified['area_top'] = (modified.get('area_top', 0) or 0) + 5.0
        modified_photos.append(modified)
    
    modified_texts = texts.copy()
    
    # Write modified layout
    print(f"\nWriting modified layout (photos shifted +5 units)...")
    result = update_page_layout(
        str(mcf_path), pageno, modified_photos, modified_texts, make_backup=True
    )
    
    print(f"Write result:")
    print(f"  Modified: {result['modified_photos']} photos, {result['modified_texts']} texts")
    print(f"  Backup: {os.path.basename(result['backup_path'])}")
    
    # Verify
    if result['modified_photos'] != len(photos):
        print(f"✗ FAILED: Expected to modify {len(photos)} photos, but modified {result['modified_photos']}")
        return False
    
    # Parse the updated file
    root_updated = parse_mcf_from_path(str(mcf_path))
    pages_updated = extract_pages_info(root_updated)
    
    updated_page_info = None
    for pn, info in pages_updated:
        if pn == pageno:
            updated_page_info = info
            break
    
    if updated_page_info is None:
        print(f"✗ FAILED: Could not find updated page {pageno}")
        return False
    
    updated_photos = updated_page_info.get('photos', [])
    
    if len(updated_photos) != len(photos):
        print(f"✗ FAILED: Photo count changed ({len(photos)} → {len(updated_photos)})")
        return False
    
    # Verify first photo
    orig_left = photos[0].get('area_left', 0) or 0
    updated_left = updated_photos[0].get('area_left', 0) or 0
    expected_left = orig_left + 5.0
    diff = abs(updated_left - expected_left)
    
    print(f"\nFirst photo verification:")
    print(f"  Original: {orig_left:.2f}")
    print(f"  Expected: {expected_left:.2f}")
    print(f"  Updated:  {updated_left:.2f}")
    print(f"  Difference: {diff:.2f}")
    
    if diff < 0.1:
        print(f"✓ PASSED: Page {pageno} correctly updated")
        return True
    else:
        print(f"✗ FAILED: Position mismatch")
        return False


def main():
    """Test even and odd pages."""
    mcf_path = Path(__file__).parent.parent.parent / 'Test-album.xmcf' / 'data.mcf'
    
    if not mcf_path.exists():
        print(f"Test album not found at {mcf_path}")
        return
    
    # Parse original file
    root = parse_mcf_from_path(str(mcf_path))
    pages = extract_pages_info(root)
    
    if not pages:
        print("No pages found in test album")
        return
    
    print(f"\nFound {len(pages)} pages in album")
    
    # Test a few pages with photos (both even and odd)
    test_pages = []
    even_pages = []
    odd_pages = []
    
    for pageno, info in pages:
        photos = info.get('photos', [])
        if photos and len(test_pages) < 4:  # Test first 4 pages with photos
            test_pages.append((pageno, info))
            if pageno % 2 == 0:
                even_pages.append(pageno)
            else:
                odd_pages.append(pageno)
    
    if not test_pages:
        print("No pages with photos found")
        return
    
    print(f"\nTesting {len(test_pages)} pages:")
    print(f"  Even pages: {even_pages}")
    print(f"  Odd pages: {odd_pages}")
    
    results = []
    for pageno, info in test_pages:
        passed = test_page(mcf_path, pageno, info)
        results.append((pageno, passed))
        
        # Restore from backup for next test
        backup_files = sorted([f for f in os.listdir(mcf_path.parent) if f.startswith('data-') and f.endswith('.mcf')])
        if backup_files:
            latest_backup = mcf_path.parent / backup_files[-1]
            os.rename(latest_backup, mcf_path)
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for pageno, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        page_type = "EVEN" if pageno % 2 == 0 else "ODD"
        print(f"  Page {pageno:2d} ({page_type}): {status}")
    
    print(f"\nTotal: {passed_count}/{total_count} passed")
    
    if passed_count == total_count:
        print("\n✓ ALL TESTS PASSED")
        print("Writer correctly handles even and odd pages in spreads!")
    else:
        print(f"\n✗ {total_count - passed_count} TESTS FAILED")


if __name__ == '__main__':
    main()
