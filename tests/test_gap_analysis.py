#!/usr/bin/env python3
"""
Test 1: Gap Analysis

For each page, compute the edge gap and internal gap using core code routines.
Write results to the page's results file.

Usage:
  python tests/test_gap_analysis.py [page_num]
  
  If page_num is provided, only that page is tested.
  Otherwise all pages in tests/samples/ are tested.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_helpers import read_page_file, write_result_section
from cewe_layout.gap_utils import analyze_gaps


def create_items_list(page_data):
    """
    Create items list in the format expected by analyze_gaps.
    
    Each item needs: area_left, area_top, area_width, area_height
    """
    items = []
    
    for photo in page_data.photos:
        pos_x, pos_y = photo['pos']
        items.append({
            'area_left': pos_x,
            'area_top': pos_y,
            'area_width': photo['slot_width'],
            'area_height': photo['slot_height']
        })
    
    for text in page_data.texts:
        pos_x, pos_y = text['pos']
        items.append({
            'area_left': pos_x,
            'area_top': pos_y,
            'area_width': text['width'],
            'area_height': text['height']
        })
    
    return items


def test_page_gaps(page_file: Path):
    """
    Test gap analysis for a single page.
    
    Args:
        page_file: Path to Test-album-page-N.txt
    """
    # Read page data
    page_data = read_page_file(page_file)
    
    # Create items list for gap analysis
    items = create_items_list(page_data)
    
    if not items:
        print(f'Page {page_data.page_num}: Skipping (no items)')
        return
    
    # Analyze gaps using core code
    gap_analysis = analyze_gaps(
        items,
        page_data.page_width,
        page_data.page_height,
        page_data.origin_left
    )
    
    # Format results
    edge_gap_mm = gap_analysis.edge_gap / 10.0  # MCF units to mm
    internal_gap_mm = gap_analysis.internal_gap / 10.0
    bleed_mm = gap_analysis.bleed / 10.0
    
    result = f'''Edge gap: {gap_analysis.edge_gap:.2f} units ({edge_gap_mm:.2f} mm)
Internal gap: {gap_analysis.internal_gap:.2f} units ({internal_gap_mm:.2f} mm)
Bleed: {gap_analysis.bleed:.2f} units ({bleed_mm:.2f} mm)

Edge gaps: {[round(g, 2) for g in gap_analysis.edge_gaps]}
Internal gaps: {[round(g, 2) for g in gap_analysis.internal_gaps]}
Bleed margins: {[round(g, 2) for g in gap_analysis.bleed_margins]}
'''
    
    # Write to results file
    results_file = page_file.parent / f'{page_file.stem}-results.txt'
    write_result_section(results_file, 'Gap Analysis', result)
    
    print(f'Page {page_data.page_num}: edge={edge_gap_mm:.1f}mm, internal={internal_gap_mm:.1f}mm, bleed={bleed_mm:.1f}mm')


def main():
    if len(sys.argv) > 1:
        # Test specific page
        page_num = int(sys.argv[1])
        page_file = Path('tests/samples') / f'Test-album-page-{page_num}.txt'
        if page_file.exists():
            test_page_gaps(page_file)
        else:
            print(f'Error: {page_file} not found')
            sys.exit(1)
    else:
        # Test all pages
        samples_dir = Path('tests/samples')
        page_files = sorted([f for f in samples_dir.glob('Test-album-page-*.txt') 
                           if not f.stem.endswith('-results')])
        
        for page_file in page_files:
            test_page_gaps(page_file)


if __name__ == '__main__':
    main()
