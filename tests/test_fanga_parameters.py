#!/usr/bin/env python3
"""Test Fan-GA with different parameters on specific pages."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from test_helpers import read_page_file
from cewe_layout.algorithms.evaluator import evaluate_layout
from cewe_layout.algorithms.fan_layout import FanLayoutAlgorithm
from cewe_layout.gap_utils import analyze_gaps, transform_page_to_gapfree
from cewe_layout.algorithms.base import LayoutRectangle

def test_with_params(page_num, pop_size, generations):
    """Test Fan-GA with specific parameters."""
    page_file = Path(f'tests/samples/Test-album-page-{page_num}.txt')
    page_data = read_page_file(page_file)
    
    # Build items for gap analysis
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
    eval_page_w, eval_page_h = transform_page_to_gapfree(
        page_data.page_width, page_data.page_height,
        gap_analysis.edge_gap, gap_analysis.internal_gap
    )
    
    # Build input rectangles
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
    
    for i, text in enumerate(page_data.texts):
        pos_x, pos_y = text['pos']
        text_w, text_h = text['width'], text['height']
        
        gf_left = pos_x - gap_analysis.edge_gap
        gf_top = pos_y - gap_analysis.edge_gap
        rect_width = text_w + gap_analysis.internal_gap
        rect_height = text_h + gap_analysis.internal_gap
        
        rect = LayoutRectangle(
            item_id=f'text_{i}',
            width=rect_width,
            height=rect_height,
            preferred_size=0,
            preserve_aspect_ratio=False,
            x=gf_left,
            y=gf_top
        )
        input_rectangles.append(rect)
    
    # Compute preferred sizes
    total_gf_area = sum(r.width * r.height for r in input_rectangles)
    for rect in input_rectangles:
        gf_area = rect.width * rect.height
        rect.preferred_size = (gf_area / total_gf_area * 10.0) if total_gf_area > 0 else 1.0
    
    # Run Fan-GA
    fanga = FanLayoutAlgorithm(
        population_size=pop_size,
        generations=generations,
        mutation_rate=0.2,
        crossover_rate=0.8,
        size_importance=100.0
    )
    
    success, result_rectangles, error_msg = fanga.generate_layout(
        page_width=eval_page_w,
        page_height=eval_page_h,
        rectangles=input_rectangles
    )
    
    if not success:
        return None, error_msg
    
    # Evaluate
    cost_result = evaluate_layout(
        eval_page_w, eval_page_h, result_rectangles,
        size_importance=100.0,
        acceptable_empty_fraction=0.05,
        undersized_threshold=0.5,
        undersized_penalty=5.0
    )
    
    return cost_result, None

# Test multiple problematic pages with increasing parameters
test_pages = [17, 29, 5, 28]  # 4, 5, 6, 6 photos respectively

for page in test_pages:
    print(f"\nTesting Page {page} with different parameters:")
    print(f"{'Pop':<6} {'Gen':<6} {'Cost':<12} {'Empty':<8} {'Under':<6}")
    print("-" * 50)
    
    for pop, gen in [(5, 10), (10, 20), (20, 50), (50, 100)]:
        result, error = test_with_params(page, pop, gen)
        if result:
            print(f"{pop:<6} {gen:<6} {result.total_cost:<12.2f} {result.empty_space_fraction*100:<8.2f} {result.undersized_count:<6}")
        else:
            print(f"{pop:<6} {gen:<6} FAILED: {error}")
