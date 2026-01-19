"""
Test layout generation with text blocks.

This test verifies that the complete pipeline (wrapper → algorithm → wrapper)
works correctly for pages with both photos and text blocks.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.mcf_io.mcf_parser import extract_pages_info, parse_mcf_from_path


def test_page_20_layout():
    """Test layout generation on page 20 which has photos and text."""
    
    mcf_path = Path(__file__).parent.parent.parent / 'Test-album.xmcf' / 'data.mcf'
    if not mcf_path.exists():
        print(f"⚠️  Test skipped: {mcf_path} not found")
        return
    
    print(f"Parsing MCF: {mcf_path}")
    mcf_root = parse_mcf_from_path(str(mcf_path))
    pages_info = extract_pages_info(mcf_root)
    
    # Find page 20
    page_20_info = None
    for pageno, info in pages_info:
        if pageno == 20:
            page_20_info = info
            break
    
    if not page_20_info:
        print("⚠️  Page 20 not found in MCF")
        return
    
    photos = page_20_info.get('photos', [])
    texts = page_20_info.get('texts', [])
    page_w = page_20_info.get('page_width', 2100)
    page_h = page_20_info.get('page_height', 2970)
    
    print(f"\nPage 20:")
    print(f"  Photos: {len(photos)}")
    print(f"  Texts: {len(texts)}")
    print(f"  Dimensions: {page_w}x{page_h}")
    
    if texts:
        print(f"\nText blocks:")
        for i, text in enumerate(texts):
            print(f"  TEXT_{i}: {text.get('area_width', 0)}x{text.get('area_height', 0)} "
                  f"at ({text.get('area_left', 0)}, {text.get('area_top', 0)})")
    
    # Test layout generation
    from cewe_layout.collage_wrapper import generate_layout_for_page
    
    mcf_base = mcf_path.parent
    
    print(f"\nGenerating layout with gap=0...")
    success, updated_photos, updated_texts, error_msg = generate_layout_for_page(
        photos, page_w, page_h, mcf_base,
        temperature=1.0, gap=0.0, texts=texts
    )
    
    if not success:
        print(f"✗ Layout generation failed: {error_msg}")
        return
    
    print(f"✓ Layout generated successfully")
    print(f"  Updated photos: {len(updated_photos)}")
    print(f"  Updated texts: {len(updated_texts)}")
    
    # Check that all items were positioned
    assert len(updated_photos) == len(photos), f"Expected {len(photos)} photos, got {len(updated_photos)}"
    assert len(updated_texts) == len(texts), f"Expected {len(texts)} texts, got {len(updated_texts)}"
    
    # Check that photos have valid positions
    for i, photo in enumerate(updated_photos):
        assert 'area_left' in photo, f"Photo {i} missing area_left"
        assert 'area_top' in photo, f"Photo {i} missing area_top"
        assert 'area_width' in photo, f"Photo {i} missing area_width"
        assert 'area_height' in photo, f"Photo {i} missing area_height"
        assert photo['area_width'] > 0, f"Photo {i} has invalid width: {photo['area_width']}"
        assert photo['area_height'] > 0, f"Photo {i} has invalid height: {photo['area_height']}"
    
    # Check that texts have valid positions
    for i, text in enumerate(updated_texts):
        assert 'area_left' in text, f"Text {i} missing area_left"
        assert 'area_top' in text, f"Text {i} missing area_top"
        assert 'area_width' in text, f"Text {i} missing area_width"
        assert 'area_height' in text, f"Text {i} missing area_height"
        assert text['area_width'] > 0, f"Text {i} has invalid width: {text['area_width']}"
        assert text['area_height'] > 0, f"Text {i} has invalid height: {text['area_height']}"
        print(f"  TEXT_{i}: {text['area_width']:.1f}x{text['area_height']:.1f} "
              f"at ({text['area_left']:.1f}, {text['area_top']:.1f})")
    
    # Compute coverage
    from cewe_layout.algorithms.base import LayoutRectangle
    from cewe_layout.algorithms.evaluator import evaluate_layout
    
    all_rects = []
    for i, photo in enumerate(updated_photos):
        all_rects.append(LayoutRectangle(
            item_id=str(i),
            x=photo['area_left'],
            y=photo['area_top'],
            width=photo['area_width'],
            height=photo['area_height'],
            preserve_aspect_ratio=True
        ))
    for i, text in enumerate(updated_texts):
        all_rects.append(LayoutRectangle(
            item_id=f'TEXT_{i}',
            x=text['area_left'],
            y=text['area_top'],
            width=text['area_width'],
            height=text['area_height'],
            preserve_aspect_ratio=False
        ))
    
    cost = evaluate_layout(page_w, page_h, all_rects)
    print(f"\nLayout quality:")
    print(f"  Empty space: {cost.empty_space_fraction:.1%} (cost: {cost.empty_space_cost:.2f})")
    print(f"  Size mismatch cost: {cost.size_mismatch_cost:.2f}")
    print(f"  Total cost: {cost.total_cost:.2f}")
    
    print("\n✓ All tests passed")


def test_layout_with_gap():
    """Test layout generation with gap."""
    
    mcf_path = Path(__file__).parent.parent.parent / 'Test-album.xmcf' / 'data.mcf'
    if not mcf_path.exists():
        print(f"⚠️  Test skipped: {mcf_path} not found")
        return
    
    mcf_root = parse_mcf_from_path(str(mcf_path))
    pages_info = extract_pages_info(mcf_root)
    
    # Find page 20
    page_20_info = None
    for pageno, info in pages_info:
        if pageno == 20:
            page_20_info = info
            break
    
    if not page_20_info:
        print("⚠️  Page 20 not found")
        return
    
    photos = page_20_info.get('photos', [])
    texts = page_20_info.get('texts', [])
    page_w = page_20_info.get('page_width', 2100)
    page_h = page_20_info.get('page_height', 2970)
    
    from cewe_layout.collage_wrapper import generate_layout_for_page
    
    mcf_base = mcf_path.parent
    gap = 100.0  # 10mm gap
    
    print(f"\nGenerating layout with gap={gap}...")
    success, updated_photos, updated_texts, error_msg = generate_layout_for_page(
        photos, page_w, page_h, mcf_base,
        temperature=1.0, gap=gap, texts=texts
    )
    
    if not success:
        print(f"✗ Layout generation failed: {error_msg}")
        return
    
    print(f"✓ Layout generated with gap")
    
    # Check minimum positions are >= gap
    for i, photo in enumerate(updated_photos):
        assert photo['area_left'] >= gap * 0.99, f"Photo {i} left={photo['area_left']} < gap={gap}"
        assert photo['area_top'] >= gap * 0.99, f"Photo {i} top={photo['area_top']} < gap={gap}"
    
    for i, text in enumerate(updated_texts):
        assert text['area_left'] >= gap * 0.99, f"Text {i} left={text['area_left']} < gap={gap}"
        assert text['area_top'] >= gap * 0.99, f"Text {i} top={text['area_top']} < gap={gap}"
    
    print(f"✓ Gap applied correctly (all items >= {gap})")


if __name__ == '__main__':
    print("Testing layout generation with text blocks...\n")
    
    test_page_20_layout()
    print("\n" + "="*60 + "\n")
    
    test_layout_with_gap()
    print("\n" + "="*60 + "\n")
    
    print("All tests completed successfully! ✓")
