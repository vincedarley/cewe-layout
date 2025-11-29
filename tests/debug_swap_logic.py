#!/usr/bin/env python3
"""Debug why swapping indices causes corruption."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.fan_layout import _generate_random_tree
import copy

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

def trees_have_same_structure(node1, node2):
    """Check if two trees have identical branching structure."""
    if node1.is_leaf and node2.is_leaf:
        return True
    if node1.is_leaf != node2.is_leaf:
        return False
    if node1.label != node2.label:
        return False
    return (trees_have_same_structure(node1.left, node2.left) and 
            trees_have_same_structure(node1.right, node2.right))

def swap_indices(node1, node2):
    """Traverse both trees simultaneously and swap photo indices."""
    if node1.is_leaf and node2.is_leaf:
        node1.item_idx, node2.item_idx = node2.item_idx, node1.item_idx
        node1.label, node2.label = node2.label, node1.label
        print(f"    Swapped: {node2.item_idx} <-> {node1.item_idx}")
    else:
        if node1.left and node2.left:
            swap_indices(node1.left, node2.left)
        if node1.right and node2.right:
            swap_indices(node1.right, node2.right)

# Create a simple test case
n_items = 6
photo_indices = list(range(n_items))

print("Generating two random trees with 6 items...")
tree1 = _generate_random_tree(n_items, photo_indices)
tree2 = _generate_random_tree(n_items, photo_indices)

print(f"\nTree1 indices: {sorted(collect_indices(tree1))}")
print(f"Tree2 indices: {sorted(collect_indices(tree2))}")

# Find subtrees with >= 3 leaves
subtrees1 = [st for st in tree1.collect_subtrees(min_leaves=3) if st.parent is not None]
subtrees2 = [st for st in tree2.collect_subtrees(min_leaves=3) if st.parent is not None]

print(f"\nTree1 has {len(subtrees1)} eligible subtrees")
print(f"Tree2 has {len(subtrees2)} eligible subtrees")

# Find matching pairs
pairs = []
for st1 in subtrees1:
    count1 = st1.count_leaves()
    for st2 in subtrees2:
        count2 = st2.count_leaves()
        if count1 == count2:
            pairs.append((st1, st2))

print(f"Found {len(pairs)} matching pairs")

if pairs:
    st1, st2 = pairs[0]
    print(f"\nTesting first pair (both have {st1.count_leaves()} leaves)")
    print(f"Subtree1 indices: {sorted(collect_indices(st1))}")
    print(f"Subtree2 indices: {sorted(collect_indices(st2))}")
    print(f"Same structure? {trees_have_same_structure(st1, st2)}")
    
    # Deep copy
    st1_copy = copy.deepcopy(st1)
    st2_copy = copy.deepcopy(st2)
    
    print("\nSwapping indices:")
    swap_indices(st1_copy, st2_copy)
    
    print(f"\nAfter swap:")
    print(f"Subtree1_copy indices: {sorted(collect_indices(st1_copy))}")
    print(f"Subtree2_copy indices: {sorted(collect_indices(st2_copy))}")
    
    # Now check if we replace these in the parents, do we get valid trees?
    # The problem is: we're swapping indices within the subtrees,
    # but the rest of the tree still has the original indices!
    
    print(f"\nOriginal full trees:")
    print(f"Tree1 indices: {sorted(collect_indices(tree1))}")
    print(f"Tree2 indices: {sorted(collect_indices(tree2))}")
    
    print(f"\nIndices in subtrees that will be swapped:")
    st1_indices = set(collect_indices(st1))
    st2_indices = set(collect_indices(st2))
    print(f"Subtree1: {sorted(st1_indices)}")
    print(f"Subtree2: {sorted(st2_indices)}")
    
    print(f"\nIndices in REST of trees (will NOT be swapped):")
    tree1_rest = set(collect_indices(tree1)) - st1_indices
    tree2_rest = set(collect_indices(tree2)) - st2_indices
    print(f"Tree1 rest: {sorted(tree1_rest)}")
    print(f"Tree2 rest: {sorted(tree2_rest)}")
    
    print(f"\nAfter crossover:")
    print(f"Child1 will have: {sorted(tree1_rest)} (from tree1 rest) + {sorted(collect_indices(st2_copy))} (from st2_copy)")
    print(f"Child2 will have: {sorted(tree2_rest)} (from tree2 rest) + {sorted(collect_indices(st1_copy))} (from st1_copy)")
    
    child1_indices = sorted(tree1_rest | set(collect_indices(st2_copy)))
    child2_indices = sorted(tree2_rest | set(collect_indices(st1_copy)))
    
    print(f"\nChild1 total: {child1_indices}")
    print(f"Child2 total: {child2_indices}")
    
    print(f"\nExpected: {list(range(n_items))}")
    print(f"Child1 valid? {child1_indices == list(range(n_items))}")
    print(f"Child2 valid? {child2_indices == list(range(n_items))}")
