#!/usr/bin/env python3
"""
Integration test: Gap Perfecter with collage_wrapper.

Demonstrates using Gap Perfecter through the full cewe-layout pipeline.
"""

import sys
sys.path.insert(0, '.')

from cewe_layout.algorithms import GapPerfecterAlgorithm
from cewe_layout.collage_wrapper import generate_layout_for_page


def test_gap_perfecter_integration():
    """Test Gap Perfecter through the full pipeline."""
    
    # Page dimensions in MCF units
    page_width = 2100.0
    page_height = 2970.0
    
    # Edge gap and internal gap (small gaps to be perfected)
    edge_gap = 0.0
    internal_gap = 0.0
    
    # Existing layout with small imperfections (3 photos in a column with tiny gaps)
    photos = [
        {
            'filename': 'photo1.jpg',
            'area_left': 1.0,
            'area_top': 1.0,
            'area_width': 2098.0,
            'area_height': 988.0,
        },
        {
            'filename': 'photo2.jpg',
            'area_left': 1.0,
            'area_top': 992.0,
            'area_width': 2098.0,
            'area_height': 988.0,
        },
        {
            'filename': 'photo3.jpg',
            'area_left': 1.0,
            'area_top': 1983.0,
            'area_width': 2098.0,
            'area_height': 986.0,
        },
    ]
    
    # Photo dimensions (required for collage_wrapper)
    photo_dimensions = {
        'photo1.jpg': (1000, 750),
        'photo2.jpg': (1000, 750),
        'photo3.jpg': (1000, 750),
    }
    
    # Create algorithm instance
    algorithm = GapPerfecterAlgorithm()
    
    # Run through collage_wrapper
    success, updated_photos, updated_texts, error = generate_layout_for_page(
        photos=photos,
        page_width_mcf=page_width,
        page_height_mcf=page_height,
        photo_dimensions=photo_dimensions,
        algorithm=algorithm,
        edge_gap=edge_gap,
        internal_gap=internal_gap,
        origin_left=0.0,
        pageno=1
    )
    
    assert success, f"Layout generation failed: {error}"
    assert len(updated_photos) == 3, "Should return all 3 photos"
    
    # After perfecting, photos should fill the page with no gaps
    photo1, photo2, photo3 = updated_photos
    
    # First photo should start at (0, 0)
    assert photo1['area_left'] == 0.0, f"Photo 1 should start at x=0, got {photo1['area_left']}"
    assert photo1['area_top'] == 0.0, f"Photo 1 should start at y=0, got {photo1['area_top']}"
    
    # Photos should be adjacent (no gaps)
    gap1_2 = photo2['area_top'] - (photo1['area_top'] + photo1['area_height'])
    gap2_3 = photo3['area_top'] - (photo2['area_top'] + photo2['area_height'])
    
    assert abs(gap1_2) < 0.1, f"Should be no gap between photo 1 and 2, got {gap1_2}"
    assert abs(gap2_3) < 0.1, f"Should be no gap between photo 2 and 3, got {gap2_3}"
    
    # Last photo should extend to bottom edge
    bottom_gap = page_height - (photo3['area_top'] + photo3['area_height'])
    assert abs(bottom_gap) < 0.1, f"Photo 3 should extend to bottom edge, gap = {bottom_gap}"
    
    # All photos should extend to left and right edges
    for i, photo in enumerate(updated_photos, 1):
        left_gap = photo['area_left']
        right_gap = page_width - (photo['area_left'] + photo['area_width'])
        
        assert abs(left_gap) < 0.1, f"Photo {i} should start at x=0, gap = {left_gap}"
        assert abs(right_gap) < 0.1, f"Photo {i} should extend to right edge, gap = {right_gap}"
    
    print("✓ Gap Perfecter integration test passed")
    print(f"  Photo 1: ({photo1['area_left']:.1f}, {photo1['area_top']:.1f}, {photo1['area_width']:.1f}, {photo1['area_height']:.1f})")
    print(f"  Photo 2: ({photo2['area_left']:.1f}, {photo2['area_top']:.1f}, {photo2['area_width']:.1f}, {photo2['area_height']:.1f})")
    print(f"  Photo 3: ({photo3['area_left']:.1f}, {photo3['area_top']:.1f}, {photo3['area_width']:.1f}, {photo3['area_height']:.1f})")


