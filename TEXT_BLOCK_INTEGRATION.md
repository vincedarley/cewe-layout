# Text Block Integration Status

## Completed ✓

### 1. MCF Parsing
- `cewe_layout/parser.py`: Extract text blocks from `<area areatype="textarea">` elements
- Pages now have both `photos` and `texts` lists
- Text blocks store position/size: `area_left`, `area_top`, `area_width`, `area_height`

### 2. Layout Data Model
- `cewe_layout/algorithms/base.py`: Added `preserve_aspect_ratio` attribute to `LayoutRectangle`
  - Default: `True` for photos (maintain aspect ratio)
  - Set to: `False` for text blocks (can stretch to fit)
- Updated `__repr__` to show item type (photo vs text)

### 3. Gap Detection
- `cewe_layout/gap_utils.py`: Text blocks included in gap analysis
- Nearest-neighbor algorithm finds closest photos/texts with overlap
- Outlier removal (>1 stdev) filters out large gaps from text blocks
- Bleed tracking for negative margins (items extending beyond page edges)

### 4. Layout Management
- `cewe_layout/layout_ops.py`: `PageLayout` stores both photos and texts
- `set_original(photos, texts)` and `push_layout(photos, texts)` signatures updated
- Undo/redo works for both photos and texts
- Text blocks use `TEXT_<index>` identifiers for preferred size tracking

### 5. GUI Display
- `cewe_layout/gui.py`: Text blocks rendered with:
  - Yellow background (`#ffffcc`)
  - Green outline (2px)
- Header shows text block count: "Page X: Y photos, Z texts"
- Gap calculations combine photos + texts
- Preferred sizes initialized for `TEXT_<index>` identifiers (scaled 10×)

### 6. Collage Wrapper
- `cewe_layout/collage_wrapper.py`: Full text block support
  - `generate_layout_for_page()` accepts `texts` parameter
  - `_texts_to_rectangles()`: Convert MCF texts to `LayoutRectangle` with `preserve_aspect_ratio=False`
  - `_rectangles_to_texts()`: Convert positioned rectangles back to MCF format
  - Texts get `TEXT_<idx>` identifiers for reversal
  - Gap handling: dimensions increased by gap for algorithm, reduced on output
  - Origin offset applied to both photos and texts for right-hand pages

### 7. Testing
- `tests/test_collage_with_texts.py`: Unit tests for:
  - Text rectangle conversion
  - Preferred size application
  - Gap handling
  - Rectangle-to-text conversion
- All tests passing ✓

## Pending ⚠️

### 1. Layout Algorithm Integration
**Current state**: Collage wrapper creates `LayoutRectangle` objects with `preserve_aspect_ratio=False` for texts, but the underlying algorithms don't yet respect this attribute.

**Required changes**:
- `cewe_layout/algorithms/collage_generator.py`:
  - When fitting items into slots, check `preserve_aspect_ratio`
  - Photos: maintain aspect ratio, crop if needed
  - Texts: stretch to fill slot exactly (no cropping)

- `cewe_layout/algorithms/evaluator.py`:
  - Size mismatch cost calculation should allow flexible aspect ratios for texts
  - May need separate cost function for text blocks vs photos

**Impact**: Currently, if you click "Generate Layout", text blocks will be treated like photos (aspect ratio preserved), which may not be desired.

### 2. GUI Buttons for Mixed Layouts
**Current state**: Buttons work for photos only.

**Required changes**:
- "Equal sizes" button: Should work for both photos and texts
- "Stored sizes" button: Should restore sizes for `TEXT_<index>` identifiers
- Weights UI: Display sizes for text blocks alongside photos

**Impact**: Minor usability - users can't easily adjust text block weights.

### 3. MCF Writing
**Current state**: Can read text blocks, but cannot write them back.

**Required changes**:
- Create `write_layout_to_mcf()` function to update MCF XML
- Update text block positions: `area_left`, `area_top`, `area_width`, `area_height`
- Preserve other text attributes (content, font, rotation, etc.)
- Test round-trip: read → modify → write → read

