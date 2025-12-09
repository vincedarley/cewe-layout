#!/usr/bin/env python3
"""
Test that clone() produces identical Fan-GA results to deepcopy().

This test runs Fan-GA on real album pages using both clone() and deepcopy()
with identical random seeds, and verifies the results are identical.
"""

import sys
import copy
import random
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
# Add tests directory to path for samples_helpers
sys.path.insert(0, str(Path(__file__).parent))

from samples_helpers import read_page_file
from cewe_layout.algorithms.fan_layout import FanLayoutAlgorithm
from cewe_layout.algorithms.base import TreeNode, LayoutRectangle
from cewe_layout.algorithms.evaluator import evaluate_layout
from cewe_layout.gap_utils import analyze_gaps, transform_page_to_gapfree, make_uniform_edge_gap


def patch_fan_to_use_deepcopy():
    """Monkey-patch TreeNode.clone() to use deepcopy instead."""
    original_clone = TreeNode.clone
    
    def deepcopy_clone(self, parent=None):
        """Use deepcopy instead of fast clone."""
        cloned = copy.deepcopy(self)
        # Fix parent pointer
        cloned.parent = parent
        return cloned
    
    TreeNode.clone = deepcopy_clone
    return original_clone


def restore_original_clone(original_clone):
    """Restore the original clone method."""
    TreeNode.clone = original_clone


def run_fanga_on_page(page_file: Path, use_deepcopy: bool, seed: int = 42):
    """
    Run Fan-GA on a page using either clone() or deepcopy().
    
    Args:
        page_file: Path to page file
        use_deepcopy: If True, patch clone() to use deepcopy
        seed: Random seed
        
    Returns:
        Tuple of (layout, cost, page_width, page_height) or (None, None, None, None)
    """
    # Read page data
    page_data = read_page_file(page_file)
    
    if not page_data.photos:
        return None, None, None, None
    
    # Analyze gaps
    items = []
    for photo in page_data.photos:
        pos_x, pos_y = photo['pos']
        items.append({
            'area_left': pos_x,
            'area_top': pos_y,
            'area_width': photo['slot_width'],
            'area_height': photo['slot_height']
        })
    
    gap_analysis = analyze_gaps(items, page_data.page_width, page_data.page_height, page_data.origin_left, is_spread=False)
    edge_gap, internal_gap = gap_analysis
    
    # Transform to gap-free space
    eval_page_w, eval_page_h = transform_page_to_gapfree(
        page_data.page_width,
        page_data.page_height,
        edge_gap,
        internal_gap,
        is_spread=False
    )
    
    # Build input rectangles
    input_rectangles = []
    for i, photo in enumerate(page_data.photos):
        # Use image dimensions as preferred size
        img_w, img_h = photo['img_width'], photo['img_height']
        preferred_size = img_w * img_h
        
        input_rectangles.append(LayoutRectangle(
            item_id=f"photo_{i}",
            width=img_w,
            height=img_h,
            preferred_size=preferred_size,
            preserve_aspect_ratio=True
        ))
    
    # Patch if using deepcopy
    original_clone = None
    if use_deepcopy:
        original_clone = patch_fan_to_use_deepcopy()
    
    try:
        # Set random seed for deterministic results
        random.seed(seed)
        
        # Run Fan-GA
        algorithm = FanLayoutAlgorithm(
            population_size=30,
            generations=20,
            mutation_rate=0.2,
            crossover_rate=0.8,
            elite_size=2
        )
        
        success, layout, msg = algorithm.generate_layout(eval_page_w, eval_page_h, input_rectangles)
        
        if not success:
            return None, None, None, None
        
        # Evaluate the cost of the final layout
        cost = evaluate_layout(eval_page_w, eval_page_h, layout, detailed=False)
        
        return layout, cost, eval_page_w, eval_page_h
    finally:
        # Restore original clone if patched
        if original_clone:
            restore_original_clone(original_clone)


