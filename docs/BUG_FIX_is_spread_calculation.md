# Bug Fix: is_spread Calculation Error

## Summary
Fixed a critical bug where `is_spread` was being calculated from page geometry instead of using the GUI's spread mode checkbox value. This caused incorrect centerfold bleed on right-hand pages when using negative edge gaps.

## The Bug

### Symptom
On right-hand pages with negative edge_gap (bleed), photos were bleeding into the centerfold (left edge) when they should only bleed on the top, right, and bottom edges.

### Root Cause
In `collage_wrapper.py` line 76, `is_spread` was calculated as:
```python
is_spread = page_width_mcf > page_height_mcf * 1.5 or (origin_left if origin_left else 0.0) > 0.0
```

This formula incorrectly set `is_spread=True` for ALL right-hand pages (because `origin_left > 0`), even when the user was in single-page mode (`spread_mode=False` in the GUI).

### Impact
When `is_spread=True` (incorrectly):
- The `has_no_left_edge` logic in `transform_item_to_gapfree` and `transform_item_from_gapfree` was bypassed
- This logic prevents centerfold bleed by treating the left edge differently for right-hand pages
- Result: Photos expanded to x=0 in gap-free space would bleed into the centerfold after inverse transformation

## The Fix

### Changes Made

1. **collage_wrapper.py**:
   - Added `is_spread` parameter to `generate_layout_for_page()` function signature
   - Removed the calculated `is_spread` line
   - `is_spread` must now be passed from the caller (GUI or tests)

2. **gui.py**:
   - Updated spread mode call (line ~2823) to pass `is_spread=True`
   - Updated single-page mode call (line ~3129) to pass `is_spread=self.spread_mode.get()`
   - This ensures `is_spread` reflects the actual GUI checkbox state

3. **tests/**:
   - Updated all test calls to `generate_layout_for_page()` to include `is_spread=False`
   - Tests now explicitly declare they're testing single-page layouts

### Design Principle
**`is_spread` should NEVER be calculated from page geometry.**

It represents user intent (viewing/editing mode), not page properties:
- `is_spread=True`: User is viewing/editing two pages side-by-side (spread mode)
- `is_spread=False`: User is viewing/editing a single page

The value comes from the GUI's spread mode checkbox (`self.spread_mode`) and must be passed explicitly to all layout generation functions.

## Verification

### Test Results
- All existing tests pass with the new parameter
- `test_debug_dump_reproduction.py` confirms transformations work correctly:
  - Photos at centerfold stay at centerfold (no bleed)
  - Gap Perfecter expansion to x=0 transforms correctly back to mcf_left=0
  - Round-trip transformations are mathematically correct

### Expected Behavior After Fix
For page 75 (right-hand page) with edge_gap=-3mm in single-page mode:
- ✓ Bleed on top edge (3mm)
- ✓ Bleed on right edge (3mm)
- ✓ Bleed on bottom edge (3mm)
- ✓ NO bleed on left edge (centerfold) - photos stay at or right of centerfold

## Related Code

### Key Functions
- `transform_item_to_gapfree()`: Uses `has_no_left_edge` logic when `is_spread=False`
- `transform_item_from_gapfree()`: Inverse transformation with same logic
- `transform_page_to_gapfree()`: Adjusts page width for centerfold when `is_spread=False`

### Logic Flow
```python
# In transform_item_to_gapfree:
has_no_left_edge = edge_gap < 0 and not is_spread and not is_left_page

# When has_no_left_edge is True:
# - Left edge gap is NOT subtracted (prevents centerfold bleed)
# - Top/right/bottom edges still get gap subtracted (for bleed)
```

## Debugging Tools

### Debug Dump System
When Debug mode is enabled in the GUI:
- `Debug-Page-N.txt` files are created on layout generation
- Captures all parameters: page dimensions, gaps, is_spread, photos, texts
- Can be used to reproduce bugs exactly via `test_debug_dump_reproduction.py`

### How to Use
1. Enable Debug checkbox in GUI
2. Navigate to problem page
3. Set edge gap
4. Generate layout
5. Check `tests/Debug-Page-N.txt`
6. Run `pytest tests/test_debug_dump_reproduction.py -v -s`

## Lessons Learned

1. **Never calculate user intent from data**: `is_spread` is user intent, not a property of the page
2. **Explicit is better than implicit**: Passing `is_spread` explicitly prevents errors
3. **Separation of concerns**: Algorithms should never know about MCF concepts like centerfold, origin_left, or spread mode
4. **Test with real data**: The debug dump system was essential for reproducing and understanding the bug
