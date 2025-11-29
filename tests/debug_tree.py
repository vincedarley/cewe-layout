"""Debug tree construction to understand cost calculation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.base import TreeNode, LayoutRectangle
from cewe_layout.algorithms.evaluator import evaluate_layout


def main():
    # Create 4 rectangles with mixed aspect ratios
    # Set preferred_size to match what the tree layout will naturally give them
    # Portrait photos will get ~15% each, landscape ~30% each
    rects = [
        LayoutRectangle('photo0', width=300, height=400, preferred_size=0.6),  # portrait - wants less
        LayoutRectangle('photo1', width=600, height=400, preferred_size=1.2),  # landscape - wants more
        LayoutRectangle('photo2', width=600, height=400, preferred_size=1.2),  # landscape - wants more
        LayoutRectangle('photo3', width=300, height=400, preferred_size=0.6),  # portrait - wants less
    ]
    
    # Manual tree: H(V(L0,L1), V(L2,L3))
    # This should create a 2x2 grid
    left_v = TreeNode(label='V', is_leaf=False)
    left_v.left = TreeNode(label=0, is_leaf=True, item_idx=0)
    left_v.right = TreeNode(label=1, is_leaf=True, item_idx=1)
    
    right_v = TreeNode(label='V', is_leaf=False)
    right_v.left = TreeNode(label=2, is_leaf=True, item_idx=2)
    right_v.right = TreeNode(label=3, is_leaf=True, item_idx=3)
    
    root = TreeNode(label='H', is_leaf=False)
    root.left = left_v
    root.right = right_v
    
    # Compute layout on a square page
    page_width = 800
    page_height = 800
    
    print(f"Page: {page_width}x{page_height}")
    print(f"Input rectangles (2 portrait 300x400, 2 landscape 600x400):")
    for i, r in enumerate(rects):
        aspect = r.width / r.height
        print(f"  [{i}] {r.width}x{r.height} (aspect={aspect:.2f}), preferred={r.preferred_size}")
    
    print(f"\nTree structure: H(V(L0,L1), V(L2,L3))")
    print("This pairs portrait+landscape in each row")
    
    # Compute
    root.compute_aspect_ratios(rects)
    print(f"\nAspect ratios computed:")
    print(f"  Root (H): {root.aspect_ratio:.3f}")
    print(f"  Left V: {root.left.aspect_ratio:.3f}")
    print(f"  Right V: {root.right.aspect_ratio:.3f}")
    
    root.compute_dimensions(page_width, page_height, rects)
    print(f"\nDimensions computed:")
    print(f"  Root: {root.width:.1f}x{root.height:.1f}")
    print(f"  Left V: {root.left.width:.1f}x{root.left.height:.1f}")
    print(f"  Right V: {root.right.width:.1f}x{root.right.height:.1f}")
    
    root.compute_layout(0, 0)
    
    # Collect leaves
    leaves = root.collect_leaves()
    for leaf in leaves:
        rect = rects[leaf.item_idx]
        leaf.item_id = rect.item_id
        leaf.preferred_size = rect.preferred_size
        leaf.preserve_aspect_ratio = rect.preserve_aspect_ratio
    
    print(f"\nFinal leaf positions:")
    total_area = 0
    for leaf in leaves:
        area = leaf.width * leaf.height
        total_area += area
        area_fraction = area / (page_width * page_height)
        print(f"  {leaf.item_id}: pos=({leaf.x:.1f}, {leaf.y:.1f}), "
              f"size={leaf.width:.1f}x{leaf.height:.1f}, "
              f"area={area:.0f} ({area_fraction:.1%} of page)")
    
    coverage = total_area / (page_width * page_height)
    print(f"\nTotal coverage: {coverage:.1%}")
    print(f"Empty space: {(1-coverage):.1%}")
    
    # Evaluate
    cost = evaluate_layout(page_width, page_height, leaves, 
                          size_importance=100.0, detailed=True)
    
    print(f"\nCost breakdown:")
    print(f"  Total cost: {cost.total_cost:.2f}")
    print(f"  Empty space cost: {cost.empty_space_cost:.2f}%")
    print(f"  Size mismatch (total): {cost.size_mismatch_cost:.2f}")
    print(f"    Normal: {cost.size_mismatch_normal_cost:.2f}")
    print(f"    Undersized: {cost.size_mismatch_undersized_cost:.2f}")
    print(f"  Undersized count: {cost.undersized_count}")
    
    print(f"\nSize errors:")
    for item_id, pref, actual, sq_err, undersized in cost.size_errors:
        status = "UNDERSIZED" if undersized else "ok"
        print(f"  {item_id}: preferred={pref:.3f}, actual={actual:.3f}, "
              f"error²={sq_err:.3f} [{status}]")
    
    print(f"\n{'='*60}")
    if cost.total_cost < 1000:
        print(f"✓ GOOD: Cost {cost.total_cost:.2f} is reasonable")
    else:
        print(f"✗ BAD: Cost {cost.total_cost:.2f} is too high!")
        print("   This indicates the tree structure is creating a bad layout.")


if __name__ == '__main__':
    main()
