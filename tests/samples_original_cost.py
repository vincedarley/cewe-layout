#!/usr/bin/env python3
"""
Test 2: Original Layout Cost

For each page, compute the cost of the original layout using core code routines.
Write results to the page's results file.

Usage:
  python tests/samples_original_cost.py [page_num]
  
  If page_num is provided, only that page is tested.
  Otherwise all pages in tests/samples/ are tested.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from samples_helpers import read_page_file, write_result_section, page_data_to_rectangles
from cewe_layout.algorithms.evaluator import evaluate_layout
from cewe_layout.gap_utils import analyze_gaps, make_uniform_edge_gap, transform_page_to_gapfree, transform_item_to_gapfree
from cewe_layout.algorithms.base import LayoutRectangle


def test_page_cost(page_file: Path):
    """
    Test original layout cost for a single page.
    
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
    
    gap_analysis = analyze_gaps(items, page_data.page_width, page_data.page_height, page_data.origin_left, is_spread=False)
    
    # Transform page to gap-free space
    eval_page_w, eval_page_h = transform_page_to_gapfree(
        page_data.page_width,
        page_data.page_height,
        gap_analysis.edge_gap,
        gap_analysis.internal_gap,
        is_spread=False
    )
    
    # Transform rectangles to gap-free space
    rectangles = []
    
    # Add photos
    for i, photo in enumerate(page_data.photos):
        pos_x, pos_y = photo['pos']
        slot_w, slot_h = photo['slot_width'], photo['slot_height']
        
        # Transform to gap-free coordinates
        gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
            pos_x, pos_y, slot_w, slot_h,
            gap_analysis.edge_gap,
            gap_analysis.internal_gap,
            is_spread=False,
            is_left_page=True
        )
        
        # Use gap-free slot area as preferred size (what was allocated in original layout)
        preferred_size = gf_width * gf_height
        
        rect = LayoutRectangle(
            item_id=f'photo_{i}',
            width=gf_width,
            height=gf_height,
            preferred_size=preferred_size,
            preserve_aspect_ratio=True,
            x=gf_left,
            y=gf_top
        )
        rect.actual_size = preferred_size
        rectangles.append(rect)
    
    # Add text blocks
    for i, text in enumerate(page_data.texts):
        pos_x, pos_y = text['pos']
        text_w, text_h = text['width'], text['height']
        
        # Transform to gap-free coordinates
        gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
            pos_x, pos_y, text_w, text_h,
            gap_analysis.edge_gap,
            gap_analysis.internal_gap,
            is_spread=False,
            is_left_page=True
        )
        
        # Use gap-free area as preferred size
        preferred_size = gf_width * gf_height
        
        rect = LayoutRectangle(
            item_id=f'text_{i}',
            width=gf_width,
            height=gf_height,
            preferred_size=preferred_size,
            preserve_aspect_ratio=False,  # Text blocks don't preserve aspect ratio
            x=gf_left,
            y=gf_top
        )
        rect.actual_size = preferred_size
        rectangles.append(rect)
    
    if not rectangles:
        print(f'Page {page_data.page_num}: Skipping (no rectangles)')
        return
    
    # Evaluate layout in gap-free space
    cost_result = evaluate_layout(
        eval_page_w,
        eval_page_h,
        rectangles,
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
'''
    
    # Write to results file
    results_file = page_file.parent / f'{page_file.stem}-results.txt'
    write_result_section(results_file, 'Original Layout Cost', result)
    
    print(f'Page {page_data.page_num}: cost={cost_result.total_cost:.2f}, empty={cost_result.empty_space_fraction * 100:.2f}%, undersized={cost_result.undersized_count}')


def main():
    if len(sys.argv) > 1:
        # Test specific page
        page_num = int(sys.argv[1])
        page_file = Path('tests/samples') / f'Test-album-page-{page_num}.txt'
        if page_file.exists():
            test_page_cost(page_file)
        else:
            print(f'Error: {page_file} not found')
            sys.exit(1)
    else:
        # Test all pages
        samples_dir = Path('tests/samples')
        page_files = sorted([f for f in samples_dir.glob('Test-album-page-*.txt') 
                           if not f.stem.endswith('-results')])
        
        for page_file in page_files:
            test_page_cost(page_file)


if __name__ == '__main__':
    main()
