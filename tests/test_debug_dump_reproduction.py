"""
Test to reproduce layout generation from debug dump file.

This test reads a Debug-Page-N.txt file (generated when debug mode is enabled in the GUI),
transforms the data through gap-free coordinate space, runs the algorithm, and validates
the results.

Usage:
    1. In GUI, enable Debug checkbox
    2. Navigate to problem page (e.g., page 75)
    3. Set edge gap (e.g., -3mm)
    4. Click "Generate Layout"
    5. A Debug-Page-75.txt file will be created
    6. Run this test: pytest tests/test_debug_dump_reproduction.py
"""

import re
from pathlib import Path
from cewe_layout.gap_utils import (
    transform_item_to_gapfree, transform_item_from_gapfree,
    transform_page_to_gapfree
)


def parse_debug_dump(filepath):
    """Parse a Debug-Page-N.txt file and extract all parameters.
    
    Returns:
        dict with keys: pageno, page_w, page_h, origin_left, is_left_page, spread_mode,
                       edge_gap, internal_gap, algorithm_name, photos, texts
    """
    with open(filepath, 'r') as f:
        content = f.read()
    
    # Extract page properties
    page_w = float(re.search(r'page_width: (\d+\.?\d*)', content).group(1))
    page_h = float(re.search(r'page_height: (\d+\.?\d*)', content).group(1))
    origin_left = float(re.search(r'origin_left: (\d+\.?\d*)', content).group(1))
    is_left_page = 'is_left_page: True' in content
    spread_mode = 'spread_mode: True' in content
    
    # Extract gap parameters
    edge_gap_match = re.search(r'edge_gap: ([-\d.]+)', content)
    edge_gap = float(edge_gap_match.group(1))
    internal_gap_match = re.search(r'internal_gap: ([-\d.]+)', content)
    internal_gap = float(internal_gap_match.group(1))
    
    # Extract algorithm name
    algo_match = re.search(r'name: (.+)', content)
    algorithm_name = algo_match.group(1).strip()
    
    # Extract photos (simplified - parse photo blocks)
    photos = []
    photo_blocks = re.findall(r'Photo \d+:(.*?)(?=Photo \d+:|TEXTS)', content, re.DOTALL)
    for block in photo_blocks:
        photo = {}
        if 'filename:' in block:
            fn_match = re.search(r'filename: (.+)', block)
            if fn_match and fn_match.group(1).strip() != 'N/A':
                photo['filename'] = fn_match.group(1).strip()
        if 'area_left:' in block:
            photo['area_left'] = float(re.search(r'area_left: ([-\d.]+)', block).group(1))
        if 'area_top:' in block:
            photo['area_top'] = float(re.search(r'area_top: ([-\d.]+)', block).group(1))
        if 'area_width:' in block:
            photo['area_width'] = float(re.search(r'area_width: ([-\d.]+)', block).group(1))
        if 'area_height:' in block:
            photo['area_height'] = float(re.search(r'area_height: ([-\d.]+)', block).group(1))
        if 'preferred_size:' in block:
            photo['preferred_size'] = float(re.search(r'preferred_size: ([-\d.]+)', block).group(1))
        photos.append(photo)
    
    # Extract texts (simplified)
    texts = []
    text_blocks = re.findall(r'Text \d+:(.*?)(?=Text \d+:|To reproduce)', content, re.DOTALL)
    for block in text_blocks:
        text = {}
        if 'area_left:' in block:
            text['area_left'] = float(re.search(r'area_left: ([-\d.]+)', block).group(1))
        if 'area_top:' in block:
            text['area_top'] = float(re.search(r'area_top: ([-\d.]+)', block).group(1))
        if 'area_width:' in block:
            text['area_width'] = float(re.search(r'area_width: ([-\d.]+)', block).group(1))
        if 'area_height:' in block:
            text['area_height'] = float(re.search(r'area_height: ([-\d.]+)', block).group(1))
        if 'preferred_size:' in block:
            text['preferred_size'] = float(re.search(r'preferred_size: ([-\d.]+)', block).group(1))
        texts.append(text)
    
    return {
        'page_w': page_w,
        'page_h': page_h,
        'origin_left': origin_left,
        'is_left_page': is_left_page,
        'spread_mode': spread_mode,
        'edge_gap': edge_gap,
        'internal_gap': internal_gap,
        'algorithm_name': algorithm_name,
        'photos': photos,
        'texts': texts
    }


