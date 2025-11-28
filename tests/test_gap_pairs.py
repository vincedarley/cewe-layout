#!/usr/bin/env python3
"""
Diagnostic tool to show which photo pairs are detected for gap calculation.
Shows the nearest neighbor to the right and below for each photo.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.parser import parse_mcf_from_path, extract_pages_info


def analyze_photo_pairs(mcf_path, target_pageno):
    """Show which photo pairs are used for gap calculation."""
    
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
    
    min_overlap = 200.0  # 20mm minimum overlap
    
    print(f"\n{'='*80}")
    print(f"PHOTO PAIR ANALYSIS FOR PAGE {target_pageno}")
    print(f"{'='*80}\n")
    print(f"Total photos: {len(photos)}\n")
    
    for i, p1 in enumerate(photos, 1):
        left1 = p1.get('area_left', 0)
        top1 = p1.get('area_top', 0)
        width1 = p1.get('area_width', 0)
        height1 = p1.get('area_height', 0)
        right1 = left1 + width1
        bottom1 = top1 + height1
        
        print(f"Photo {i}: ({left1:.1f}, {top1:.1f}) to ({right1:.1f}, {bottom1:.1f})")
        
        # Find closest photo to the right
        closest_right_idx = None
        closest_right_gap = None
        for j, p2 in enumerate(photos, 1):
            if i == j:
                continue
            left2 = p2.get('area_left', 0)
            top2 = p2.get('area_top', 0)
            width2 = p2.get('area_width', 0)
            height2 = p2.get('area_height', 0)
            right2 = left2 + width2
            bottom2 = top2 + height2
            
            # Check Y-overlap
            y_overlap_start = max(top1, top2)
            y_overlap_end = min(bottom1, bottom2)
            y_overlap = max(0, y_overlap_end - y_overlap_start)
            
            if y_overlap >= min_overlap:
                gap = left2 - right1
                if -100 < gap:  # -10mm to infinity
                    if closest_right_gap is None or abs(gap) < abs(closest_right_gap):
                        closest_right_gap = gap
                        closest_right_idx = j
        
        if closest_right_idx:
            print(f"  → Closest to right: Photo {closest_right_idx}, gap={closest_right_gap:.1f} MCF ({closest_right_gap/10:.2f}mm)")
        else:
            print(f"  → No photo to the right (with ≥20mm Y-overlap)")
        
        # Find closest photo below
        closest_below_idx = None
        closest_below_gap = None
        for j, p2 in enumerate(photos, 1):
            if i == j:
                continue
            left2 = p2.get('area_left', 0)
            top2 = p2.get('area_top', 0)
            width2 = p2.get('area_width', 0)
            height2 = p2.get('area_height', 0)
            right2 = left2 + width2
            bottom2 = top2 + height2
            
            # Check X-overlap
            x_overlap_start = max(left1, left2)
            x_overlap_end = min(right1, right2)
            x_overlap = max(0, x_overlap_end - x_overlap_start)
            
            if x_overlap >= min_overlap:
                gap = top2 - bottom1
                if -100 < gap:  # -10mm to infinity
                    if closest_below_gap is None or abs(gap) < abs(closest_below_gap):
                        closest_below_gap = gap
                        closest_below_idx = j
        
        if closest_below_idx:
            print(f"  ↓ Closest below: Photo {closest_below_idx}, gap={closest_below_gap:.1f} MCF ({closest_below_gap/10:.2f}mm)")
        else:
            print(f"  ↓ No photo below (with ≥20mm X-overlap)")
        
        print()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python test_gap_pairs.py <mcf_file> <page_number>")
        print("Example: python test_gap_pairs.py Test-album.xmcf/data.mcf 14")
        sys.exit(1)
    
    mcf_path = sys.argv[1]
    page_num = int(sys.argv[2])
    
    analyze_photo_pairs(mcf_path, page_num)
