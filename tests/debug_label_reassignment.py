#!/usr/bin/env python3
"""Debug label reassignment in crossover."""

import sys, copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.fan_layout import TreeNode
import random

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

# Create simple test case
# Tree1: V[H[0,1], H[2,3]]  - subtree is H[2,3]
# Tree2: H[V[0,1], V[2,3]]  - subtree is V[2,3]

root1 = TreeNode('V', is_leaf=False)
root1.left = TreeNode('H', is_leaf=False)
root1.left.parent = root1
root1.left.left = TreeNode(label=0, is_leaf=True, item_idx=0)
root1.left.left.parent = root1.left
root1.left.right = TreeNode(label=1, is_leaf=True, item_idx=1)
root1.left.right.parent = root1.left

root1.right = TreeNode('H', is_leaf=False)
root1.right.parent = root1
root1.right.left = TreeNode(label=2, is_leaf=True, item_idx=2)
root1.right.left.parent = root1.right
root1.right.right = TreeNode(label=3, is_leaf=True, item_idx=3)
root1.right.right.parent = root1.right

root2 = TreeNode('H', is_leaf=False)
root2.left = TreeNode('V', is_leaf=False)
root2.left.parent = root2
root2.left.left = TreeNode(label=0, is_leaf=True, item_idx=0)
root2.left.left.parent = root2.left
root2.left.right = TreeNode(label=1, is_leaf=True, item_idx=1)
root2.left.right.parent = root2.left

root2.right = TreeNode('V', is_leaf=False)
root2.right.parent = root2
root2.right.left = TreeNode(label=2, is_leaf=True, item_idx=2)
root2.right.left.parent = root2.right
root2.right.right = TreeNode(label=3, is_leaf=True, item_idx=3)
root2.right.right.parent = root2.right

print("BEFORE CROSSOVER:")
print("\nTree 1:")
print_tree(root1)
print("\nTree 2:")
print_tree(root2)

# Simulate crossover on right subtrees
st1 = root1.right  # H[2,3]
st2 = root2.right  # V[2,3]

labels1 = collect_leaf_labels(st1)  # [2, 3]
labels2 = collect_leaf_labels(st2)  # [2, 3]

print(f"\nSubtree 1 labels: {labels1}")
print(f"Subtree 2 labels: {labels2}")

# Deep copy structures
st1_structure = copy.deepcopy(st1)
st2_structure = copy.deepcopy(st2)

# Reassign (keeping own labels)
reassign_labels(st1_structure, labels1)
reassign_labels(st2_structure, labels2)

print("\nAfter reassignment:")
print("st1_structure (should have labels1=[2,3]):")
print_tree(st1_structure)
print("st2_structure (should have labels2=[2,3]):")
print_tree(st2_structure)

# Now swap: root1.right gets st2_structure, root2.right gets st1_structure
root1.right = st2_structure
st2_structure.parent = root1
root2.right = st1_structure
st1_structure.parent = root2

print("\nAFTER CROSSOVER:")
print("\nTree 1 (should have V on right now):")
print_tree(root1)
labels_tree1 = collect_leaf_labels(root1)
print(f"Labels: {sorted(labels_tree1)} (should be [0,1,2,3])")

print("\nTree 2 (should have H on right now):")
print_tree(root2)
labels_tree2 = collect_leaf_labels(root2)
print(f"Labels: {sorted(labels_tree2)} (should be [0,1,2,3])")

if sorted(labels_tree1) == [0,1,2,3] and sorted(labels_tree2) == [0,1,2,3]:
    print("\n✓ NO CORRUPTION!")
else:
    print("\n✗ CORRUPTION DETECTED!")
