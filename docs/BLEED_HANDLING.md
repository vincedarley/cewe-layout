# Bleed Handling in CEWE Photobook Layouts

## Summary
- **Bleed** is extra image area that extends beyond the visible page, intended to be trimmed during printing.
- **CEWE convention:** Bleed is applied only to the three outer edges of each page (top, bottom, and the outer side). The center fold (where two pages meet in a spread) should have **no bleed**—images must end exactly at the fold, not overlap.

## Page Geometry

### Single Page Mode
For a single page (not a spread):
- **Left (even) page:**
  - Bleed on left, top, bottom edges
  - **No bleed on right edge (centerfold)**
  - Page size including bleed: `(page_width + bleed) × (page_height + 2×bleed)`
  - Coordinate system: `-bleed` (left edge) to `page_width` (right edge/centerfold)
- **Right (odd) page:**
  - Bleed on right, top, bottom edges
  - **No bleed on left edge (centerfold)**
  - Page size including bleed: `(page_width + bleed) × (page_height + 2×bleed)`
  - Coordinate system: `0` (left edge/centerfold) to `page_width + bleed` (right edge)

### Spread Mode
For a spread (two pages side-by-side):
  - Bleed on all four edges (left, right, top, bottom)
  - Page size including bleed: `(page_width + 2×bleed) × (page_height + 2×bleed)`

## Page Coordinates
- **Left page (single page mode):**
  - Left edge: `-bleed`
  - Right edge (centerfold): `page_width` (no bleed)
  - Top edge: `-bleed`
  - Bottom edge: `page_height + bleed`
- **Right page (single page mode):**
  - Left edge (centerfold): `0` (no bleed)
  - Right edge: `page_width + bleed`
  - Top edge: `-bleed`
  - Bottom edge: `page_height + bleed`
- **Spread mode:**
  - Left edge: `-bleed`
  - Right edge: `page_width + bleed`
  - Top edge: `-bleed`
  - Bottom edge: `page_height + bleed`

## Layout Logic
- When calculating the full page size for layout in **single page mode**, only add bleed to the three outer edges:
  - Width including bleed: `page_width + bleed` (bleed on one side only)
  - Height including bleed: `page_height + 2×bleed` (bleed on top and bottom)
- When calculating the full page size for layout in **spread mode**, add bleed to all four edges:
  - Width including bleed: `page_width + 2×bleed`
  - Height including bleed: `page_height + 2×bleed`
- When positioning images that should touch the center fold, their edge should be exactly at the fold coordinate (not offset by bleed).
- Images should never overlap the center fold in single page mode.

## Example
For a single page with width `W=2100`, height `H=2970`, and bleed `B=20`:

### Left Page (Single Page Mode)
- **Visible page area:** `0` to `W` (horizontal), `0` to `H` (vertical)
- **With bleed:**
  - Left edge: `-B` (= -20)
  - Right edge (centerfold): `W` (= 2100, **no bleed**)
  - Top edge: `-B` (= -20)
  - Bottom edge: `H + B` (= 2990)
- **Full page size including bleed:** `(W + B) × (H + 2B)` = `2120 × 3010`
- **Image touching centerfold:**
  - Its right edge should be exactly at `W` (= 2100)

### Right Page (Single Page Mode)
- **Visible page area:** `0` to `W` (horizontal), `0` to `H` (vertical)
- **With bleed:**
  - Left edge (centerfold): `0` (**no bleed**)
  - Right edge: `W + B` (= 2120)
  - Top edge: `-B` (= -20)
  - Bottom edge: `H + B` (= 2990)
- **Full page size including bleed:** `(W + B) × (H + 2B)` = `2120 × 3010`
- **Image touching centerfold:**
  - Its left edge should be exactly at `0`

### Spread Mode (Double Page)
For a spread with the same dimensions:
- **Full page size including bleed:** `(W + 2B) × (H + 2B)` = `2140 × 3010`
- All four edges have bleed

## Implementation Notes
- When rendering or saving layouts, ensure that bleed is only applied to the three outer edges.
- When splitting a spread into two pages, do not add bleed at the center fold.
- This matches CEWE’s own XML output and avoids unwanted overlap at the fold.

