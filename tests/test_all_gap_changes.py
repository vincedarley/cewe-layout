#!/usr/bin/env python3
"""
Test that gap transformation works correctly for ALL gap change scenarios:
1. Change internal_gap only
2. Change edge_gap only
3. Change both gaps simultaneously
"""

import sys
sys.path.insert(0, '.')

from cewe_layout.utils.gap_utils import transform_item_for_gap_change, transform_page_to_gapfree

# Test setup
page_w = 2100.0
page_h = 2970.0
is_spread = False  # Single page mode
is_left_page = True

def calculate_br_photo_for_gaps(edge, internal):
    """Calculate bottom-right photo position for a 2x2 grid with given gaps."""
    avail_w = page_w - 2*edge
    avail_h = page_h - 2*edge
    item_w = (avail_w - internal) / 2
    item_h = (avail_h - internal) / 2
    
    left = edge + item_w + internal
    top = edge + item_h + internal
    
    return left, top, item_w, item_h

def run_gap_change_test(name, old_edge, old_internal, new_edge, new_internal):
    """Test a gap change scenario."""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    print(f"Old gaps: edge={old_edge}, internal={old_internal}")
    print(f"New gaps: edge={new_edge}, internal={new_internal}")
    
    # Calculate original photo position for OLD gaps
    original_left, original_top, original_width, original_height = calculate_br_photo_for_gaps(old_edge, old_internal)
    
    # Calculate gap-free page sizes
    old_gf_w, old_gf_h = transform_page_to_gapfree(page_w, page_h, old_edge, old_internal, is_spread)
    new_gf_w, new_gf_h = transform_page_to_gapfree(page_w, page_h, new_edge, new_internal, is_spread)
    
    print(f"\nGap-free pages:")
    print(f"  Old: {old_gf_w} x {old_gf_h}")
    print(f"  New: {new_gf_w} x {new_gf_h}")
    print(f"  Change: {new_gf_w - old_gf_w:+.1f} x {new_gf_h - old_gf_h:+.1f}")
    
    # Transform the photo
    new_left, new_top, new_width, new_height = transform_item_for_gap_change(
        original_left, original_top, original_width, original_height,
        page_w, page_h,
        old_edge, old_internal, new_edge, new_internal,
        is_spread, is_left_page
    )
    
    print(f"\nPhoto transformation:")
    print(f"  Original MCF: ({original_left}, {original_top}, {original_width}, {original_height})")
    print(f"  New MCF: ({new_left:.1f}, {new_top:.1f}, {new_width:.1f}, {new_height:.1f})")
    
    # Check if photo fits within page bounds (accounting for new edge_gap)
    # For single page mode with negative edge_gap (bleed), right edge is at page_w (no bleed at centerfold)
    if not is_spread and new_edge < 0:
        if is_left_page:
            expected_right = page_w  # No bleed at centerfold (right edge)
        else:
            expected_right = page_w - new_edge  # Bleed on outer edge (right)
    else:
        expected_right = page_w - new_edge
    expected_bottom = page_h - new_edge
    
    actual_right = new_left + new_width
    actual_bottom = new_top + new_height
    
    right_error = actual_right - expected_right
    bottom_error = actual_bottom - expected_bottom
    
    print(f"\nBoundary check:")
    print(f"  Expected right edge: {expected_right}")
    print(f"  Actual right edge: {actual_right:.1f}")
    print(f"  Error: {right_error:.3f}")
    print(f"  Expected bottom edge: {expected_bottom}")
    print(f"  Actual bottom edge: {actual_bottom:.1f}")
    print(f"  Error: {bottom_error:.3f}")
    
    # Allow tiny floating point errors
    tolerance = 0.01
    if abs(right_error) < tolerance and abs(bottom_error) < tolerance:
        print(f"\n✓ PASS: Photo fits within page bounds")
        return True
    else:
        print(f"\n✗ FAIL: Photo overflow detected!")
        return False


# Test scenarios
print("Testing gap transformation for all change scenarios")
print("=" * 60)

results = []

# Scenario 1: Change internal_gap only (decrease)
results.append(run_gap_change_test(
    "Change internal_gap only (decrease 112→10)",
    old_edge=50.0, old_internal=112.0,
    new_edge=50.0, new_internal=10.0
))

# Scenario 2: Change internal_gap only (increase)
results.append(run_gap_change_test(
    "Change internal_gap only (increase 10→112)",
    old_edge=50.0, old_internal=10.0,
    new_edge=50.0, new_internal=112.0
))

# Scenario 3: Change edge_gap only (increase)
results.append(run_gap_change_test(
    "Change edge_gap only (increase 50→100)",
    old_edge=50.0, old_internal=112.0,
    new_edge=100.0, new_internal=112.0
))

# Scenario 4: Change edge_gap only (decrease)
results.append(run_gap_change_test(
    "Change edge_gap only (decrease 100→50)",
    old_edge=100.0, old_internal=112.0,
    new_edge=50.0, new_internal=112.0
))

# Scenario 5: Change edge_gap to negative (bleed)
results.append(run_gap_change_test(
    "Change edge_gap to negative bleed (50→-20)",
    old_edge=50.0, old_internal=112.0,
    new_edge=-20.0, new_internal=112.0
))

# Scenario 6: Change both gaps (decrease both)
results.append(run_gap_change_test(
    "Change both gaps (decrease: edge 100→50, internal 112→10)",
    old_edge=100.0, old_internal=112.0,
    new_edge=50.0, new_internal=10.0
))

# Scenario 7: Change both gaps (increase both)
results.append(run_gap_change_test(
    "Change both gaps (increase: edge 50→100, internal 10→112)",
    old_edge=50.0, old_internal=10.0,
    new_edge=100.0, new_internal=112.0
))

# Scenario 8: Change both gaps (opposite directions)
results.append(run_gap_change_test(
    "Change both gaps (edge↑ 50→100, internal↓ 112→10)",
    old_edge=50.0, old_internal=112.0,
    new_edge=100.0, new_internal=10.0
))

# Summary
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
print(f"Total tests: {len(results)}")
print(f"Passed: {sum(results)}")
print(f"Failed: {len(results) - sum(results)}")

if all(results):
    print("\n✓ ALL TESTS PASSED")
    print("Gap transformation correctly handles:")
    print("  - Changes to internal_gap only")
    print("  - Changes to edge_gap only")
    print("  - Changes to both gaps simultaneously")
    print("  - Increases and decreases")
    print("  - Negative edge_gap (bleed)")
else:
    print("\n✗ SOME TESTS FAILED")
    sys.exit(1)
