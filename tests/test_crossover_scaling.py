#!/usr/bin/env python3
"""Test crossover effectiveness on small vs large layouts."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from samples_helpers import read_page_file
from cewe_layout.algorithms.fan_layout import _generate_random_tree, _crossover_trees, _evaluate_cost
from cewe_layout.gap_utils import analyze_gaps, transform_page_to_gapfree
from cewe_layout.algorithms.base import LayoutRectangle
import copy

def test_crossover_on_page(page_num, num_trials=20):
    """Test how often crossover finds matching subtrees and changes layouts."""
    page_file = Path(f'tests/samples/Test-album-page-{page_num}.txt')
    page_data = read_page_file(page_file)
    
    # Build items and rectangles
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
    
    n_items = len(input_rectangles)
    photo_indices = list(range(n_items))
    
    # Statistics
    total_crossovers = 0
    successful_crossovers = 0  # Found matching subtrees
    effective_crossovers = 0   # Actually changed layout
    cost_improvements = 0      # Improved cost
    
    for trial in range(num_trials):
        # Generate two random trees
        tree1 = _generate_random_tree(n_items, photo_indices)
        tree2 = _generate_random_tree(n_items, photo_indices)
        
        # Evaluate parents
        tree1.compute_aspect_ratios(input_rectangles)
        tree1.compute_dimensions(eval_page_w, eval_page_h, input_rectangles)
        tree1.compute_layout(0, 0)
        cost1 = _evaluate_cost(tree1, eval_page_w, eval_page_h, input_rectangles, 100.0, 0.5, 5.0)
        
        tree2.compute_aspect_ratios(input_rectangles)
        tree2.compute_dimensions(eval_page_w, eval_page_h, input_rectangles)
        tree2.compute_layout(0, 0)
        cost2 = _evaluate_cost(tree2, eval_page_w, eval_page_h, input_rectangles, 100.0, 0.5, 5.0)
        
        # Get parent layouts
        parent1_leaves = tree1.collect_leaves()
        parent1_positions = [(l.x, l.y, l.width, l.height) for l in sorted(parent1_leaves, key=lambda x: x.item_idx)]
        
        # Perform crossover
        child1, child2 = _crossover_trees(tree1, tree2)
        
        # Check if crossover found matching subtrees
        # (if children are deep copies of parents, no crossover happened)
        child1_copy = copy.deepcopy(tree1)
        child1.compute_aspect_ratios(input_rectangles)
        child1.compute_dimensions(eval_page_w, eval_page_h, input_rectangles)
        child1.compute_layout(0, 0)
        
        child1_leaves = child1.collect_leaves()
        child1_positions = [(l.x, l.y, l.width, l.height) for l in sorted(child1_leaves, key=lambda x: x.item_idx)]
        
        # Check if layout actually changed
        layout_changed = any(
            abs(p[0] - c[0]) > 0.1 or abs(p[1] - c[1]) > 0.1 or 
            abs(p[2] - c[2]) > 0.1 or abs(p[3] - c[3]) > 0.1
            for p, c in zip(parent1_positions, child1_positions)
        )
        
        total_crossovers += 1
        if layout_changed:
            effective_crossovers += 1
            
            # Evaluate child
            child1_cost = _evaluate_cost(child1, eval_page_w, eval_page_h, input_rectangles, 100.0, 0.5, 5.0)
            if child1_cost < min(cost1, cost2):
                cost_improvements += 1
    
    return {
        'n_items': n_items,
        'total_crossovers': total_crossovers,
        'effective_crossovers': effective_crossovers,
        'effective_rate': effective_crossovers / total_crossovers if total_crossovers > 0 else 0,
        'cost_improvements': cost_improvements,
        'improvement_rate': cost_improvements / total_crossovers if total_crossovers > 0 else 0
    }

# Test small, medium, and large layouts
test_pages = [
    (2, 4),    # Small: 4 photos
    (17, 4),   # Small: 4 photos + 1 text
    (29, 5),   # Small: 5 photos
    (8, 11),   # Medium: 11 photos
    (30, 12),  # Medium: 12 photos
    (34, 18),  # Large: 18 photos
]

print("="*80)
print("Crossover Effectiveness: Small vs Medium vs Large Layouts")
print("="*80)
print(f"{'Page':<6} {'Items':<6} {'Effective':<12} {'Rate':<12} {'Improvements':<15}")
print("-"*80)

for page_num, expected_items in test_pages:
    result = test_crossover_on_page(page_num, num_trials=20)
    print(f"{page_num:<6} {result['n_items']:<6} "
          f"{result['effective_crossovers']}/20{'':<7} "
          f"{result['effective_rate']*100:>5.1f}%{'':<6} "
          f"{result['cost_improvements']}/20 ({result['improvement_rate']*100:.1f}%)")

print("\n" + "="*80)
print("HYPOTHESIS: Larger layouts should have higher crossover effectiveness")
print("="*80)
