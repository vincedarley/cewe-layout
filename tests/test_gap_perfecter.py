#!/usr/bin/env python3
"""
Test Gap Perfecter Algorithm.

Verifies that the algorithm correctly eliminates gaps from nearly-perfect layouts.
"""

import sys
sys.path.insert(0, '.')

from cewe_layout.algorithms.gap_perfecter import GapPerfecterAlgorithm
from cewe_layout.algorithms.base import LayoutRectangle


def test_simple_2x2_grid_with_small_gaps():
    """Test that Gap Perfecter eliminates small gaps in a 2x2 grid."""
    # Page: 1000 x 1000
    page_width = 1000.0
    page_height = 1000.0
    
    # Nearly perfect 2x2 grid with small gaps (2 units between items, 1 unit at edges)
    # Top-left: (1, 1, 498, 498)
    # Top-right: (501, 1, 498, 498)
    # Bottom-left: (1, 501, 498, 498)
    # Bottom-right: (501, 501, 498, 498)
    rectangles = [
        LayoutRectangle("0", x=1.0, y=1.0, width=498.0, height=498.0, preferred_size=1.0),
        LayoutRectangle("1", x=501.0, y=1.0, width=498.0, height=498.0, preferred_size=1.0),
        LayoutRectangle("2", x=1.0, y=501.0, width=498.0, height=498.0, preferred_size=1.0),
        LayoutRectangle("3", x=501.0, y=501.0, width=498.0, height=498.0, preferred_size=1.0),
    ]
    
    algorithm = GapPerfecterAlgorithm()
    success, result, error = algorithm.generate_layout(page_width, page_height, rectangles)
    
    assert success, f"Algorithm failed: {error}"
    assert len(result) == 4, "Should return all 4 rectangles"
    
    # After perfecting, the layout should have no gaps
    # Find each rectangle by item_id
    rects_by_id = {r.item_id: r for r in result}
    
    # Top-left should expand to (0, 0)
    tl = rects_by_id["0"]
    assert tl.x == 0.0, f"Top-left x should be 0, got {tl.x}"
    assert tl.y == 0.0, f"Top-left y should be 0, got {tl.y}"
    
    # Top-right should expand left to meet top-left, and left edge should be at 0
    tr = rects_by_id["1"]
    assert tr.y == 0.0, f"Top-right y should be 0, got {tr.y}"
    assert abs(tr.x - (tl.x + tl.width)) < 0.1, f"Top-right left edge should meet top-left right edge"
    
    # Bottom-left should expand up to meet top-left, and top edge should be at 0
    bl = rects_by_id["2"]
    assert bl.x == 0.0, f"Bottom-left x should be 0, got {bl.x}"
    assert abs(bl.y - (tl.y + tl.height)) < 0.1, f"Bottom-left top edge should meet top-left bottom edge"
    
    # Bottom-right should expand left and up to meet adjacent rects
    br = rects_by_id["3"]
    assert abs(br.x - (bl.x + bl.width)) < 0.1, f"Bottom-right left edge should meet bottom-left right edge"
    assert abs(br.y - (tr.y + tr.height)) < 0.1, f"Bottom-right top edge should meet top-right bottom edge"
    
    # All rectangles should extend to page edges
    assert abs(tr.x + tr.width - page_width) < 0.1, "Top-right should extend to right page edge"
    assert abs(br.x + br.width - page_width) < 0.1, "Bottom-right should extend to right page edge"
    assert abs(bl.y + bl.height - page_height) < 0.1, "Bottom-left should extend to bottom page edge"
    assert abs(br.y + br.height - page_height) < 0.1, "Bottom-right should extend to bottom page edge"
    
    print("✓ Simple 2x2 grid with small gaps perfected correctly")


def test_single_photo_with_margins():
    """Test that a single photo expands to fill the entire page."""
    page_width = 500.0
    page_height = 700.0
    
    # Single photo with margins on all sides
    rectangles = [
        LayoutRectangle("0", x=10.0, y=15.0, width=470.0, height=660.0, preferred_size=1.0),
    ]
    
    algorithm = GapPerfecterAlgorithm()
    success, result, error = algorithm.generate_layout(page_width, page_height, rectangles)
    
    assert success, f"Algorithm failed: {error}"
    assert len(result) == 1, "Should return 1 rectangle"
    
    photo = result[0]
    assert photo.x == 0.0, f"Photo should expand to x=0, got {photo.x}"
    assert photo.y == 0.0, f"Photo should expand to y=0, got {photo.y}"
    assert abs(photo.width - page_width) < 0.1, f"Photo should fill page width"
    assert abs(photo.height - page_height) < 0.1, f"Photo should fill page height"
    
    print("✓ Single photo with margins expanded to fill page")


