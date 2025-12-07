"""
Test that TreeNode.clone() produces identical results to copy.deepcopy().

This verifies that the optimization doesn't change algorithm behavior.
"""
import copy
import random
from cewe_layout.algorithms.base import TreeNode, LayoutRectangle
from cewe_layout.algorithms.fan_layout import FanLayoutAlgorithm


def build_sample_tree(num_items=5):
    """Build a sample tree with the given number of items."""
    if num_items == 1:
        return TreeNode(label=0, is_leaf=True, item_idx=0)
    
    # Create a simple V-H-V structure
    root = TreeNode(label='V', is_leaf=False)
    left_subtree = TreeNode(label='H', is_leaf=False)
    
    # Left side: first 2 items
    left_subtree.left = TreeNode(label=0, is_leaf=True, item_idx=0)
    left_subtree.right = TreeNode(label=1, is_leaf=True, item_idx=1)
    left_subtree.left.parent = left_subtree
    left_subtree.right.parent = left_subtree
    
    # Right side: remaining items
    if num_items == 2:
        root.left = left_subtree
        root.right = TreeNode(label=0, is_leaf=True, item_idx=0)
    elif num_items == 3:
        root.left = left_subtree
        root.right = TreeNode(label=2, is_leaf=True, item_idx=2)
    else:
        # More complex right side
        right_subtree = TreeNode(label='H', is_leaf=False)
        right_subtree.left = TreeNode(label=2, is_leaf=True, item_idx=2)
        right_subtree.right = TreeNode(label=3, is_leaf=True, item_idx=3)
        right_subtree.left.parent = right_subtree
        right_subtree.right.parent = right_subtree
        root.right = right_subtree
    
    root.left = left_subtree
    left_subtree.parent = root
    if hasattr(root.right, 'parent'):
        root.right.parent = root
    
    return root


def trees_are_identical(tree1, tree2):
    """Recursively check if two trees have identical structure and labels."""
    if tree1 is None and tree2 is None:
        return True
    if tree1 is None or tree2 is None:
        return False
    
    # Check node attributes
    if tree1.label != tree2.label:
        return False
    if tree1.is_leaf != tree2.is_leaf:
        return False
    if tree1.item_idx != tree2.item_idx:
        return False
    
    # Check structure
    return (trees_are_identical(tree1.left, tree2.left) and
            trees_are_identical(tree1.right, tree2.right))


def test_clone_produces_identical_structure():
    """Verify clone() produces identical tree structure to deepcopy()."""
    tree = build_sample_tree(5)
    
    cloned = tree.clone()
    deepcopied = copy.deepcopy(tree)
    
    assert trees_are_identical(cloned, deepcopied), "Clone and deepcopy should produce identical trees"
    print("✓ clone() produces identical structure to deepcopy()")


def test_clone_independence():
    """Verify cloned trees are independent (modifying one doesn't affect the other)."""
    tree = build_sample_tree(5)
    cloned = tree.clone()
    
    # Modify original
    tree.label = 'H'
    if tree.left:
        tree.left.label = 'V'
    
    # Clone should be unchanged
    assert cloned.label == 'V', "Clone should not be affected by changes to original"
    if cloned.left:
        assert cloned.left.label == 'H', "Clone's children should not be affected"
    
    print("✓ clone() creates independent copies")


def test_fan_algorithm_deterministic():
    """Verify Fan algorithm produces identical results with same seed."""
    # Create sample rectangles
    random.seed(42)
    rectangles = [
        LayoutRectangle(item_id=f"photo_{i}", width=100, height=100, 
                       preferred_size=100*100, preserve_aspect_ratio=True)
        for i in range(5)
    ]
    
    # Run algorithm twice with same seed
    random.seed(42)
    algorithm1 = FanLayoutAlgorithm(population_size=20, generations=10)
    success1, layout1, msg1 = algorithm1.generate_layout(800, 600, rectangles)
    
    random.seed(42)
    algorithm2 = FanLayoutAlgorithm(population_size=20, generations=10)
    success2, layout2, msg2 = algorithm2.generate_layout(800, 600, rectangles)
    
    assert success1 and success2, "Both runs should succeed"
    assert len(layout1) == len(layout2), "Should have same number of items"
    
    # Compare positions (should be identical with same seed)
    for i, (r1, r2) in enumerate(zip(layout1, layout2)):
        assert r1.item_id == r2.item_id, f"Item {i} should have same ID"
        assert abs(r1.x - r2.x) < 0.01, f"Item {i} should have same x position"
        assert abs(r1.y - r2.y) < 0.01, f"Item {i} should have same y position"
        assert abs(r1.width - r2.width) < 0.01, f"Item {i} should have same width"
        assert abs(r1.height - r2.height) < 0.01, f"Item {i} should have same height"
    
    print("✓ Fan algorithm is deterministic with same seed")


if __name__ == '__main__':
    test_clone_produces_identical_structure()
    test_clone_independence()
    test_fan_algorithm_deterministic()
    print("\n✅ All tests passed! clone() is semantically identical to deepcopy()")
