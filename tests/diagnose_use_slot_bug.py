"""
Diagnostic script to demonstrate the use_slot checkbox bug.

This simulates the logic flow in collage_wrapper._photos_to_rectangles
to show that use_slot=False still results in slot dimensions being used.
"""

def simulate_dimension_selection_buggy(use_slot, has_custom_aspect, slot_width, slot_height, img_width, img_height):
    """Simulate the OLD (buggy) logic."""
    rect_width = None
    rect_height = None
    internal_gap = 0.0
    
    # Old buggy logic from collage_wrapper.py
    if use_slot:
        # User wants slot aspect ratio
        if has_custom_aspect:
            # Would use custom aspect ratio here
            pass
    
    # BUG: This fallback happens even when use_slot=False!
    if rect_width is None or rect_height is None:
        if slot_width > 0 and slot_height > 0:
            rect_width = float(slot_width) + internal_gap
            rect_height = float(slot_height) + internal_gap
    
    # Only reach here if slot dimensions were invalid
    if rect_width is None or rect_height is None:
        rect_width = float(img_width)
        rect_height = float(img_height)
    
    return rect_width, rect_height


def simulate_dimension_selection_fixed(use_slot, has_custom_aspect, slot_width, slot_height, img_width, img_height):
    """Simulate the FIXED logic."""
    rect_width = None
    rect_height = None
    internal_gap = 0.0
    
    # Fixed logic from collage_wrapper.py
    if use_slot:
        # User wants slot aspect ratio
        if has_custom_aspect:
            # Would use custom aspect ratio here
            pass
        
        # If custom aspect calculation failed or not provided, use current slot dimensions
        if rect_width is None or rect_height is None:
            if slot_width > 0 and slot_height > 0:
                rect_width = float(slot_width) + internal_gap
                rect_height = float(slot_height) + internal_gap
    else:
        # User wants photo's natural aspect ratio (use_slot = False)
        rect_width = float(img_width)
        rect_height = float(img_height)
    
    # Final fallback: if still no dimensions, use image file dimensions
    if rect_width is None or rect_height is None:
        rect_width = float(img_width)
        rect_height = float(img_height)
    
    return rect_width, rect_height


def test_use_slot_bug():
    """Test case showing the bug and the fix."""
    print("=" * 60)
    print("DEMONSTRATING THE USE_SLOT BUG AND FIX")
    print("=" * 60)
    
    # Test case: Photo with aspect ratio 1.5 (3:2), slot with aspect ratio 0.8 (4:5)
    img_width, img_height = 3000, 2000  # Image AR = 1.5
    slot_width, slot_height = 400, 500  # Slot AR = 0.8
    
    print(f"\nImage dimensions: {img_width} x {img_height} (AR = {img_width/img_height:.2f})")
    print(f"Slot dimensions:  {slot_width} x {slot_height} (AR = {slot_width/slot_height:.2f})")
    
    print("\n" + "=" * 60)
    print("OLD (BUGGY) LOGIC:")
    print("=" * 60)
    
    # Case 1: use_slot = True (checkbox ticked) - EXPECTED: use slot AR
    print("\n--- Case 1: use_slot = True (checkbox TICKED) ---")
    w, h = simulate_dimension_selection_buggy(True, False, slot_width, slot_height, img_width, img_height)
    print(f"Result: {w} x {h} (AR = {w/h:.2f})")
    print(f"✓ Correct: Using slot aspect ratio")
    
    # Case 2: use_slot = False (checkbox unticked) - EXPECTED: use image AR
    print("\n--- Case 2: use_slot = False (checkbox UNTICKED) ---")
    w, h = simulate_dimension_selection_buggy(False, False, slot_width, slot_height, img_width, img_height)
    print(f"Result: {w} x {h} (AR = {w/h:.2f})")
    if abs(w/h - slot_width/slot_height) < 0.01:
        print(f"✗ BUG: Using slot aspect ratio ({w/h:.2f}) instead of image AR ({img_width/img_height:.2f})")
    else:
        print(f"✓ Correct: Using image aspect ratio")
    
    print("\n" + "=" * 60)
    print("NEW (FIXED) LOGIC:")
    print("=" * 60)
    
    # Case 1: use_slot = True (checkbox ticked) - EXPECTED: use slot AR
    print("\n--- Case 1: use_slot = True (checkbox TICKED) ---")
    w, h = simulate_dimension_selection_fixed(True, False, slot_width, slot_height, img_width, img_height)
    print(f"Result: {w} x {h} (AR = {w/h:.2f})")
    if abs(w/h - slot_width/slot_height) < 0.01:
        print(f"✓ Correct: Using slot aspect ratio")
    else:
        print(f"✗ BUG: Should be using slot aspect ratio")
    
    # Case 2: use_slot = False (checkbox unticked) - EXPECTED: use image AR
    print("\n--- Case 2: use_slot = False (checkbox UNTICKED) ---")
    w, h = simulate_dimension_selection_fixed(False, False, slot_width, slot_height, img_width, img_height)
    print(f"Result: {w} x {h} (AR = {w/h:.2f})")
    if abs(w/h - img_width/img_height) < 0.01:
        print(f"✓ FIXED: Now using image aspect ratio")
    else:
        print(f"✗ Still broken: Should be using image aspect ratio")
    
    print("\n" + "=" * 60)
    print("ROOT CAUSE (OLD BUG):")
    print("=" * 60)
    print("When use_slot=False, the code skipped the 'if use_slot:' block,")
    print("leaving rect_width=None and rect_height=None.")
    print("It then fell through to the 'if rect_width is None' block")
    print("which always used slot dimensions as a 'fallback'.")
    print("The image dimensions code was never reached!")
    print("\n" + "=" * 60)
    print("FIX:")
    print("=" * 60)
    print("Added an 'else:' clause to the 'if use_slot:' block.")
    print("When use_slot=False, it now explicitly uses image dimensions.")
    print("The final fallback only catches truly unexpected edge cases.")
    print("=" * 60)


if __name__ == '__main__':
    test_use_slot_bug()