def test_horizontal_row_with_gaps():
    """Test a horizontal row of 3 photos with gaps between them."""
    page_width = 1000.0
    page_height = 400.0
    
    # Three photos in a row with small gaps
    rectangles = [
        LayoutRectangle("0", x=2.0, y=2.0, width=330.0, height=396.0, preferred_size=1.0),
        LayoutRectangle("1", x=335.0, y=2.0, width=330.0, height=396.0, preferred_size=1.0),
        LayoutRectangle("2", x=668.0, y=2.0, width=330.0, height=396.0, preferred_size=1.0),
    ]
    
    algorithm = GapPerfecterAlgorithm()
    success, result, error = algorithm.generate_layout(page_width, page_height, rectangles)
    
    assert success, f"Algorithm failed: {error}"
    assert len(result) == 3, "Should return 3 rectangles"
    
    # Sort by x position for easier testing
    result_sorted = sorted(result, key=lambda r: r.x)
    
    # First photo should expand to left and top edges
    assert result_sorted[0].x == 0.0, "First photo should start at x=0"
    assert result_sorted[0].y == 0.0, "First photo should start at y=0"
    
    # Photos should be adjacent (no gaps)
    assert abs(result_sorted[0].x + result_sorted[0].width - result_sorted[1].x) < 0.1, "Photo 0 and 1 should be adjacent"
    assert abs(result_sorted[1].x + result_sorted[1].width - result_sorted[2].x) < 0.1, "Photo 1 and 2 should be adjacent"
    
    # Last photo should extend to right edge
    assert abs(result_sorted[2].x + result_sorted[2].width - page_width) < 0.1, "Last photo should extend to right edge"
    
    # All photos should extend to top and bottom edges
    for photo in result_sorted:
        assert photo.y == 0.0, f"Photo {photo.item_id} should start at y=0"
        assert abs(photo.y + photo.height - page_height) < 0.1, f"Photo {photo.item_id} should extend to bottom edge"
    
    print("✓ Horizontal row with gaps perfected correctly")


def test_vertical_column_with_gaps():
    """Test a vertical column of 3 photos with gaps between them."""
    page_width = 300.0
    page_height = 1000.0
    
    # Three photos in a column with small gaps
    rectangles = [
        LayoutRectangle("0", x=2.0, y=2.0, width=296.0, height=330.0, preferred_size=1.0),
        LayoutRectangle("1", x=2.0, y=335.0, width=296.0, height=330.0, preferred_size=1.0),
        LayoutRectangle("2", x=2.0, y=668.0, width=296.0, height=330.0, preferred_size=1.0),
    ]
    
    algorithm = GapPerfecterAlgorithm()
    success, result, error = algorithm.generate_layout(page_width, page_height, rectangles)
    
    assert success, f"Algorithm failed: {error}"
    assert len(result) == 3, "Should return 3 rectangles"
    
    # Sort by y position for easier testing
    result_sorted = sorted(result, key=lambda r: r.y)
    
    # First photo should expand to left and top edges
    assert result_sorted[0].x == 0.0, "First photo should start at x=0"
    assert result_sorted[0].y == 0.0, "First photo should start at y=0"
    
    # Photos should be adjacent (no gaps)
    assert abs(result_sorted[0].y + result_sorted[0].height - result_sorted[1].y) < 0.1, "Photo 0 and 1 should be adjacent"
    assert abs(result_sorted[1].y + result_sorted[1].height - result_sorted[2].y) < 0.1, "Photo 1 and 2 should be adjacent"
    
    # Last photo should extend to bottom edge
    assert abs(result_sorted[2].y + result_sorted[2].height - page_height) < 0.1, "Last photo should extend to bottom edge"
    
    # All photos should extend to left and right edges
    for photo in result_sorted:
        assert photo.x == 0.0, f"Photo {photo.item_id} should start at x=0"
        assert abs(photo.x + photo.width - page_width) < 0.1, f"Photo {photo.item_id} should extend to right edge"
    
    print("✓ Vertical column with gaps perfected correctly")


