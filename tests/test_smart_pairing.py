"""Test smart pairing in Fan algorithm."""

from cewe_layout.algorithms.fan_layout import _generate_smart_tree
from cewe_layout.algorithms.base import LayoutRectangle


def print_tree(node, indent=0):
    """Print tree structure."""
    prefix = "  " * indent
    if node.is_leaf:
        print(f"{prefix}Leaf(photo={node.photo_idx})")
    else:
        print(f"{prefix}{node.label}-Split")
        if node.left:
            print_tree(node.left, indent + 1)
        if node.right:
            print_tree(node.right, indent + 1)


def test_page10_smart_pairing():
    """Test smart pairing with page 10's photo configuration.
    
    Page 10 has:
    - Photo 0: portrait (0.750), size=1.0 (less important)
    - Photo 1: landscape (1.333), size=3.1 (important)
    - Photo 2: landscape (1.333), size=3.1 (important)
    - Photo 3: portrait (0.750), size=1.0 (less important)
    
    Smart pairing should create:
    - Pair 1: Photo 1 (landscape, important) + Photo 0 or 3 (portrait, small)
    - Pair 2: Photo 2 (landscape, important) + Photo 0 or 3 (portrait, small)
    - Structure: H-split of two V-splits (2x2 grid)
    """
    
    # Create rectangles mimicking page 10
    rectangles = [
        LayoutRectangle(item_id='0', width=75, height=100, preferred_size=1.0, preserve_aspect_ratio=True),  # Portrait, small
        LayoutRectangle(item_id='1', width=133.3, height=100, preferred_size=3.1, preserve_aspect_ratio=True),  # Landscape, important
        LayoutRectangle(item_id='2', width=133.3, height=100, preferred_size=3.1, preserve_aspect_ratio=True),  # Landscape, important
        LayoutRectangle(item_id='3', width=75, height=100, preferred_size=1.0, preserve_aspect_ratio=True),  # Portrait, small
    ]
    
    print("\nPhoto Configuration:")
    for i, rect in enumerate(rectangles):
        aspect = rect.width / rect.height
        orientation = "landscape" if aspect > 1.0 else "portrait"
        importance = "important" if rect.preferred_size > 2.0 else "small"
        print(f"  Photo {i}: {orientation:10s} (AR={aspect:.3f}), {importance:10s} (size={rect.preferred_size:.1f})")
    
    # Generate smart tree
    tree = _generate_smart_tree(4, [0, 1, 2, 3], rectangles)
    
    print("\nSmart Tree Structure:")
    print_tree(tree)
    
    # Analyze structure
    print("\nAnalysis:")
    
    # Check if root is H-split (should be for 2x2 grid)
    if tree.label == 'H':
        print("✅ Root is H-split (creates rows)")
        
        # Check if both children are V-splits
        if tree.left and tree.left.label == 'V':
            print("✅ Top row is V-split (creates columns)")
            if tree.left.left and tree.left.right:
                left_photos = [tree.left.left.photo_idx, tree.left.right.photo_idx]
                print(f"   Top row photos: {left_photos}")
                
                # Check if pairing is good (one landscape + one portrait)
                aspects = [rectangles[i].width / rectangles[i].height for i in left_photos]
                if (aspects[0] > 1.0 and aspects[1] < 1.0) or (aspects[0] < 1.0 and aspects[1] > 1.0):
                    print("   ✅ Good pairing: landscape + portrait")
                else:
                    print(f"   ⚠️  Same orientation: {aspects}")
        
        if tree.right and tree.right.label == 'V':
            print("✅ Bottom row is V-split (creates columns)")
            if tree.right.left and tree.right.right:
                right_photos = [tree.right.left.photo_idx, tree.right.right.photo_idx]
                print(f"   Bottom row photos: {right_photos}")
                
                # Check if pairing is good
                aspects = [rectangles[i].width / rectangles[i].height for i in right_photos]
                if (aspects[0] > 1.0 and aspects[1] < 1.0) or (aspects[0] < 1.0 and aspects[1] > 1.0):
                    print("   ✅ Good pairing: landscape + portrait")
                else:
                    print(f"   ⚠️  Same orientation: {aspects}")
    else:
        print(f"⚠️  Root is {tree.label}-split (expected H-split for 2x2 grid)")
    
    print("\n✅ Test complete")


if __name__ == '__main__':
    test_page10_smart_pairing()