def layouts_are_identical(layout1, layout2, cost1, cost2, tolerance=0.01):
    """
    Check if two layouts are identical within tolerance.
    
    Args:
        layout1, layout2: Lists of LayoutRectangle objects
        cost1, cost2: Layout costs
        tolerance: Maximum difference allowed in positions/dimensions/costs
        
    Returns:
        True if layouts are identical, False otherwise
    """
    # First check costs
    if abs(cost1 - cost2) > tolerance:
        print(f"  ✗ Different costs: {cost1:.6f} vs {cost2:.6f} (diff: {abs(cost1 - cost2):.6f})")
        return False
    
    if len(layout1) != len(layout2):
        print(f"  ✗ Different number of items: {len(layout1)} vs {len(layout2)}")
        return False
    
    for i, (r1, r2) in enumerate(zip(layout1, layout2)):
        if r1.item_id != r2.item_id:
            print(f"  ✗ Item {i}: Different IDs: {r1.item_id} vs {r2.item_id}")
            return False
        
        if abs(r1.x - r2.x) > tolerance:
            print(f"  ✗ Item {i} ({r1.item_id}): Different x: {r1.x:.6f} vs {r2.x:.6f} (diff: {abs(r1.x - r2.x):.6f})")
            return False
        
        if abs(r1.y - r2.y) > tolerance:
            print(f"  ✗ Item {i} ({r1.item_id}): Different y: {r1.y:.6f} vs {r2.y:.6f} (diff: {abs(r1.y - r2.y):.6f})")
            return False
        
        if abs(r1.width - r2.width) > tolerance:
            print(f"  ✗ Item {i} ({r1.item_id}): Different width: {r1.width:.6f} vs {r2.width:.6f} (diff: {abs(r1.width - r2.width):.6f})")
            return False
        
        if abs(r1.height - r2.height) > tolerance:
            print(f"  ✗ Item {i} ({r1.item_id}): Different height: {r1.height:.6f} vs {r2.height:.6f} (diff: {abs(r1.height - r2.height):.6f})")
            return False
    
    return True


def test_page(page_file: Path, seed: int = 42):
    """Test a single page with both clone() and deepcopy()."""
    try:
        page_num = int(page_file.stem.split('-')[-1])
    except ValueError:
        # Not a valid page file
        return None
    print(f"Testing page {page_num}...", end=' ', flush=True)
    
    # Run with clone()
    layout_clone, cost_clone, page_w, page_h = run_fanga_on_page(page_file, use_deepcopy=False, seed=seed)
    
    if layout_clone is None:
        print("skipped (no photos or algorithm failed)")
        return True
    
    # Run with deepcopy()
    layout_deepcopy, cost_deepcopy, _, _ = run_fanga_on_page(page_file, use_deepcopy=True, seed=seed)
    
    if layout_deepcopy is None:
        print("✗ FAILED (deepcopy version failed)")
        return False
    
    # Compare results
    if layouts_are_identical(layout_clone, layout_deepcopy, cost_clone, cost_deepcopy):
        print(f"✓ IDENTICAL (cost: {cost_clone:.2f})")
        return True
    else:
        print("✗ DIFFERENT")
        return False


def main():
    """Run tests on all sample pages."""
    test_dir = Path(__file__).parent / 'samples'
    
    if not test_dir.exists():
        print(f"Error: Test directory not found: {test_dir}")
        sys.exit(1)
    
    # Get all page files
    page_files = sorted(test_dir.glob('Test-album-page-*.txt'))
    
    if not page_files:
        print(f"Error: No page files found in {test_dir}")
        sys.exit(1)
    
    # If a page number is provided, test only that page
    if len(sys.argv) > 1:
        page_num = sys.argv[1]
        page_files = [f for f in page_files if f.stem.endswith(f'-{page_num}')]
        if not page_files:
            print(f"Error: Page {page_num} not found")
            sys.exit(1)
    
    print(f"Testing clone() vs deepcopy() determinism on {len(page_files)} pages\n")
    print("=" * 70)
    
    passed = 0
    failed = 0
    skipped = 0
    
    for page_file in page_files:
        result = test_page(page_file, seed=42)
        if result is None:
            # Not a valid page file, skip without counting
            continue
        elif result is True:
            passed += 1
        elif result is False:
            failed += 1
        else:
            skipped += 1
    
    print("=" * 70)
    print(f"\nResults: {passed} passed, {failed} failed, {skipped} skipped")
    
    if failed > 0:
        print("\n✗ TESTS FAILED - clone() and deepcopy() produce different results!")
        sys.exit(1)
    else:
        print("\n✅ ALL TESTS PASSED - clone() is identical to deepcopy()!")
        sys.exit(0)


if __name__ == '__main__':
    main()
