#!/usr/bin/env python3
"""
Test suite for layout cost evaluation.

Tests the LayoutCost computation with various scenarios:
- Empty page
- Uniform weights with equal areas
- Non-uniform weights with mismatched areas
- Partial page coverage
"""
import sys
from pathlib import Path

# Add parent directory to path so we can import cewe_layout
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.algorithms.evaluator import evaluate_layout, evaluate_mcf_page


def test_empty_page():
    """Test cost evaluation for an empty page (no rectangles)."""
    print("Test: Empty page")
    
    cost = evaluate_layout(
        page_width=2970.0,
        page_height=4200.0,
        rectangles=[],
        size_importance=10.0
    )
    
    print(f"  {cost}")
    assert cost.empty_space_fraction == 1.0, "Empty page should have 100% empty"
    assert cost.size_mismatch_cost == 0.0, "No rectangles means no size mismatch"
    assert cost.total_cost > 0, "Empty page should have positive cost"
    print("  ✅ Pass\n")


def test_perfect_layout():
    """Test cost for perfect layout: all weights matched, minimal empty space."""
    print("Test: Perfect layout (uniform weights, equal areas)")
    
    page_w, page_h = 1000.0, 1000.0
    page_area = page_w * page_h
    
    # 4 rectangles with equal preferred size (1.0 each)
    # Each should get 25% of page area for zero cost
    rect_size = 500.0  # Each rectangle is 500×500 = 250,000 = 25% of 1M page
    rectangles = [
        LayoutRectangle("0", width=rect_size, height=rect_size, preferred_size=1.0, x=0, y=0),
        LayoutRectangle("1", width=rect_size, height=rect_size, preferred_size=1.0, x=500, y=0),
        LayoutRectangle("2", width=rect_size, height=rect_size, preferred_size=1.0, x=0, y=500),
        LayoutRectangle("3", width=rect_size, height=rect_size, preferred_size=1.0, x=500, y=500),
    ]
    
    cost = evaluate_layout(page_w, page_h, rectangles, acceptable_empty_fraction=0.0)
    
    print(f"  {cost}")
    print(f"  Empty fraction: {cost.empty_space_fraction:.2%}")
    print(f"  Size errors:")
    for item_id, preferred, actual, sq_err in cost.size_errors:
        print(f"    Item {item_id}: preferred={preferred:.4f}, actual={actual:.4f}, error²={sq_err:.6f}")
    
    assert cost.empty_space_fraction == 0.0, "Perfect layout should have 0% empty"
    assert cost.size_mismatch_cost < 0.01, f"Perfect uniform layout should have near-zero size mismatch (got {cost.size_mismatch_cost})"
    print("  ✅ Pass\n")


def test_weight_mismatch():
    """Test cost when preferred sizes don't match actual areas."""
    print("Test: Weight mismatch (non-uniform weights with equal areas)")
    
    page_w, page_h = 1000.0, 1000.0
    
    # 2 rectangles with different preferred sizes but equal actual areas
    # Preferred: A=2.0 (67%), B=1.0 (33%)
    # Actual: A=50%, B=50%
    # Mismatch: (0.67-0.5)² + (0.33-0.5)² = 0.0289 + 0.0289 = 0.0578
    rectangles = [
        LayoutRectangle("A", width=500, height=1000, preferred_size=2.0, x=0, y=0),      # 50% of page
        LayoutRectangle("B", width=500, height=1000, preferred_size=1.0, x=500, y=0),    # 50% of page
    ]
    
    cost = evaluate_layout(page_w, page_h, rectangles, size_importance=10.0, acceptable_empty_fraction=0.0)
    
    print(f"  {cost}")
    print(f"  Size errors:")
    for item_id, preferred, actual, sq_err in cost.size_errors:
        print(f"    Item {item_id}: preferred={preferred:.4f}, actual={actual:.4f}, error²={sq_err:.6f}")
    
    # Check weight mismatch is calculated correctly
    expected_mismatch_sum = (2.0/3.0 - 0.5)**2 + (1.0/3.0 - 0.5)**2
    expected_cost = expected_mismatch_sum * (100.0 * 100.0) * 10.0

    assert abs(cost.size_mismatch_cost - expected_cost) < 0.01, \
        f"Size mismatch cost should be ~{expected_cost:.4f}, got {cost.size_mismatch_cost:.4f}"
    assert cost.empty_space_fraction == 0.0, "Full coverage should have 0% empty"
    print(f"  Expected mismatch cost: {expected_cost:.4f}")
    print("  ✅ Pass\n")


