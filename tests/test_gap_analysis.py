#!/usr/bin/env python3
"""
Test script to analyze gap calculation for a specific page.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.gap_utils import estimate_gaps

def analyze_gap_for_page(mcf_path, target_pageno):
    """Analyze and report gap calculation details for a specific page."""
    
    # Parse MCF
    root = parse_mcf_from_path(mcf_path)
    pages = extract_pages_info(root)
    
    # Find target page
    target_page = None
    for pageno, info in pages:
        if pageno == target_pageno:
            target_page = info
            break
    
    if not target_page:
        print(f"Page {target_pageno} not found in MCF file")
        return
    
    photos = target_page.get('photos', [])
    page_width = target_page.get('page_width', 2100.0)
    page_height = target_page.get('page_height', 2970.0)
    origin_left = target_page.get('origin_left', 0.0)
    
    # Calculate page bounds
    page_left = origin_left
    page_right = origin_left + page_width
    
    print(f"\n{'='*80}")
    print(f"GAP ANALYSIS FOR PAGE {target_pageno}")
    print(f"{'='*80}")
    print(f"\nPage dimensions: {page_width} × {page_height} MCF units")
    print(f"Origin left: {origin_left} (page bounds: {page_left} to {page_right})")
    print(f"Number of photos: {len(photos)}\n")
    
    # Display photo positions and sizes
    print(f"{'Photo':<6} {'Left':<10} {'Top':<10} {'Width':<10} {'Height':<10} {'Right':<10} {'Bottom':<10}")
    print("-" * 80)
    
    for i, p in enumerate(photos, 1):
        left = p.get('area_left', 0)
        top = p.get('area_top', 0)
        width = p.get('area_width', 0)
        height = p.get('area_height', 0)
        right = left + width
        bottom = top + height
        print(f"{i:<6} {left:<10.1f} {top:<10.1f} {width:<10.1f} {height:<10.1f} {right:<10.1f} {bottom:<10.1f}")
    
    # Now analyze gap calculation step-by-step
    print(f"\n{'='*80}")
    print("GAP CALCULATION DETAILS")
    print(f"{'='*80}\n")
    
    edge_gaps = []
    inter_photo_gaps = []
    
    # Calculate page bounds in absolute coordinates
    page_top = 0.0
    page_bottom = page_height
    
    # Collect all edge gaps (margins from page boundaries)
    print("EDGE GAPS (margins from page boundaries):")
    for i, p in enumerate(photos, 1):
        left = p.get('area_left', 0)
        top = p.get('area_top', 0)
        width = p.get('area_width', 0)
        height = p.get('area_height', 0)
        right = left + width
        bottom = top + height
        
        print(f"\n  Photo {i} (left={left:.1f}, top={top:.1f}, right={right:.1f}, bottom={bottom:.1f}):")
        
        # Left edge (distance from page left boundary)
        left_margin = left - page_left
        if 0 < left_margin < page_width * 0.2:
            print(f"    Left margin: {left_margin:.1f} ✓ COUNTED")
            edge_gaps.append(left_margin)
        else:
            print(f"    Left margin: {left_margin:.1f} (outside threshold)")
        
        # Right edge (distance from page right boundary)
        right_margin = page_right - right
        if 0 < right_margin < page_width * 0.2:
            print(f"    Right margin: {right_margin:.1f} ✓ COUNTED")
            edge_gaps.append(right_margin)
        else:
            print(f"    Right margin: {right_margin:.1f} (outside threshold)")
        
        # Top edge (distance from page top)
        top_margin = top - page_top
        if 0 < top_margin < page_height * 0.2:
            print(f"    Top margin: {top_margin:.1f} ✓ COUNTED")
            edge_gaps.append(top_margin)
        else:
            print(f"    Top margin: {top_margin:.1f} (outside threshold)")
        
        # Bottom edge (distance from page bottom)
        bottom_margin = page_bottom - bottom
        if 0 < bottom_margin < page_height * 0.2:
            print(f"    Bottom margin: {bottom_margin:.1f} ✓ COUNTED")
            edge_gaps.append(bottom_margin)
        else:
            print(f"    Bottom margin: {bottom_margin:.1f} (outside threshold)")
    
    # Check horizontal adjacency
    print("\n\nINTER-PHOTO GAPS:")
    print("\nHorizontal adjacency (side-by-side):")
    horiz_gap_threshold = page_width * 0.1
    horiz_count = 0
    for i, p1 in enumerate(photos):
        left1 = p1.get('area_left', 0)
        top1 = p1.get('area_top', 0)
        width1 = p1.get('area_width', 0)
        height1 = p1.get('area_height', 0)
        right1 = left1 + width1
        bottom1 = top1 + height1
        
        for j, p2 in enumerate(photos[i+1:], i+1):
            left2 = p2.get('area_left', 0)
            top2 = p2.get('area_top', 0)
            width2 = p2.get('area_width', 0)
            height2 = p2.get('area_height', 0)
            right2 = left2 + width2
            bottom2 = top2 + height2
            
            # Check vertical overlap
            vertical_overlap = not (bottom1 <= top2 or bottom2 <= top1)
            
            # Check p2 to the right of p1
            if vertical_overlap and left2 > right1:
                gap = left2 - right1
                if 0 < gap < horiz_gap_threshold:
                    print(f"  Photo {i+1} → Photo {j+1}: gap={gap:.1f} (right1={right1:.1f}, left2={left2:.1f}) ✓ COUNTED")
                    inter_photo_gaps.append(gap)
                    horiz_count += 1
                elif left2 > right1 and gap > 0:
                    print(f"  Photo {i+1} → Photo {j+1}: gap={gap:.1f} (exceeds threshold {horiz_gap_threshold:.1f}) ✗ skipped")
            
            # Check p1 to the right of p2
            if vertical_overlap and left1 > right2:
                gap = left1 - right2
                if 0 < gap < horiz_gap_threshold:
                    print(f"  Photo {j+1} → Photo {i+1}: gap={gap:.1f} (right2={right2:.1f}, left1={left1:.1f}) ✓ COUNTED")
                    inter_photo_gaps.append(gap)
                    horiz_count += 1
                elif left1 > right2 and gap > 0:
                    print(f"  Photo {j+1} → Photo {i+1}: gap={gap:.1f} (exceeds threshold {horiz_gap_threshold:.1f}) ✗ skipped")
    
    if horiz_count == 0:
        print("  (none found)")
    
    # Check vertical adjacency
    print("\nVertical adjacency (stacked):")
    vert_gap_threshold = page_height * 0.1
    vert_count = 0
    for i, p1 in enumerate(photos):
        left1 = p1.get('area_left', 0)
        top1 = p1.get('area_top', 0)
        width1 = p1.get('area_width', 0)
        height1 = p1.get('area_height', 0)
        right1 = left1 + width1
        bottom1 = top1 + height1
        
        for j, p2 in enumerate(photos[i+1:], i+1):
            left2 = p2.get('area_left', 0)
            top2 = p2.get('area_top', 0)
            width2 = p2.get('area_width', 0)
            height2 = p2.get('area_height', 0)
            right2 = left2 + width2
            bottom2 = top2 + height2
            
            # Check horizontal overlap
            horizontal_overlap = not (right1 <= left2 or right2 <= left1)
            
            # Check p2 below p1
            if horizontal_overlap and top2 > bottom1:
                gap = top2 - bottom1
                if 0 < gap < vert_gap_threshold:
                    print(f"  Photo {i+1} → Photo {j+1}: gap={gap:.1f} (bottom1={bottom1:.1f}, top2={top2:.1f}) ✓ COUNTED")
                    inter_photo_gaps.append(gap)
                    vert_count += 1
                elif top2 > bottom1 and gap > 0:
                    print(f"  Photo {i+1} → Photo {j+1}: gap={gap:.1f} (exceeds threshold {vert_gap_threshold:.1f}) ✗ skipped")
            
            # Check p1 below p2
            if horizontal_overlap and top1 > bottom2:
                gap = top1 - bottom2
                if 0 < gap < vert_gap_threshold:
                    print(f"  Photo {j+1} → Photo {i+1}: gap={gap:.1f} (bottom2={bottom2:.1f}, top1={top1:.1f}) ✓ COUNTED")
                    inter_photo_gaps.append(gap)
                    vert_count += 1
                elif top1 > bottom2 and gap > 0:
                    print(f"  Photo {j+1} → Photo {i+1}: gap={gap:.1f} (exceeds threshold {vert_gap_threshold:.1f}) ✗ skipped")
    
    if vert_count == 0:
        print("  (none found)")
    
    # Calculate final gaps
    print(f"\n{'='*80}")
    print("FINAL CALCULATION")
    print(f"{'='*80}\n")
    
    if not edge_gaps:
        print("Edge gaps: none detected")
        edge_gap_avg = 0.0
    else:
        edge_gaps.sort()
        print(f"Edge gaps collected: {[f'{g:.1f}' for g in edge_gaps]}")
        edge_gap_avg = sum(edge_gaps) / len(edge_gaps)
        print(f"Average edge gap: {edge_gap_avg:.1f} MCF units ({edge_gap_avg/10.0:.2f}mm)")
    
    if not inter_photo_gaps:
        print("\nInter-photo gaps: none detected")
        inter_gap_avg = 0.0
    else:
        inter_photo_gaps.sort()
        print(f"\nInter-photo gaps collected: {[f'{g:.1f}' for g in inter_photo_gaps]}")
        inter_gap_avg = sum(inter_photo_gaps) / len(inter_photo_gaps)
        print(f"Average inter-photo gap: {inter_gap_avg:.1f} MCF units ({inter_gap_avg/10.0:.2f}mm)")
    
    # Verify with estimate_gaps function
    print(f"\n{'='*80}")
    print("VERIFICATION WITH estimate_gaps() FUNCTION")
    print(f"{'='*80}\n")
    calc_edge, calc_inter = estimate_gaps(photos, page_width, page_height, origin_left)
    print(f"estimate_gaps returned:")
    print(f"  Edge gap: {calc_edge:.1f} MCF units ({calc_edge/10.0:.2f}mm)")
    print(f"  Inter-photo gap: {calc_inter:.1f} MCF units ({calc_inter/10.0:.2f}mm)")
    print(f"\nGap used (prefer inter-photo): {calc_inter if calc_inter > 0 else calc_edge:.1f} MCF units ({(calc_inter if calc_inter > 0 else calc_edge)/10.0:.2f}mm)")
    
    print()


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python test_gap_analysis.py <mcf_file> <page_number>")
        sys.exit(1)
    
    mcf_path = sys.argv[1]
    page_num = int(sys.argv[2])
    
    analyze_gap_for_page(mcf_path, page_num)
