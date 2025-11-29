#!/usr/bin/env python3
"""Verify that structure-only crossover DOES change physical positions."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_helpers import read_page_file
from cewe_layout.algorithms.fan_layout import _generate_random_tree, _crossover_trees, _evaluate_cost
from cewe_layout.gap_utils import analyze_gaps, transform_page_to_gapfree
from cewe_layout.algorithms.base import LayoutRectangle

def compare_tree_structures(tree1, tree2):
    """Compare if two trees have identical structure (V/H topology)."""
    if tree1.is_leaf and tree2.is_leaf:
        return True
    if tree1.is_leaf or tree2.is_leaf:
        return False
    if tree1.label != tree2.label:
        return False
    return (compare_tree_structures(tree1.left, tree2.left) and 
            compare_tree_structures(tree1.right, tree2.right))

def test_structure_vs_physical_change(page_num, num_trials=20):
    """Test if structure changes lead to physical position changes."""
    page_file = Path(f'tests/samples/Test-album-page-{page_num}.txt')
    page_data = read_page_file(page_file)
    
    # Build items and rectangles (same as before)
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
    
    total_gf_area = sum(r.width * r.height for r in input_rectangles)
    for rect in input_rectangles:
        gf_area = rect.width * rect.height
        rect.preferred_size = (gf_area / total_gf_area * 10.0) if total_gf_area > 0 else 1.0
    
    n_items = len(input_rectangles)
    photo_indices = list(range(n_items))
    
    structure_changes = 0
    physical_changes = 0
    improvements = 0
    
    for trial in range(num_trials):
        tree1 = _generate_random_tree(n_items, photo_indices)
        tree2 = _generate_random_tree(n_items, photo_indices)
        
        # Evaluate parent1
        tree1.compute_aspect_ratios(input_rectangles)
        tree1.compute_dimensions(eval_page_w, eval_page_h, input_rectangles)
        tree1.compute_layout(0, 0)
        cost1 = _evaluate_cost(tree1, eval_page_w, eval_page_h, input_rectangles, 100.0, 0.5, 5.0)
        
        parent1_leaves = tree1.collect_leaves()
        parent1_positions = [(l.x, l.y, l.width, l.height) for l in sorted(parent1_leaves, key=lambda x: x.item_idx)]
        
        # Evaluate parent2
        tree2.compute_aspect_ratios(input_rectangles)
        tree2.compute_dimensions(eval_page_w, eval_page_h, input_rectangles)
        tree2.compute_layout(0, 0)
        cost2 = _evaluate_cost(tree2, eval_page_w, eval_page_h, input_rectangles, 100.0, 0.5, 5.0)
        
        # Crossover
        child1, child2 = _crossover_trees(tree1, tree2)
        
        # Check if structure changed
        structure_changed = not compare_tree_structures(tree1, child1)
        
        # Evaluate child1
        child1.compute_aspect_ratios(input_rectangles)
        child1.compute_dimensions(eval_page_w, eval_page_h, input_rectangles)
        child1.compute_layout(0, 0)
        child_cost = _evaluate_cost(child1, eval_page_w, eval_page_h, input_rectangles, 100.0, 0.5, 5.0)
        
        child1_leaves = child1.collect_leaves()
        child1_positions = [(l.x, l.y, l.width, l.height) for l in sorted(child1_leaves, key=lambda x: x.item_idx)]
        
        # Check if physical positions changed
        physical_changed = any(
            abs(p[0] - c[0]) > 0.1 or abs(p[1] - c[1]) > 0.1 or 
            abs(p[2] - c[2]) > 0.1 or abs(p[3] - c[3]) > 0.1
            for p, c in zip(parent1_positions, child1_positions)
        )
        
        if structure_changed:
            structure_changes += 1
            if physical_changed:
                physical_changes += 1
            if child_cost < min(cost1, cost2):
                improvements += 1
    
    return {
        'n_items': n_items,
        'structure_changes': structure_changes,
        'physical_changes': physical_changes,
        'improvements': improvements
    }

# Test across layout sizes
test_pages = [
    (2, 4),
    (29, 5),
    (8, 11),
    (30, 12),
    (31, 12),
    (34, 18),
]

print("="*80)
print("Structure Changes → Physical Position Changes")
print("="*80)
print(f"{'Page':<6} {'Items':<6} {'Structure':<15} {'Physical':<15} {'Improvements':<15}")
print("-"*80)

for page_num, expected_items in test_pages:
    result = test_structure_vs_physical_change(page_num, num_trials=50)
    print(f"{page_num:<6} {result['n_items']:<6} "
          f"{result['structure_changes']}/50{'':<10} "
          f"{result['physical_changes']}/50{'':<10} "
          f"{result['improvements']}/50")

print("\n" + "="*80)
print("HYPOTHESIS: Structure changes SHOULD cause physical changes")
print("="*80)
