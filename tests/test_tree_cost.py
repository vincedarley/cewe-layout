#!/usr/bin/env python3
"""
Test 3: Tree Layout Cost

For each page, build a tree from the original layout, recompute the layout from
the tree, and evaluate the cost of the tree-recomputed layout.

This test resolves the mystery: tree costs should be ~100-400 (small adjustments
from tree constraints), not < 1 like original layouts.

Usage:
  python tests/test_tree_cost.py [page_num]
  
  If page_num is provided, only that page is tested.
  Otherwise all pages in tests/samples/ are tested.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_helpers import read_page_file, write_result_section
from cewe_layout.algorithms.evaluator import evaluate_layout
from cewe_layout.algorithms.tree_builder import build_tree_from_layout, TreeNode
from cewe_layout.gap_utils import analyze_gaps, transform_page_to_gapfree, transform_item_to_gapfree
from cewe_layout.algorithms.base import LayoutRectangle


def test_page_tree_cost(page_file: Path):
    """
    Test tree layout cost for a single page.
    
    Args:
        page_file: Path to Test-album-page-N.txt
    """
    # Read page data
    page_data = read_page_file(page_file)
    
    if not page_data.photos and not page_data.texts:
        print(f'Page {page_data.page_num}: Skipping (no items)')
        return
    
    # Analyze gaps to get edge and internal gap
    items = []
    for photo in page_data.photos:
        pos_x, pos_y = photo['pos']
        items.append({
            'area_left': pos_x,
            'area_top': pos_y,
            'area_width': photo['slot_width'],
            'area_height': photo['slot_height']
        })
    
    for text in page_data.texts:
        pos_x, pos_y = text['pos']
        items.append({
            'area_left': pos_x,
            'area_top': pos_y,
            'area_width': text['width'],
            'area_height': text['height']
        })
    
    gap_analysis = analyze_gaps(items, page_data.page_width, page_data.page_height, page_data.origin_left)
    
    # Transform page to gap-free space
    eval_page_w, eval_page_h = transform_page_to_gapfree(
        page_data.page_width,
        page_data.page_height,
        gap_analysis.edge_gap,
        gap_analysis.internal_gap
    )
    
    # Build original rectangles for tree building
    # TreeBuilder uses slot dimensions with gap-free coordinates
    # Match collage_wrapper: add internal_gap to slot dimensions to convert to gap-free space
    original_rectangles = []
    
    for i, photo in enumerate(page_data.photos):
        pos_x, pos_y = photo['pos']
        slot_w, slot_h = photo['slot_width'], photo['slot_height']
        
        # Position: gap-free (subtract edge_gap only, NOT transform_item_to_gapfree)
        gf_left = pos_x - gap_analysis.edge_gap
        gf_top = pos_y - gap_analysis.edge_gap
        
        # Dimensions: gap-free slot dimensions (add internal_gap to match collage_wrapper)
        rect_width = slot_w + gap_analysis.internal_gap
        rect_height = slot_h + gap_analysis.internal_gap
        
        rect = LayoutRectangle(
            item_id=f'photo_{i}',
            width=rect_width,
            height=rect_height,
            preferred_size=0,  # Will be set below after all areas computed
            preserve_aspect_ratio=True,
            x=gf_left,
            y=gf_top
        )
        original_rectangles.append(rect)
    
    for i, text in enumerate(page_data.texts):
        pos_x, pos_y = text['pos']
        text_w, text_h = text['width'], text['height']
        
        # Position: gap-free (subtract edge_gap)
        gf_left = pos_x - gap_analysis.edge_gap
        gf_top = pos_y - gap_analysis.edge_gap
        
        # Dimensions: RAW dimensions (no gap added)
        rect_width = text_w
        rect_height = text_h
        
        rect = LayoutRectangle(
            item_id=f'text_{i}',
            width=rect_width,
            height=rect_height,
            preferred_size=0,  # Will be set below
            preserve_aspect_ratio=False,
            x=gf_left,
            y=gf_top
        )
        original_rectangles.append(rect)
    
    # Now compute preferred sizes using gap-free areas (matching GUI)
    # GUI uses transform_item_to_gapfree which adds internal_gap to dimensions
    # We already added internal_gap to rect dimensions above, so use those directly
    total_gf_area = sum(r.width * r.height for r in original_rectangles)
    
    for rect in original_rectangles:
        gf_area = rect.width * rect.height
        rect.preferred_size = (gf_area / total_gf_area * 10.0) if total_gf_area > 0 else 1.0
    
    if not original_rectangles:
        print(f'Page {page_data.page_num}: Skipping (no rectangles)')
        return
    
    # Build tree from original layout
    tolerance = 20.0  # 2mm tolerance as used in TreeBuilder
    tree = build_tree_from_layout(original_rectangles, eval_page_w, eval_page_h, tolerance)
    
    if tree is None:
        result = f'''Tree building FAILED
Cannot build tree from this layout (tolerance={tolerance})
'''
        results_file = page_file.parent / f'{page_file.stem}-results.txt'
        write_result_section(results_file, 'Tree Layout Cost', result)
        print(f'Page {page_data.page_num}: FAILED to build tree')
        return
    
    # Recompute layout from tree
    tree.compute_aspect_ratios(original_rectangles)
    
    # Diagnostic for Page 2: check aspect ratios
    if page_data.page_num == 2:
        print(f"\n=== Tree Debug for Page 2 ===")
        print(f"Original rectangles passed to tree:")
        for i, rect in enumerate(original_rectangles):
            aspect = rect.width / rect.height if rect.height > 0 else 0
            print(f"  Photo {i}: {rect.width:.2f} x {rect.height:.2f}, aspect={aspect:.6f}")
        print(f"\nTree aspect ratios after compute_aspect_ratios:")
        leaves = tree.collect_leaves()
        for i, leaf in enumerate(leaves):
            print(f"  Leaf {i}: aspect_ratio={leaf.aspect_ratio:.6f}")
        print()
    
    tree.compute_dimensions(eval_page_w, eval_page_h, original_rectangles)
    tree.compute_layout(0, 0)
    
    # Collect results from tree leaves
    leaves = tree.collect_leaves()
    tree_rectangles = []
    for leaf in leaves:
        rect = original_rectangles[leaf.item_idx]
        
        tree_rect = LayoutRectangle(
            item_id=rect.item_id,
            width=leaf.width,
            height=leaf.height,
            preferred_size=rect.preferred_size,
            preserve_aspect_ratio=rect.preserve_aspect_ratio,
            x=leaf.x,
            y=leaf.y
        )
        # Don't set actual_size - let evaluator compute it from width * height
        tree_rectangles.append(tree_rect)
    
    # Evaluate tree-recomputed layout
    cost_result = evaluate_layout(
        eval_page_w,
        eval_page_h,
        tree_rectangles,
        size_importance=100.0,
        acceptable_empty_fraction=0.05,
        undersized_threshold=0.5,
        undersized_penalty=5.0
    )
    
    # Diagnostic output for problematic pages
    if page_data.page_num in [2, 22, 35]:
        print(f"\nDiagnostic for Page {page_data.page_num}:")
        print(f"  Cost result: {cost_result.total_cost}")
        print(f"  Empty space cost: {cost_result.empty_space_cost}")
        print(f"  Size mismatch cost: {cost_result.size_mismatch_cost}")
        print(f"  Size mismatch / size_importance = {cost_result.size_mismatch_cost / 100.0}")
        print(f"\n  Rectangles passed to evaluator:")
        for i, rect in enumerate(tree_rectangles):
            area = rect.width * rect.height
            print(f"    {i}: preferred_size={rect.preferred_size:.4f}, dims={rect.width:.2f}x{rect.height:.2f}, area={area:.2f}")
        print(f"\n  Size errors from evaluator:")
        for item_id, pref_norm, actual_norm, sq_err, undersized in cost_result.size_errors:
            print(f"    {item_id}: pref={pref_norm:.6f}, actual={actual_norm:.6f}, sq_err={sq_err:.8f}, undersized={undersized}")
        print()
    
    # Format results
    tree_structure = tree.to_compact_string()
    result = f'''Total cost: {cost_result.total_cost:.2f}

Tree structure: {tree_structure}

Components:
  Empty space cost: {cost_result.empty_space_cost:.2f}
  Size mismatch cost: {cost_result.size_mismatch_cost:.2f}
    - Normal: {cost_result.size_mismatch_normal_cost:.2f}
    - Undersized: {cost_result.size_mismatch_undersized_cost:.2f}

Details:
  Empty fraction: {cost_result.empty_space_fraction:.4f} ({cost_result.empty_space_fraction * 100:.2f}%)
  Undersized count: {cost_result.undersized_count}
  Tree tolerance: {tolerance} units ({tolerance / 10:.1f} mm)
'''
    
    # Write to results file
    results_file = page_file.parent / f'{page_file.stem}-results.txt'
    write_result_section(results_file, 'Tree Layout Cost', result)
    
    print(f'Page {page_data.page_num}: cost={cost_result.total_cost:.2f}, empty={cost_result.empty_space_fraction * 100:.2f}%, undersized={cost_result.undersized_count}')


def main():
    if len(sys.argv) > 1:
        # Test specific page
        page_num = int(sys.argv[1])
        page_file = Path('tests/samples') / f'Test-album-page-{page_num}.txt'
        if page_file.exists():
            test_page_tree_cost(page_file)
        else:
            print(f'Error: {page_file} not found')
            sys.exit(1)
    else:
        # Test all pages
        samples_dir = Path('tests/samples')
        page_files = sorted([f for f in samples_dir.glob('Test-album-page-*.txt') 
                           if not f.stem.endswith('-results')])
        
        for page_file in page_files:
            test_page_tree_cost(page_file)


if __name__ == '__main__':
    main()
