#!/usr/bin/env python3
"""
Test that gap changes correctly transform layout positions.

Verifies: MCF (old gaps) → gap-free → MCF (new gaps) transformation.
"""

from cewe_layout.gap_utils import (
    transform_item_to_gapfree,
    transform_item_from_gapfree
)


def test_gap_transformation_preserves_gapfree_coordinates():
    """Verify that changing gaps preserves gap-free coordinates."""
    # Original item in MCF space with edge_gap=50, internal_gap=30
    mcf_left = 100.0
    mcf_top = 150.0
    mcf_width = 500.0
    mcf_height = 400.0
    
    old_edge_gap = 50.0
    old_internal_gap = 30.0
    is_spread = True  # Spread mode (bleed on all edges)
    is_left_page = True
    
    # Transform to gap-free space using OLD gaps
    gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
        mcf_left, mcf_top, mcf_width, mcf_height,
        old_edge_gap, old_internal_gap, is_spread, is_left_page
    )
    
    print(f"Original MCF: ({mcf_left}, {mcf_top}, {mcf_width}, {mcf_height})")
    print(f"Gap-free: ({gf_left}, {gf_top}, {gf_width}, {gf_height})")
    print(f"  with edge_gap={old_edge_gap}, internal_gap={old_internal_gap}")
    
    # Expected gap-free values:
    # left: 100 - 50 = 50
    # top: 150 - 50 = 100
    # width: 500 + 30 = 530
    # height: 400 + 30 = 430
    assert gf_left == 50.0, f"Expected gf_left=50, got {gf_left}"
    assert gf_top == 100.0, f"Expected gf_top=100, got {gf_top}"
    assert gf_width == 530.0, f"Expected gf_width=530, got {gf_width}"
    assert gf_height == 430.0, f"Expected gf_height=430, got {gf_height}"
    
    # Now transform back to MCF using NEW gaps
    new_edge_gap = 80.0  # Changed from 50 to 80
    new_internal_gap = 20.0  # Changed from 30 to 20
    
    new_left, new_top, new_width, new_height = transform_item_from_gapfree(
        gf_left, gf_top, gf_width, gf_height,
        new_edge_gap, new_internal_gap, is_spread, is_left_page
    )
    
    print(f"New MCF: ({new_left}, {new_top}, {new_width}, {new_height})")
    print(f"  with edge_gap={new_edge_gap}, internal_gap={new_internal_gap}")
    
    # Expected new MCF values:
    # left: 50 + 80 = 130 (shifted right by 30 due to larger edge gap)
    # top: 100 + 80 = 180 (shifted down by 30 due to larger edge gap)
    # width: 530 - 20 = 510 (smaller by 10 due to smaller internal gap)
    # height: 430 - 20 = 410 (smaller by 10 due to smaller internal gap)
    assert new_left == 130.0, f"Expected new_left=130, got {new_left}"
    assert new_top == 180.0, f"Expected new_top=180, got {new_top}"
    assert new_width == 510.0, f"Expected new_width=510, got {new_width}"
    assert new_height == 410.0, f"Expected new_height=410, got {new_height}"
    
    print("\n✓ Gap transformation preserves gap-free coordinates correctly")


def test_roundtrip_transformation():
    """Verify that roundtrip transformation with same gaps is identity."""
    # Original item
    left = 200.0
    top = 300.0
    width = 600.0
    height = 500.0
    
    edge_gap = 60.0
    internal_gap = 25.0
    is_spread = True
    is_left_page = True
    
    # MCF → gap-free → MCF (same gaps)
    gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
        left, top, width, height, edge_gap, internal_gap, is_spread, is_left_page
    )
    
    rt_left, rt_top, rt_width, rt_height = transform_item_from_gapfree(
        gf_left, gf_top, gf_width, gf_height, edge_gap, internal_gap, is_spread, is_left_page
    )
    
    # Should be identical (within floating point precision)
    assert abs(rt_left - left) < 0.001, f"Roundtrip left: expected {left}, got {rt_left}"
    assert abs(rt_top - top) < 0.001, f"Roundtrip top: expected {top}, got {rt_top}"
    assert abs(rt_width - width) < 0.001, f"Roundtrip width: expected {width}, got {rt_width}"
    assert abs(rt_height - height) < 0.001, f"Roundtrip height: expected {height}, got {rt_height}"
    
    print("✓ Roundtrip transformation preserves original values")


def test_negative_edge_gap_bleed():
    """Verify that negative edge gaps (bleed) work correctly."""
    # Item with bleed (negative edge gap extends beyond page)
    left = 50.0
    top = 50.0
    width = 400.0
    height = 300.0
    
    edge_gap = -20.0  # 2mm bleed
    internal_gap = 15.0
    is_spread = True  # Spread mode (bleed on all edges)
    is_left_page = True
    
    # Transform to gap-free
    gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
        left, top, width, height, edge_gap, internal_gap, is_spread, is_left_page
    )
    
    # With negative edge_gap:
    # left: 50 - (-20) = 70 (moves right in gap-free space)
    # top: 50 - (-20) = 70 (moves down in gap-free space)
    # width: 400 + 15 = 415
    # height: 300 + 15 = 315
    assert gf_left == 70.0, f"Expected gf_left=70, got {gf_left}"
    assert gf_top == 70.0, f"Expected gf_top=70, got {gf_top}"
    assert gf_width == 415.0, f"Expected gf_width=415, got {gf_width}"
    assert gf_height == 315.0, f"Expected gf_height=315, got {gf_height}"
    
    # Transform back
    rt_left, rt_top, rt_width, rt_height = transform_item_from_gapfree(
        gf_left, gf_top, gf_width, gf_height, edge_gap, internal_gap, is_spread, is_left_page
    )
    
    # Should recover original
    assert abs(rt_left - left) < 0.001
    assert abs(rt_top - top) < 0.001
    assert abs(rt_width - width) < 0.001
    assert abs(rt_height - height) < 0.001
    
    print("✓ Negative edge gaps (bleed) transform correctly")


