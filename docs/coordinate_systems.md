# Coordinate System Transformations

This document describes the coordinate transformations used in cewe-layout.

## 1. PDF Points (from PDF file)
- **Unit**: PDF points (72 points = 1 inch = 25.4mm)
- **Origin**: Top-left of PDF page
- **Usage**: Raw coordinates from PyMuPDF when extracting PDF content

## 2. MCF Units (in data.mcf file)
- **Unit**: 0.1mm (10 MCF units = 1mm)
- **Conversion from PDF points**: `mcf_value = pdf_points * 3.52778`
- **Calculation**: 
  - 1 point = 25.4mm / 72 = 0.352778mm
  - 0.352778mm = 3.52778 × 0.1mm = 3.52778 MCF units
- **Origin**: Top-left of the **spread** (two pages side-by-side)
- **X-offset**: 
  - Right pages: `x_mcf = pdf_x * 3.52778 + page_width_mcf`
  - Left pages: `x_mcf = pdf_x * 3.52778 + 0`

### MCF Spread Layout
```
+----------------+----------------+
|   Left Page    |   Right Page   |
|   (x=0)        | (x=page_width) |
+----------------+----------------+
      spread_width = page_width * 2
```

## 3. Canvas Pixels (on-screen rendering)
- **Unit**: Screen pixels
- **Conversion from MCF**:
  ```python
  # Calculate scale to fit spread + margins in canvas
  total_w_mcf = page_width + 2 * margin_mcf
  total_h_mcf = page_height + 2 * margin_mcf
  scale = min(canvas_w / total_w_mcf, canvas_h / total_h_mcf)
  
  # Convert MCF to pixels
  x_pixels = (margin_mcf + x_mcf - origin_left) * scale
  y_pixels = (margin_mcf + y_mcf) * scale
  ```
- **Origin**: Top-left of canvas
- **origin_left**: Offset for right pages (= page_width for right pages, 0 for left pages)

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

## Overlay Rectangle Coordinate Flow

For PDF-to-screen overlay rectangles:

1. **Extract from PDF**: Coordinates in PDF points, relative to PDF page origin
   ```python
   seg_left_pdf = 426.3  # points from top-left of PDF page
   seg_width_pdf = 142.5 # points
   ```

2. **Convert to MCF**: Multiply by `pt_to_mcf` factor (3.52778)
   ```python
   pt_to_mcf = 3.52778  # 25.4mm/inch ÷ 72 points/inch × 10 units/mm
   seg_left_mcf = seg_left_pdf * pt_to_mcf   # MCF units from top-left of PDF page
   seg_width_mcf = seg_width_pdf * pt_to_mcf  # MCF units
   ```

3. **Convert to screen pixels**: Apply margin, origin_left, and scale
   ```python
   scale = min(canvas_w / total_w_mcf, canvas_h / total_h_mcf)
   x_pixels = (margin_mcf + seg_left_mcf - origin_left) * scale
   width_pixels = seg_width_mcf * scale
   ```
   Note: `origin_left` is subtracted to position right-page overlays correctly (it's 0 for left pages, page_width for right pages)

## Implementation Details

### Segment Extraction (in image_segmenter.py)
Segments start as **image pixels** (relative to the composite image):
```python
segments = segment_composite_image(img)  # Returns [{'left': x, 'top': y, 'width': w, 'height': h}]
```

### Scaling to PDF Points (in pdf_extractor.py)
Convert from image pixels to PDF points using scale factors:
```python
scale_x = composite_rect.width / img_width_pixels
scale_y = composite_rect.height / img_height_pixels

segment_pdf = {
    'left': composite_rect.x0 + seg['left'] * scale_x,  # Absolute position on PDF page
    'top': composite_rect.y0 + seg['top'] * scale_y,
    'width': seg['width'] * scale_x,
    'height': seg['height'] * scale_y
}
```

### Rendering Overlay (in page_gui.py)
Convert from PDF points to canvas pixels:
```python
pt_to_mcf = 3.52778
seg_left_mcf = seg['left'] * pt_to_mcf
seg_width_mcf = seg['width'] * pt_to_mcf

x1 = int((margin_mcf + seg_left_mcf - origin_left) * scale)
width_canvas = int(seg_width_mcf * scale)
```

### Why origin_left Matters for Overlays
Even though overlays show where photos are in the PDF (not in the MCF spread), we still need `origin_left` because:
- The renderer positions everything relative to the visible page frame
- For right pages: origin_left = page_width_mcf, so we subtract it to show the page starting at 0
- For left pages: origin_left = 0, so no adjustment needed