def test_partial_coverage():
    """Test cost when layout doesn't fill the entire page."""
    print("Test: Partial coverage (70% of page used)")
    
    page_w, page_h = 1000.0, 1000.0
    page_area = page_w * page_h
    
    # 1 rectangle covering 70% of page
    # 30% empty → 25% excess over 5% acceptable → penalty
    rect_area = 700000  # 70% of 1M
    rectangles = [
        LayoutRectangle("0", width=1000, height=700, preferred_size=1.0, x=0, y=0),
    ]
    
    cost = evaluate_layout(
        page_w, page_h, rectangles,
        size_importance=10.0,
        acceptable_empty_fraction=0.05
    )
    
    print(f"  {cost}")
    print(f"  Empty fraction: {cost.empty_space_fraction:.2%}")
    print(f"  Excess empty: {max(0, cost.empty_space_fraction - 0.05):.2%}")
    
    assert abs(cost.empty_space_fraction - 0.3) < 0.01, "Should have 30% empty"
    excess = cost.empty_space_fraction - 0.05
    assert abs(cost.empty_space_cost - (excess * 100.0)) < 0.01, f"Empty space cost should be ~{excess*100.0:.4f}"
    print("  ✅ Pass\n")


def test_mcf_helper():
    """Test the MCF page helper function."""
    print("Test: MCF page evaluation helper")
    
    photos = [
        {'filename': 'photo1.jpg', 'area_left': 0, 'area_top': 0, 'area_width': 1485, 'area_height': 2100},
        {'filename': 'photo2.jpg', 'area_left': 1485, 'area_top': 0, 'area_width': 1485, 'area_height': 2100},
    ]
    
    page_w, page_h = 2970.0, 4200.0
    
    # Without preferred sizes: uniform (each preferred = 1.0)
    cost1 = evaluate_mcf_page(photos, page_w, page_h)
    print(f"  Uniform sizes: {cost1}")
    print(f"    Empty fraction: {cost1.empty_space_fraction:.2%}")
    
    # With custom preferred sizes
    preferred = {'photo1.jpg': 2.0, 'photo2.jpg': 1.0}
    cost2 = evaluate_mcf_page(photos, page_w, page_h, preferred_sizes=preferred)
    print(f"  Custom preferred sizes (2.0, 1.0): {cost2}")
    print(f"    Empty fraction: {cost2.empty_space_fraction:.2%}")
    
    # Both should have same empty fraction (50%)
    assert abs(cost1.empty_space_fraction - 0.5) < 0.01, "Should have ~50% empty (2 photos covering top half)"
    assert abs(cost2.empty_space_fraction - 0.5) < 0.01, "Empty fraction should be same regardless of weights"
    
    # But different weight mismatch costs
    assert cost2.size_mismatch_cost != cost1.size_mismatch_cost, "Different preferred sizes should give different mismatch costs"
    
    print("  ✅ Pass\n")


def test_cost_importance_sizes():
    """Test that importance (λ) correctly scales the size mismatch component."""
    print("Test: Importance size scaling")
    
    page_w, page_h = 1000.0, 1000.0
    rectangles = [
        LayoutRectangle("0", width=500, height=1000, preferred_size=2.0, x=0, y=0),      # 50% of page
        LayoutRectangle("1", width=500, height=700, preferred_size=1.0, x=500, y=0),     # 35% of page
    ]
    
    # Test with size_importance = 100 (very high)
    cost_high_weight = evaluate_layout(
        page_w, page_h, rectangles,
        size_importance=100.0
    )
    
    # Test with size_importance = 1 (balanced)
    cost_balanced = evaluate_layout(
        page_w, page_h, rectangles,
        size_importance=1.0
    )
    
    print(f"  High size importance (100×): {cost_high_weight}")
    print(f"  Balanced (1×): {cost_balanced}")
    
    # Weight mismatch should dominate when importance is high
    assert cost_high_weight.size_mismatch_cost > cost_high_weight.empty_space_cost * 10, \
        "With high size_importance, size mismatch should dominate"
    
    print("  ✅ Pass\n")


if __name__ == "__main__":
    print("=" * 70)
    print("Layout Cost Evaluation Tests")
    print("=" * 70)
    print()
    
    test_empty_page()
    test_perfect_layout()
    test_weight_mismatch()
    test_partial_coverage()
    test_mcf_helper()
    test_cost_importance_sizes()
    
    print("=" * 70)
    print("✅ All tests passed!")
    print("=" * 70)