def test_complex_layout_with_varying_sizes():
    """Test a more complex layout with varying photo sizes."""
    page_width = 1000.0
    page_height = 800.0
    
    # Layout:
    # +----------+-----+
    # |          |  2  |
    # |    0     +-----+
    # |          |  3  |
    # +-----+----+-----+
    # |  4  |    5     |
    # +-----+----------+
    
    rectangles = [
        # Large photo top-left
        LayoutRectangle("0", x=2.0, y=2.0, width=648.0, height=498.0, preferred_size=1.0),
        # Two medium photos top-right stacked
        LayoutRectangle("2", x=655.0, y=2.0, width=343.0, height=248.0, preferred_size=1.0),
        LayoutRectangle("3", x=655.0, y=253.0, width=343.0, height=248.0, preferred_size=1.0),
        # Two photos bottom row
        LayoutRectangle("4", x=2.0, y=505.0, width=323.0, height=293.0, preferred_size=1.0),
        LayoutRectangle("5", x=328.0, y=505.0, width=670.0, height=293.0, preferred_size=1.0),
    ]
    
    algorithm = GapPerfecterAlgorithm()
    success, result, error = algorithm.generate_layout(page_width, page_height, rectangles)
    
    assert success, f"Algorithm failed: {error}"
    assert len(result) == 5, "Should return 5 rectangles"
    
    # Find each rectangle by item_id
    rects_by_id = {r.item_id: r for r in result}
    
    # Check that layout fills the page with no gaps
    # Top-left corner should be at (0, 0)
    r0 = rects_by_id["0"]
    assert r0.x == 0.0 and r0.y == 0.0, "Photo 0 should start at (0, 0)"
    
    # Top-right photos should align
    r2 = rects_by_id["2"]
    r3 = rects_by_id["3"]
    assert r2.y == 0.0, "Photo 2 should start at y=0"
    assert abs(r2.x + r2.width - page_width) < 0.1, "Photo 2 should extend to right edge"
    assert abs(r3.x + r3.width - page_width) < 0.1, "Photo 3 should extend to right edge"
    
    # Bottom photos should extend to bottom edge
    r4 = rects_by_id["4"]
    r5 = rects_by_id["5"]
    assert r4.x == 0.0, "Photo 4 should start at x=0"
    assert abs(r4.y + r4.height - page_height) < 0.1, "Photo 4 should extend to bottom edge"
    assert abs(r5.x + r5.width - page_width) < 0.1, "Photo 5 should extend to right edge"
    assert abs(r5.y + r5.height - page_height) < 0.1, "Photo 5 should extend to bottom edge"
    
    print("✓ Complex layout with varying sizes perfected correctly")


def test_diagonal_sorting():
    """Test that diagonal sorting works correctly."""
    page_width = 1000.0
    page_height = 1000.0
    
    # Photos placed diagonally - should be processed in order of distance from (0,0)
    rectangles = [
        LayoutRectangle("far", x=500.0, y=500.0, width=100.0, height=100.0, preferred_size=1.0),  # Distance ~707
        LayoutRectangle("near", x=10.0, y=10.0, width=100.0, height=100.0, preferred_size=1.0),  # Distance ~14
        LayoutRectangle("medium", x=200.0, y=200.0, width=100.0, height=100.0, preferred_size=1.0),  # Distance ~283
    ]
    
    algorithm = GapPerfecterAlgorithm()
    success, result, error = algorithm.generate_layout(page_width, page_height, rectangles)
    
    assert success, f"Algorithm failed: {error}"
    
    # The "near" photo should be processed first and expand to (0,0)
    rects_by_id = {r.item_id: r for r in result}
    near = rects_by_id["near"]
    assert near.x == 0.0 and near.y == 0.0, "Nearest photo should expand to (0, 0)"
    
    print("✓ Diagonal sorting works correctly")


