# Aspect Ratio UI Enhancement - Implementation Summary

## Overview
Enhanced the Controls window to provide granular aspect ratio controls for photos and text blocks, allowing users to view and edit both slot and photo aspect ratios independently.

## Changes Made

### 1. GUI Column Headers (gui.py, lines ~239-258)
**Before:** Single "Slot AR" checkbox column
**After:** "Aspect Ratio" header with three sub-columns:
- "Slot" - editable aspect ratio for the slot/box (2 decimal places)
- "Photo" - read-only aspect ratio from the image file (2 decimal places, empty for text blocks)
- "Use slot" - checkbox to toggle between using slot AR or photo AR

### 2. Data Storage (gui.py, lines ~52-58)
Added new instance variable to track custom slot aspect ratios:
```python
self.slot_aspect_ratios = {}  # {(pageno, item_idx): aspect_ratio}
```

### 3. Row Display Logic (gui.py, lines ~1110-1240)
Complete rewrite of the item row creation in `update_weights_display()`:

**For Photos:**
- Column 1: Editable slot aspect ratio (Entry widget)
- Column 2: Read-only photo aspect ratio from image dimensions (Label)
- Column 3: Checkbox to choose which AR to use (auto-checked if photo/slot differ >30%)

**For Text Blocks:**
- Column 1: Editable slot aspect ratio (Entry widget)
- Column 2: Empty (no native image aspect ratio for text)
- Column 3: Checkbox always checked and disabled (text always uses slot AR)

### 4. Event Handlers (gui.py, lines ~1250-1270)
Added new handler for slot aspect ratio changes:
```python
def on_slot_aspect_changed(self, pageno, item_idx, var):
    """Store custom aspect ratio (validates 0.1 to 10.0 range)"""
```

### 5. Layout Generation Integration (gui.py, lines ~1607-1620)
Modified `generate_layout()` to:
- Collect custom slot aspect ratios for all items on the current page
- Pass them to `generate_layout_for_page()` via new `slot_aspect_ratios` parameter

### 6. Collage Wrapper API Extension (collage_wrapper.py)
**Function Signature:**
```python
def generate_layout_for_page(..., slot_aspect_ratios=None, ...)
```

**New Parameter:**
- `slot_aspect_ratios`: Dict mapping item_idx -> custom aspect ratio value

**Propagated to:**
- `_photos_to_rectangles(..., slot_aspect_ratios=None, ...)`

### 7. Custom Aspect Ratio Logic (collage_wrapper.py, lines ~200-225)
When `use_slot=True` and custom aspect ratio is provided:
1. Calculate area from original slot dimensions (gap-free space)
2. Compute new width/height from: `w = sqrt(area × AR)`, `h = sqrt(area / AR)`
3. This preserves area while applying the custom aspect ratio

**Fallback behavior:** If no custom AR, uses original slot dimensions as before.

## How It Works

### User Workflow:
1. User sees current slot AR and photo AR in the Controls window
2. User can edit the slot AR value (e.g., change from 1.33 to 1.50)
3. User ensures "Use slot" checkbox is ticked (for photos)
4. User clicks "Generate Layout"
5. Algorithm receives rectangles with the custom aspect ratio but same area as original slot

### Algorithm Integration:
- When checkbox is ticked: algorithm uses custom slot AR (or original slot dimensions if not customized)
- When checkbox is unticked: algorithm uses photo's native image AR
- Text blocks always use slot AR (checkbox disabled)

## Testing Considerations

### Manual Testing Checklist:
- [ ] Open a page with multiple photos
- [ ] Verify slot and photo AR columns show correct values (2 decimal places)
- [ ] Edit a slot AR value and press Enter
- [ ] Toggle "Use slot" checkbox and verify layout generation respects it
- [ ] Verify text blocks show empty photo AR column
- [ ] Verify text block checkbox is always checked and disabled
- [ ] Generate layout and verify custom ARs are applied correctly

### Edge Cases Handled:
- Invalid aspect ratio input (non-numeric, out of range) - silently ignored
- Missing photo dimensions - falls back to defaults or shows "--"
- Text blocks - always use slot AR, no photo AR column
- TreeBuilder/Gridify algorithms - force slot AR for all items (unchanged behavior)

## Future Enhancements (Optional)
1. Add visual indicator when slot AR differs from photo AR
2. Add button to reset slot AR to photo AR
3. Show warning if custom AR would cause extreme distortion
4. Persist custom ARs in layout manager for undo/redo

## Files Modified
1. `/cewe-layout/cewe_layout/gui.py` - UI and interaction logic
2. `/cewe-layout/cewe_layout/collage_wrapper.py` - Layout generation API
3. `/cewe-layout/tests/test_aspect_ratio_ui.py` - New test file (created)

## Compatibility Notes
- Backward compatible: existing code paths unchanged when `slot_aspect_ratios` is not provided
- No changes to MCF file format or persistence
- Custom ARs are session-only (not saved to file)
