#!/usr/bin/env python3
"""
Test Gridify algorithm.

Tests the grid-snapping layout algorithm that aligns all photo corners
to a regular grid based on the smallest photo's dimensions.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.gridify import GridifyAlgorithm
from cewe_layout.algorithms.base import LayoutRectangle


def test_basic_gridify():
    """Test basic gridify functionality."""
    print("\n" + "="*60)
    print("Testing Gridify Algorithm - Basic")
    print("="*60)
    
    # Page dimensions
    page_width = 2100.0
    page_height = 2970.0
    
    # Create rectangles with slightly off-grid positions
    # Smallest photo is 700x700 (fits 3x4.24 times)
    # Should create a 3x4 grid: spacing = 700x742.5
    rectangles = [
        LayoutRectangle(item_id="photo_0", width=710.0, height=705.0, x=5.0, y=10.0, preferred_size=1.0),
        LayoutRectangle(item_id="photo_1", width=1405.0, height=1490.0, x=705.0, y=0.0, preferred_size=2.0),
        LayoutRectangle(item_id="photo_2", width=695.0, height=1475.0, x=0.0, y=1480.0, preferred_size=2.0),
        LayoutRectangle(item_id="photo_3", width=1410.0, height=705.0, x=700.0, y=2260.0, preferred_size=1.0),
    ]
    
    print(f"Page: {page_width} x {page_height}")
    print(f"Smallest photo: {min(rectangles, key=lambda r: r.width * r.height).width} x {min(rectangles, key=lambda r: r.width * r.height).height}")
    
    # Run algorithm
    algo = GridifyAlgorithm()
    success, result, error = algo.generate_layout(page_width, page_height, rectangles)
    
    if not success:
        print(f"FAILED: {error}")
        return False
    
    print(f"\n✅ Success!")
    
    # Calculate expected grid
    smallest = min(rectangles, key=lambda r: r.width * r.height)
    grid_cols = round(page_width / smallest.width)
    grid_rows = round(page_height / smallest.height)
    grid_x = page_width / grid_cols
    grid_y = page_height / grid_rows
    
    print(f"\nGrid: {grid_cols} cols x {grid_rows} rows")
    print(f"Grid spacing: {grid_x:.2f} x {grid_y:.2f}")
    
    print("\nSnapped rectangles:")
    for rect in result:
        print(f"  {rect.item_id}: ({rect.x:.2f}, {rect.y:.2f}) {rect.width:.2f} x {rect.height:.2f}")
        
        # Verify all corners are on grid
        left_on_grid = abs(rect.x % grid_x) < 0.01 or abs(rect.x % grid_x - grid_x) < 0.01
        top_on_grid = abs(rect.y % grid_y) < 0.01 or abs(rect.y % grid_y - grid_y) < 0.01
        right_on_grid = abs((rect.x + rect.width) % grid_x) < 0.01 or abs((rect.x + rect.width) % grid_x - grid_x) < 0.01
        bottom_on_grid = abs((rect.y + rect.height) % grid_y) < 0.01 or abs((rect.y + rect.height) % grid_y - grid_y) < 0.01
        
        if not (left_on_grid and top_on_grid and right_on_grid and bottom_on_grid):
            print(f"    ⚠️  Not all corners on grid!")
            print(f"       left={left_on_grid}, top={top_on_grid}, right={right_on_grid}, bottom={bottom_on_grid}")
        else:
            print(f"    ✅ All corners on grid")
    
    return True


def test_gridify_with_text():
    """Test gridify with mixed photos and text blocks."""
    print("\n" + "="*60)
    print("Testing Gridify Algorithm - With Text Blocks")
    print("="*60)
    
    # Page dimensions
    page_width = 2100.0
    page_height = 2970.0
    
    # Mix of photos and text
    rectangles = [
        LayoutRectangle(item_id="photo_0", width=1050.0, height=1050.0, x=0.0, y=0.0, 
                       preferred_size=1.5, preserve_aspect_ratio=True),
        LayoutRectangle(item_id="text_0", width=1045.0, height=485.0, x=1055.0, y=0.0, 
                       preferred_size=0.5, preserve_aspect_ratio=False),
        LayoutRectangle(item_id="photo_1", width=1050.0, height=1430.0, x=1050.0, y=490.0, 
                       preferred_size=2.0, preserve_aspect_ratio=True),
        LayoutRectangle(item_id="photo_2", width=2095.0, height=1045.0, x=5.0, y=1920.0, 
                       preferred_size=1.5, preserve_aspect_ratio=True),
    ]
    
    print(f"Page: {page_width} x {page_height}")
    print(f"Photos: {len([r for r in rectangles if r.preserve_aspect_ratio])}")
    print(f"Text blocks: {len([r for r in rectangles if not r.preserve_aspect_ratio])}")
    
    # Run algorithm
    algo = GridifyAlgorithm()
    success, result, error = algo.generate_layout(page_width, page_height, rectangles)
    
    if not success:
        print(f"FAILED: {error}")
        return False
    
    print(f"\n✅ Success!")
    
    # Grid should be based on smallest photo only
    photos = [r for r in rectangles if r.preserve_aspect_ratio]
    smallest = min(photos, key=lambda r: r.width * r.height)
    grid_cols = round(page_width / smallest.width)
    grid_rows = round(page_height / smallest.height)
    grid_x = page_width / grid_cols
    grid_y = page_height / grid_rows
    
    print(f"\nGrid based on smallest photo: {smallest.item_id}")
    print(f"Grid: {grid_cols} cols x {grid_rows} rows")
    print(f"Grid spacing: {grid_x:.2f} x {grid_y:.2f}")
    
    print("\nSnapped rectangles:")
    for rect in result:
        print(f"  {rect.item_id}: ({rect.x:.2f}, {rect.y:.2f}) {rect.width:.2f} x {rect.height:.2f}")
    
    return True


def test_no_photos():
    """Test gridify with only text blocks (should return unchanged)."""
    print("\n" + "="*60)
    print("Testing Gridify Algorithm - No Photos")
    print("="*60)
    
    rectangles = [
        LayoutRectangle(item_id="text_0", width=1000.0, height=500.0, x=0.0, y=0.0, 
                       preferred_size=1.0, preserve_aspect_ratio=False),
        LayoutRectangle(item_id="text_1", width=1000.0, height=500.0, x=1100.0, y=0.0, 
                       preferred_size=1.0, preserve_aspect_ratio=False),
    ]
    
    algo = GridifyAlgorithm()
    success, result, error = algo.generate_layout(2100.0, 2970.0, rectangles)
    
    if success:
        print("✅ Success - returned unchanged (no photos)")
        return True
    else:
        print(f"FAILED: {error}")
        return False


if __name__ == '__main__':
    all_passed = True
    
    all_passed &= test_basic_gridify()
    all_passed &= test_gridify_with_text()
    all_passed &= test_no_photos()
    
    print("\n" + "="*60)
    if all_passed:
        print("✅ All Gridify tests passed!")
    else:
        print("❌ Some tests failed")
    print("="*60)
    
    sys.exit(0 if all_passed else 1)
