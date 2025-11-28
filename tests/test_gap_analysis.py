#!/usr/bin/env python3
"""
Test script to analyze gap calculation for a specific page.
Shows detailed breakdown of edge gaps, inter-photo gaps, and bleed.
Uses actual functions from gap_utils.py.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.gap_utils import analyze_gaps

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
    page_top = 0.0
    page_bottom = page_height
    
    print(f"\n{'='*80}")
    print(f"GAP ANALYSIS FOR PAGE {target_pageno}")
    print(f"{'='*80}")
    print(f"\nPage dimensions: {page_width:.1f} × {page_height:.1f} MCF units")
    print(f"Origin left: {origin_left:.1f} (page bounds: {page_left:.1f} to {page_right:.1f})")
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
    
    # Use the actual gap analysis function from gap_utils.py
    analysis = analyze_gaps(photos, page_width, page_height, origin_left)
    
    # Display detailed breakdown
    print(f"\n{'='*80}")
    print("GAP ANALYSIS RESULTS")
    print(f"{'='*80}\n")
    
    # Show detected margins by type
    print("EDGE GAPS (positive margins, 1mm-20% of page):")
    if analysis.edge_gaps:
        for i, gap in enumerate(analysis.edge_gaps, 1):
            print(f"  {i}. {gap:.1f} MCF ({gap/10:.2f}mm)")
        print(f"\n  Average edge gap: {analysis.edge_gap:.1f} MCF ({analysis.edge_gap/10:.2f}mm)")
    else:
        print("  None detected")
    
    print("\n\nBLEED (negative margins, photo extends beyond page):")
    if analysis.bleed_margins:
        for i, bleed in enumerate(analysis.bleed_margins, 1):
            print(f"  {i}. {bleed:.1f} MCF ({bleed/10:.2f}mm)")
        print(f"\n  Maximum bleed: {analysis.bleed:.1f} MCF ({analysis.bleed/10:.2f}mm)")
    else:
        print("  None detected")
    
    print("\n\nINTER-PHOTO GAPS (spacing between adjacent photos, 1mm-10% of page):")
    if analysis.inter_photo_gaps:
        for i, gap in enumerate(analysis.inter_photo_gaps, 1):
            print(f"  {i}. {gap:.1f} MCF ({gap/10:.2f}mm)")
        print(f"\n  Average inter-photo gap: {analysis.inter_photo_gap:.1f} MCF ({analysis.inter_photo_gap/10:.2f}mm)")
    else:
        print("  None detected")
    
    # Show individual photo margin analysis
    print(f"\n{'='*80}")
    print("INDIVIDUAL PHOTO MARGIN ANALYSIS")
    print(f"{'='*80}\n")
    
    for i, p in enumerate(photos, 1):
        left = p.get('area_left', 0)
        top = p.get('area_top', 0)
        width = p.get('area_width', 0)
        height = p.get('area_height', 0)
        right = left + width
        bottom = top + height
        
        print(f"Photo {i}:")
        
        # Left margin
        left_margin = left - page_left
        if left_margin < 0:
            print(f"  Left: {left_margin:.1f} MCF (BLEED {abs(left_margin)/10:.2f}mm)")
        elif 10 < left_margin < page_width * 0.2:
            print(f"  Left: {left_margin:.1f} MCF ({left_margin/10:.2f}mm) ✓ counted as edge gap")
        else:
            print(f"  Left: {left_margin:.1f} MCF ({left_margin/10:.2f}mm)")
        
        # Right margin
        right_margin = page_right - right
        if right_margin < 0:
            print(f"  Right: {right_margin:.1f} MCF (BLEED {abs(right_margin)/10:.2f}mm)")
        elif 10 < right_margin < page_width * 0.2:
            print(f"  Right: {right_margin:.1f} MCF ({right_margin/10:.2f}mm) ✓ counted as edge gap")
        else:
            print(f"  Right: {right_margin:.1f} MCF ({right_margin/10:.2f}mm)")
        
        # Top margin
        top_margin = top - page_top
        if top_margin < 0:
            print(f"  Top: {top_margin:.1f} MCF (BLEED {abs(top_margin)/10:.2f}mm)")
        elif 10 < top_margin < page_height * 0.2:
            print(f"  Top: {top_margin:.1f} MCF ({top_margin/10:.2f}mm) ✓ counted as edge gap")
        else:
            print(f"  Top: {top_margin:.1f} MCF ({top_margin/10:.2f}mm)")
        
        # Bottom margin
        bottom_margin = page_bottom - bottom
        if bottom_margin < 0:
            print(f"  Bottom: {bottom_margin:.1f} MCF (BLEED {abs(bottom_margin)/10:.2f}mm)")
        elif 10 < bottom_margin < page_height * 0.2:
            print(f"  Bottom: {bottom_margin:.1f} MCF ({bottom_margin/10:.2f}mm) ✓ counted as edge gap")
        else:
            print(f"  Bottom: {bottom_margin:.1f} MCF ({bottom_margin/10:.2f}mm)")
        print()
    
    # Summary
    print(f"{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    print(f"Edge gap (average positive margin): {analysis.edge_gap:.1f} MCF ({analysis.edge_gap/10:.2f}mm)")
    print(f"Inter-photo gap (average spacing): {analysis.inter_photo_gap:.1f} MCF ({analysis.inter_photo_gap/10:.2f}mm)")
    print(f"Bleed (maximum negative margin): {analysis.bleed:.1f} MCF ({analysis.bleed/10:.2f}mm)")
    print(f"\nGap used for layout (prefer inter-photo): {max(analysis.inter_photo_gap, analysis.edge_gap):.1f} MCF ({max(analysis.inter_photo_gap, analysis.edge_gap)/10:.2f}mm)")
    print()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python test_gap_analysis.py <mcf_file> <page_number>")
        print("Example: python test_gap_analysis.py Test-album.xmcf/data.mcf 14")
        sys.exit(1)
    
    mcf_path = sys.argv[1]
    page_num = int(sys.argv[2])
    
    analyze_gap_for_page(mcf_path, page_num)
