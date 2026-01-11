# Coordinate Transformation Analysis for Resize Feature

## Current Rendering Pipeline

### Overview
The rendering happens in `page_gui.py` (PageRenderer class), called from `gui.py` (LayoutViewer class).

### Key Coordinate Usage Points

#### 1. Page-Level Coordinates
**Location**: `PageRenderer.render_pages()` (lines 73-273)
- `page_w`, `page_h`: Page dimensions in MCF units (from `page_data.page_width`, `page_data.page_height`)
- `margin_mcf`: Display margin in MCF units
- `scale`: Calculated to fit page(s) + margins in canvas
  - Formula: `scale = min(canvas_w / total_w_mcf, canvas_h / total_h_mcf)`
  - For spread mode: `total_w_mcf = (2 * page_w) + 2 * margin_mcf`
  - For single page: `total_w_mcf = page_w + 2 * margin_mcf`
  - `total_h_mcf = page_h + 2 * margin_mcf`
- `frame_x`, `frame_y`: Canvas position for page frame
  - Spread mode: second page offset by `page_w`

#### 2. Photo Coordinates
**Location**: `PageRenderer._render_photos()` (lines 496-584)
- Read from photo dict:
  - `left = p.get('area_left') or 0`
  - `top = p.get('area_top') or 0`
  - `w = p.get('area_width') or 0`
  - `h = p.get('area_height') or 0`
- Origin adjustment for right pages:
  - `local_left = left - origin_left`
  - This converts from spread coordinates to page-relative coordinates
- Scaling to canvas pixels:
  - `x0 = frame_x + local_left * scale`
  - `y0 = frame_y + top * scale`
  - `x1 = frame_x + (local_left + w) * scale`
  - `y1 = frame_y + (top + h) * scale`

#### 3. Text Coordinates
**Location**: `PageRenderer._render_texts()` (lines 586-665)
- Identical coordinate handling to photos:
  - `left`, `top`, `w`, `h` from text dict
  - `local_left = left - origin_left`
  - Same scaling formulas as photos

#### 4. PDF Composite Coordinates
**Location**: `PageRenderer._draw_single_pdf_composite()` (lines 374-494)
- Composite image coordinates in MCF spread units:
  - `comp_left_mcf`, `comp_top_mcf`, `comp_width_mcf`, `comp_height_mcf`
- PDF-to-CEWE scaling factors:
  - `pdf_to_cewe_width_scale = cewe_page_width_mcf / pdf_page_width_mcf`
  - `pdf_to_cewe_height_scale = cewe_page_height_mcf / pdf_page_height_mcf`
- Conversion to page-relative then to canvas pixels

## Proposed ResizeTransformer Interface

### Requirements
The transformer must handle:
1. **Scaling** (uniform or non-uniform)
2. **Padding/Margins** (added whitespace)
3. **Cropping** (content exceeding new page bounds)
4. **Origin adjustment** (right page coordinate handling)

### Core Methods Needed

```python
class ResizeTransformer:
    """Transforms coordinates from original book size to resized book size."""
    
    def __init__(self, old_width_mcf, old_height_mcf, new_width_mcf, new_height_mcf,
                 scaling_mode: str, bleed_mm: float = 3):
        """Initialize with old/new dimensions and scaling mode.
        
        Args:
            old_width_mcf: Original single page width in MCF units
            old_height_mcf: Original page height in MCF units
            new_width_mcf: Target single page width in MCF units
            new_height_mcf: Target page height in MCF units
            scaling_mode: One of 5 modes from resize_gui
            bleed_mm: Bleed amount in mm
        """
        pass
    
    def transform_page_dimensions(self) -> Tuple[int, int]:
        """Get transformed page dimensions.
        
        Returns:
            (new_page_width_mcf, new_page_height_mcf)
        """
        pass
    
    def transform_rect(self, left_mcf: int, top_mcf: int, width_mcf: int, height_mcf: int,
                      origin_left: int = 0) -> Tuple[int, int, int, int]:
        """Transform a rectangle from old to new coordinate system.
        
        Args:
            left_mcf: Left position in original MCF spread coordinates
            top_mcf: Top position in original MCF coordinates
            width_mcf: Width in original MCF units
            height_mcf: Height in original MCF units
            origin_left: Origin offset for right pages (pass through unchanged)
        
        Returns:
            (new_left_mcf, new_top_mcf, new_width_mcf, new_height_mcf)
            Returns None if rectangle is completely cropped out
        """
        pass
    
    def transform_origin_left(self, origin_left: int) -> int:
        """Transform origin_left for right pages.
        
        Args:
            origin_left: Original origin_left value
        
        Returns:
            Transformed origin_left value
        """
        # If mode changes page width, origin_left needs adjustment
        # origin_left == old_page_width for right pages
        # Should become new_page_width for right pages
        pass
```