**Impact**: Cannot persist layout changes to disk yet.

### 4. Cost Function for Text Blocks
**Current state**: Gap estimation includes texts, but evaluator doesn't handle them specially.

**Required changes**:
- `cewe_layout/algorithms/evaluator.py`:
  - Recognize text blocks by `item_id.startswith('TEXT_')`
  - Apply different cost function for flexible aspect ratio items
  - May need to consider text readability (minimum size, aspect ratio bounds)

**Impact**: Layout quality scores may not be accurate for pages with text blocks.

## Architecture Notes

### Text Block Flow
```
MCF XML (areatype="textarea")
    ↓ parser.py
PageInfo['texts'] = [{'area_left': ..., 'area_width': ...}, ...]
    ↓ collage_wrapper.py
LayoutRectangle(item_id='TEXT_0', preserve_aspect_ratio=False)
    ↓ algorithm.generate_layout()
LayoutRectangle(item_id='TEXT_0', x=..., y=..., width=..., height=...)
    ↓ collage_wrapper.py
{'area_left': ..., 'area_top': ..., 'area_width': ..., 'area_height': ...}
    ↓ layout_mgr.push_layout()
PageLayout.texts (stored in history)
    ↓ gui.py render_page()
Yellow rectangle with green outline on canvas
```

### Key Design Decisions
1. **Separate lists**: Photos and texts stored separately throughout the stack
   - Allows different handling at each layer
   - Simplifies filtering (e.g., "photos only" operations)

2. **Identifier convention**: `TEXT_<index>` vs numeric for photos
   - Enables easy type detection: `item_id.startswith('TEXT_')`
   - Works with existing preferred_sizes dict structure

3. **preserve_aspect_ratio flag**: Single attribute controls stretching
   - Clean abstraction: algorithms don't need to know about "photos" vs "texts"
   - Extensible: could add other item types (shapes, decorations) with different behaviors

4. **Gap handling**: Uniform treatment for photos and texts
   - Both have dimensions increased by gap before layout
   - Both have dimensions reduced by gap after layout
   - Simplifies algorithm implementation

## Testing Strategy

### Unit Tests
- ✓ Text rectangle conversion (preserve_aspect_ratio=False)
- ✓ Preferred size application for TEXT_<idx>
- ✓ Gap handling in conversion functions
- ✓ Rectangle-to-text conversion with origin offset

### Integration Tests (needed)
- Layout generation with mixed photo/text pages
- Undo/redo with text blocks
- MCF round-trip (read → write → read)
- Cost calculation for pages with texts

### Manual Testing
- ✓ GUI displays text blocks correctly (yellow/green)
- ✓ Gap calculations include texts (outliers filtered)
- ⚠️ Generate layout with texts (needs algorithm update)
- ⚠️ Equal sizes button with texts
- ⚠️ Save layout to MCF

## Next Steps (Priority Order)

1. **Update CollageGeneratorAlgorithm** to respect `preserve_aspect_ratio`
   - Text blocks should stretch to fit slots without aspect ratio constraints
   - Photos should maintain aspect ratio as currently implemented

2. **Update Evaluator** cost calculations
   - Handle flexible aspect ratio items (texts) differently
   - Ensure cost function doesn't penalize stretched text blocks

3. **Implement MCF writing**
   - Create `write_layout_to_mcf()` function
   - Test round-trip with text blocks
   - Preserve all text attributes except position/size

4. **Update GUI buttons**
   - Extend "Equal sizes" and "Stored sizes" to handle texts
   - Show text weights in UI

## Questions for User

1. Should text blocks have minimum/maximum aspect ratio constraints?
   - Current: completely flexible (can be stretched arbitrarily)
   - Alternative: constrain to readable range (e.g., 2:1 to 5:1)

2. Should text blocks participate in "Equal sizes" button?
   - Current: button only affects photos
   - Alternative: include texts with separate weight

3. What should happen if text content doesn't fit in resized slot?
   - Option A: Reduce font size automatically
   - Option B: Crop text (overflow hidden)
   - Option C: Prevent resizing if text won't fit
