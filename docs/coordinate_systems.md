# Coordinate System Transformations

This document describes the coordinate transformations used in cewe-layout.

## 1. PDF Points (from PDF file) - INTERNAL ONLY
- **Unit**: PDF points (72 points = 1 inch = 25.4mm)
- **Origin**: Top-left of PDF page  
- **Usage**: Internal to pdf_extractor.py only - converted immediately to MCF
- **⚠️ NOT EXPOSED**: pdf_extractor API only returns MCF coordinates

## 2. MCF Spread Coordinates (Universal for all code except pdf_extractor internals)
- **Unit**: 0.1mm (10 MCF units = 1mm)
- **Origin**: Top-left of the **spread** (two pages side-by-side)
- **Range**: 
  - Left pages: x ∈ [0, page_width_mcf)
  - Right pages: x ∈ [page_width_mcf, 2×page_width_mcf]
  - Both pages: y ∈ [0, page_height_mcf]

**⚠️ CRITICAL**: ALL coordinates outside of pdf_extractor.py are in MCF spread units:
- Photos from MCF files: spread coordinates
- PDF segments from pdf_extractor: spread coordinates (converted internally)
- Composite images from pdf_extractor: spread coordinates (converted internally)
- Segmentation algorithms: operate on MCF spread coordinates
- GUI business logic: works with MCF spread coordinates

**Conversion (done internally in pdf_extractor.py only)**:
```python
PT_TO_MCF = 3.52778  # 1 PDF point = 0.352778mm = 3.52778 × 0.1mm
is_right_page rules:
    Page positioning rules based on UI page number:
    - "F" (front cover): RIGHT side of cover spread
    - "B" (back cover): LEFT side of cover spread
    - UI page 0 (inside front): LEFT side
    - Other odd UI pages (1,3,5...): RIGHT side of content spreads
    - Other even UI pages (2,4,6...): LEFT side of content spreads
    - Final numbered page (always odd) is the blank inside back page: RIGHT side.
x_mcf_spread = pdf_x * PT_TO_MCF + (page_width_mcf if is_right_page else 0)
```

### MCF Spread Layout
```
+----------------+----------------+
|   Left Page    |   Right Page   |
|   (x=0)        | (x=page_width) |
+----------------+----------------+
      spread_width = page_width * 2
```

## 3. Canvas Pixels (on-screen rendering in page_gui.py only)
- **Unit**: Screen pixels
- **Input**: MCF spread coordinates from all sources
- **Conversion**:
  ```python
  # When rendering single page view, subtract origin_left to show just that page
  # origin_left = 0 for left pages, page_width_mcf for right pages
  
  # Calculate scale to fit page + margins in canvas
  total_w_mcf = page_width + 2 * margin_mcf
  total_h_mcf = page_height + 2 * margin_mcf
  scale = min(canvas_w / total_w_mcf, canvas_h / total_h_mcf)
  
  # Convert MCF spread coordinates to canvas pixels (single page view)
  x_page_relative = x_mcf_spread - origin_left  # Extract just this page
  x_pixels = (margin_mcf + x_page_relative) * scale
  y_pixels = (margin_mcf + y_mcf_spread) * scale
  
  # When using pre-calculated frame_x (which already includes margin):
  x_page_relative = x_mcf_spread - origin_left
  x_pixels = frame_x + x_page_relative * scale
  ```
- **Origin**: Top-left of canvas
- **Page Renderer Responsibility**: 
  - Receives MCF spread coordinates from all sources
  - Converts to canvas pixels for display
  - ONLY code that handles canvas pixels

### Canvas Layout
```
+--------------------------------------------------+
| margin_mcf                                       |
| +-----------+-------------+                      |
| | Left Page | Right Page  | <-- page rendering  |
| +-----------+-------------+                      |
|                                                  |
+--------------------------------------------------+
```

## Coordinate Flow Example

**From PDF extraction to screen rendering:**

1. **PDF Extraction** (pdf_extractor.py):
   ```python
   # PDF page 3 (right page), image at (100, 50) PDF points
   pdf_x, pdf_y = 100, 50  # PDF points, page-relative
   
   # Convert to MCF spread coordinates (done internally)
   PT_TO_MCF = 3.52778
   is_right = (3 % 2 == 1)  # True
   page_width_mcf = 5400
   x_mcf_spread = 100 * 3.52778 + 5400 = 5752.78  # MCF spread coordinate
   ```

