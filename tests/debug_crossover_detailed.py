#!/usr/bin/env python3
"""Debug: detailed trace of crossover corruption."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.fan_layout import _generate_random_tree, TreeNode
import copy, random

def print_tree(node, depth=0):
    """Print tree structure."""
    if node.is_leaf:
        print("  " * depth + f"Leaf[{node.item_idx}]")
    else:
        print("  " * depth + f"{node.label}")
        if node.left:
            print_tree(node.left, depth + 1)
        if node.right:
            print_tree(node.right, depth + 1)

def collect_leaf_labels(node):
    if node.is_leaf:
        return [node.item_idx]
    labels = []
    if node.left:
        labels.extend(collect_leaf_labels(node.left))
    if node.right:
        labels.extend(collect_leaf_labels(node.right))
    return labels

def reassign_labels(node, labels):
    """Reassign labels to leaf nodes in pre-order traversal."""
    idx = [0]
    def _reassign(n):
        if n.is_leaf:
            n.label = labels[idx[0]]
            n.item_idx = labels[idx[0]]
            idx[0] += 1
        else:
            if n.left:
                _reassign(n.left)
            if n.right:
                _reassign(n.right)
    _reassign(node)

def fix_parent_pointers(node, parent=None):
    node.parent = parent
    if node.left:
        fix_parent_pointers(node.left, node)
    if node.right:
        fix_parent_pointers(node.right, node)

def test_single_crossover():
    """Test one crossover with detailed output."""
    n_items = 4
    photo_indices = list(range(n_items))
    
    # Generate two random trees
    tree1 = _generate_random_tree(n_items, photo_indices)
    tree2 = _generate_random_tree(n_items, photo_indices)
    
    print("PARENT TREES:")
    print("\nTree 1:")
    print_tree(tree1)
    labels1_before = collect_leaf_labels(tree1)
    print(f"Labels: {labels1_before}")
    
    print("\nTree 2:")
    print_tree(tree2)
    labels2_before = collect_leaf_labels(tree2)
    print(f"Labels: {labels2_before}")
    
    # COPY the crossover logic exactly
    offspring1 = copy.deepcopy(tree1)
    offspring2 = copy.deepcopy(tree2)
    
    # Find subtrees
    subtrees1 = [st for st in offspring1.collect_subtrees(min_leaves=3) if st.parent is not None]
    subtrees2 = [st for st in offspring2.collect_subtrees(min_leaves=3) if st.parent is not None]
    
    print(f"\nSubtrees1: {len(subtrees1)} eligible")
    print(f"Subtrees2: {len(subtrees2)} eligible")
    
    if not subtrees1 or not subtrees2:
        print("NO CROSSOVER (no eligible subtrees)")
        return
    
    # Find pairs
    pairs = []
    for st1 in subtrees1:
        count1 = st1.count_leaves()
        for st2 in subtrees2:
            count2 = st2.count_leaves()
            if count1 == count2:
                pairs.append((st1, st2))
    
    if not pairs:
        print("NO CROSSOVER (no matching pairs)")
        return
    
    print(f"Matching pairs: {len(pairs)}")
    
    # Select a pair
    st1, st2 = random.choice(pairs)
    
    print(f"\nSelected subtree from tree1 ({st1.count_leaves()} leaves):")
    print_tree(st1)
    labels_st1 = collect_leaf_labels(st1)
    print(f"Labels: {labels_st1}")
    
    print(f"\nSelected subtree from tree2 ({st2.count_leaves()} leaves):")
    print_tree(st2)
    labels_st2 = collect_leaf_labels(st2)
    print(f"Labels: {labels_st2}")
    
    # Deep copy structures
    st1_structure = copy.deepcopy(st1)
    st2_structure = copy.deepcopy(st2)
    
    # Reassign labels
    reassign_labels(st1_structure, labels_st1)
    reassign_labels(st2_structure, labels_st2)
    
    print("\nAfter reassignment:")
    print("st1_structure:")
    print_tree(st1_structure)
    print(f"Labels: {collect_leaf_labels(st1_structure)}")
    
    print("st2_structure:")
    print_tree(st2_structure)
    print(f"Labels: {collect_leaf_labels(st2_structure)}")
    
    # Swap structures
    fix_parent_pointers(st2_structure, st1.parent)
    if st1.parent.left == st1:
        st1.parent.left = st2_structure
    else:
        st1.parent.right = st2_structure
    
    fix_parent_pointers(st1_structure, st2.parent)
    if st2.parent.left == st2:
        st2.parent.left = st1_structure
    else:
        st2.parent.right = st1_structure
    
    print("\nOFFSPRING TREES:")
    print("\nOffspring 1:")
    print_tree(offspring1)
    labels_off1 = collect_leaf_labels(offspring1)
    print(f"Labels: {sorted(labels_off1)} (should be [0,1,2,3])")
    
    print("\nOffspring 2:")
    print_tree(offspring2)
    labels_off2 = collect_leaf_labels(offspring2)
    print(f"Labels: {sorted(labels_off2)} (should be [0,1,2,3])")
    
    if sorted(labels_off1) == [0,1,2,3] and sorted(labels_off2) == [0,1,2,3]:
        print("\n✓ NO CORRUPTION!")
    else:
        print("\n✗ CORRUPTION!")
        print(f"Off1 missing: {set(range(4)) - set(labels_off1)}")
        print(f"Off2 missing: {set(range(4)) - set(labels_off2)}")

# Run a few times to see if we can reproduce corruption
for i in range(10):
    print("\n" + "="*80)
    print(f"Trial {i+1}")
    print("="*80)
    test_single_crossover()
    print()
