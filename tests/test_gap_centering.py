"""
Test that changing internal gap preserves layout centering.

When internal gap is changed, the layout should stay centered on the page,
not shift left or right. This test uses a layout based on the hand-drawn
diagram to verify centering is preserved.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.gap_utils import transform_item_for_gap_change, analyze_gaps


def test_gap_change_preserves_centering():
    """Test that reducing internal gap doesn't shift layout left."""
    
    # Page dimensions from diagram: 250 x 250 (in mm, so 2500 x 2500 MCF units)
    page_width = 2500.0
    page_height = 2500.0
    
    # Gaps from diagram
    edge_gap = 200.0  # 20mm
    old_internal_gap = 100.0  # 10mm
    
    # Assume spread mode for this test
    is_spread = True
    is_left_page = True
    
    # Test both directions: reducing gap and increasing gap
    test_cases = [
        ("Reduce gap 10->5", 50.0),   # Reduce to 5mm
        ("Increase gap 10->15", 150.0),  # Increase to 15mm
    ]
    
    # Gap-free page with old gaps: 2500 - 2*200 + 100 = 2200
    # Available space for layout (gap-free): 2200 x 2200
    
    # Layout from diagram (working in gap-free coordinates first for clarity):
    # Top row: 100x50, gap, 100x50  (total width: 100+10+100=210, centered in 220)
    # Middle row: 50x100, gap, 40x100, gap, 45x100, gap, 45x100 (total: 50+10+40+10+45+10+45=210)
    # Bottom: 210x40 (spans full width minus margins)
    
    # In gap-free space, layout should be centered
    # Horizontal centering: (2200 - 210) / 2 = 995 offset from left edge
    # But wait - the diagram shows edge_gap of 20 on sides too
    
    # Let me recalculate based on MCF coordinates shown in diagram:
    # Top-left rect: starts at x=50 (edge_gap + centering offset), width=100
    # In MCF: left=50*10=500, width=100*10=1000
    
    # MCF coordinates with edge_gap=20mm on all sides, internal_gap=10mm between items:
    # Available width in MCF = 250 - 20 - 20 = 210mm = 2100 MCF units
    # Top row: 100 + 10(gap) + 100 = 210 - perfect fit
    # Middle row: 50 + 10 + 40 + 10 + 45 + 10 + 45 = 210 - perfect fit
    # Bottom: 210 - perfect fit
    
    initial_layout = [
        # Top row (2 rects, 100mm wide each)
        {'left': 200.0, 'top': 200.0, 'width': 1000.0, 'height': 500.0},   # x=20, w=100
        {'left': 1300.0, 'top': 200.0, 'width': 1000.0, 'height': 500.0},  # x=130, w=100
        # Middle row (4 tall rects at y=80)
        {'left': 200.0, 'top': 800.0, 'width': 500.0, 'height': 1000.0},   # x=20, w=50
        {'left': 800.0, 'top': 800.0, 'width': 400.0, 'height': 1000.0},   # x=80, w=40
        {'left': 1300.0, 'top': 800.0, 'width': 450.0, 'height': 1000.0},  # x=130, w=45
        {'left': 1850.0, 'top': 800.0, 'width': 450.0, 'height': 1000.0},  # x=185, w=45
        # Bottom row (1 wide rect at y=190)
        {'left': 200.0, 'top': 1900.0, 'width': 2100.0, 'height': 400.0},  # x=20, w=210
    ]
    
    for test_name, new_internal_gap in test_cases:
        print(f"\n{'='*70}")
        print(f"TEST: {test_name}")
        print(f"{'='*70}")
        
        # Transform each rectangle with gap change
        transformed_layout = []
        for rect in initial_layout:
            new_left, new_top, new_width, new_height = transform_item_for_gap_change(
                rect['left'], rect['top'], rect['width'], rect['height'],
                page_width, page_height,
                edge_gap, old_internal_gap,
                edge_gap, new_internal_gap,
                is_spread, is_left_page
            )
            transformed_layout.append({
                'left': new_left,
                'top': new_top,
                'width': new_width,
                'height': new_height
            })
        
        # Test 1: Verify layout bounding box stays centered
        def compute_bbox_center(layout):
            """Compute the center of the layout's bounding box."""
            min_left = min(r['left'] for r in layout)
            max_right = max(r['left'] + r['width'] for r in layout)
            return (min_left + max_right) / 2.0
        
        page_center = page_width / 2
        initial_bbox_center = compute_bbox_center(initial_layout)
        transformed_bbox_center = compute_bbox_center(transformed_layout)
        shift = abs(transformed_bbox_center - initial_bbox_center)
        
        print(f"\nCentering test:")
        print(f"  Page center: {page_center:.1f}")
        print(f"  Initial bbox center: {initial_bbox_center:.1f}")
        print(f"  Transformed bbox center: {transformed_bbox_center:.1f}")
        print(f"  Shift due to gap change: {shift:.1f}")
        
        assert shift < 0.1, f"Layout shifted by {shift:.1f} units when changing internal gap. Expected < 0.1"
        print(f"  ✓ Layout stayed centered (shift = {shift:.3f} units)")
        
        # Test 2: Manually verify gaps in transformed layout
        # Check edge gaps (distance from page edge to first item)
        min_left = min(r['left'] for r in transformed_layout)
        max_right = max(r['left'] + r['width'] for r in transformed_layout)
        min_top = min(r['top'] for r in transformed_layout)
        max_bottom = max(r['top'] + r['height'] for r in transformed_layout)
        
        left_edge_gap = min_left
        right_edge_gap = page_width - max_right
        top_edge_gap = min_top
        bottom_edge_gap = page_height - max_bottom
        
        print(f"\nManual gap measurements:")
        print(f"  Left edge gap: {left_edge_gap:.1f} (expected {edge_gap:.1f})")
        print(f"  Right edge gap: {right_edge_gap:.1f} (expected {edge_gap:.1f})")
        print(f"  Top edge gap: {top_edge_gap:.1f} (expected {edge_gap:.1f})")
        print(f"  Bottom edge gap: {bottom_edge_gap:.1f} (expected {edge_gap:.1f})")
        
        # Edge gaps should be unchanged
        assert abs(left_edge_gap - edge_gap) < 0.5, f"Left edge gap wrong: {left_edge_gap:.1f}"
        assert abs(right_edge_gap - edge_gap) < 0.5, f"Right edge gap wrong: {right_edge_gap:.1f}"
        print(f"  ✓ Edge gaps preserved")
        
        # Check internal gaps (horizontal gaps between adjacent items in same row)
        # For top row: gap between rect 0 and rect 1
        top_row_gap = transformed_layout[1]['left'] - (transformed_layout[0]['left'] + transformed_layout[0]['width'])
        print(f"  Top row horizontal gap: {top_row_gap:.1f} (expected {new_internal_gap:.1f})")
        
        # For middle row: gaps between the 4 tall rectangles
        middle_gaps = []
        for i in range(2, 5):  # Indices 2,3,4 -> check gaps to indices 3,4,5
            gap = transformed_layout[i+1]['left'] - (transformed_layout[i]['left'] + transformed_layout[i]['width'])
            middle_gaps.append(gap)
            print(f"  Middle row gap {i-1}: {gap:.1f} (expected {new_internal_gap:.1f})")
        
        # Verify internal gaps match expected value
        assert abs(top_row_gap - new_internal_gap) < 0.5, f"Top row gap wrong: {top_row_gap:.1f}"
        for i, gap in enumerate(middle_gaps):
            assert abs(gap - new_internal_gap) < 0.5, f"Middle gap {i} wrong: {gap:.1f}"
        print(f"  ✓ Internal gaps correct")
        
        # Print per-rectangle center shifts for debugging
        print(f"\nPer-rectangle center shifts:")
        for i, (orig, trans) in enumerate(zip(initial_layout, transformed_layout)):
            orig_center = orig['left'] + orig['width'] / 2
            trans_center = trans['left'] + trans['width'] / 2
            shift_x = trans_center - orig_center
            print(f"  Rect {i}: {shift_x:+7.2f} units")
    
    print(f"\n{'='*70}")
    print("All tests passed!")
    print(f"{'='*70}")


if __name__ == '__main__':
    test_gap_change_preserves_centering()
