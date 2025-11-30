"""
Test get_final_tree() method for all algorithms.
"""

from cewe_layout.algorithms.collage_generator import CollageGeneratorAlgorithm
from cewe_layout.algorithms.fan_layout import FanLayoutAlgorithm
from cewe_layout.algorithms.tree_builder import TreeBuilderAlgorithm
from cewe_layout.algorithms.base import LayoutRectangle


def test_collage_generator_get_final_tree():
    """Test CollageGeneratorAlgorithm.get_final_tree()"""
    print("\n" + "="*60)
    print("Testing CollageGeneratorAlgorithm.get_final_tree()")
    print("="*60)
    
    algo = CollageGeneratorAlgorithm(temperature=1.0)
    
    # Before layout, should return None
    assert algo.get_final_tree() is None, "Should return None before layout"
    print("  ✅ Returns None before layout")
    
    # Create test rectangles
    rectangles = [
        LayoutRectangle(item_id=str(i), width=1000.0, height=1000.0, preferred_size=1.0)
        for i in range(3)
    ]
    
    # Generate layout
    success, result, error = algo.generate_layout(4200.0, 4200.0, rectangles)
    assert success, f"Layout failed: {error}"
    
    # After layout, should return TreeNode
    tree = algo.get_final_tree()
    assert tree is not None, "Should return tree after layout"
    assert not tree.is_leaf, "Root should be internal node"
    assert tree.label in ['V', 'H'], f"Root label should be V or H, got {tree.label}"
    
    # Verify tree structure
    leaves = tree.collect_leaves()
    assert len(leaves) == 3, f"Should have 3 leaves, got {len(leaves)}"
    print(f"  ✅ Tree has {len(leaves)} leaves")
    
    # Verify leaf nodes have correct item_idx
    for leaf in leaves:
        assert leaf.is_leaf, "Leaf should have is_leaf=True"
        assert 0 <= leaf.item_idx < 3, f"item_idx {leaf.item_idx} out of range"
    print(f"  ✅ All leaves have valid item_idx")
    
    # Verify tree structure string
    tree_str = tree.to_compact_string()
    print(f"  ✅ Tree structure: {tree_str}")


def test_fan_layout_get_final_tree():
    """Test FanLayoutAlgorithm.get_final_tree()"""
    print("\n" + "="*60)
    print("Testing FanLayoutAlgorithm.get_final_tree()")
    print("="*60)
    
    algo = FanLayoutAlgorithm(generations=10, population_size=20)
    
    # Before layout, should return None
    assert algo.get_final_tree() is None, "Should return None before layout"
    print("  ✅ Returns None before layout")
    
    # Create test rectangles
    rectangles = [
        LayoutRectangle(item_id=str(i), width=1000.0, height=1000.0, preferred_size=1.0)
        for i in range(3)
    ]
    
    # Generate layout
    success, result, error = algo.generate_layout(4200.0, 4200.0, rectangles)
    assert success, f"Layout failed: {error}"
    
    # After layout, should return TreeNode
    tree = algo.get_final_tree()
    assert tree is not None, "Should return tree after layout"
    
    # Verify tree structure
    leaves = tree.collect_leaves()
    assert len(leaves) == 3, f"Should have 3 leaves, got {len(leaves)}"
    print(f"  ✅ Tree has {len(leaves)} leaves")
    
    tree_str = tree.to_compact_string()
    print(f"  ✅ Tree structure: {tree_str}")


def test_tree_builder_get_final_tree():
    """Test TreeBuilderAlgorithm.get_final_tree()"""
    print("\n" + "="*60)
    print("Testing TreeBuilderAlgorithm.get_final_tree()")
    print("="*60)
    
    algo = TreeBuilderAlgorithm(tolerance=20.0)
    
    # Before layout, should return None
    assert algo.get_final_tree() is None, "Should return None before layout"
    print("  ✅ Returns None before layout")
    
    # Create test rectangles with positions (tree-representable layout)
    rectangles = [
        LayoutRectangle(item_id="0", width=2100.0, height=2100.0, x=0, y=0, preferred_size=1.0),
        LayoutRectangle(item_id="1", width=2100.0, height=1050.0, x=0, y=2100.0, preferred_size=1.0),
        LayoutRectangle(item_id="2", width=2100.0, height=1050.0, x=0, y=3150.0, preferred_size=1.0),
    ]
    
    # Generate layout
    success, result, error = algo.generate_layout(4200.0, 4200.0, rectangles)
    assert success, f"Layout failed: {error}"
    
    # After layout, should return TreeNode
    tree = algo.get_final_tree()
    assert tree is not None, "Should return tree after layout"
    
    # Verify tree structure
    leaves = tree.collect_leaves()
    assert len(leaves) == 3, f"Should have 3 leaves, got {len(leaves)}"
    print(f"  ✅ Tree has {len(leaves)} leaves")
    
    tree_str = tree.to_compact_string()
    print(f"  ✅ Tree structure: {tree_str}")


if __name__ == "__main__":
    test_collage_generator_get_final_tree()
    test_fan_layout_get_final_tree()
    test_tree_builder_get_final_tree()
    
    print("\n" + "="*60)
    print("✅ All get_final_tree() tests passed!")
    print("="*60)
