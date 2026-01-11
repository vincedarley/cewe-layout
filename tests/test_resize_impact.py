"""Test resize impact calculations for different scenarios."""

import sys
from pathlib import Path

# Add parent directory to path to import cewe_layout
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.book.utils import calculate_resize_impact


def print_impact(title, old_w, old_h, new_w, new_h, scaling_rule, bleed_mm=0):
    """Print the impact of a resize operation."""
    print(f"\n{'='*80}")
    print(f"{title}")
    print(f"{'='*80}")
    print(f"Old size: {old_w/10:.1f} cm × {old_h/10:.1f} cm (aspect: {old_w/old_h:.3f})")
    print(f"New size: {new_w/10:.1f} cm × {new_h/10:.1f} cm (aspect: {new_w/new_h:.3f})")
    print(f"Scaling rule: {scaling_rule}")
    print(f"Bleed: {bleed_mm} mm")
    
    result = calculate_resize_impact(old_w, old_h, new_w, new_h, scaling_rule, bleed_mm)
    
    print(f"\nScaling factors:")
    print(f"  X: {result['scale_x']:.4f} ({result['scale_x']*100:.1f}%)")
    print(f"  Y: {result['scale_y']:.4f} ({result['scale_y']*100:.1f}%)")
    
    print(f"\nCropping (mm):")
    print(f"  Left:   {result['crop_left_mm']:.2f}")
    print(f"  Right:  {result['crop_right_mm']:.2f}")
    print(f"  Top:    {result['crop_top_mm']:.2f}")
    print(f"  Bottom: {result['crop_bottom_mm']:.2f}")
    total_crop = sum([result['crop_left_mm'], result['crop_right_mm'], 
                     result['crop_top_mm'], result['crop_bottom_mm']])
    print(f"  Total:  {total_crop:.2f}")
    
    print(f"\nMargins (mm):")
    print(f"  Left:   {result['margin_left_mm']:.2f}")
    print(f"  Right:  {result['margin_right_mm']:.2f}")
    print(f"  Top:    {result['margin_top_mm']:.2f}")
    print(f"  Bottom: {result['margin_bottom_mm']:.2f}")
    total_margin = sum([result['margin_left_mm'], result['margin_right_mm'],
                       result['margin_top_mm'], result['margin_bottom_mm']])
    print(f"  Total:  {total_margin:.2f}")
    
    print(f"\nAspect ratio change: {result['aspect_ratio_change_pct']:+.2f}%")
    print(f"Estimated photo crop: {result['photo_crop_pct']:.2f}%")


def run_tests():
    """Run a series of test cases."""
    
    # Test case 1: XXL landscape (38.2 × 29.0) to XL landscape (27.0 × 20.5)
    # Getting narrower/smaller
    print("\n" + "█"*80)
    print("TEST CASE 1: XXL landscape → XL landscape (smaller, slightly different aspect)")
    print("█"*80)
    
    xxl_w = 3820  # 38.2 cm (single page width from 7640 spread)
    xxl_h = 2900  # 29.0 cm
    xl_w = 2700   # 27.0 cm (single page width from 5400 spread)
    xl_h = 2050   # 20.5 cm
    
    for bleed in [0, 3]:
        for rule in ['None', 'None (center on page)', 'Fit (may have margins)', 
                     'Fill (crop to avoid margins)', 'Fill (may change aspect ratio)']:
            print_impact(f"Test 1 - {rule} (bleed={bleed}mm)", 
                        xxl_w, xxl_h, xl_w, xl_h, rule, bleed)
    
    # Test case 2: L landscape (19.0 × 14.8) to XXL landscape (38.2 × 29.0)
    # Getting wider/larger
    print("\n" + "█"*80)
    print("TEST CASE 2: L landscape → XXL landscape (larger, slightly different aspect)")
    print("█"*80)
    
    l_w = 1900  # 19.0 cm (single page width from 3800 spread)
    l_h = 1480  # 14.8 cm
    
    for bleed in [0, 3]:
        for rule in ['None', 'None (center on page)', 'Fit (may have margins)', 
                     'Fill (crop to avoid margins)', 'Fill (may change aspect ratio)']:
            print_impact(f"Test 2 - {rule} (bleed={bleed}mm)", 
                        l_w, l_h, xxl_w, xxl_h, rule, bleed)
    
    # Test case 3: XXL landscape to same size (no change)
    print("\n" + "█"*80)
    print("TEST CASE 3: XXL landscape → XXL landscape (no change)")
    print("█"*80)
    
    for bleed in [0, 3]:
        for rule in ['None', 'Fit (may have margins)']:  # Just test a couple
            print_impact(f"Test 3 - {rule} (bleed={bleed}mm)", 
                        xxl_w, xxl_h, xxl_w, xxl_h, rule, bleed)
    
    # Test case 4: Square to wide rectangle (major aspect ratio change)
    print("\n" + "█"*80)
    print("TEST CASE 4: Square (30×30) → Wide rectangle (40×20) (major aspect change)")
    print("█"*80)
    
    square_w = 3000
    square_h = 3000
    wide_w = 4000
    wide_h = 2000
    
    for bleed in [0]:  # Just no bleed for this test
        for rule in ['None (center on page)', 'Fit (may have margins)', 
                     'Fill (crop to avoid margins)', 'Fill (may change aspect ratio)']:
            print_impact(f"Test 4 - {rule}", 
                        square_w, square_h, wide_w, wide_h, rule, bleed)
    
    # Test case 5: Wide to tall (aspect ratio flip)
    print("\n" + "█"*80)
    print("TEST CASE 5: Wide (40×20) → Tall (20×40) (aspect ratio flip)")
    print("█"*80)
    
    tall_w = 2000
    tall_h = 4000
    
    for bleed in [0]:  # Just no bleed
        for rule in ['None (center on page)', 'Fit (may have margins)', 
                     'Fill (crop to avoid margins)']:
            print_impact(f"Test 5 - {rule}", 
                        wide_w, wide_h, tall_w, tall_h, rule, bleed)


if __name__ == '__main__':
    run_tests()
