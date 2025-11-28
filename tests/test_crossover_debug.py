#!/usr/bin/env python
"""Debug crossover operation to find why photos are lost."""

import sys
sys.path.insert(0, '/Users/vincedarley/Documents/GitHub-photostuff/cewe-layout')

from cewe_layout.algorithms.fan_layout import _generate_random_tree, _crossover_trees
import copy


def collect_all_photo_indices(tree):
    """Collect all photo indices from a tree."""
    if tree.is_leaf:
        return [tree.photo_idx]
    indices = []
    if tree.left:
        indices.extend(collect_all_photo_indices(tree.left))
    if tree.right:
        indices.extend(collect_all_photo_indices(tree.right))
    return indices


def test_crossover(n_photos):
    """Test crossover with n photos."""
    print(f"\n{'='*60}")
    print(f"Testing crossover with {n_photos} photos")
    print('='*60)
    
    # Create two random trees
    indices1 = list(range(n_photos))
    indices2 = list(range(n_photos))
    
    tree1 = _generate_random_tree(n_photos, indices1)
    tree2 = _generate_random_tree(n_photos, indices2)
    
    print(f"Tree 1 before: {sorted(collect_all_photo_indices(tree1))}")
    print(f"Tree 2 before: {sorted(collect_all_photo_indices(tree2))}")
    
    # Do crossover
    offspring1, offspring2 = _crossover_trees(tree1, tree2)
    
    indices_off1 = collect_all_photo_indices(offspring1)
    indices_off2 = collect_all_photo_indices(offspring2)
    
    print(f"Offspring 1 after: {sorted(indices_off1)}")
    print(f"Offspring 2 after: {sorted(indices_off2)}")
    
    # Check for correctness
    expected = set(range(n_photos))
    actual1 = set(indices_off1)
    actual2 = set(indices_off2)
    
    if len(indices_off1) != n_photos:
        print(f"❌ Offspring 1 has {len(indices_off1)} photos, expected {n_photos}")
    if len(indices_off2) != n_photos:
        print(f"❌ Offspring 2 has {len(indices_off2)} photos, expected {n_photos}")
    
    if actual1 != expected:
        missing = expected - actual1
        extra = actual1 - expected
        print(f"❌ Offspring 1: missing {missing}, extra {extra}")
    else:
        print("✅ Offspring 1 has all photos")
    
    if actual2 != expected:
        missing = expected - actual2
        extra = actual2 - expected
        print(f"❌ Offspring 2: missing {missing}, extra {extra}")
    else:
        print("✅ Offspring 2 has all photos")
    
    return actual1 == expected and actual2 == expected


if __name__ == "__main__":
    all_pass = True
    
    for n in [3, 5, 8, 10]:
        if not test_crossover(n):
            all_pass = False
    
    print(f"\n{'='*60}")
    if all_pass:
        print("✅ All crossover tests passed!")
    else:
        print("❌ Some crossover tests failed!")
        sys.exit(1)
    print('='*60)