def test_debug_dump_exists():
    """Check if a debug dump file exists to test."""
    # Look for Debug-Page-*.txt in tests directory
    test_dir = Path(__file__).parent
    debug_files = list(test_dir.glob('Debug-Page-*.txt'))
    assert len(debug_files) > 0, "No Debug-Page-*.txt files found. Run GUI with debug mode enabled first."


def test_reproduce_from_debug_dump():
    """Reproduce layout generation from debug dump and validate transformations."""
    # Find most recent debug dump in tests directory
    test_dir = Path(__file__).parent
    debug_files = sorted(test_dir.glob('Debug-Page-*.txt'), key=lambda p: p.stat().st_mtime, reverse=True)
    if not debug_files:
        import pytest
        pytest.skip("No debug dump file found")
    
    debug_file = debug_files[0]
    print(f"\nReproducing from: {debug_file}")
    
    # Parse the dump
    data = parse_debug_dump(debug_file)
    
    print(f"\nPage properties:")
    print(f"  Page: {data['page_w']} x {data['page_h']}")
    print(f"  origin_left: {data['origin_left']}")
    print(f"  is_left_page: {data['is_left_page']}")
    print(f"  Edge gap: {data['edge_gap']} ({data['edge_gap']/10:.1f}mm)")
    print(f"  Internal gap: {data['internal_gap']} ({data['internal_gap']/10:.1f}mm)")
    print(f"  Algorithm: {data['algorithm_name']}")
    print(f"  Photos: {len(data['photos'])}, Texts: {len(data['texts'])}")
    
    # Step 1: Transform items to gap-free coordinates
    gapfree_photos = []
    for i, photo in enumerate(data['photos']):
        left = photo.get('area_left', 0)
        top = photo.get('area_top', 0)
        w = photo.get('area_width', 0)
        h = photo.get('area_height', 0)
        
        # Convert to page-relative coordinates (subtract origin_left)
        page_relative_left = left - data['origin_left']
        
        # Transform to gap-free
        gf_left, gf_top, gf_w, gf_h = transform_item_to_gapfree(
            page_relative_left, top, w, h,
            data['edge_gap'], data['internal_gap'],
            data['spread_mode'], data['is_left_page']
        )
        
        gapfree_photos.append({
            'original_left': left,
            'page_relative_left': page_relative_left,
            'gapfree_left': gf_left,
            'gapfree_top': gf_top,
            'gapfree_width': gf_w,
            'gapfree_height': gf_h
        })
    
    # Step 2: Transform page dimensions
    gf_page_w, gf_page_h = transform_page_to_gapfree(
        data['page_w'], data['page_h'],
        data['edge_gap'], data['internal_gap'],
        data['spread_mode']
    )
    
    print(f"\nGap-free page: {gf_page_w} x {gf_page_h}")
    
    # Step 3: Validate gap-free transformations
    print(f"\nGap-free photos:")
    for i, gf_photo in enumerate(gapfree_photos):
        print(f"  Photo {i}:")
        print(f"    Original MCF left: {gf_photo['original_left']}")
        print(f"    Page-relative left: {gf_photo['page_relative_left']}")
        print(f"    Gap-free left: {gf_photo['gapfree_left']}")
        print(f"    Gap-free dims: {gf_photo['gapfree_width']} x {gf_photo['gapfree_height']}")
        
        # Validate: For right pages with negative edge_gap, items should NOT have
        # negative gap-free left positions (centerfold bleed prevention)
        if not data['is_left_page'] and data['edge_gap'] < 0:
            if gf_photo['page_relative_left'] == 0:  # Item at left edge (centerfold)
                # Gap-free left should be 0 (not negative)
                assert gf_photo['gapfree_left'] == 0, \
                    f"Photo {i} at centerfold should have gapfree_left=0, got {gf_photo['gapfree_left']}"
                print(f"    ✓ Centerfold bleed prevention working correctly")
    
    # Step 4: Transform back from gap-free to MCF coordinates (for round-trip validation)
    print(f"\n=== INVERSE TRANSFORMATION (Gap-free back to MCF) ===")
    mcf_photos = []
    for i, gf_photo in enumerate(gapfree_photos):
        # Transform back from gap-free to page-relative MCF
        mcf_left, mcf_top, mcf_w, mcf_h = transform_item_from_gapfree(
            gf_photo['gapfree_left'], gf_photo['gapfree_top'],
            gf_photo['gapfree_width'], gf_photo['gapfree_height'],
            data['edge_gap'], data['internal_gap'],
            data['spread_mode'], data['is_left_page']
        )
        
        # Convert back to absolute MCF coordinates (add origin_left)
        mcf_left_abs = mcf_left + data['origin_left']
        
        mcf_photos.append({
            'gapfree_left': gf_photo['gapfree_left'],
            'mcf_left': mcf_left,
            'mcf_left_abs': mcf_left_abs,
            'mcf_top': mcf_top,
            'mcf_width': mcf_w,
            'mcf_height': mcf_h
        })
    
    # Step 5: Simulate what Gap Perfecter does - expand items to left edge (x=0)
    print(f"\n=== GAP PERFECTER SIMULATION ===")
    print(f"Gap Perfecter expands items to x=0 in gap-free space")
    print(f"What happens when we transform back?")
    print()
    
    # Simulate a photo at the centerfold that Gap Perfecter expands to x=0
    for i in [1, 6, 19]:  # Photos at centerfold
        orig_photo = data['photos'][i]
        print(f"Photo {i} (originally at centerfold):")
        print(f"  Original MCF left: {orig_photo.get('area_left', 0):.2f}")
        print(f"  Original page-relative left: {orig_photo.get('area_left', 0) - data['origin_left']:.2f}")
        
        # Current gap-free position (from forward transform)
        current_gf_left = gapfree_photos[i]['gapfree_left']
        print(f"  Current gap-free left: {current_gf_left:.2f}")
        
        # Simulate Gap Perfecter expanding to left edge
        gp_gf_left = 0.0  # Gap Perfecter moves it to x=0
        print(f"  Gap Perfecter moves to: {gp_gf_left:.2f} (left edge in gap-free space)")
        
        # Transform back from gap-free to page-relative MCF
        gp_mcf_left, _, _, _ = transform_item_from_gapfree(
            gp_gf_left, 
            gapfree_photos[i]['gapfree_top'],
            gapfree_photos[i]['gapfree_width'],
            gapfree_photos[i]['gapfree_height'],
            data['edge_gap'], data['internal_gap'],
            data['spread_mode'], data['is_left_page']
        )
        
        # Convert back to absolute MCF coordinates
        gp_mcf_left_abs = gp_mcf_left + data['origin_left']
        
        print(f"  After inverse transform:")
        print(f"    Page-relative MCF left: {gp_mcf_left:.2f}")
        print(f"    Absolute MCF left: {gp_mcf_left_abs:.2f}")
        print(f"    Expected (>= origin_left): {data['origin_left']:.2f}")
        
        if gp_mcf_left < 0:
            print(f"    ❌ BUG FOUND: Photo bleeds into centerfold by {abs(gp_mcf_left):.2f} units!")
        elif gp_mcf_left_abs < data['origin_left'] - 0.1:
            print(f"    ❌ BUG FOUND: Photo at {gp_mcf_left_abs:.2f} is left of centerfold {data['origin_left']:.2f}!")
        else:
            print(f"    ✓ Correct: Photo stays at or right of centerfold")
        print()
    
    # Step 6: Check if left edge items would bleed into centerfold (the bug)
    if not data['is_left_page'] and data['edge_gap'] < 0:
        print(f"\n=== CENTERFOLD BLEED CHECK (After inverse transform) ===")
        print(f"This is a RIGHT page with negative edge_gap ({data['edge_gap']/10:.1f}mm)")
        print(f"Items at left edge (centerfold) should NOT have mcf_left < origin_left")
        
        for i, photo in enumerate(data['photos']):
            page_rel_left = photo.get('area_left', 0) - data['origin_left']
            if abs(page_rel_left) < 1:  # At or near left edge (centerfold)
                mcf_left_abs = mcf_photos[i]['mcf_left_abs']
                expected_mcf_left = data['origin_left']  # Should be at origin_left (not less)
                
                print(f"  Photo {i} at centerfold:")
                print(f"    Original MCF left: {photo.get('area_left', 0):.2f}")
                print(f"    Expected MCF left (>= origin_left): {expected_mcf_left:.2f}")
                print(f"    Actual MCF left after transform: {mcf_left_abs:.2f}")
                
                if mcf_left_abs < expected_mcf_left - 0.1:
                    print(f"    ❌ FAIL: Photo bleeds into centerfold by {expected_mcf_left - mcf_left_abs:.2f} units!")
                    assert False, f"Photo {i} should not bleed at centerfold! Expected >= {expected_mcf_left}, got {mcf_left_abs}"
                else:
                    print(f"    ✓ PASS")


if __name__ == '__main__':
    # Run standalone
    test_debug_dump_exists()
    test_reproduce_from_debug_dump()
