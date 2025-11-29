#!/usr/bin/env python3
"""
Step 3: Compare Fan-GA algorithm performance against tree-based layouts.

For each page that can be represented as a tree (51/53 pages), we:
1. Build the tree layout (known to be low cost from Step 2)
2. Run Fan-GA on the same page  
3. Compare the total costs

This helps us understand where Fan-GA succeeds vs fails to discover good layouts.
"""

from pathlib import Path
from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.algorithms.tree_builder import build_tree_from_layout
from cewe_layout.algorithms.fan_layout import FanLayoutAlgorithm, _evaluate_cost
from cewe_layout.algorithms.base import LayoutRectangle
import cv2

def load_page_rectangles(page_data, mcf_base_folder, edge_gap=155.6):
    """
    Load rectangles from page data with positions and slot dimensions.
    
    Args:
        page_data: Page dict from extract_pages_info
        mcf_base_folder: Base folder for images
        edge_gap: Edge gap in MCF units (default 155.6 for typical margins)
    
    Returns:
        List of LayoutRectangle objects with x, y, width, height set
    """
    rectangles = []
    photos = page_data.get('photos', [])
    
    for idx, photo in enumerate(photos):
        # Use slot dimensions (area_width, area_height)
        width = photo.get('area_width', 0)
        height = photo.get('area_height', 0)
        left = photo.get('area_left', 0)
        top = photo.get('area_top', 0)
        
        if width <= 0 or height <= 0:
            continue
            
        # Adjust to gap-free coordinates
        x = float(left) - edge_gap
        y = float(top) - edge_gap
        
        rect = LayoutRectangle(
            item_id=str(idx),
            x=x,
            y=y,
            width=float(width),
            height=float(height),
            preferred_size=1.0,
            preserve_aspect_ratio=True
        )
        rectangles.append(rect)
    
    return rectangles


def main():
    mcf_path = Path('../Test-album.xmcf/data.mcf')
    mcf_base = Path('../Test-album.xmcf')
    
    root_el = parse_mcf_from_path(str(mcf_path))
    pages = extract_pages_info(root_el)
    
    print("Step 3: Comparing Fan-GA vs Tree layouts")
    print("=" * 70)
    
    tolerance = 20.0  # 2mm tolerance for tree building
    edge_gap = 155.6  # Typical edge gap
    internal_gap = 0.0  # No internal gaps in these layouts
    
    # Skip pages 23, 24 (known to not be tree-representable)
    skip_pages = {23, 24}
    
    results = []
    
    for page_num, page_data in pages:
        if page_num in skip_pages:
            continue
            
        photos = page_data.get('photos', [])
        if len(photos) == 0:
            continue
        
        page_width = page_data.get('page_width', 0)
        page_height = page_data.get('page_height', 0)
        
        # Load rectangles with slot dimensions and positions
        rectangles = load_page_rectangles(page_data, mcf_base, edge_gap)
        
        if len(rectangles) == 0:
            continue
        
        # Adjust page to gap-free coordinates
        algo_page_width = page_width - 2 * edge_gap
        algo_page_height = page_height - 2 * edge_gap
        
        # Step 1: Build tree and compute cost
        tree = build_tree_from_layout(rectangles, algo_page_width, algo_page_height, tolerance)
        
        if tree is None:
            print(f"Page {page_num}: SKIP - cannot build tree (unexpected!)")
            continue
        
        # Compute tree layout
        tree.compute_aspect_ratios(rectangles)
        tree.compute_dimensions(algo_page_width, algo_page_height, rectangles)
        tree.compute_layout(0, 0)
        
        # Compute cost for tree layout
        tree_cost = _evaluate_cost(
            tree, algo_page_width, algo_page_height, rectangles
        )
        
        # Step 2: Run Fan-GA on same page
        fan_algo = FanLayoutAlgorithm(
            generations=50,  # Reduced for faster testing
            population_size=30
        )
        
        # Fan-GA needs rectangles without positions (generates new layout)
        fan_rectangles = []
        for rect in rectangles:
            fan_rect = LayoutRectangle(
                item_id=rect.item_id,
                width=rect.width,
                height=rect.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio
            )
            fan_rectangles.append(fan_rect)
        
        success, positioned_rects, error_msg = fan_algo.generate_layout(
            algo_page_width, algo_page_height, fan_rectangles
        )
        
        if not success:
            print(f"Page {page_num}: SKIP - Fan-GA failed: {error_msg}")
            results.append({
                'page': page_num,
                'items': len(rectangles),
                'tree_cost': tree_cost,
                'fan_cost': None,
                'fan_error': error_msg
            })
            continue
        
        # Build tree from Fan-GA result to compute cost
        fan_tree = build_tree_from_layout(
            positioned_rects, algo_page_width, algo_page_height, tolerance
        )
        
        if fan_tree is None:
            # Fan-GA produced non-tree layout, compute cost differently
            # For now, just mark as N/A
            fan_cost = None
            fan_note = "Non-tree layout"
        else:
            fan_tree.compute_aspect_ratios(positioned_rects)
            fan_tree.compute_dimensions(algo_page_width, algo_page_height, positioned_rects)
            fan_tree.compute_layout(0, 0)
            fan_cost = _evaluate_cost(
                fan_tree, algo_page_width, algo_page_height, positioned_rects
            )
            fan_note = "OK"
        
        results.append({
            'page': page_num,
            'items': len(rectangles),
            'tree_cost': tree_cost,
            'fan_cost': fan_cost,
            'fan_error': None,
            'fan_note': fan_note
        })
        
        # Print progress
        if fan_cost is not None:
            diff_pct = ((fan_cost - tree_cost) / tree_cost * 100) if tree_cost > 0 else 0
            status = "GOOD" if diff_pct < 10 else "POOR"
            print(f"Page {page_num:2d}: {len(rectangles)} items | Tree: {tree_cost:8.1f} | Fan-GA: {fan_cost:8.1f} | Diff: {diff_pct:+5.1f}% | {status}")
        else:
            print(f"Page {page_num:2d}: {len(rectangles)} items | Tree: {tree_cost:8.1f} | Fan-GA: {fan_note}")
    
    print("\n" + "=" * 70)
    print("Summary:")
    print("=" * 70)
    
    good_count = sum(1 for r in results if r['fan_cost'] is not None and 
                     (r['fan_cost'] - r['tree_cost']) / r['tree_cost'] < 0.10)
    poor_count = sum(1 for r in results if r['fan_cost'] is not None and 
                     (r['fan_cost'] - r['tree_cost']) / r['tree_cost'] >= 0.10)
    failed_count = sum(1 for r in results if r['fan_cost'] is None)
    
    total = len(results)
    
    print(f"Total pages tested: {total}")
    print(f"Fan-GA within 10% of tree cost: {good_count} ({100*good_count/total:.1f}%)")
    print(f"Fan-GA >10% worse than tree: {poor_count} ({100*poor_count/total:.1f}%)")
    print(f"Fan-GA failed/non-tree: {failed_count} ({100*failed_count/total:.1f}%)")
    
    if poor_count > 0:
        print("\nPages where Fan-GA performed poorly (>10% worse than tree):")
        for r in results:
            if r['fan_cost'] is not None:
                diff_pct = (r['fan_cost'] - r['tree_cost']) / r['tree_cost'] * 100
                if diff_pct >= 10:
                    print(f"  Page {r['page']:2d}: {r['items']} items, Tree={r['tree_cost']:.1f}, Fan-GA={r['fan_cost']:.1f}, Diff=+{diff_pct:.1f}%")


if __name__ == '__main__':
    main()
