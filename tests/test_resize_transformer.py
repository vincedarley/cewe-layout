"""Test ResizeTransformer coordinate transformations."""

import sys
from pathlib import Path

# Add parent directory to path to import cewe_layout
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.book.utils import ResizeTransformer


def test_transform_rect_none_mode():
    """Test 'None' mode - no scaling, just placement."""
    # XXL (3820 x 2900) to XL (2700 x 2050)
    transformer = ResizeTransformer(3820, 2900, 2700, 2050, 'None', bleed_mm=3)
    
    # Photo at (100, 100) size (500, 400) - should stay same position/size
    result = transformer.transform_rect(100, 100, 500, 400, origin_left=0)
    print(f"None mode - left page photo:")
    print(f"  Input:  (100, 100, 500, 400)")
    print(f"  Output: {result}")
    assert result is not None
    left, top, width, height = result
    assert left == 100  # Same position
    assert top == 100
    assert width == 500  # Same size
    assert height == 400
    
    # Photo that starts within bounds but extends beyond should still be returned
    # (it will be clipped when rendered, but we return the transformed coordinates)
    result = transformer.transform_rect(2400, 100, 500, 400, origin_left=0)
    print(f"\nNone mode - photo partially extending beyond right edge:")
    print(f"  New page width: 2700 (content area: 2640 with 30 bleed)")
    print(f"  Input:  (2400, 100, 500, 400)")
    print(f"  Output: {result}")
    # Should return (starts at 2400, within content area of 2640)
    assert result is not None


def test_transform_rect_center_mode():
    """Test 'None (center on page)' mode."""
    # L (1900 x 1480) to XXL (3820 x 2900)
    transformer = ResizeTransformer(1900, 1480, 3820, 2900, 'None (center on page)', bleed_mm=3)
    
    # Photo at (100, 100) size (500, 400)
    # Should be offset by centering amount
    result = transformer.transform_rect(100, 100, 500, 400, origin_left=0)
    print(f"\nCenter mode - left page photo (small to large):")
    print(f"  Old page: 1900 x 1480, New page: 3820 x 2900")
    print(f"  Input:  (100, 100, 500, 400)")
    print(f"  Output: {result}")
    assert result is not None
    left, top, width, height = result
    # Width difference: (3820 - 2*30) - (1900 - 2*30) = 3760 - 1840 = 1920
    # Offset: 1920 / 2 = 960
    # Expected left: 100 + 960 = 1060
    print(f"  Expected left: ~1060 (100 + 960 offset)")
    assert abs(left - 1060) < 5  # Allow small rounding difference
    assert width == 500  # Size unchanged


def test_transform_rect_fit_mode():
    """Test 'Fit (may have margins)' mode - uniform scaling."""
    # XXL (3820 x 2900) to XL (2700 x 2050)
    transformer = ResizeTransformer(3820, 2900, 2700, 2050, 'Fit (may have margins)', bleed_mm=3)
    
    # Photo at (100, 100) size (500, 400)
    result = transformer.transform_rect(100, 100, 500, 400, origin_left=0)
    print(f"\nFit mode - uniform scaling:")
    print(f"  Old page: 3820 x 2900, New page: 2700 x 2050")
    print(f"  Input:  (100, 100, 500, 400)")
    print(f"  Output: {result}")
    assert result is not None
    left, top, width, height = result
    # Scale should be min of width/height ratios
    # Content area old: (3820 - 60) x (2900 - 60) = 3760 x 2840
    # Content area new: (2700 - 60) x (2050 - 60) = 2640 x 1990
    # Scale: min(2640/3760, 1990/2840) = min(0.7021, 0.7007) ≈ 0.7007
    expected_scale = 2640 / 3760  # Tighter dimension
    print(f"  Expected scale: ~{expected_scale:.4f}")
    print(f"  Expected width: ~{500 * expected_scale:.1f}")
    assert abs(width - 500 * expected_scale) < 5


def test_transform_rect_fill_mode():
    """Test 'Fill (crop to avoid margins)' mode."""
    # L (1900 x 1480) to XXL (3820 x 2900)
    transformer = ResizeTransformer(1900, 1480, 3820, 2900, 'Fill (crop to avoid margins)', bleed_mm=3)
    
    # Photo at (100, 100) size (500, 400)
    result = transformer.transform_rect(100, 100, 500, 400, origin_left=0)
    print(f"\nFill (crop) mode - uniform scaling with potential crop:")
    print(f"  Old page: 1900 x 1480, New page: 3820 x 2900")
    print(f"  Input:  (100, 100, 500, 400)")
    print(f"  Output: {result}")
    assert result is not None
    left, top, width, height = result
    # Scale should be max of width/height ratios
    # Content area old: (1900 - 60) x (1480 - 60) = 1840 x 1420
    # Content area new: (3820 - 60) x (2900 - 60) = 3760 x 2840
    # Scale: max(3760/1840, 2840/1420) = max(2.0435, 2.0) ≈ 2.0435
    expected_scale = 3760 / 1840  # Looser dimension
    print(f"  Expected scale: ~{expected_scale:.4f}")
    print(f"  Expected width: ~{500 * expected_scale:.1f}")
    assert abs(width - 500 * expected_scale) < 5


