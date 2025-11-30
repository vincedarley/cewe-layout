#!/usr/bin/env python3
"""Test Fan-GA on pages 30, 31, 34 with increasing parameters."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from samples_helpers import read_page_file
from cewe_layout.algorithms.fan_layout import FanLayoutAlgorithm
from cewe_layout.gap_utils import analyze_gaps, transform_page_to_gapfree
from cewe_layout.algorithms.base import LayoutRectangle

def test_page_with_params(page_num, pop, gen):
    """Test a page with specific parameters."""
    page_file = Path(f'tests/samples/Test-album-page-{page_num}.txt')
    page_data = read_page_file(page_file)
    
    items = []
    for photo in page_data.photos:
        pos_x, pos_y = photo['pos']
        items.append({
            'area_left': pos_x,
            'area_top': pos_y,
            'area_width': photo['slot_width'],
            'area_height': photo['slot_height']
        })
    
    gap_analysis = analyze_gaps(items, page_data.page_width, page_data.page_height, page_data.origin_left)
    eval_page_w, eval_page_h = transform_page_to_gapfree(
        page_data.page_width, page_data.page_height,
        gap_analysis.edge_gap, gap_analysis.internal_gap
    )
    
    # Build rectangles
    input_rectangles = []
    for i, photo in enumerate(page_data.photos):
        pos_x, pos_y = photo['pos']
        slot_w, slot_h = photo['slot_width'], photo['slot_height']
        
        gf_left = pos_x - gap_analysis.edge_gap
        gf_top = pos_y - gap_analysis.edge_gap
        rect_width = slot_w + gap_analysis.internal_gap
        rect_height = slot_h + gap_analysis.internal_gap
        
        rect = LayoutRectangle(
            item_id=f'photo_{i}',
            width=rect_width,
            height=rect_height,
            preferred_size=0,
            preserve_aspect_ratio=True,
            x=gf_left,
            y=gf_top
        )
        input_rectangles.append(rect)
    
    total_gf_area = sum(r.width * r.height for r in input_rectangles)
    for rect in input_rectangles:
        gf_area = rect.width * rect.height
        rect.preferred_size = (gf_area / total_gf_area * 10.0) if total_gf_area > 0 else 1.0
    
    algo = FanLayoutAlgorithm(population_size=pop, generations=gen)
    success, result_rectangles, error_msg = algo.generate_layout(
        page_width=eval_page_w,
        page_height=eval_page_h,
        rectangles=input_rectangles
    )
    
    if not success:
        return None, None, None
    
    # Evaluate cost
    from cewe_layout.algorithms.evaluator import evaluate_layout as eval_fn
    cost_result = eval_fn(
        eval_page_w,
        eval_page_h,
        result_rectangles,
        size_importance=100.0,
        acceptable_empty_fraction=0.05,
        undersized_threshold=0.5,
        undersized_penalty=5.0
    )
    
    return cost_result.total_cost, cost_result.empty_space_fraction * 100, cost_result.undersized_count

# Test pages 30, 31, 34 with increasing parameters
test_configs = [
    (10, 20),
    (20, 50),
    (50, 100),
    (100, 200),
]

for page_num in [30, 31, 34]:
    page_file = Path(f'tests/samples/Test-album-page-{page_num}.txt')
    page_data = read_page_file(page_file)
    n_items = len(page_data.photos)
    
    print(f"\nPage {page_num} ({n_items} photos):")
    print(f"{'Pop':>5} {'Gen':>5} {'Cost':>15} {'Empty%':>8} {'Under':>6}")
    print("-" * 50)
    
    for pop, gen in test_configs:
        cost, empty, under = test_page_with_params(page_num, pop, gen)
        if cost is not None:
            print(f"{pop:>5} {gen:>5} {cost:>15,.2f} {empty:>7.2f}% {under:>6}")
        else:
            print(f"{pop:>5} {gen:>5} {'FAILED':>15}")
