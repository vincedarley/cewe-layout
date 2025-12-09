#!/usr/bin/env python3
"""
Test: Collage-Generator Layout Cost

For each page, run the Collage-Generator algorithm and evaluate the cost of the resulting layout.
Compare with other algorithm results to validate collage-generator performance.

Usage:
  python tests/samples_collage_cost.py [page_num]
  
  If page_num is provided, only that page is tested.
  Otherwise all pages in tests/samples/ are tested.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from samples_helpers import read_page_file, write_result_section
from cewe_layout.algorithms.evaluator import evaluate_layout
from cewe_layout.algorithms.collage_generator import CollageGeneratorAlgorithm
from cewe_layout.gap_utils import analyze_gaps, transform_page_to_gapfree, make_uniform_edge_gap
from cewe_layout.algorithms.base import LayoutRectangle


def test_page_collage_cost(page_file: Path):
    """
    Test Collage-Generator layout cost for a single page.
    
    Args:
        page_file: Path to Test-album-page-N.txt
    """
    # Read page data
    page_data = read_page_file(page_file)
    
    print(f'Page {page_data.page_num}...', end='', flush=True)
    
    if not page_data.photos and not page_data.texts:
        print(f' Skipping (no items)')
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
    
    gap_analysis = analyze_gaps(items, page_data.page_width, page_data.page_height, page_data.origin_left, is_spread=False)
    
    # Transform page to gap-free space
    eval_page_w, eval_page_h = transform_page_to_gapfree(
        page_data.page_width,
        page_data.page_height,
        gap_analysis.edge_gap,
        gap_analysis.internal_gap,
        is_spread=False
    )
    
    # Build input rectangles for Collage-Generator
    # Collage-Generator operates in gap-free coordinate space
    input_rectangles = []
    
    for i, photo in enumerate(page_data.photos):
        pos_x, pos_y = photo['pos']
        slot_w, slot_h = photo['slot_width'], photo['slot_height']
        
        # Dimensions: gap-free slot dimensions (add internal_gap)
        rect_width = slot_w + gap_analysis.internal_gap
        rect_height = slot_h + gap_analysis.internal_gap
        
        rect = LayoutRectangle(
            item_id=f'photo_{i}',
            width=rect_width,
            height=rect_height,
            preferred_size=0,  # Will be set below
            preserve_aspect_ratio=True
        )
        input_rectangles.append(rect)
    
    for i, text in enumerate(page_data.texts):
        pos_x, pos_y = text['pos']
        text_w, text_h = text['width'], text['height']
        
        # Dimensions: gap-free (add internal_gap)
        rect_width = text_w + gap_analysis.internal_gap
        rect_height = text_h + gap_analysis.internal_gap
        
        rect = LayoutRectangle(
            item_id=f'text_{i}',
            width=rect_width,
            height=rect_height,
            preferred_size=0,  # Will be set below
            preserve_aspect_ratio=False
        )
        input_rectangles.append(rect)
    
    # Compute preferred sizes using gap-free areas (matching GUI)
    total_gf_area = sum(r.width * r.height for r in input_rectangles)
    
    for rect in input_rectangles:
        gf_area = rect.width * rect.height
        rect.preferred_size = (gf_area / total_gf_area * 10.0) if total_gf_area > 0 else 1.0
    
    if not input_rectangles:
        print(f' Skipping (no rectangles)')
        return
    
    # Run Collage-Generator algorithm
    collage = CollageGeneratorAlgorithm(
        temperature=1.0,
        threshold=1e-4
    )
    
    try:
        # Run algorithm
        success, result_rectangles, error_msg = collage.generate_layout(
            page_width=eval_page_w,
            page_height=eval_page_h,
            rectangles=input_rectangles
        )
        
        if not success:
            result = f'''Collage-Generator FAILED
Error: {error_msg}
'''
            results_file = page_file.parent / f'{page_file.stem}-results.txt'
            write_result_section(results_file, 'Collage-Generator Layout Cost', result)
            print(f' FAILED ({error_msg})')
            return
        
        if not result_rectangles:
            result = f'''Collage-Generator FAILED
Algorithm returned no rectangles
'''
            results_file = page_file.parent / f'{page_file.stem}-results.txt'
            write_result_section(results_file, 'Collage-Generator Layout Cost', result)
            print(f' FAILED (no result rectangles)')
            return
        
    except Exception as e:
        result = f'''Collage-Generator FAILED
Exception: {str(e)}
'''
        results_file = page_file.parent / f'{page_file.stem}-results.txt'
        write_result_section(results_file, 'Collage-Generator Layout Cost', result)
        print(f' FAILED (exception: {str(e)})')
        return
    
    # Evaluate Collage-Generator layout
    cost_result = evaluate_layout(
        eval_page_w,
        eval_page_h,
        result_rectangles,
        size_importance=100.0,
        acceptable_empty_fraction=0.05,
        undersized_threshold=0.5,
        undersized_penalty=5.0
    )
    
    # Get tree structure from converted TreeNode
    tree = collage.get_final_tree()
    tree_structure = tree.to_compact_string() if tree else "N/A"
    
    # Format results
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
'''
    
    # Write to results file
    results_file = page_file.parent / f'{page_file.stem}-results.txt'
    write_result_section(results_file, 'Collage-Generator Layout Cost', result)
    
    print(f' cost={cost_result.total_cost:.2f}, empty={cost_result.empty_space_fraction * 100:.2f}%, undersized={cost_result.undersized_count}')


def main():
    if len(sys.argv) > 1:
        # Test specific page
        page_num = int(sys.argv[1])
        page_file = Path('tests/samples') / f'Test-album-page-{page_num}.txt'
        if page_file.exists():
            test_page_collage_cost(page_file)
        else:
            print(f'Error: {page_file} not found')
            sys.exit(1)
    else:
        # Test all pages
        samples_dir = Path('tests/samples')
        page_files = sorted([f for f in samples_dir.glob('Test-album-page-*.txt') 
                           if not f.stem.endswith('-results')])
        
        for page_file in page_files:
            test_page_collage_cost(page_file)


if __name__ == '__main__':
    main()
