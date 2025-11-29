#!/usr/bin/env python3
"""Demonstrate the crossover bug in Fan-GA."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.fan_layout import _generate_random_tree, _crossover_trees

def print_tree_structure(tree, indent=0):
    """Print tree structure with labels."""
    prefix = "  " * indent
    if tree.is_leaf:
        print(f"{prefix}Leaf: item_idx={tree.item_idx}, label={tree.label}")
    else:
        print(f"{prefix}Internal: label={tree.label}")
        if tree.left:
            print_tree_structure(tree.left, indent + 1)
        if tree.right:
            print_tree_structure(tree.right, indent + 1)

# Create two simple trees
print("=== Testing Crossover ===\n")

tree1 = _generate_random_tree(4, [0, 1, 2, 3])
tree2 = _generate_random_tree(4, [0, 1, 2, 3])

print("Parent 1:")
print_tree_structure(tree1)

print("\nParent 2:")
print_tree_structure(tree2)

# Perform crossover
child1, child2 = _crossover_trees(tree1, tree2)

print("\n" + "="*50)
print("AFTER CROSSOVER:")
print("="*50)

print("\nChild 1 (should have mixed structure from parents):")
print_tree_structure(child1)

print("\nChild 2 (should have mixed structure from parents):")
print_tree_structure(child2)

# Check if children are actually different from parents
def get_leaf_order(tree):
    """Get the order of leaf item_idx values."""
    if tree.is_leaf:
        return [tree.item_idx]
    result = []
    if tree.left:
        result.extend(get_leaf_order(tree.left))
    if tree.right:
        result.extend(get_leaf_order(tree.right))
    return result

parent1_order = get_leaf_order(tree1)
parent2_order = get_leaf_order(tree2)
child1_order = get_leaf_order(child1)
child2_order = get_leaf_order(child2)

print("\n" + "="*50)
print("LEAF ORDERS (should show mixing if crossover works):")
print("="*50)
print(f"Parent 1 leaf order: {parent1_order}")
print(f"Parent 2 leaf order: {parent2_order}")
print(f"Child 1 leaf order:  {child1_order}")
print(f"Child 2 leaf order:  {child2_order}")

if child1_order == parent1_order and child2_order == parent2_order:
    print("\n❌ BUG CONFIRMED: Children are identical to parents!")
    print("   Crossover is not actually exchanging genetic material.")
elif child1_order != parent1_order or child2_order != parent2_order:
    print("\n✓ Crossover appears to work (children differ from parents)")
else:
    print("\n? Inconclusive (need more tests)")
