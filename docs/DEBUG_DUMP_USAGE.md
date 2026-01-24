# Debug Dump System

## Overview

The debug dump system allows you to capture all parameters used during layout generation and reproduce the exact same transformation pipeline in a test case.

## How to Generate a Debug Dump

1. **Run the GUI:**
   ```bash
   python ./cewe-layout/run_qlayout.py --cewe ./Test-album.xmcf --gui
   ```

2. **Navigate to the problem page** (e.g., page 75)

3. **Enable Debug Mode:**
   - Check the "Debug" checkbox in the GUI

4. **Set your parameters:**
   - Edge gap (e.g., -3 for 3mm bleed)
   - Internal gap
   - Select algorithm

5. **Click "Generate Layout"**

6. **Find the debug dump:**
   - A file named `Debug-Page-N.txt` will be created in the current directory
   - Terminal will show: `Debug dump written to Debug-Page-N.txt`

## Debug Dump File Contents

The debug dump contains:

```
Debug Dump for Page 75
================================================================================

PAGE PROPERTIES:
  page_width: 2000
  page_height: 2400
  origin_left: 2000.0
  is_left_page: False
  spread_mode: False

GAP PARAMETERS:
  edge_gap: -30 (-3.0mm)
  internal_gap: 90 (9.0mm)

ALGORITHM:
  name: Gap Perfecter

PHOTOS (6 total):
  Photo 0:
    filename: DSC_1234.JPG
    area_left: 2000.0
    area_top: 0.0
    area_width: 500.0
    area_height: 600.0
    preferred_size: 1.5
    use_slot_aspect: False

  ...

TEXTS (1 total):
  Text 0:
    area_left: 2500.0
    area_top: 1200.0
    area_width: 400.0
    area_height: 200.0
    preferred_size: 1.0

To reproduce in test:
1. Transform items to gap-free coordinates using transform_item_to_gapfree()
2. Transform page dimensions using transform_page_to_gapfree()
3. Run algorithm
4. Transform results back using transform_item_from_gapfree()
```

## Using the Debug Dump in Tests

### Automatic Test

Run the provided test that automatically parses the most recent debug dump:

```bash
cd cewe-layout
pytest tests/test_debug_dump_reproduction.py -v
```

This test will:
1. Parse the debug dump file
2. Transform items to gap-free coordinates
3. Validate the transformations
4. Check for centerfold bleed issues on right pages

### Manual Reproduction

```python
from cewe_layout.utils.gap_utils import (
    transform_item_to_gapfree,
    transform_item_from_gapfree,
    transform_page_to_gapfree
)

# From debug dump
page_w = 2000
page_h = 2400
origin_left = 2000.0
is_left_page = False
edge_gap = -30.0
internal_gap = 90.0

# Photo from debug dump
photo_mcf_left = 2000.0
photo_top = 0.0
photo_width = 500.0
photo_height = 600.0

# Convert to page-relative
photo_page_left = photo_mcf_left - origin_left  # = 0.0

# Transform to gap-free
gf_left, gf_top, gf_w, gf_h = transform_item_to_gapfree(
    photo_page_left, photo_top, photo_width, photo_height,
    edge_gap, internal_gap,
    is_spread=False,
    is_left_page=is_left_page
)

print(f"Gap-free position: ({gf_left}, {gf_top})")
print(f"Gap-free dims: {gf_w} x {gf_h}")

# For right page with negative edge_gap, photo at left edge (centerfold)
# should have gf_left = 0 (NOT -30), to prevent bleed into centerfold
assert gf_left == 0.0, "Centerfold bleed prevention failed!"
```

## Diagnostic Output

When debug mode is enabled, the GUI also logs:

```
INFO: Single-page mode: pageno=75, origin_left=2000.0, is_left_page=False
INFO: Debug dump written to Debug-Page-75.txt
```

This helps confirm:
- Which page is being processed
- The `origin_left` value (0 for left pages, non-zero for right pages)
- Whether the page is correctly identified as left or right

## Common Issues to Debug

### Right Page Centerfold Bleed

**Problem:** Right-hand pages with negative edge_gap show bleed on all 4 sides instead of just top/right/bottom.

**What to check in debug dump:**
- `is_left_page: False` (should be False for right pages)
- `origin_left: 2000.0` (should be non-zero for right pages)
- `edge_gap: -30` (negative = bleed)

**Expected behavior:**
- Photos at `area_left = origin_left` (i.e., at the centerfold) should have `gapfree_left = 0`
- Photos NOT at centerfold should have `gapfree_left < 0`

**How to verify:**
Run `pytest tests/test_debug_dump_reproduction.py -v -s` to see detailed output.

### Origin Left Not Set

**Problem:** `origin_left: 0.0` for a right page.

**Diagnosis:** The MCF file doesn't have `origin_left` attribute, or it's being read incorrectly.

**Fix:** Check the MCF parser to ensure `origin_left` is extracted from the XML.

## Tips

1. **Always check debug dumps** when you suspect coordinate transformation issues
2. **Keep debug dumps** for failing test cases - they're invaluable for regression tests
3. **Run the test** to validate your fix works correctly
4. **Compare dumps** before/after algorithm changes to see what changed
