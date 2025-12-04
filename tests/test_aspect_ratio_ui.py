"""Test aspect ratio UI controls functionality."""

import math


def test_slot_aspect_ratio_calculation():
    """Test that custom aspect ratios are correctly calculated from area."""
    # Simulate a slot with area 1000x500 (aspect ratio 2.0)
    slot_width = 1000.0
    slot_height = 500.0
    internal_gap = 10.0
    
    # Gap-free area
    slot_area = (slot_width + internal_gap) * (slot_height + internal_gap)
    
    # User wants aspect ratio 1.5 instead of 2.0
    custom_aspect = 1.5
    
    # Calculate new dimensions
    rect_width = math.sqrt(slot_area * custom_aspect)
    rect_height = math.sqrt(slot_area / custom_aspect)
    
    print(f"Original slot: {slot_width} x {slot_height} (AR = {slot_width/slot_height:.2f})")
    print(f"Gap-free area: {slot_area:.1f}")
    print(f"Custom aspect ratio: {custom_aspect}")
    print(f"New dimensions: {rect_width:.1f} x {rect_height:.1f}")
    print(f"New aspect ratio: {rect_width/rect_height:.2f}")
    print(f"New area: {rect_width * rect_height:.1f}")
    
    # Verify aspect ratio is correct
    assert abs((rect_width / rect_height) - custom_aspect) < 0.01, "Aspect ratio calculation is incorrect"
    
    # Verify area is preserved
    assert abs((rect_width * rect_height) - slot_area) < 1.0, "Area is not preserved"
    
    print("✓ Aspect ratio calculation test passed")


def test_aspect_ratio_bounds():
    """Test that aspect ratio validation works."""
    
    def validate_aspect_ratio(ar_str):
        """Simulate the validation logic."""
        try:
            new_aspect = float(ar_str)
            if 0.1 <= new_aspect <= 10.0:
                return True, new_aspect
            return False, None
        except ValueError:
            return False, None
    
    # Valid cases
    valid, ar = validate_aspect_ratio("1.5")
    assert valid and ar == 1.5
    
    valid, ar = validate_aspect_ratio("0.5")
    assert valid and ar == 0.5
    
    valid, ar = validate_aspect_ratio("3.0")
    assert valid and ar == 3.0
    
    # Edge cases
    valid, ar = validate_aspect_ratio("0.1")
    assert valid and ar == 0.1
    
    valid, ar = validate_aspect_ratio("10.0")
    assert valid and ar == 10.0
    
    # Invalid cases
    valid, ar = validate_aspect_ratio("0.05")
    assert not valid
    
    valid, ar = validate_aspect_ratio("15.0")
    assert not valid
    
    valid, ar = validate_aspect_ratio("abc")
    assert not valid
    
    print("✓ Aspect ratio validation test passed")


if __name__ == '__main__':
    test_slot_aspect_ratio_calculation()
    test_aspect_ratio_bounds()
    print("\n✅ All aspect ratio UI tests passed!")
