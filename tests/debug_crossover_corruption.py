#!/usr/bin/env python3
"""Debug: Why does crossover show effectiveness but cause corruption?"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_helpers import read_page_file
from cewe_layout.algorithms.fan_layout import _generate_random_tree, _crossover_trees
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.gap_utils import analyze_gaps, transform_page_to_gapfree

def verify_tree_integrity(tree, n_items):
    """Check that tree has exactly the right photo indices."""
    leaves = tree.collect_leaves()
    indices = sorted([l.item_idx for l in leaves])
    expected = list(range(n_items))
    
    if indices != expected:
        missing = set(expected) - set(indices)
        extra = set(indices) - set(expected)
        return False, missing, extra
    return True, set(), set()

def test_crossover_integrity(page_num):
    """Test crossover with ORIGINAL code (labels1/labels2)."""
    page_file = Path(f'tests/samples/Test-album-page-{page_num}.txt')
    page_data = read_page_file(page_file)
    
    n_items = len(page_data.photos)
    photo_indices = list(range(n_items))
    
    print(f"\nPage {page_num} ({n_items} items):")
    print("-" * 60)
    
    # Test 20 crossovers
    corruptions = 0
    for trial in range(20):
        tree1 = _generate_random_tree(n_items, photo_indices)
        tree2 = _generate_random_tree(n_items, photo_indices)
        
        # Verify parents are valid
        valid1, miss1, extra1 = verify_tree_integrity(tree1, n_items)
        valid2, miss2, extra2 = verify_tree_integrity(tree2, n_items)
        
        if not valid1 or not valid2:
            print(f"  Trial {trial}: PARENT CORRUPTION!")
            continue
        
        # Perform crossover
        child1, child2 = _crossover_trees(tree1, tree2)
        
        # Verify children
        valid_c1, miss_c1, extra_c1 = verify_tree_integrity(child1, n_items)
        valid_c2, miss_c2, extra_c2 = verify_tree_integrity(child2, n_items)
        
        if not valid_c1:
            print(f"  Trial {trial}: Child 1 CORRUPT - missing {miss_c1}, extra {extra_c1}")
            corruptions += 1
        if not valid_c2:
            print(f"  Trial {trial}: Child 2 CORRUPT - missing {miss_c2}, extra {extra_c2}")
            corruptions += 1
    
    print(f"  Corruptions: {corruptions}/40 children")
    return corruptions

# Test pages of various sizes
test_pages = [
    (2, 4),
    (29, 5),
    (8, 11),
    (34, 18),
]

print("="*60)
print("Testing Crossover Integrity (ORIGINAL CODE)")
print("="*60)

for page_num, expected_items in test_pages:
    corruptions = test_crossover_integrity(page_num)