2. **Algorithm Processing** (segmenters, GUI logic):
   ```python
   # Work directly with MCF spread coordinates
   segment_left = 5752.78  # MCF spread units
   # All comparisons, calculations in MCF spread coordinates
   ```

3. **Screen Rendering** (page_gui.py):
   ```python
   # Convert MCF spread to canvas pixels
   origin_left = 5400  # For right page
   x_page = 5752.78 - 5400 = 352.78  # Page-relative MCF
   x_canvas = frame_x + 352.78 * scale  # Canvas pixels
   ```

## Summary

**Three clear layers with strict separation of concerns:**

1. **pdf_extractor.py**: PDF points → MCF spread coordinates (only place that knows about PDF points)
2. **All business logic**: Works exclusively with MCF spread coordinates (algorithms, GUI, segmenters)
3. **page_gui.py**: MCF spread coordinates → Canvas pixels (only place that converts to pixels)

**Key Rules:**
- ✅ pdf_extractor returns MCF spread coordinates for all content (composite, segments, images, text)
- ✅ All code outside pdf_extractor works with MCF spread coordinates
- ✅ page_gui.py subtracts origin_left to show single page view (converts spread → page-relative for display)
- ❌ No PT_TO_MCF conversions outside pdf_extractor.py
- ❌ No canvas pixel calculations outside page_gui.py

---

## 4. Mimeo Photos Coordinates

### System Properties

| Property | Mimeo Photos | CEWE/MCF |
|----------|--------------|----------|
| **Units** | Points (1/72 inch) | MCF (0.1mm) |
| **Origin** | Bottom-left | Top-left |
| **Y-axis** | Increases upward | Increases downward |
| **Anchor** | Center-based | Top-left |
| **Scope** | Per single page | Per spread |
| **Bleed** | All 4 edges | 3 edges (not spine) |

### Conversion Factor

```python
POINTS_TO_MCF = 25.4 / 72 / 0.1  # = 3.527778
```

### 5-Step Transformation

The `MimeoCoordinateTransformer` class handles conversion from Mimeo to MCF coordinates:

```python
def transform(self, mimeo_x, mimeo_y, mimeo_w, mimeo_h, is_right_page=False):
    # Step 1: Center-based → Top-left-based
    mimeo_x_topleft = mimeo_x - mimeo_w / 2
    mimeo_y_topleft = mimeo_y - mimeo_h / 2
    
    # Step 2: Y-flip (bottom-left origin → top-left origin)
    mimeo_y_topleft = self.mimeo_page_height - mimeo_y_topleft - mimeo_h
    
    # Step 3: Per-page → Per-spread (offset right pages)
    if is_right_page:
        mimeo_x_topleft += self.mimeo_page_width
    
    # Step 4: Points → MCF
    mcf_x = mimeo_x_topleft * self.POINTS_TO_MCF
    mcf_y = mimeo_y_topleft * self.POINTS_TO_MCF
    mcf_w = mimeo_w * self.POINTS_TO_MCF
    mcf_h = mimeo_h * self.POINTS_TO_MCF
    
    # Step 5: Adjust bleed for CEWE constraints
    mcf_x, mcf_w = self._adjust_spine_bleed(mcf_x, mcf_w, is_right_page)
    
    return int(mcf_x), int(mcf_y), int(mcf_w), int(mcf_h)
```

### Bleed Adjustment (Step 5)

**Problem:** Mimeo allows bleed on all 4 edges; CEWE only allows bleed on 3 edges (NOT on spine/binding).

**Solution:** Remove spine bleed only; preserve outer edge bleed:

- **Left pages** (spine on RIGHT at x=page_width):
  - **Remove spine bleed**: if `x + w > page_width` (small overhang <2cm), clip width
  - **Preserve spread-spanning**: if overhang ≥2cm, it's intentional (don't clip)
  - **Allow outer bleed**: negative `x` is OK (outer edge can bleed freely)

- **Right pages** (spine on LEFT at x=page_width):
  - **Remove spine bleed**: if `x < page_width`, adjust `x = page_width` and reduce `w`
  - **Allow outer bleed**: `x + w` can exceed `2*page_width` (outer edge can bleed freely)