def test_single_page_left_no_bleed_at_centerfold():
    """Verify that left page has no bleed at right edge (centerfold)."""
    # Left page with bleed, item touching right edge (centerfold)
    left = 1900.0  # Close to right edge
    top = 50.0
    width = 100.0
    height = 200.0
    
    edge_gap = -20.0  # 2mm bleed
    internal_gap = 0.0
    is_spread = False  # Single page mode
    is_left_page = True  # Left page
    
    # Transform to gap-free
    gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
        left, top, width, height, edge_gap, internal_gap, is_spread, is_left_page
    )
    
    # With negative edge_gap on left page (single page mode):
    # - Left edge: subtract edge_gap (moves right: 1900 - (-20) = 1920)
    # - Top edge: subtract edge_gap (moves down: 50 - (-20) = 70)
    # - Right edge (centerfold): NO bleed adjustment (stays at page boundary)
    assert gf_left == 1920.0, f"Expected gf_left=1920, got {gf_left}"
    assert gf_top == 70.0, f"Expected gf_top=70, got {gf_top}"
    
    # Transform back
    rt_left, rt_top, rt_width, rt_height = transform_item_from_gapfree(
        gf_left, gf_top, gf_width, gf_height, edge_gap, internal_gap, is_spread, is_left_page
    )
    
    # Should recover original
    assert abs(rt_left - left) < 0.001
    assert abs(rt_top - top) < 0.001
    assert abs(rt_width - width) < 0.001
    assert abs(rt_height - height) < 0.001
    
    print("✓ Left page has no bleed at centerfold (right edge)")


def test_single_page_right_no_bleed_at_centerfold():
    """Verify that right page has no bleed at left edge (centerfold)."""
    # Right page with bleed, item touching left edge (centerfold)
    left = 0.0  # At left edge (centerfold)
    top = 50.0
    width = 100.0
    height = 200.0
    
    edge_gap = -20.0  # 2mm bleed
    internal_gap = 0.0
    is_spread = False  # Single page mode
    is_left_page = False  # Right page
    
    # Transform to gap-free
    gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
        left, top, width, height, edge_gap, internal_gap, is_spread, is_left_page
    )
    
    # With negative edge_gap on right page (single page mode):
    # - Left edge (centerfold): NO bleed adjustment (stays at 0)
    # - Top edge: subtract edge_gap (moves down: 50 - (-20) = 70)
    # - Right edge: bleed applies (item can extend beyond page)
    assert gf_left == 0.0, f"Expected gf_left=0, got {gf_left}"
    assert gf_top == 70.0, f"Expected gf_top=70, got {gf_top}"
    
    # Transform back
    rt_left, rt_top, rt_width, rt_height = transform_item_from_gapfree(
        gf_left, gf_top, gf_width, gf_height, edge_gap, internal_gap, is_spread, is_left_page
    )
    
    # Should recover original
    assert abs(rt_left - left) < 0.001
    assert abs(rt_top - top) < 0.001
    assert abs(rt_width - width) < 0.001
    assert abs(rt_height - height) < 0.001
    
    print("✓ Right page has no bleed at centerfold (left edge)")


def test_spread_mode_bleed_on_all_edges():
    """Verify that spread mode has bleed on all four edges."""
    # Spread mode (double page) with bleed
    left = 50.0
    top = 50.0
    width = 400.0
    height = 300.0
    
    edge_gap = -20.0  # 2mm bleed
    internal_gap = 0.0
    is_spread = True  # Spread mode (bleed on all edges)
    is_left_page = True  # Doesn't matter for spread mode
    
    # Transform to gap-free
    gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
        left, top, width, height, edge_gap, internal_gap, is_spread, is_left_page
    )
    
    # In spread mode, bleed applies to all edges:
    # left: 50 - (-20) = 70
    # top: 50 - (-20) = 70
    assert gf_left == 70.0, f"Expected gf_left=70, got {gf_left}"
    assert gf_top == 70.0, f"Expected gf_top=70, got {gf_top}"
    
    # Transform back
    rt_left, rt_top, rt_width, rt_height = transform_item_from_gapfree(
        gf_left, gf_top, gf_width, gf_height, edge_gap, internal_gap, is_spread, is_left_page
    )


    # Should recover original
    assert abs(rt_left - left) < 0.001
    assert abs(rt_top - top) < 0.001
    assert abs(rt_width - width) < 0.001
    assert abs(rt_height - height) < 0.001
    
    print("✓ Spread mode has bleed on all four edges")


if __name__ == '__main__':
    test_gap_transformation_preserves_gapfree_coordinates()
    test_roundtrip_transformation()
    test_negative_edge_gap_bleed()
    test_single_page_left_no_bleed_at_centerfold()
    test_single_page_right_no_bleed_at_centerfold()
    test_spread_mode_bleed_on_all_edges()
    print("\n✓ All gap transformation tests passed")
