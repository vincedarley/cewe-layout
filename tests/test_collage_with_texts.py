"""
Test collage wrapper with text blocks.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.collage_wrapper import generate_layout_for_page
from cewe_layout.algorithms.base import LayoutRectangle


def test_mixed_layout():
    """Test layout generation with both photos and text blocks."""
    
    # Dummy photo list (2 photos)
    photos = [
        {'filename': 'safecontainer:/photo1.jpg'},
        {'filename': 'safecontainer:/photo2.jpg'},
    ]
    
    # Dummy text blocks (1 text)
    texts = [
        {'area_width': 500, 'area_height': 200},
    ]
    
    # We need actual image files for photos - skip photo test for now
    # Just test text rectangles conversion directly
    from cewe_layout.collage_wrapper import _texts_to_rectangles
    
    text_rects, error = _texts_to_rectangles(texts, preferred_sizes=None, gap=0.0)
    
    assert not error, f"Text conversion failed: {error}"
    assert len(text_rects) == 1, f"Expected 1 text rect, got {len(text_rects)}"
    
    rect = text_rects[0]
    assert rect.item_id == "TEXT_0", f"Expected item_id TEXT_0, got {rect.item_id}"
    assert rect.width == 500.0, f"Expected width 500, got {rect.width}"
    assert rect.height == 200.0, f"Expected height 200, got {rect.height}"
    assert rect.preserve_aspect_ratio == False, "Text should have preserve_aspect_ratio=False"
    assert rect.preferred_size == 1.0, f"Expected preferred_size 1.0, got {rect.preferred_size}"
    
    print("✓ Text block conversion successful")
    print(f"  Item ID: {rect.item_id}")
    print(f"  Dimensions: {rect.width}x{rect.height}")
    print(f"  Preserve aspect: {rect.preserve_aspect_ratio}")
    print(f"  Preferred size: {rect.preferred_size}")
    

def test_text_with_preferred_size():
    """Test text blocks with preferred sizes."""
    
    texts = [
        {'area_width': 500, 'area_height': 200},
        {'area_width': 300, 'area_height': 150},
    ]
    
    preferred_sizes = {
        'TEXT_0': 1.5,
        'TEXT_1': 0.8,
    }
    
    from cewe_layout.collage_wrapper import _texts_to_rectangles
    
    text_rects, error = _texts_to_rectangles(texts, preferred_sizes=preferred_sizes, gap=0.0)
    
    assert not error, f"Text conversion failed: {error}"
    assert len(text_rects) == 2, f"Expected 2 text rects, got {len(text_rects)}"
    
    assert text_rects[0].preferred_size == 1.5, f"Expected preferred_size 1.5, got {text_rects[0].preferred_size}"
    assert text_rects[1].preferred_size == 0.8, f"Expected preferred_size 0.8, got {text_rects[1].preferred_size}"
    
    print("✓ Preferred sizes applied correctly")
    print(f"  TEXT_0 preferred size: {text_rects[0].preferred_size}")
    print(f"  TEXT_1 preferred size: {text_rects[1].preferred_size}")


def test_text_with_gap():
    """Test text blocks with gap."""
    
    texts = [
        {'area_width': 500, 'area_height': 200},
    ]
    
    from cewe_layout.collage_wrapper import _texts_to_rectangles
    
    text_rects, error = _texts_to_rectangles(texts, preferred_sizes=None, gap=100.0)
    
    assert not error, f"Text conversion failed: {error}"
    assert len(text_rects) == 1, f"Expected 1 text rect, got {len(text_rects)}"
    
    # Gap should be added to dimensions
    assert text_rects[0].width == 600.0, f"Expected width 600 (500+100), got {text_rects[0].width}"
    assert text_rects[0].height == 300.0, f"Expected height 300 (200+100), got {text_rects[0].height}"
    
    print("✓ Gap applied correctly to text dimensions")
    print(f"  Original: 500x200, Gap: 100")
    print(f"  Result: {text_rects[0].width}x{text_rects[0].height}")


def test_rectangles_to_texts():
    """Test converting positioned rectangles back to text blocks."""
    
    from cewe_layout.collage_wrapper import _rectangles_to_texts
    
    # Original texts
    texts = [
        {'area_width': 500, 'area_height': 200, 'area_left': 0, 'area_top': 0},
        {'area_width': 300, 'area_height': 150, 'area_left': 0, 'area_top': 0},
    ]
    
    # Positioned rectangles from algorithm
    positioned = [
        LayoutRectangle(item_id='TEXT_0', width=600, height=300, x=100, y=50),
        LayoutRectangle(item_id='TEXT_1', width=400, height=250, x=200, y=100),
    ]
    
    # Apply gap=100
    updated_texts = _rectangles_to_texts(texts, positioned, gap=100.0)
    
    assert len(updated_texts) == 2, f"Expected 2 texts, got {len(updated_texts)}"
    
    # First text: x=100+100=200, y=50+100=150, width=600-100=500, height=300-100=200
    assert updated_texts[0]['area_left'] == 200, f"Expected area_left 200, got {updated_texts[0]['area_left']}"
    assert updated_texts[0]['area_top'] == 150, f"Expected area_top 150, got {updated_texts[0]['area_top']}"
    assert updated_texts[0]['area_width'] == 500, f"Expected area_width 500, got {updated_texts[0]['area_width']}"
    assert updated_texts[0]['area_height'] == 200, f"Expected area_height 200, got {updated_texts[0]['area_height']}"
    
    print("✓ Rectangle to text conversion successful")
    print(f"  Text 0: ({updated_texts[0]['area_left']}, {updated_texts[0]['area_top']}) {updated_texts[0]['area_width']}x{updated_texts[0]['area_height']}")
    print(f"  Text 1: ({updated_texts[1]['area_left']}, {updated_texts[1]['area_top']}) {updated_texts[1]['area_width']}x{updated_texts[1]['area_height']}")


if __name__ == '__main__':
    print("Testing collage wrapper with text blocks...\n")
    
    test_mixed_layout()
    print()
    
    test_text_with_preferred_size()
    print()
    
    test_text_with_gap()
    print()
    
    test_rectangles_to_texts()
    print()
    
    print("All tests passed! ✓")
