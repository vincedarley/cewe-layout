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
    
    # Build original rectangles in gap-free space for tree building
    # First, compute total gap-free area to normalize preferred sizes (like GUI does)
    total_gf_area = 0.0
    gf_areas = []
    
    for photo in page_data.photos:
        slot_w, slot_h = photo['slot_width'], photo['slot_height']
        gf_w = slot_w + gap_analysis.internal_gap
        gf_h = slot_h + gap_analysis.internal_gap
        gf_area = gf_w * gf_h
        gf_areas.append(gf_area)
        total_gf_area += gf_area
    
    for text in page_data.texts:
        text_w, text_h = text['width'], text['height']
        gf_w = text_w + gap_analysis.internal_gap
        gf_h = text_h + gap_analysis.internal_gap
        gf_area = gf_w * gf_h
        gf_areas.append(gf_area)
        total_gf_area += gf_area
    
    original_rectangles = []
    gf_idx = 0
    
    for i, photo in enumerate(page_data.photos):
        pos_x, pos_y = photo['pos']
        slot_w, slot_h = photo['slot_width'], photo['slot_height']
        
        # Transform to gap-free coordinates
        gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
            pos_x, pos_y, slot_w, slot_h,
            gap_analysis.edge_gap,
            gap_analysis.internal_gap
        )
        
        # Use normalized gap-free area scaled by 10× (matching GUI's approach)
        # This represents the relative importance from the original layout
        preferred_size = (gf_areas[gf_idx] / total_gf_area * 10.0) if total_gf_area > 0 else 1.0
        gf_idx += 1
        
        rect = LayoutRectangle(
            item_id=f'photo_{i}',
            width=gf_width,
            height=gf_height,
            preferred_size=preferred_size,
            preserve_aspect_ratio=True,
            x=gf_left,
            y=gf_top
        )
        # Don't set actual_size - let evaluator compute it
        original_rectangles.append(rect)
    
    for i, text in enumerate(page_data.texts):
        pos_x, pos_y = text['pos']
        text_w, text_h = text['width'], text['height']
        
        # Transform to gap-free coordinates
        gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
            pos_x, pos_y, text_w, text_h,
            gap_analysis.edge_gap,
            gap_analysis.internal_gap
        )
        
        # Use normalized gap-free area scaled by 10× (matching GUI)
        preferred_size = (gf_areas[gf_idx] / total_gf_area * 10.0) if total_gf_area > 0 else 1.0
        gf_idx += 1
        
        rect = LayoutRectangle(
            item_id=f'text_{i}',
            width=gf_width,
            height=gf_height,
            preferred_size=preferred_size,
            preserve_aspect_ratio=False,
            x=gf_left,
            y=gf_top
        )
        # Don't set actual_size - let evaluator compute it
        original_rectangles.append(rect)
    
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
    
    # Format results
    result = f'''Total cost: {cost_result.total_cost:.2f}

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
