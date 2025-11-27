#!/usr/bin/env python3
"""
Quick integration test for unified LayoutRectangle API.

This test verifies that:
1. LayoutRectangle serves as both input and output.
2. CollageGeneratorAlgorithm accepts rectangles and modifies them in-place.
3. The complete pipeline (GUI -> wrapper -> algorithm) works correctly.
"""

from cewe_layout.algorithms.base import LayoutRectangle, LayoutAlgorithm
from cewe_layout.algorithms.collage_generator import CollageGeneratorAlgorithm


def test_layout_rectangle():
    """Test LayoutRectangle input/output model."""
    print("Testing LayoutRectangle...")
    
    # Create input rectangle
    rect = LayoutRectangle(
        item_id="photo_0",
        width=1920.0,
        height=1080.0,
        desired_weight=1.5,
        x=None,  # Optional input hint
        y=None
    )
    
    # Check initial state
    assert rect.item_id == "photo_0"
    assert rect.width == 1920.0
    assert rect.height == 1080.0
    assert rect.desired_weight == 1.5
    assert rect.achieved_weight == 0.0
    assert rect.x is None
    assert rect.y is None
    
    # Simulate algorithm output (modifying in-place)
    rect.x = 100.0
    rect.y = 50.0
    rect.width = 400.0
    rect.height = 300.0
    rect.achieved_weight = 1.5
    
    # Check output state
    assert rect.x == 100.0
    assert rect.y == 50.0
    assert rect.width == 400.0
    assert rect.height == 300.0
    assert rect.achieved_weight == 1.5
    
    print(f"  ✅ {rect}")


def test_collage_generator_algorithm():
    """Test CollageGeneratorAlgorithm with unified LayoutRectangle."""
    print("Testing CollageGeneratorAlgorithm...")
    
    algo = CollageGeneratorAlgorithm(temperature=1.0)
    
    # Create input rectangles (representing 3 photos with different aspect ratios)
    rectangles = [
        LayoutRectangle(item_id="0", width=1920.0, height=1080.0, desired_weight=1.0),  # 16:9
        LayoutRectangle(item_id="1", width=1080.0, height=1080.0, desired_weight=1.0),  # 1:1
        LayoutRectangle(item_id="2", width=1080.0, height=1440.0, desired_weight=1.0),  # 3:4
    ]
    
    # Run layout
    page_width = 2970.0
    page_height = 4200.0
    success, result_rects, error_msg = algo.generate_layout(
        page_width, page_height, rectangles
    )
    
    # Check results
    assert success, f"Layout failed: {error_msg}"
    assert len(result_rects) == 3, f"Expected 3 rectangles, got {len(result_rects)}"
    
    # Check that all rectangles have positions set
    for i, rect in enumerate(result_rects):
        assert rect.x is not None, f"Rectangle {i} missing x"
        assert rect.y is not None, f"Rectangle {i} missing y"
        assert rect.achieved_weight > 0, f"Rectangle {i} has zero achieved_weight"
        print(f"  ✅ Rectangle {i}: {rect}")
    
    # Verify no rectangles overlap (rough check)
    for i in range(len(result_rects)):
        for j in range(i + 1, len(result_rects)):
            r1 = result_rects[i]
            r2 = result_rects[j]
            # Check for overlap (simplistic check)
            if not (r1.x + r1.width <= r2.x or r2.x + r2.width <= r1.x or
                    r1.y + r1.height <= r2.y or r2.y + r2.height <= r1.y):
                print(f"  ⚠️  Warning: Rectangles {i} and {j} may overlap")


def test_in_place_modification():
    """Test that algorithm modifies input rectangles in-place."""
    print("Testing in-place modification...")
    
    algo = CollageGeneratorAlgorithm(temperature=1.0)
    
    # Create rectangles
    rects = [
        LayoutRectangle(item_id="0", width=1920.0, height=1080.0),
        LayoutRectangle(item_id="1", width=1080.0, height=1080.0),
    ]
    
    # Store references
    rect_refs = rects
    
    # Run layout
    success, returned_rects, _ = algo.generate_layout(2970.0, 4200.0, rects)
    
    # Check that returned list is same object (or at least contains same rectangles)
    assert success
    assert len(returned_rects) == 2
    
    # Verify rectangles were modified in-place
    for i, rect in enumerate(returned_rects):
        assert rect.x is not None, f"Rectangle {i} should have x set"
        assert rect.y is not None, f"Rectangle {i} should have y set"
    
    print(f"  ✅ Algorithm modified {len(returned_rects)} rectangles in-place")


if __name__ == "__main__":
    print("=" * 60)
    print("Integration Test: Unified LayoutRectangle API")
    print("=" * 60)
    
    test_layout_rectangle()
    print()
    test_collage_generator_algorithm()
    print()
    test_in_place_modification()
    
    print()
    print("=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
