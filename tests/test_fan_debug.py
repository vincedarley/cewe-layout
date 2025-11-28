#!/usr/bin/env python3
"""
Debug test for Fan algorithm to trace positioning issues.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.fan_layout import FanLayoutAlgorithm
from cewe_layout.algorithms.base import LayoutRectangle


def test_fan_single_photo():
    """Test Fan algorithm with single photo."""
    print("Testing Fan with 1 photo...")
    
    algo = FanLayoutAlgorithm(generations=10, population_size=10)
    
    rectangles = [
        LayoutRectangle(item_id="0", width=1920.0, height=1080.0, preferred_size=1.0),
    ]
    
    page_width = 2970.0
    page_height = 4200.0
    success, result_rects, error_msg = algo.generate_layout(
        page_width, page_height, rectangles
    )
    
    if not success:
        print(f"  ❌ Failed: {error_msg}")
        return False
    
    print(f"  ✅ Success")
    for i, rect in enumerate(result_rects):
        print(f"    Rectangle {i}: x={rect.x}, y={rect.y}, w={rect.width}, h={rect.height}")
    
    return True


def test_fan_two_photos():
    """Test Fan algorithm with two photos."""
    print("\nTesting Fan with 2 photos...")
    
    algo = FanLayoutAlgorithm(generations=10, population_size=10)
    
    rectangles = [
        LayoutRectangle(item_id="0", width=1920.0, height=1080.0, preferred_size=1.0),
        LayoutRectangle(item_id="1", width=1080.0, height=1080.0, preferred_size=1.0),
    ]
    
    page_width = 2970.0
    page_height = 4200.0
    success, result_rects, error_msg = algo.generate_layout(
        page_width, page_height, rectangles
    )
    
    if not success:
        print(f"  ❌ Failed: {error_msg}")
        return False
    
    print(f"  ✅ Success")
    for i, rect in enumerate(result_rects):
        print(f"    Rectangle {i}: x={rect.x}, y={rect.y}, w={rect.width}, h={rect.height}")
    
    return True


def test_fan_eight_photos():
    """Test Fan algorithm with eight photos (like page 3)."""
    print("\nTesting Fan with 8 photos...")
    
    algo = FanLayoutAlgorithm(generations=10, population_size=10)
    
    rectangles = [
        LayoutRectangle(item_id=str(i), width=1920.0, height=1080.0, preferred_size=1.0)
        for i in range(8)
    ]
    
    page_width = 2970.0
    page_height = 4200.0
    success, result_rects, error_msg = algo.generate_layout(
        page_width, page_height, rectangles
    )
    
    if not success:
        print(f"  ❌ Failed: {error_msg}")
        return False
    
    print(f"  ✅ Success")
    for i, rect in enumerate(result_rects):
        print(f"    Rectangle {i}: x={rect.x}, y={rect.y}, w={rect.width}, h={rect.height}")
    
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Debug Test: Fan-GA Algorithm")
    print("=" * 60)
    
    success1 = test_fan_single_photo()
    success2 = test_fan_two_photos()
    success3 = test_fan_eight_photos()
    
    print()
    print("=" * 60)
    if success1 and success2 and success3:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")
        sys.exit(1)
    print("=" * 60)