```python
def _adjust_spine_bleed(self, mcf_x, mcf_w, is_right_page):
    MAX_BLEED_MCF = 200  # 2cm threshold for spread-spanning detection
    
    if is_right_page:
        # Remove spine bleed (left edge must be >= page_width)
        if mcf_x < self.mcf_page_width:
            bleed = self.mcf_page_width - mcf_x
            mcf_x = self.mcf_page_width
            mcf_w -= bleed
        
        # Outer edge (right) bleed is allowed - no adjustment
        
    else:
        # Remove spine bleed (right edge must be <= page_width, unless spread-spanning)
        overhang = (mcf_x + mcf_w) - self.mcf_page_width
        if 0 < overhang < MAX_BLEED_MCF:
            mcf_w -= overhang
        # Large overhang (≥2cm) preserved as spread-spanning photo
        
        # Outer edge (left) bleed is allowed - negative x OK
    
    return mcf_x, mcf_w
```

### Example: Pages 29 & 30 (with Bleed Adjustment)

**Mimeo Database Values (identical frame on both pages):**
- Page dimensions: 909×702 points = 32.07×24.77 cm
- Frame center: (454.5, 351.0) points
- Frame size: 919.33×712.32 points

**Page 29 (Right page):**
```
Step 1 (Center→TopLeft): x = 454.5 - 919.33/2 = -5.165, y = 351.0 - 712.32/2 = -5.16
Step 2 (Y-flip): y = 702 - (-5.16) - 712.32 = -5.16
Step 3 (Right offset): x = -5.165 + 909 = 903.835
Step 4 (Points→MCF): x = 903.835 × 3.527778 = 3188 MCF, y = -18 MCF
                      w = 3243 MCF, h = 2512 MCF
Step 5 (Bleed adjust): x = 3188 < 3206 (page_width) → SPINE BLEED!
                       Adjust: x = 3206, w = 3243 - 18 = 3225 MCF
→ Final MCF: (3206, -18, 3225, 2512) = 32.06×-0.18 cm, 32.25×25.12 cm
```

**Page 30 (Left page):**
```
Steps 1-4: Same as page 29 up to MCF conversion
           x = -18 MCF, y = -18 MCF, w = 3243 MCF, h = 2512 MCF
Step 5 (Bleed adjust): x = -18 (outer edge bleed - OK)
                       x + w = -18 + 3243 = 3225 > 3206 (page_width) → SPINE BLEED!
                       Adjust: w = 3206 - (-18) = 3224 MCF
→ Final MCF: (-18, -18, 3224, 2512) = -0.18×-0.18 cm, 32.24×25.12 cm
```

**Physical Verification:**
- Spread dimensions: 3206×2476 MCF = 32.06×24.76 cm ✓ (matches 32.07×24.77 cm physical)
- Left page: x=-18 MCF = -0.18 cm (1.8mm bleed on outer edge - allowed)
- Right page: x=3206 MCF (no spine bleed - adjusted from 3188)
- Bleed adjustment: ~18 MCF (~2mm) removed from spine edges

### Integration

**Where Used:**
- `cewe_layout/mimeo/mimeo_co5 steps in order (center→topleft, Y-flip, page→spread, points→MCF, bleed adjust)
- ✅ Right-page offset happens BEFORE MCF conversion (Step 3 before Step 4)
- ✅ Use content page dimensions (layouts[2]), NOT cover dimensions (layouts[0])
- ✅ Bleed adjustment removes spine bleed but preserves spread-spanning photos (>2cm overhang)
- ❌ Never treat Mimeo coordinates as if already in MCF units
- ❌ Never skip the center-to-topleft conversion (Mimeo anchors at center)
- ❌ Never allow negative x on right pages or x+w > page_width on left pages (spine bleed
- ✅ All Mimeo coordinates are in points (1/72"), never MCF
- ✅ Transform must apply all 4 steps in order (center→topleft, Y-flip, page→spread, points→MCF)
- ✅ Right-page offset happens BEFORE MCF conversion (Step 3 before Step 4)
- ❌ Never treat Mimeo coordinates as if already in MCF units
- ❌ Never skip the center-to-topleft conversion (Mimeo anchors at center)

