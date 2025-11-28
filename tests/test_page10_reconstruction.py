"""Test if we can reconstruct page 10's layout with Fan algorithm.

Page 10 has 4 photos in a 2x2 grid with -3.2% empty space (bleed).
This should be a simple layout for the algorithm to find.
"""

from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.gap_utils import analyze_gaps
from cewe_layout.algorithms.evaluator import evaluate_layout
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.algorithms.fan_layout import FanLayoutAlgorithm, TreeNode
import cv2
from pathlib import Path


def test_page10_manual_tree():
    """Manually construct a tree that represents page 10's layout."""
    
    # Load page 10
    mcf = parse_mcf_from_path('../Test-album.xmcf/data.mcf')
    pages = extract_pages_info(mcf)
    
    page10 = None
    for pageno, info in pages:
        if pageno == 10:
            page10 = info
            break
    
    assert page10 is not None, "Page 10 not found"
    
    photos = page10.get('photos', [])
    page_w = page10.get('page_width')
    page_h = page10.get('page_height')
    
    print(f"\nPage 10: {page_w} x {page_h}")
    print(f"Photos: {len(photos)}")
    
    # Get image aspect ratios
    mcf_base = Path('../Test-album.xmcf')
    photo_aspects = []
    for i, p in enumerate(photos):
        fn = p.get('filename', '').replace('safecontainer:/', '').lstrip('/')
        img_path = mcf_base / fn
        if img_path.exists():
            arr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if arr is not None:
                img_h, img_w = arr.shape[:2]
                aspect = img_w / img_h
                photo_aspects.append(aspect)
                print(f"  Photo {i}: {fn.split('/')[-1]}, aspect={aspect:.3f}")
    
    print(f"\nCurrent layout:")
    for i, p in enumerate(photos):
        left = p.get('area_left', 0)
        top = p.get('area_top', 0)
        w = p.get('area_width', 0)
        h = p.get('area_height', 0)
        aspect = w / h if h > 0 else 0
        print(f"  Photo {i}: L={left:6.1f}, T={top:6.1f}, W={w:6.1f}, H={h:6.1f}, AR={aspect:.3f}")
    
    # Analysis: The layout is a 2x2 grid:
    # Top row: Photo 0 (left) | Photo 1 (right)
    # Bottom row: Photo 2 (left) | Photo 3 (right)
    #
    # Tree structure (V = vertical split, H = horizontal split):
    #     H (horizontal split at ~1450)
    #    / \
    #   V   V  (vertical splits)
    #  / \ / \
    # 0  1 2  3
    
    # Manually construct this tree
    # Top row: split vertically at x ~ 1425
    top_left = TreeNode(label='L0', is_leaf=True, photo_idx=0)
    top_right = TreeNode(label='L1', is_leaf=True, photo_idx=1)
    top_row = TreeNode(label='V')
    top_row.left = top_left
    top_row.right = top_right
    top_left.parent = top_row
    top_right.parent = top_row
    
    # Bottom row: split vertically at x ~ 2391
    bottom_left = TreeNode(label='L2', is_leaf=True, photo_idx=2)
    bottom_right = TreeNode(label='L3', is_leaf=True, photo_idx=3)
    bottom_row = TreeNode(label='V')
    bottom_row.left = bottom_left
    bottom_row.right = bottom_right
    bottom_left.parent = bottom_row
    bottom_right.parent = bottom_row
    
    # Full tree: split horizontally at y ~ 1450
    root = TreeNode(label='H')
    root.left = top_row
    root.right = bottom_row
    top_row.parent = root
    bottom_row.parent = root
    
    # Now position this tree on the page (with bleed)
    # The current layout has bleed of 30 units on all sides
    # So the effective canvas is (page_w + 60) x (page_h + 60)
    # But we'll use the nominal page size and see what happens
    
    print(f"\nManual tree structure:")
    print_tree(root, indent=0)
    
    # Evaluate the manual tree
    # For this test, we need to position the tree
    # Let's use the Fan algorithm's positioning logic
    from cewe_layout.algorithms.fan_layout import _compute_layout, _compute_aspect_ratios, _compute_dimensions
    
    # Create rectangles with image aspect ratios
    rectangles = []
    for i, aspect in enumerate(photo_aspects):
        rect = LayoutRectangle(
            item_id=str(i),
            width=aspect * 100,  # arbitrary scale
            height=100,
            preferred_size=1.0,
            preserve_aspect_ratio=True
        )
        rectangles.append(rect)
    
    # Compute aspect ratios for the tree
    _compute_aspect_ratios(root, rectangles)
    
    # Compute dimensions (allocate space)
    _compute_dimensions(root, page_w, page_h, rectangles)
    
    # Position the tree
    _compute_layout(root, 0, 0)
    
    print(f"\nPositioned tree:")
    leaves = []
    def collect_leaves(node):
        if node.is_leaf:
            leaves.append(node)
        else:
            if node.left:
                collect_leaves(node.left)
            if node.right:
                collect_leaves(node.right)
    collect_leaves(root)
    
    for leaf in leaves:
        print(f"  Photo {leaf.photo_idx}: x={leaf.x:.1f}, y={leaf.y:.1f}, w={leaf.width:.1f}, h={leaf.height:.1f}")
    
    # Compare with original
    print(f"\nComparison (manual tree vs original):")
    for i, leaf in enumerate(leaves):
        orig_p = photos[i]
        orig_left = orig_p.get('area_left', 0)
        orig_top = orig_p.get('area_top', 0)
        orig_w = orig_p.get('area_width', 0)
        orig_h = orig_p.get('area_height', 0)
        
        dx = leaf.x - orig_left
        dy = leaf.y - orig_top
        dw = leaf.width - orig_w
        dh = leaf.height - orig_h
        
        print(f"  Photo {i}: dx={dx:6.1f}, dy={dy:6.1f}, dw={dw:6.1f}, dh={dh:6.1f}")


def print_tree(node, indent=0):
    """Print tree structure for debugging."""
    prefix = "  " * indent
    if node.is_leaf:
        print(f"{prefix}Leaf(photo={node.photo_idx})")
    else:
        print(f"{prefix}{node.label}-Split")
        if node.left:
            print_tree(node.left, indent + 1)
        if node.right:
            print_tree(node.right, indent + 1)


if __name__ == '__main__':
    test_page10_manual_tree()
    print("\n✅ Test complete")
