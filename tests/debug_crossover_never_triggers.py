#!/usr/bin/env python3
"""Debug why crossover never triggers."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_helpers import read_page_file
from cewe_layout.algorithms.fan_layout import _generate_random_tree
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.gap_utils import analyze_gaps, transform_page_to_gapfree

def analyze_tree_structure(tree, depth=0):
    """Analyze tree structure to find eligible crossover subtrees."""
    if tree.is_leaf:
        return {
            'leaves': 1,
            'eligible_subtrees': []
        }
    
    left_info = analyze_tree_structure(tree.left, depth + 1)
    right_info = analyze_tree_structure(tree.right, depth + 1)
    
    total_leaves = left_info['leaves'] + right_info['leaves']
    eligible = left_info['eligible_subtrees'] + right_info['eligible_subtrees']
    
    # Check if this node's subtrees are eligible for crossover
    # min_leaves = 3 in the actual code
    if left_info['leaves'] >= 3 and depth > 0:  # Not root
        eligible.append(('left', left_info['leaves'], depth))
    if right_info['leaves'] >= 3 and depth > 0:  # Not root
        eligible.append(('right', right_info['leaves'], depth))
    
    return {
        'leaves': total_leaves,
        'eligible_subtrees': eligible
    }

def test_page(page_num):
    """Analyze crossover opportunities on a specific page."""
    page_file = Path(f'tests/samples/Test-album-page-{page_num}.txt')
    page_data = read_page_file(page_file)
    
    # Build items
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
    
    # Generate several random trees and analyze their structure
    print(f"\nPage {page_num} ({n_items} items):")
    print("-" * 60)
    
    eligible_counts = []
    for trial in range(10):
        tree = _generate_random_tree(n_items, photo_indices)
        info = analyze_tree_structure(tree)
        eligible_counts.append(len(info['eligible_subtrees']))
        
        if trial < 3:  # Show first 3 in detail
            print(f"  Tree {trial+1}: {len(info['eligible_subtrees'])} eligible subtrees")
            for side, n_leaves, depth in info['eligible_subtrees']:
                print(f"    - {side} subtree: {n_leaves} leaves, depth {depth}")
    
    avg_eligible = sum(eligible_counts) / len(eligible_counts)
    print(f"  Average eligible subtrees: {avg_eligible:.1f}")
    
    # Now test crossover matching probability
    # Even if both trees have eligible subtrees, they need matching leaf counts
    matching_pairs = 0
    total_pairs = 0
    
    for _ in range(20):
        tree1 = _generate_random_tree(n_items, photo_indices)
        tree2 = _generate_random_tree(n_items, photo_indices)
        
        info1 = analyze_tree_structure(tree1)
        info2 = analyze_tree_structure(tree2)
        
        # Check if there's any matching pair
        has_match = False
        for _, n1, _ in info1['eligible_subtrees']:
            for _, n2, _ in info2['eligible_subtrees']:
                if n1 == n2:
                    has_match = True
                    break
            if has_match:
                break
        
        total_pairs += 1
        if has_match:
            matching_pairs += 1
    
    match_rate = matching_pairs / total_pairs if total_pairs > 0 else 0
    print(f"  Matching pair rate: {matching_pairs}/{total_pairs} ({match_rate*100:.1f}%)")
    
    return avg_eligible, match_rate

# Test across sizes
print("="*60)
print("Analyzing Why Crossover Never Triggers")
print("="*60)

test_pages = [
    (2, 4),
    (17, 4),
    (29, 5),
    (8, 11),
    (30, 12),
    (34, 18),
]

for page_num, expected_items in test_pages:
    avg_eligible, match_rate = test_page(page_num)
