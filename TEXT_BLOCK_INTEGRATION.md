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

### 1. MCF Writing
**Current state**: Can read text blocks, but cannot write them back.

**Required changes**:
- Create `write_layout_to_mcf()` function to update MCF XML
- Update text block positions: `area_left`, `area_top`, `area_width`, `area_height`
- Preserve other text attributes (content, font, rotation, etc.)
- Test round-trip: read → modify → write → read

**Impact**: Cannot persist layout changes to disk yet. Users can generate and view layouts but changes are lost when closing the application.

### 2. Layout Algorithm Integration (Future Enhancement)
**Current state**: Collage wrapper creates `LayoutRectangle` objects with `preserve_aspect_ratio=False` for texts, but the collage-generator algorithm doesn't yet respect this attribute. Text blocks are positioned in the layout but maintain their original aspect ratio like photos.

**Why this is complex**:
The collage-generator algorithm (Wu et al. 2016) fundamentally operates by:
1. Creating synthetic images with aspect ratios matching input items
2. Building a binary tree layout that optimizes aspect ratio matching
3. Computing pixel positions that preserve aspect ratios

For text blocks with flexible aspect ratios, we have several options:

**Option A: Post-process text blocks** (Recommended)
- Let algorithm position texts like photos
- After layout, stretch text blocks to fill available space better
- Example: if text is in a vertical slot, stretch it vertically
- Pros: Simple, preserves algorithm stability
- Cons: May not optimize layout for text flexibility

**Option B: Separate text positioning**
- Position photos using collage algorithm
- Fill remaining gaps with text blocks
- Pros: Treats texts as true "filler" content
- Cons: More complex, may not achieve optimal layouts

**Option C: Enhanced tree algorithm**
- Modify collage-generator to support flexible aspect ratios
- Would require deep changes to tree generation/adjustment
- Pros: Mathematically optimal
- Cons: Complex, may break existing behavior

**Required changes** (for Option A):
- `cewe_layout/algorithms/collage_generator.py`:
  - After `_map_pixel_layout_to_page()`, identify text rectangles
  - For each text, check if slot aspect differs significantly from text aspect
  - Stretch text to fill slot (adjust width and/or height)
  - Example: if slot is 500×200 but text wants 300×200, stretch width to 500

**Impact**: Currently, text blocks work but don't stretch optimally. This is acceptable for initial integration - texts are positioned correctly, just not optimally resized.

**Future enhancement priority**: Medium - texts work but could be better optimized.

## Recently Completed ✅

### GUI Buttons for Mixed Layouts
**Completed**: All buttons and displays now work for both photos and texts.

**Completed changes**:
- ✅ "Equal sizes" button: Sets equal sizes (10.0) for both photos and texts
- ✅ "Stored sizes" button: Restores sizes for both filenames and `TEXT_<index>` identifiers
- ✅ Weights UI: Displays both photos (P1, P2, ...) and texts (T1, T2, ...) with preferred/actual sizes
- ✅ Item identifier handling: Filenames for photos, TEXT_N for texts
- ✅ Combined cost calculation: All items participate in empty space and size mismatch costs

**Implementation details**:
- Header changed from "Photo" to "Item"
- Display labels use type prefix: P1-PN for photos, T1-TN for texts
- `on_size_changed()` handles both filenames and TEXT_N identifiers
- `update_weights_display()` builds combined list of photos and texts
- Test coverage: [tests/test_gui_items.py](tests/test_gui_items.py)

### Cost Function for Text Blocks
**Completed**: Evaluator already handles text blocks correctly - no changes needed.

**Why current approach works**:
- Size mismatch cost = sum of (preferred_area_fraction - actual_area_fraction)²
- This is valid for both photos and texts
- Text blocks with `preserve_aspect_ratio=False` still have preferred sizes
- We want them to occupy their preferred fraction of the page
- The aspect ratio flexibility doesn't affect size preference

**No changes needed**:
- `cewe_layout/algorithms/evaluator.py` works as-is
- Empty space cost: same for photos and texts
- Size mismatch cost: same for photos and texts
- The `preserve_aspect_ratio` attribute affects *how* the size is achieved (stretch vs crop), not the target size itself

**Impact**: None - evaluator already handles text blocks correctly.

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
