#!/usr/bin/env python3
"""
Validation: Confirm that tree layouts have low costs (<1000).

This script validates Step 2 of our plan - that tree-represented layouts
correspond to extremely low "total cost".
"""

from pathlib import Path
from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.algorithms.tree_builder import build_tree_from_layout
from cewe_layout.algorithms.evaluator import evaluate_layout
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.gap_utils import (
    analyze_gaps, transform_page_to_gapfree, transform_item_to_gapfree
)
from cewe_layout.gap_utils import analyze_gaps
from cewe_layout.collage_wrapper import transform_page_to_gapfree


def load_page_rectangles_with_gaps(page_data):
    """
    Load rectangles from page data properly transformed to gap-free space.
    
    This mimics what the GUI does:
    1. Analyze gaps from original layout
    2. Transform items to gap-free space
    3. Return rectangles and transformed page dimensions
    """
    photos = page_data.get('photos', [])
    texts = page_data.get('texts', [])
    origin_left = page_data.get('origin_left', 0.0)
    page_width = page_data.get('page_width', 0)
    page_height = page_data.get('page_height', 0)
    
    # Analyze gaps from original layout
    all_items = photos + texts
    if not all_items:
        return [], page_width, page_height, 0.0, 0.0
    
    gap_analysis = analyze_gaps(all_items, page_width, page_height, origin_left)
    edge_gap = gap_analysis.edge_gap
    internal_gap = gap_analysis.internal_gap
    
    # Transform page to gap-free space
    gapfree_page_w, gapfree_page_h = transform_page_to_gapfree(
        page_width, page_height, edge_gap, internal_gap
    )
    
    rectangles = []
    
    # Transform photos to gap-free space
    for idx, photo in enumerate(photos):
        left = photo.get('area_left', 0)
        top = photo.get('area_top', 0)
        width = photo.get('area_width', 0)
        height = photo.get('area_height', 0)
        
        if width <= 0 or height <= 0:
            continue
        
        # Subtract origin_left for right pages (NOT edge_gap here, just page offset)
        left_adjusted = left - origin_left
        
        # Transform to gap-free space
        gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
            left_adjusted, top, width, height, edge_gap, internal_gap
        )
        
        rect = LayoutRectangle(
            item_id=str(idx),
            x=gf_left,
            y=gf_top,
            width=gf_width,
            height=gf_height,
            preferred_size=1.0,
            preserve_aspect_ratio=True
        )
        rectangles.append(rect)
    
    # Transform texts to gap-free space
    for idx, text in enumerate(texts):
        left = text.get('area_left', 0)
        top = text.get('area_top', 0)
        width = text.get('area_width', 0)
        height = text.get('area_height', 0)
        
        if width <= 0 or height <= 0:
            continue
        
        left_adjusted = left - origin_left
        
        gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
            left_adjusted, top, width, height, edge_gap, internal_gap
        )
        
        rect = LayoutRectangle(
            item_id=f'TEXT_{idx}',
            x=gf_left,
            y=gf_top,
            width=gf_width,
            height=gf_height,
            preferred_size=1.0,
            preserve_aspect_ratio=False
        )
        rectangles.append(rect)
    
    return rectangles, gapfree_page_w, gapfree_page_h, edge_gap, internal_gap


def main():
    mcf_path = Path('../Test-album.xmcf/data.mcf')
    
    root_el = parse_mcf_from_path(str(mcf_path))
    pages = extract_pages_info(root_el)
    
    print("Validating tree layout costs")
    print("=" * 70)
    
    tolerance = 20.0
    skip_pages = {23, 24}  # Not tree-representable
    
    low_cost_count = 0
    high_cost_count = 0
    cannot_build = 0
    
    for page_num, page_data in pages:
        if page_num in skip_pages:
            continue
            
        photos = page_data.get('photos', [])
        if len(photos) == 0:
            continue
        
        # Load rectangles properly transformed to gap-free space
        rectangles, gapfree_page_w, gapfree_page_h, edge_gap, internal_gap = load_page_rectangles_with_gaps(page_data)
        
        if len(rectangles) == 0:
            continue
        
        # Build tree from original layout (in gap-free space)
        tree = build_tree_from_layout(rectangles, gapfree_page_w, gapfree_page_h, tolerance)
        
        if tree is None:
            print(f"Page {page_num:2d}: Cannot build tree (unexpected!)")
            cannot_build += 1
            continue
        
        # Compute tree layout
        tree.compute_aspect_ratios(rectangles)
        tree.compute_dimensions(gapfree_page_w, gapfree_page_h, rectangles)
        tree.compute_layout(0, 0)
        
        # Collect tree leaves as positioned rectangles
        leaves = tree.collect_leaves()
        tree_rects = []
        for leaf in leaves:
            original = rectangles[leaf.item_idx]
            tr = LayoutRectangle(
                item_id=original.item_id,
                x=leaf.x,
                y=leaf.y,
                width=leaf.width,
                height=leaf.height,
                preferred_size=original.preferred_size,
                preserve_aspect_ratio=original.preserve_aspect_ratio
            )
            tree_rects.append(tr)
        
        # Evaluate cost using the evaluator (same as GUI)
        cost_result = evaluate_layout(
            gapfree_page_w, gapfree_page_h, tree_rects,
            size_importance=100.0,
            acceptable_empty_fraction=0.05,
            undersized_threshold=0.5,
            undersized_penalty=5.0
        )
        
        cost = cost_result.total_cost
        
        if cost < 1000:
            status = "✓ GOOD"
            low_cost_count += 1
        else:
            status = "✗ HIGH COST"
            high_cost_count += 1
        
        print(f"Page {page_num:2d}: {len(rectangles)} items, cost={cost:7.1f} {status}")
    
    print("\n" + "=" * 70)
    print("Summary:")
    print(f"  Low cost (< 1000): {low_cost_count}")
    print(f"  High cost (>= 1000): {high_cost_count}")
    print(f"  Cannot build tree: {cannot_build}")
    
    total = low_cost_count + high_cost_count + cannot_build
    if low_cost_count == total:
        print("\n✓ All pages have low cost - validation PASSED")
    else:
        print(f"\n✗ {high_cost_count + cannot_build} pages failed - validation FAILED")
        
        if cost < 1000:
            status = "✓ GOOD"
            low_cost_count += 1
        else:
            status = "✗ HIGH COST"
            high_cost_count += 1
        
        print(f"Page {page_num:2d}: {len(rectangles)} items, cost={cost:7.1f} {status}")
    
    print("\n" + "=" * 70)
    print("Summary:")
    print(f"  Low cost (< 1000): {low_cost_count}")
    print(f"  High cost (>= 1000): {high_cost_count}")
    print(f"  Cannot build tree: {cannot_build}")
    
    total = low_cost_count + high_cost_count + cannot_build
    if low_cost_count == total:
        print("\n✓ All pages have low cost - validation PASSED")
    else:
        print(f"\n✗ {high_cost_count + cannot_build} pages failed - validation FAILED")


if __name__ == '__main__':
    main()
