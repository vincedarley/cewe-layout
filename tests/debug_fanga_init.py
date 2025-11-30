#!/usr/bin/env python3
"""Debug Fan-GA initialization to understand why it fails."""

import sys
from pathlib import Path
import random

sys.path.insert(0, str(Path(__file__).parent.parent))

from samples_helpers import read_page_file
from cewe_layout.algorithms.evaluator import evaluate_layout
from cewe_layout.algorithms.fan_layout import _generate_random_tree, _evaluate_cost
from cewe_layout.gap_utils import analyze_gaps, transform_page_to_gapfree
from cewe_layout.algorithms.base import LayoutRectangle

def analyze_initial_population(page_num, pop_size=20):
    """Analyze the initial random population for a page."""
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
    
    # Compute preferred sizes
    total_gf_area = sum(r.width * r.height for r in input_rectangles)
    for rect in input_rectangles:
        gf_area = rect.width * rect.height
        rect.preferred_size = (gf_area / total_gf_area * 10.0) if total_gf_area > 0 else 1.0
    
    print(f"\nPage {page_num}: {len(input_rectangles)} items")
    print(f"Preferred sizes: {[f'{r.preferred_size:.2f}' for r in input_rectangles]}")
    print(f"\nGenerating {pop_size} random trees...")
    
    n_photos = len(input_rectangles)
    photo_indices = list(range(n_photos))
    
    # Generate random population
    costs = []
    for i in range(pop_size):
        tree = _generate_random_tree(n_photos, photo_indices)
        tree.compute_aspect_ratios(input_rectangles)
        tree.compute_dimensions(eval_page_w, eval_page_h, input_rectangles)
        tree.compute_layout(0, 0)
        
        cost = _evaluate_cost(tree, eval_page_w, eval_page_h, input_rectangles, 
                            size_importance=100.0, undersized_threshold=0.5, 
                            undersized_penalty=5.0)
        costs.append(cost)
    
    costs.sort()
    print(f"\nInitial population costs:")
    print(f"  Best:    {costs[0]:.2f}")
    print(f"  Median:  {costs[len(costs)//2]:.2f}")
    print(f"  Worst:   {costs[-1]:.2f}")
    print(f"  Mean:    {sum(costs)/len(costs):.2f}")
    
    return costs

# Compare good vs bad pages
if __name__ == '__main__':
    print("="*60)
    print("Comparing initial populations: Good pages vs Bad pages")
    print("="*60)
    
    print("\n### GOOD PAGES (Fan-GA works) ###")
    for page in [2, 7]:
        analyze_initial_population(page, pop_size=20)
    
    print("\n\n### BAD PAGES (Fan-GA fails) ###")
    for page in [17, 29]:
        analyze_initial_population(page, pop_size=20)
    
    # Test if larger pop helps Page 17
    print("\n\n### Testing larger population on Page 17 ###")
    analyze_initial_population(17, pop_size=200)