### Integration Points in PageRenderer

#### 1. Page Dimensions
**File**: `gui.py`, method `_build_page_render_data()`
- Must transform `page_width`, `page_height` from page_info
- Must transform `origin_left` for right pages

#### 2. Photo/Text Rectangles  
**File**: `page_gui.py`, method `_render_photos()` and `_render_texts()`
- Before: `left = p.get('area_left')`
- After: `left, top, w, h = transformer.transform_rect(p.get('area_left'), p.get('area_top'), ...)`
- Handle None return (rectangle cropped out completely)

#### 3. Cutout Calculations
**File**: `page_gui.py`, method `_load_and_prepare_thumbnail()`
- Cutout scale/offset may need adjustment if photo areas are scaled
- May need to recalculate based on new rectangle dimensions

#### 4. PDF Composite
**File**: `page_gui.py`, method `_draw_single_pdf_composite()`
- Composite image coordinates need transformation
- PDF-to-CEWE scale factors need recalculation

### Scaling Mode Behaviors

#### Mode 1: "None"
- `transform_rect()`: Return input unchanged (except crop right/bottom if exceeds bounds)
- `transform_page_dimensions()`: Return new dimensions
- `transform_origin_left()`: Return new page width if right page

#### Mode 2: "None (center on page)"
- `transform_rect()`: Offset by centering amount, no scaling
- `transform_page_dimensions()`: Return new dimensions
- Cropping applied equally on all sides

#### Mode 3: "Fit (may have margins)"
- `transform_rect()`: Apply uniform scale (min of width/height ratios)
- Center in new page with margins on loose dimension
- `transform_page_dimensions()`: Return new dimensions

#### Mode 4: "Fill (crop to avoid margins)"
- `transform_rect()`: Apply uniform scale (max of width/height ratios)
- Center in new page, crop on tight dimension
- May return None if rectangle entirely cropped

#### Mode 5: "Fill (may change aspect ratio)"
- `transform_rect()`: Apply non-uniform scale (independent X/Y)
- No margins, no cropping (fills exactly)
- `transform_page_dimensions()`: Return new dimensions

## Implementation Strategy

### Phase 1: Create ResizeTransformer in book/utils.py
- Implement all transform methods
- Use logic from calculate_resize_impact() but return transformed coordinates

### Phase 2: Simplify MimeoCoordinateTransformer
- Remove all scaling/padding logic
- Keep ONLY Y-axis flip (bottom-left to top-left origin)
- Remove `mode` parameter (always 'identity' equivalent)

### Phase 3: Add transformer to PageRenderer
- Add optional `resize_transformer` parameter to PageRenderer.__init__()
- If provided, apply transformations in:
  - `_render_photos()`
  - `_render_texts()`
  - `_draw_single_pdf_composite()` (if needed)

### Phase 4: Wire up from resize_gui
- "View As Resized" creates ResizeTransformer
- Passes transformer to page_gui somehow
- Need to determine how to pass this - perhaps through LayoutViewer?

### Phase 5: Update gui.py
- LayoutViewer needs to hold current ResizeTransformer (or None)
- Pass transformer to PageRenderer when creating/updating
- Transform page dimensions in `_build_page_render_data()`

## Open Questions

1. **How to pass transformer from resize_gui to page_gui?**
   - Option A: Store in LayoutViewer, pass to PageRenderer
   - Option B: Store in Book object itself
   - Option C: Create new LayoutViewer instance with transformer

2. **Should transformer modify book data or only rendering?**
   - Rendering only (cleaner, allows toggling back)
   - Requires consistent application everywhere coordinates used

3. **How to handle "Save As Resized"?**
   - Write transformed coordinates back to MCF
   - Use mcf_writer with transformed data

4. **What about cutout/scale transformations?**
   - Photos have cutout_left, cutout_top, cutout_scale
   - These may need recalculation if photo areas change size
   - Or keep original and let rendering handle it?

5. **Calendar edge gaps?**
   - These are absolute values in MCF units
   - Need to be transformed if page size changes
   - Store separately and apply transform?

## Next Steps

1. Implement ResizeTransformer in book/utils.py
2. Create tests to validate transformation logic
3. Simplify MimeoCoordinateTransformer
4. Decide on transformer passing mechanism
5. Update PageRenderer to use transformer
6. Wire up "View As Resized" button
