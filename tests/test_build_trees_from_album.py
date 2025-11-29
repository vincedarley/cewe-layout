"""
Test building trees from actual album layouts.

This extracts rectangular slots from Test-album.xmcf pages and attempts to
build slicing trees from them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.algorithms.tree_builder import build_tree_from_layout
from cewe_layout.algorithms.evaluator import evaluate_layout


def extract_layout_rectangles(page_data):
    """Extract LayoutRectangles from page data.
    
    Uses the photo slots (area positions) as the rectangles to layout.
    """
    photos = page_data['photos']
    texts = page_data['texts']
    page_width = page_data['page_width']
    page_height = page_data['page_height']
    origin_left = page_data.get('origin_left', 0.0)
    
    rectangles = []
    
    # Add photos
    for p in photos:
        # Get slot dimensions
        area_left = p.get('area_left', 0)
        area_top = p.get('area_top', 0)
        area_width = p.get('area_width', 100)
        area_height = p.get('area_height', 100)
        
        # Skip invalid rectangles
        if area_width <= 0 or area_height <= 0:
            continue
        
        # Adjust coordinates relative to this page (subtract origin_left)
        x = area_left - origin_left
        y = area_top
        
        # Skip rectangles outside page bounds (bleed, etc.)
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
            preserve_aspect_ratio=False,  # Text can stretch
            x=x,
            y=y
        )
        rectangles.append(rect)
    
    return rectangles, page_width, page_height


def test_page_tree_construction(page_num, page_data):
    """Test tree construction for a single page."""
    rectangles, page_width, page_height = extract_layout_rectangles(page_data)
    
    if len(rectangles) == 0:
        return None  # Skip empty pages
    
    print(f"\n{'='*70}")
    print(f"Page {page_num}: {len(rectangles)} items, {page_width:.0f}x{page_height:.0f}")
    
    # Show rectangles
    for i, r in enumerate(rectangles):
        print(f"  [{i}] x={r.x:.1f}, y={r.y:.1f}, w={r.width:.1f}, h={r.height:.1f}")
    
    # Try to build tree
    tree = build_tree_from_layout(rectangles, page_width, page_height, tolerance=20.0)
    
    if tree is None:
        print(f"  ✗ FAIL: Cannot build slicing tree for this layout")
        print(f"  This page has a layout incompatible with binary slicing trees")
        return False
    
    print(f"  ✓ Built tree successfully")
    
    # Now evaluate the tree
    # First compute the layout from the tree
    tree.compute_aspect_ratios(rectangles)
    tree.compute_dimensions(page_width, page_height, rectangles)
    tree.compute_layout(0, 0)
    
    # Collect leaves
    leaves = tree.collect_leaves()
    for leaf in leaves:
        rect = rectangles[leaf.item_idx]
        leaf.item_id = rect.item_id
        leaf.preferred_size = rect.preferred_size
        leaf.preserve_aspect_ratio = rect.preserve_aspect_ratio
    
    # Evaluate cost
    cost = evaluate_layout(page_width, page_height, leaves, 
                          size_importance=100.0, detailed=True)
    
    print(f"  Tree evaluation:")
    print(f"    Total cost: {cost.total_cost:.1f}")
    print(f"    Empty space: {cost.empty_space_cost:.1f}% ({cost.empty_space_fraction:.1%})")
    print(f"    Size mismatch: {cost.size_mismatch_cost:.1f}")
    
    # Compare tree layout to original layout
    print(f"  Position comparison (original vs tree):")
    max_error = 0
    for leaf in leaves:
        orig = rectangles[leaf.item_idx]
        dx = abs(leaf.x - orig.x)
        dy = abs(leaf.y - orig.y)
        dw = abs(leaf.width - orig.width)
        dh = abs(leaf.height - orig.height)
        max_error = max(max_error, dx, dy, dw, dh)
        
        if dx > 10 or dy > 10 or dw > 10 or dh > 10:
            print(f"    Item {leaf.item_idx}: Δx={dx:.1f}, Δy={dy:.1f}, Δw={dw:.1f}, Δh={dh:.1f}")
    
    if max_error < 10:
        print(f"  ✓ Tree layout matches original (max error: {max_error:.1f})")
    else:
        print(f"  ⚠ Tree layout differs from original (max error: {max_error:.1f})")
    
    return True


def main():
    """Test tree construction on all album pages."""
    album_path = Path(__file__).parent.parent.parent / 'Test-album.xmcf'
    if not album_path.exists():
        print(f"✗ Album not found: {album_path}")
        return False
    
    print("=" * 70)
    print("Testing tree construction from Test-album.xmcf layouts")
    print("=" * 70)
    
    fotobook_root = parse_mcf_from_path(str(album_path / 'data.mcf'))
    pages = extract_pages_info(fotobook_root)
    
    results = []
    for page_num, page_data in pages:
        result = test_page_tree_construction(page_num, page_data)
        if result is not None:
            results.append((page_num, result))
    
    # Summary
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    
    total = len(results)
    successes = sum(1 for _, r in results if r)
    failures = total - successes
    
    print(f"Total pages tested: {total}")
    print(f"Successfully built trees: {successes}")
    print(f"Failed (not tree-representable): {failures}")
    
    if failures > 0:
        print(f"\nFailed pages:")
        for page_num, result in results:
            if not result:
                print(f"  Page {page_num}")
    
    success_rate = successes / total if total > 0 else 0
    print(f"\nSuccess rate: {success_rate:.1%}")
    
    return success_rate >= 0.9  # 90% success rate


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