def test_no_positions_set_fails():
    """Test that algorithm fails gracefully when rectangles have no positions."""
    page_width = 1000.0
    page_height = 1000.0
    
    # Rectangle without position
    rectangles = [
        LayoutRectangle("0", x=None, y=None, width=500.0, height=500.0, preferred_size=1.0),
    ]
    
    algorithm = GapPerfecterAlgorithm()
    success, result, error = algorithm.generate_layout(page_width, page_height, rectangles)
    
    assert not success, "Algorithm should fail when rectangles have no positions"
    assert "requires all rectangles to have x,y positions" in error.lower(), f"Error message should explain the issue: {error}"
    
    print("✓ Algorithm correctly rejects rectangles without positions")


def test_small_overlap_fixing():
    """Test that small overlaps (<5mm) are fixed by shifting and shrinking."""
    page_width = 2000.0
    page_height = 2000.0
    
    # Two photos with 3mm overlap (30 units in 0.1mm MCF)
    rectangles = [
        LayoutRectangle("0", x=0.0, y=0.0, width=1003.0, height=1000.0, preferred_size=1.0),  # Left photo
        LayoutRectangle("1", x=1000.0, y=0.0, width=1000.0, height=1000.0, preferred_size=1.0),  # Right photo (overlaps by 3)
    ]
    
    algorithm = GapPerfecterAlgorithm()
    success, result, error = algorithm.generate_layout(page_width, page_height, rectangles)
    
    assert success, f"Algorithm failed: {error}"
    assert len(result) == 2
    
    rects_by_id = {r.item_id: r for r in result}
    left = rects_by_id["0"]
    right = rects_by_id["1"]
    
    # Left photo should expand to fill left side (processed first)
    assert left.x == 0.0, "Left photo should start at x=0"
    
    # Right photo should have been shifted right to fix overlap, then expanded
    # After fixing overlap, it should start at 1003 (left's right edge)
    assert abs(right.x - 1003.0) < 0.1, f"Right photo should start at left's edge (1003), got {right.x}"
    
    # Right photo should extend to page edge
    assert abs(right.x + right.width - page_width) < 0.1, "Right photo should extend to page right edge"
    
    print("✓ Small overlaps (<5mm) fixed by shifting and shrinking")


def test_mixed_photos_and_texts():
    """Test that algorithm works with both photos and text blocks."""
    page_width = 2000.0
    page_height = 1000.0
    
    # Mix of photos and texts with small gaps
    rectangles = [
        LayoutRectangle("0", x=1.0, y=1.0, width=998.0, height=998.0, preferred_size=1.0, preserve_aspect_ratio=True),  # Photo
        LayoutRectangle("TEXT_0", x=1001.0, y=1.0, width=998.0, height=498.0, preferred_size=1.0, preserve_aspect_ratio=False),  # Text
        LayoutRectangle("TEXT_1", x=1001.0, y=501.0, width=998.0, height=498.0, preferred_size=1.0, preserve_aspect_ratio=False),  # Text
    ]
    
    algorithm = GapPerfecterAlgorithm()
    success, result, error = algorithm.generate_layout(page_width, page_height, rectangles)
    
    assert success, f"Algorithm failed: {error}"
    assert len(result) == 3
    
    rects_by_id = {r.item_id: r for r in result}
    photo = rects_by_id["0"]
    text1 = rects_by_id["TEXT_0"]
    text2 = rects_by_id["TEXT_1"]
    
    # All should start at (0, 0)
    assert photo.x == 0.0 and photo.y == 0.0, "Photo should expand to origin"
    assert text1.y == 0.0, "Text 1 should expand to top"
    assert text2.y == text1.y + text1.height, "Text 2 should be adjacent to Text 1"
    
    # Photo and texts should meet
    assert abs(text1.x - (photo.x + photo.width)) < 0.1, "Text 1 should meet photo"
    
    # Everything should extend to edges
    assert abs(text1.x + text1.width - page_width) < 0.1, "Text 1 should extend to right edge"
    assert abs(photo.y + photo.height - page_height) < 0.1, "Photo should extend to bottom edge"
    
    print("✓ Mixed photos and texts handled correctly")


if __name__ == '__main__':
    test_simple_2x2_grid_with_small_gaps()
    test_single_photo_with_margins()
    test_horizontal_row_with_gaps()
    test_vertical_column_with_gaps()
    test_complex_layout_with_varying_sizes()
    test_diagonal_sorting()
    test_no_positions_set_fails()
    test_small_overlap_fixing()
    test_mixed_photos_and_texts()
    print("\n✓ All Gap Perfecter tests passed!")