def test_transform_rect_stretch_mode():
    """Test 'Fill (may change aspect ratio)' mode."""
    # Square (3000 x 3000) to Wide (4000 x 2000)
    transformer = ResizeTransformer(3000, 3000, 4000, 2000, 'Fill (may change aspect ratio)', bleed_mm=0)
    
    # Square photo at (500, 500) size (1000, 1000)
    result = transformer.transform_rect(500, 500, 1000, 1000, origin_left=0)
    print(f"\nFill (stretch) mode - independent scaling:")
    print(f"  Old page: 3000 x 3000, New page: 4000 x 2000")
    print(f"  Input:  (500, 500, 1000, 1000)")
    print(f"  Output: {result}")
    assert result is not None
    left, top, width, height = result
    # Scale X: 4000/3000 = 1.333
    # Scale Y: 2000/3000 = 0.667
    # Expected: left ≈ 500*1.333 = 667, top ≈ 500*0.667 = 333
    #           width ≈ 1000*1.333 = 1333, height ≈ 1000*0.667 = 667
    print(f"  Expected: left≈667, top≈333, width≈1333, height≈667")
    assert abs(left - 667) < 10
    assert abs(top - 333) < 10
    assert abs(width - 1333) < 10
    assert abs(height - 667) < 10


def test_transform_origin_left():
    """Test origin_left transformation for right pages."""
    transformer = ResizeTransformer(3820, 2900, 2700, 2050, 'None', bleed_mm=3)
    
    # Left page (origin_left = 0)
    assert transformer.transform_origin_left(0) == 0
    
    # Right page (origin_left = old page width)
    result = transformer.transform_origin_left(3820)
    print(f"\nOrigin left transform:")
    print(f"  Old page width: 3820")
    print(f"  New page width: 2700")
    print(f"  Input origin_left: 3820")
    print(f"  Output origin_left: {result}")
    assert result == 2700  # Should be new page width


def test_transform_right_page_photo():
    """Test photo on right page with origin_left."""
    transformer = ResizeTransformer(3820, 2900, 2700, 2050, 'None (center on page)', bleed_mm=3)
    
    # Right page: origin_left = 3820
    # Photo in spread coordinates: left = 4000 (i.e., 180 pixels into right page)
    # After transform, should maintain page-relative position but with new origin_left
    
    result = transformer.transform_rect(4000, 100, 500, 400, origin_left=3820)
    print(f"\nRight page photo (center mode):")
    print(f"  Old origin_left: 3820")
    print(f"  New origin_left: 2700")
    print(f"  Input:  (4000, 100, 500, 400) in spread coords")
    print(f"  Output: {result}")
    assert result is not None
    left, top, width, height = result
    # Page-relative position: 4000 - 3820 = 180
    # After centering offset and new origin: should be around 2700 + centered_180
    print(f"  Page-relative input: {4000 - 3820} = 180")
    print(f"  Output in spread coords: {left}")


def test_cropping_detection():
    """Test that rectangles completely outside bounds return None."""
    # XXL to L (downsize significantly)
    transformer = ResizeTransformer(3820, 2900, 1900, 1480, 'None', bleed_mm=3)
    
    # Photo way off the right edge
    result = transformer.transform_rect(5000, 100, 500, 400, origin_left=0)
    print(f"\nCropping detection:")
    print(f"  Old page: 3820 x 2900, New page: 1900 x 1480")
    print(f"  Photo at x=5000 (far beyond new page bounds)")
    print(f"  Result: {result}")
    assert result is None  # Should be cropped out


def test_page_dimensions():
    """Test page dimension transformation."""
    transformer = ResizeTransformer(3820, 2900, 2700, 2050, 'Fit (may have margins)', bleed_mm=3)
    
    width, height = transformer.transform_page_dimensions()
    print(f"\nPage dimensions:")
    print(f"  Input:  3820 x 2900")
    print(f"  Output: {width} x {height}")
    assert width == 2700
    assert height == 2050


if __name__ == '__main__':
    print("="*80)
    print("Testing ResizeTransformer")
    print("="*80)
    
    test_transform_rect_none_mode()
    test_transform_rect_center_mode()
    test_transform_rect_fit_mode()
    test_transform_rect_fill_mode()
    test_transform_rect_stretch_mode()
    test_transform_origin_left()
    test_transform_right_page_photo()
    test_cropping_detection()
    test_page_dimensions()
    
    print("\n" + "="*80)
    print("All tests passed!")
    print("="*80)
