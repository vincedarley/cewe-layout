#!/usr/bin/env python3
"""Quick test: evaluate ORIGINAL layout cost for Page 2"""

from pathlib import Path
from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.algorithms.evaluator import evaluate_layout
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.gap_utils import analyze_gaps, transform_page_to_gapfree, transform_item_to_gapfree

mcf_path = Path('../Test-album.xmcf/data.mcf')
root_el = parse_mcf_from_path(str(mcf_path))
pages = extract_pages_info(root_el)

# Find page 2
for page_num, page_data in pages:
    if page_num != 2:
        continue
    
    photos = page_data.get('photos', [])
    origin_left = page_data.get('origin_left', 0.0)
    page_width = page_data.get('page_width', 0)
    page_height = page_data.get('page_height', 0)
    
    print(f"Page 2: {len(photos)} photos")
    print(f"Page size: {page_width} x {page_height}")
    print(f"Origin left: {origin_left}")
    
    # Analyze gaps
    gap_analysis = analyze_gaps(photos, page_width, page_height, origin_left)
    print(f"\nGap analysis:")
    print(f"  Edge gap: {gap_analysis.edge_gap}")
    print(f"  Internal gap: {gap_analysis.internal_gap}")
    print(f"  Bleed: {gap_analysis.bleed}")
    
    # Transform to gap-free space
    gf_page_w, gf_page_h = transform_page_to_gapfree(
        page_width, page_height, gap_analysis.edge_gap, gap_analysis.internal_gap
    )
    print(f"\nGap-free page: {gf_page_w} x {gf_page_h}")
    
    # Load rectangles
    rectangles = []
    for idx, photo in enumerate(photos):
        left = photo.get('area_left', 0)
        top = photo.get('area_top', 0)
        width = photo.get('area_width', 0)
        height = photo.get('area_height', 0)
        
        left_adj = left - origin_left
        gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
            left_adj, top, width, height, gap_analysis.edge_gap, gap_analysis.internal_gap
        )
        
        print(f"\nPhoto {idx}:")
        print(f"  MCF: left={left}, top={top}, w={width}, h={height}")
        print(f"  Adjusted: left={left_adj}")
        print(f"  Gap-free: x={gf_left}, y={gf_top}, w={gf_width}, h={gf_height}")
        
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
    
    # Evaluate ORIGINAL layout
    cost_result = evaluate_layout(
        gf_page_w, gf_page_h, rectangles,
        size_importance=100.0,
        acceptable_empty_fraction=0.05,
        undersized_threshold=0.5,
        undersized_penalty=5.0
    )
    
    print(f"\nORIGINAL layout cost: {cost_result.total_cost:.1f}")
    print(f"  Empty space: {cost_result.empty_space_fraction*100:.2f}%")
    print(f"  Empty cost: {cost_result.empty_space_cost:.1f}")
    print(f"  Size mismatch: {cost_result.size_mismatch_cost:.1f}")
    
    break
