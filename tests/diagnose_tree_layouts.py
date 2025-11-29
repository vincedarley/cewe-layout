"""
Diagnostic: Understanding why tree-computed layouts differ from originals.

This tool helps us understand:
1. What positions/sizes does the tree compute?
2. How do those differ from the original layout?
3. What causes high costs in the tree-computed layout?
4. What are the gap sizes and edge margins in both layouts?
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.algorithms.tree_builder import build_tree_from_layout
from cewe_layout.algorithms.evaluator import evaluate_layout


def extract_layout_rectangles(page_data):
    """Extract LayoutRectangles from page data."""
    photos = page_data['photos']
    texts = page_data['texts']
    page_width = page_data['page_width']
    page_height = page_data['page_height']
    origin_left = page_data.get('origin_left', 0.0)
    
    rectangles = []
    
    # Add photos
    for p in photos:
        area_left = p.get('area_left', 0)
        area_top = p.get('area_top', 0)
        area_width = p.get('area_width', 100)
        area_height = p.get('area_height', 100)
        
        if area_width <= 0 or area_height <= 0:
            continue
        
        x = area_left - origin_left
        y = area_top
        
        if x + area_width < -50 or x > page_width + 50:
            continue
        if y + area_height < -50 or y > page_height + 50:
            continue
        
        rect = LayoutRectangle(
            item_id=p.get('filename', f'photo{len(rectangles)}'),
            width=area_width,
            height=area_height,
            preferred_size=1.0,
            x=x,
            y=y
        )
        rectangles.append(rect)
    
    # Add text blocks
    for i, t in enumerate(texts):
        area_left = t.get('area_left', 0)
        area_top = t.get('area_top', 0)
        area_width = t.get('area_width', 100)
        area_height = t.get('area_height', 100)
        
        if area_width <= 0 or area_height <= 0:
            continue
        
        x = area_left - origin_left
        y = area_top
        
        if x + area_width < -50 or x > page_width + 50:
            continue
        if y + area_height < -50 or y > page_height + 50:
            continue
        
        rect = LayoutRectangle(
            item_id=f'text_{i}',
            width=area_width,
            height=area_height,
            preferred_size=1.0,
            preserve_aspect_ratio=False,
            x=x,
            y=y
        )
        rectangles.append(rect)
    
    return rectangles, page_width, page_height


def analyze_gaps(rectangles, page_width, page_height, label):
    """Analyze gap sizes in a layout."""
    print(f"\n{label} gap analysis:")
    
    if not rectangles:
        return
    
    # Find edge gaps
    min_x = min(r.x for r in rectangles)
    min_y = min(r.y for r in rectangles)
    max_x = max(r.x + r.width for r in rectangles)
    max_y = max(r.y + r.height for r in rectangles)
    
    left_gap = min_x
    top_gap = min_y
    right_gap = page_width - max_x
    bottom_gap = page_height - max_y
    
    print(f"  Edge gaps: left={left_gap:.1f}, top={top_gap:.1f}, right={right_gap:.1f}, bottom={bottom_gap:.1f}")
    
    # Find internal gaps (simplified - just look at x and y coordinates)
    x_coords = sorted(set([r.x for r in rectangles] + [r.x + r.width for r in rectangles]))
    y_coords = sorted(set([r.y for r in rectangles] + [r.y + r.height for r in rectangles]))
    
    x_gaps = [x_coords[i+1] - x_coords[i] for i in range(len(x_coords)-1)]
    y_gaps = [y_coords[i+1] - y_coords[i] for i in range(len(y_coords)-1)]
    
    # Filter out zero gaps and gaps that span across items
    x_gaps = [g for g in x_gaps if g > 1]
    y_gaps = [g for g in y_gaps if g > 1]
    
    if x_gaps:
        print(f"  Horizontal gaps: min={min(x_gaps):.1f}, max={max(x_gaps):.1f}, mean={sum(x_gaps)/len(x_gaps):.1f}")
    if y_gaps:
        print(f"  Vertical gaps: min={min(y_gaps):.1f}, max={max(y_gaps):.1f}, mean={sum(y_gaps)/len(y_gaps):.1f}")


def diagnose_page(page_num, page_data):
    """Detailed diagnosis of a single page."""
    rectangles, page_width, page_height = extract_layout_rectangles(page_data)
    
    if len(rectangles) == 0:
        return
    
    print("\n" + "=" * 70)
    print(f"Page {page_num}: {len(rectangles)} items, {page_width:.0f}x{page_height:.0f}")
    print("=" * 70)
    
    # Analyze original layout
    print("\n--- ORIGINAL LAYOUT ---")
    for i, r in enumerate(rectangles):
        print(f"  [{i}] x={r.x:.1f}, y={r.y:.1f}, w={r.width:.1f}, h={r.height:.1f}, aspect={r.width/r.height:.3f}")
    
    analyze_gaps(rectangles, page_width, page_height, "Original")
    
    orig_cost = evaluate_layout(page_width, page_height, rectangles, 
                                size_importance=100.0, detailed=True)
    print(f"\nOriginal layout cost:")
    print(f"  Total: {orig_cost.total_cost:.1f}")
    print(f"  Empty space: {orig_cost.empty_space_cost:.1f}% (fraction={orig_cost.empty_space_fraction:.1%})")
    print(f"  Size mismatch: {orig_cost.size_mismatch_cost:.1f}")
    
    # Build tree and compute layout
    tree = build_tree_from_layout(rectangles, page_width, page_height, tolerance=20.0)
    
    if tree is None:
        print("\n✗ Cannot build tree for this page")
        return
    
    print("\n--- TREE-COMPUTED LAYOUT ---")
    
    # Compute layout from tree
    tree.compute_aspect_ratios(rectangles)
    tree.compute_dimensions(page_width, page_height, rectangles)
    tree.compute_layout(0, 0)
    
    leaves = tree.collect_leaves()
    for leaf in leaves:
        rect = rectangles[leaf.item_idx]
        leaf.item_id = rect.item_id
        leaf.preferred_size = rect.preferred_size
        leaf.preserve_aspect_ratio = rect.preserve_aspect_ratio
    
    for leaf in leaves:
        orig = rectangles[leaf.item_idx]
        print(f"  [{leaf.item_idx}] x={leaf.x:.1f}, y={leaf.y:.1f}, w={leaf.width:.1f}, h={leaf.height:.1f}, aspect={leaf.width/leaf.height:.3f}")
        print(f"       Δx={leaf.x - orig.x:.1f}, Δy={leaf.y - orig.y:.1f}, Δw={leaf.width - orig.width:.1f}, Δh={leaf.height - orig.height:.1f}")
    
    analyze_gaps(leaves, page_width, page_height, "Tree-computed")
    
    tree_cost = evaluate_layout(page_width, page_height, leaves,
                                size_importance=100.0, detailed=True)
    print(f"\nTree-computed layout cost:")
    print(f"  Total: {tree_cost.total_cost:.1f}")
    print(f"  Empty space: {tree_cost.empty_space_cost:.1f}% (fraction={tree_cost.empty_space_fraction:.1%})")
    print(f"  Size mismatch: {tree_cost.size_mismatch_cost:.1f}")
    
    print(f"\nCost difference: {tree_cost.total_cost - orig_cost.total_cost:.1f}")
    
    # Understand what changed
    print(f"\n--- DIAGNOSIS ---")
    print(f"Why does tree layout have different cost?")
    
    if abs(tree_cost.empty_space_fraction - orig_cost.empty_space_fraction) > 0.01:
        print(f"  • Empty space changed: {orig_cost.empty_space_fraction:.1%} → {tree_cost.empty_space_fraction:.1%}")
        print(f"    This suggests edge gaps or internal gaps changed")
    
    if abs(tree_cost.size_mismatch_cost - orig_cost.size_mismatch_cost) > 100:
        print(f"  • Size mismatch changed: {orig_cost.size_mismatch_cost:.1f} → {tree_cost.size_mismatch_cost:.1f}")
        print(f"    This suggests item sizes changed significantly")
        
        # Find which items changed size most
        for leaf in leaves:
            orig = rectangles[leaf.item_idx]
            orig_area = orig.width * orig.height
            tree_area = leaf.width * leaf.height
            area_ratio = tree_area / orig_area if orig_area > 0 else 0
            if abs(area_ratio - 1.0) > 0.1:
                print(f"    Item {leaf.item_idx}: area changed by {(area_ratio-1)*100:.1f}%")


def main():
    """Diagnose a few pages to understand the pattern."""
    album_path = Path(__file__).parent.parent.parent / 'Test-album.xmcf'
    fotobook_root = parse_mcf_from_path(str(album_path / 'data.mcf'))
    pages = extract_pages_info(fotobook_root)
    
    # Diagnose a few interesting pages
    pages_to_check = [2, 3, 6, 10]  # Mix of simple and complex
    
    for page_num, page_data in pages:
        if page_num in pages_to_check:
            diagnose_page(page_num, page_data)


if __name__ == '__main__':
    main()