def test_gap_perfecter_with_2x2_grid():
    """Test Gap Perfecter on a 2x2 grid through the pipeline."""
    
    # Page dimensions
    page_width = 2000.0
    page_height = 2000.0
    
    # No gaps initially
    edge_gap = 0.0
    internal_gap = 0.0
    
    # Nearly perfect 2x2 grid with tiny imperfections
    photos = [
        {'filename': 'tl.jpg', 'area_left': 1.0, 'area_top': 1.0, 'area_width': 998.0, 'area_height': 998.0},
        {'filename': 'tr.jpg', 'area_left': 1001.0, 'area_top': 1.0, 'area_width': 998.0, 'area_height': 998.0},
        {'filename': 'bl.jpg', 'area_left': 1.0, 'area_top': 1001.0, 'area_width': 998.0, 'area_height': 998.0},
        {'filename': 'br.jpg', 'area_left': 1001.0, 'area_top': 1001.0, 'area_width': 998.0, 'area_height': 998.0},
    ]
    
    photo_dimensions = {
        'tl.jpg': (1000, 1000),
        'tr.jpg': (1000, 1000),
        'bl.jpg': (1000, 1000),
        'br.jpg': (1000, 1000),
    }
    
    algorithm = GapPerfecterAlgorithm()
    
    success, updated_photos, _, error = generate_layout_for_page(
        photos=photos,
        page_width_mcf=page_width,
        page_height_mcf=page_height,
        photo_dimensions=photo_dimensions,
        algorithm=algorithm,
        edge_gap=edge_gap,
        internal_gap=internal_gap,
        origin_left=0.0,
        pageno=1
    )
    
    assert success, f"Layout generation failed: {error}"
    assert len(updated_photos) == 4, "Should return all 4 photos"
    
    # Find photos by filename
    photos_by_name = {p['filename']: p for p in updated_photos}
    
    # Check that layout is perfect
    tl = photos_by_name['tl.jpg']
    tr = photos_by_name['tr.jpg']
    bl = photos_by_name['bl.jpg']
    br = photos_by_name['br.jpg']
    
    # Top-left at origin
    assert tl['area_left'] == 0.0 and tl['area_top'] == 0.0, "TL should be at (0, 0)"
    
    # No gaps horizontally
    assert abs(tr['area_left'] - (tl['area_left'] + tl['area_width'])) < 0.1, "TR should touch TL"
    assert abs(br['area_left'] - (bl['area_left'] + bl['area_width'])) < 0.1, "BR should touch BL"
    
    # No gaps vertically
    assert abs(bl['area_top'] - (tl['area_top'] + tl['area_height'])) < 0.1, "BL should touch TL"
    assert abs(br['area_top'] - (tr['area_top'] + tr['area_height'])) < 0.1, "BR should touch TR"
    
    # Extends to page edges
    assert abs(tr['area_left'] + tr['area_width'] - page_width) < 0.1, "TR should extend to right edge"
    assert abs(br['area_left'] + br['area_width'] - page_width) < 0.1, "BR should extend to right edge"
    assert abs(bl['area_top'] + bl['area_height'] - page_height) < 0.1, "BL should extend to bottom edge"
    assert abs(br['area_top'] + br['area_height'] - page_height) < 0.1, "BR should extend to bottom edge"
    
    print("✓ Gap Perfecter 2x2 grid test passed")


if __name__ == '__main__':
    test_gap_perfecter_integration()
    test_gap_perfecter_with_2x2_grid()
    print("\n✓ All integration tests passed!")
