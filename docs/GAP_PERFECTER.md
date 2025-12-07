# Gap Perfecter Algorithm

The Gap Perfecter algorithm deterministically eliminates small gaps and overlaps from nearly-perfect layouts.

## Purpose

Takes an existing layout that is already very close to perfect (e.g., photos nearly touching with tiny gaps of 1-3 pixels, or small overlaps of 1-5mm) and adjusts it to be 100% gap-free without changing the overall layout structure.

Works with both photos and text blocks interchangeably.

## Algorithm

### 1. Diagonal Processing

All rectangles (photos and texts) are sorted by diagonal distance from the origin (0,0):
```
distance = sqrt(x² + y²)
```

This ensures we process items starting from the top-left corner and working toward the bottom-right, which is critical for deterministic expansion.

### 2. Four-Stage Processing

For each rectangle (in diagonal order):

**a) Fix Small Overlaps**
- If this rect overlaps with any previous rect by less than 5mm:
  - Shift this rect right/down to eliminate the overlap
  - Shrink width/height accordingly

**b) Expand Top-Left**
- Move top edge up to meet rects above (or page top)
- Move left edge left to meet rects to the left (or page left edge)

**c) Expand to Right Edge (if close)**
- If within 15mm of the right page edge, expand to align perfectly

**d) Expand to Bottom Edge (if close)**
- If within 15mm of the bottom page edge, expand to align perfectly

### 3. Overlap Detection

Two rectangles are considered to overlap if their X and Y ranges both intersect.

Vertical/horizontal overlap is checked for gap-filling expansion decisions.

## Usage

### Via collage_wrapper (recommended)

```python
from cewe_layout.algorithms import GapPerfecterAlgorithm
from cewe_layout.collage_wrapper import generate_layout_for_page

# Existing layout with small gaps
photos = [
    {'filename': 'tl.jpg', 'area_left': 1.0, 'area_top': 1.0, 
     'area_width': 998.0, 'area_height': 998.0},
    {'filename': 'tr.jpg', 'area_left': 1001.0, 'area_top': 1.0,
     'area_width': 998.0, 'area_height': 998.0},
    # ... more photos
]

algorithm = GapPerfecterAlgorithm()
success, updated_photos, _, error = generate_layout_for_page(
    photos=photos,
    page_width_mcf=2000.0,
    page_height_mcf=2000.0,
    photo_dimensions={'tl.jpg': (1000, 1000), ...},
    algorithm=algorithm,
    edge_gap=0.0,
    internal_gap=0.0,
    origin_left=0.0,
    pageno=1
)

# updated_photos now have perfect layout with no gaps
```

### Direct usage (advanced)

```python
from cewe_layout.algorithms import GapPerfecterAlgorithm
from cewe_layout.algorithms.base import LayoutRectangle

rectangles = [
    LayoutRectangle(item_id='0', x=1.0, y=1.0, width=998.0, height=998.0),
    LayoutRectangle(item_id='1', x=1001.0, y=1.0, width=998.0, height=998.0),
    # ... more rectangles with positions set
]

algorithm = GapPerfecterAlgorithm()
success, perfected_rects, error = algorithm.generate_layout(
    rectangles=rectangles,
    page_width=2000.0,
    page_height=2000.0
)
```

## Requirements

1. **Positions must be set**: All input rectangles must have x,y positions defined
2. **Nearly perfect layout**: Works best when gaps are small (1-5mm) and overlaps are tiny (<5mm)
3. **Uses slot dimensions**: Gap Perfecter requires actual slot dimensions from the current layout, not image dimensions
4. **Mixed items supported**: Works with both photos and text blocks in the same layout

## Implementation Details

- **Slot dimensions**: Gap Perfecter automatically uses slot dimensions (via `use_slot_aspect=True`) because it refines an existing layout
- **Gap-free coordinates**: Operates in gap-free coordinate space like all layout algorithms
- **Deterministic**: Same input always produces same output (no randomness)
- **Non-destructive**: Creates new rectangles, doesn't modify input
- **Tolerances**: 
  - Overlap fix threshold: 5mm (50 MCF units)
  - Edge proximity: 15mm (150 MCF units)

## Test Coverage

- Unit tests: [tests/test_gap_perfecter.py](../tests/test_gap_perfecter.py)
  - 2x2 grid with small gaps
  - Single photo with margins
  - Horizontal/vertical layouts
  - Complex multi-photo layouts
  - Diagonal sorting verification
  - Small overlap fixing
  - Mixed photos and texts
  
- Integration tests: [tests/test_gap_perfecter_integration.py](../tests/test_gap_perfecter_integration.py)
  - Full pipeline through collage_wrapper
  - 2x2 grid perfect expansion
  - Vertical column perfect expansion

## Related Documentation

- [BLEED_HANDLING.md](BLEED_HANDLING.md) - Gap and bleed handling
- [algorithms/gap_perfecter.py](../cewe_layout/algorithms/gap_perfecter.py) - Implementation
