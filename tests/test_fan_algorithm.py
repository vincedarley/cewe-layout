#!/usr/bin/env python3
"""
Test Fan-GA algorithm on real page data.

This test reproduces the error from the GUI and helps debug the Fan algorithm.
"""
import sys
from pathlib import Path

# Add parent directory to path so we can import cewe_layout
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.algorithms.fan_layout import FanLayoutAlgorithm
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.collage_wrapper import generate_layout_for_page


def test_fan_algorithm_simple():
    """Test Fan algorithm with simple rectangles."""
    print("Testing Fan algorithm with simple rectangles...")
    
    algo = FanLayoutAlgorithm()
    
    # Create input rectangles (representing 3 photos with different aspect ratios)
    rectangles = [
        LayoutRectangle(item_id="0", width=1920.0, height=1080.0, preferred_size=1.0),  # 16:9
        LayoutRectangle(item_id="1", width=1080.0, height=1080.0, preferred_size=1.0),  # 1:1
        LayoutRectangle(item_id="2", width=1080.0, height=1440.0, preferred_size=1.0),  # 3:4
    ]
    
    # Run layout
    page_width = 2970.0
    page_height = 4200.0
    success, result_rects, error_msg = algo.generate_layout(
        page_width, page_height, rectangles
    )
    
    # Check results
    if not success:
        print(f"  ❌ Layout failed: {error_msg}")
        import traceback
        traceback.print_exc()
        return False
    
    print(f"  ✅ Layout succeeded with {len(result_rects)} rectangles")
    
    # Check that all rectangles have positions set
    for i, rect in enumerate(result_rects):
        print(f"    Rectangle {i}: x={rect.x}, y={rect.y}, w={rect.width}, h={rect.height}, actual_size={rect.actual_size}")
        assert rect.x is not None, f"Rectangle {i} missing x"
        assert rect.y is not None, f"Rectangle {i} missing y"
        assert rect.width > 0, f"Rectangle {i} has zero width"
        assert rect.height > 0, f"Rectangle {i} has zero height"
    
    return True


def test_fan_algorithm_page3():
    """Test Fan algorithm on page 3 of the test album."""
    print("\nTesting Fan algorithm on page 3 of test album...")
    
    # Parse the test album (try multiple possible locations)
    possible_paths = [
        Path(__file__).parent.parent.parent / "Album-2022-tester.xmcf",
        Path(__file__).parent.parent.parent.parent / "Album-2022-tester.xmcf",
    ]
    
    album_path = None
    for path in possible_paths:
        if path.exists():
            album_path = path
            break
    
    if album_path is None:
        print(f"  ⚠️  Test album not found (tried {len(possible_paths)} locations)")
        return True  # Skip test
    
    mcf_root = parse_mcf_from_path(str(album_path))
    pages = extract_pages_info(mcf_root)
    
    # Find page 3
    page3_info = None
    for pageno, info in pages:
        if pageno == 3:
            page3_info = info
            break
    
    if page3_info is None:
        print("  ⚠️  Page 3 not found in test album")
        return True  # Skip test
    
    photos = page3_info.get('photos', [])
    print(f"  Page 3 has {len(photos)} photos")
    
    if not photos:
        print("  ⚠️  Page 3 has no photos")
        return True  # Skip test
    
    # Get page dimensions
    page_width = page3_info.get('page_width', 2100.0)
    page_height = page3_info.get('page_height', 2970.0)
    
    print(f"  Page dimensions: {page_width} x {page_height}")
    
    # Use the wrapper to run the algorithm
    algo = FanLayoutAlgorithm()
    mcf_base_folder = str(album_path)
    
    try:
        success, updated_photos, updated_texts, error_msg = generate_layout_for_page(
            photos, page_width, page_height, mcf_base_folder,
            algorithm=algo, edge_gap=0.0, internal_gap=0.0, texts=[]
        )
        
        if not success:
            print(f"  ❌ Layout generation failed: {error_msg}")
            return False
        
        print(f"  ✅ Layout succeeded with {len(updated_photos)} photos")
        
        # Show results
        for i, photo in enumerate(updated_photos):
            print(f"    Photo {i}: left={photo.get('area_left')}, top={photo.get('area_top')}, "
                  f"w={photo.get('area_width')}, h={photo.get('area_height')}")
        
        return True
    
    except Exception as e:
        print(f"  ❌ Exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Test: Fan-GA Algorithm")
    print("=" * 60)
    
    success1 = test_fan_algorithm_simple()
    success2 = test_fan_algorithm_page3()
    
    print()
    print("=" * 60)
    if success1 and success2:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
        sys.exit(1)
    print("=" * 60)
