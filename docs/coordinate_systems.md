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
  - Left pages: x ∈ [0, page_width_mcf]
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
is_right_page = (pdf_page_num % 2 == 0)  # Pages 0, 2, 4... are right
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
   # PDF page 2 (right page), image at (100, 50) PDF points
   pdf_x, pdf_y = 100, 50  # PDF points, page-relative
   
   # Convert to MCF spread coordinates (done internally)
   PT_TO_MCF = 3.52778
   is_right = (2 % 2 == 0)  # True
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

