#!/usr/bin/env python3
"""
Integration test: Verify complete gap workflow.

Tests the full lifecycle:
1. Initial page load → gaps initialized from layout analysis
2. User edits gap → layout transforms, gaps update
3. User reverts → gaps cleared, re-initialized on next view
4. Zero gaps are valid and don't trigger re-initialization
"""

import sys
sys.path.insert(0, '.')

from cewe_layout.layout_ops import LayoutManager
from cewe_layout.gap_utils import analyze_gap_details, transform_item_to_gapfree, transform_item_from_gapfree


def test_complete_gap_workflow():
    """Test the full gap initialization and modification workflow."""
    mgr = LayoutManager()
    pageno = 5
    
    # Simulate a page with photos (bleed layout: photos extend to edge)
    page_w = 2100.0
    page_h = 2970.0
    original_photos = [
        {'area_left': -10.0, 'area_top': -10.0, 'area_width': 1060.0, 'area_height': 1500.0, 'filename': 'photo1.jpg'},
        {'area_left': 1050.0, 'area_top': -10.0, 'area_width': 1060.0, 'area_height': 1500.0, 'filename': 'photo2.jpg'},
        {'area_left': -10.0, 'area_top': 1490.0, 'area_width': 2120.0, 'area_height': 1490.0, 'filename': 'photo3.jpg'},
    ]
    
    # Step 1: Initial page load - gaps should be uninitialized
    print("Step 1: Initial state")
    assert not mgr.has_edge_gap(pageno), "Gaps should not be initialized yet"
    assert not mgr.has_internal_gap(pageno), "Gaps should not be initialized yet"
    print("  ✓ Gaps uninitialized")
    
    # Step 2: Analyze and initialize gaps
    print("\nStep 2: Initialize gaps from layout analysis")
    is_spread = False  # Single page
    analysis = analyze_gap_details(original_photos, page_w, page_h, origin_left=0.0, is_spread=is_spread)
    print(f"  Analysis: edge_gap={analysis.edge_gap:.1f}, internal_gap={analysis.internal_gap:.1f}, bleed={analysis.bleed:.1f}")
    
    # Initialize based on analysis (simulating GUI logic)
    if analysis.bleed > 0:
        mgr.set_edge_gap(pageno, -analysis.bleed)
    else:
        mgr.set_edge_gap(pageno, analysis.edge_gap)
    
    if analysis.internal_gap > 0:
        mgr.set_internal_gap(pageno, analysis.internal_gap)
    else:
        mgr.set_internal_gap(pageno, analysis.edge_gap)
    
    print(f"  Set edge_gap={mgr.get_edge_gap(pageno):.1f}, internal_gap={mgr.get_internal_gap(pageno):.1f}")
    assert mgr.has_edge_gap(pageno), "Edge gap should now be set"
    assert mgr.has_internal_gap(pageno), "Internal gap should now be set"
    print("  ✓ Gaps initialized")
    
    # Step 3: User edits gap value
    print("\nStep 3: User changes edge gap from negative (bleed) to positive (margin)")
    old_edge_gap = mgr.get_edge_gap(pageno)
    old_internal_gap = mgr.get_internal_gap(pageno)
    new_edge_gap = 50.0  # 5mm margin
    is_left_page = True  # Assume left page
    
    # Transform layout: MCF (old gaps) → gap-free → MCF (new gaps)
    photo = original_photos[0]
    gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
        photo['area_left'], photo['area_top'], photo['area_width'], photo['area_height'],
        old_edge_gap, old_internal_gap, is_spread, is_left_page
    )
    print(f"  Gap-free coords: ({gf_left:.1f}, {gf_top:.1f}, {gf_width:.1f}, {gf_height:.1f})")
    
    new_left, new_top, new_width, new_height = transform_item_from_gapfree(
        gf_left, gf_top, gf_width, gf_height,
        new_edge_gap, old_internal_gap, is_spread, is_left_page
    )
    print(f"  New MCF coords: ({new_left:.1f}, {new_top:.1f}, {new_width:.1f}, {new_height:.1f})")
    
    # Update stored gap
    mgr.set_edge_gap(pageno, new_edge_gap)
    assert mgr.get_edge_gap(pageno) == new_edge_gap, "Edge gap should be updated"
    print(f"  ✓ Edge gap updated to {new_edge_gap:.1f}")
    
    # Step 4: Verify zero gaps are valid
    print("\nStep 4: Set gaps to zero (valid values)")
    mgr.set_edge_gap(pageno, 0.0)
    mgr.set_internal_gap(pageno, 0.0)
    
    assert mgr.has_edge_gap(pageno), "Zero edge_gap should still be 'set'"
    assert mgr.has_internal_gap(pageno), "Zero internal_gap should still be 'set'"
    assert mgr.get_edge_gap(pageno) == 0.0, "Edge gap should be 0.0"
    assert mgr.get_internal_gap(pageno) == 0.0, "Internal gap should be 0.0"
    print("  ✓ Zero gaps are valid and don't trigger re-initialization")
    
    # Step 5: User reverts to original
    print("\nStep 5: User reverts to original (clear gaps)")
    mgr.clear_gaps(pageno)
    
    assert not mgr.has_edge_gap(pageno), "Edge gap should be cleared"
    assert not mgr.has_internal_gap(pageno), "Internal gap should be cleared"
    print("  ✓ Gaps cleared")
    
    # Step 6: Next page view re-initializes
    print("\nStep 6: Next page view re-initializes gaps")
    needs_init = not mgr.has_edge_gap(pageno) or not mgr.has_internal_gap(pageno)
    assert needs_init, "Should detect need for re-initialization"
    print("  ✓ Re-initialization detected")
    
    # Re-analyze and initialize
    if analysis.bleed > 0:
        mgr.set_edge_gap(pageno, -analysis.bleed)
    else:
        mgr.set_edge_gap(pageno, analysis.edge_gap)
    
    if analysis.internal_gap > 0:
        mgr.set_internal_gap(pageno, analysis.internal_gap)
    else:
        mgr.set_internal_gap(pageno, analysis.edge_gap)
    
    print(f"  Re-initialized: edge_gap={mgr.get_edge_gap(pageno):.1f}, internal_gap={mgr.get_internal_gap(pageno):.1f}")
    assert mgr.has_edge_gap(pageno), "Edge gap should be re-initialized"
    assert mgr.has_internal_gap(pageno), "Internal gap should be re-initialized"
    print("  ✓ Gaps re-initialized")
    
    print("\n✓ Complete gap workflow test passed")


if __name__ == '__main__':
    test_complete_gap_workflow()
