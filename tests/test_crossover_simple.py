#!/usr/bin/env python3
"""Test one specific crossover to debug corruption."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.fan_layout import _generate_random_tree, _crossover_trees

def collect_indices(node):
    """Collect all photo indices in tree."""
    if node.is_leaf:
        return [node.item_idx]
    indices = []
    if node.left:
        indices.extend(collect_indices(node.left))
    if node.right:
        indices.extend(collect_indices(node.right))
    return indices

# Test many crossovers
n_items = 11
photo_indices = list(range(n_items))

print("Testing 50 crossovers with 11 items...")
corruptions = 0

for trial in range(50):
    tree1 = _generate_random_tree(n_items, photo_indices)
    tree2 = _generate_random_tree(n_items, photo_indices)
    
    # Verify parents
    indices1 = sorted(collect_indices(tree1))
    indices2 = sorted(collect_indices(tree2))
    
    if indices1 != photo_indices or indices2 != photo_indices:
        print(f"Trial {trial}: PARENT CORRUPTION!")
        continue
    
    # Crossover
    child1, child2 = _crossover_trees(tree1, tree2)
    
    # Check children
    child1_indices = sorted(collect_indices(child1))
    child2_indices = sorted(collect_indices(child2))
    
    if child1_indices != photo_indices:
        missing = set(photo_indices) - set(child1_indices)
        extra = set(child1_indices) - set(photo_indices)
        print(f"Trial {trial}: Child1 CORRUPT - missing {missing}, extra {extra}")
        print(f"  Expected: {photo_indices}")
        print(f"  Got: {child1_indices}")
        corruptions += 1
        
    if child2_indices != photo_indices:
        missing = set(photo_indices) - set(child2_indices)
        extra = set(child2_indices) - set(photo_indices)
        print(f"Trial {trial}: Child2 CORRUPT - missing {missing}, extra {extra}")
        print(f"  Expected: {photo_indices}")
        print(f"  Got: {child2_indices}")
        corruptions += 1

print(f"\nTotal corruptions: {corruptions}/100")
