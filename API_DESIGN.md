# Unified Layout Algorithm API

## Overview

The cewe-layout project uses a **unified `LayoutRectangle` class** that serves as both **input and output** to layout algorithms. This design eliminates the need for separate input/output classes and makes the API cleaner and more flexible.

## Core Classes

### `LayoutRectangle`

Represents an item (photo, text block, etc.) on a page. Works in both directions:

**On Input:**
- `item_id`: Unique identifier (string, e.g., "0", "photo_1")
- `width`: Item width in page coordinates (e.g., 1920.0)
- `height`: Item height in page coordinates (e.g., 1080.0)
- `desired_weight`: Relative importance for layout (float, 0.5 to 2.0, default 1.0)
- `x`: Optional starting hint (may be None; algorithm can ignore)
- `y`: Optional starting hint (may be None; algorithm can ignore)
- `achieved_weight`: Always 0.0 on input

**On Output (after algorithm runs):**
- `x`: Computed top-left corner x-coordinate
- `y`: Computed top-left corner y-coordinate
- `width`: Final positioned width (may differ from input due to aspect-ratio constraints)
- `height`: Final positioned height (may differ from input due to aspect-ratio constraints)
- `achieved_weight`: Actual weight achieved by the layout algorithm (typically ≈ desired_weight)

### `LayoutAlgorithm` (Abstract Base Class)

All layout algorithms inherit from `LayoutAlgorithm` and implement the `generate_layout()` method.

```python
def generate_layout(
    self,
    page_width: float,
    page_height: float,
    rectangles: List[LayoutRectangle],
    **kwargs
) -> Tuple[bool, List[LayoutRectangle], str]:
    """
    Generate layout for items on a page.
    
    Args:
        page_width: Page width in page coordinates (typically 0.1 mm units).
        page_height: Page height in page coordinates.
        rectangles: List of LayoutRectangle objects to position.
        **kwargs: Algorithm-specific parameters.
    
    Returns:
        (success, rectangles, error_msg)
        - success: True if layout succeeded, False otherwise.
        - rectangles: Same list, with x/y/width/height/achieved_weight updated.
        - error_msg: Empty string on success, error description on failure.
    """
```

**Important Contract:**
- Algorithms **modify rectangles in-place** (set x, y, width, height, achieved_weight on each rectangle).
- Algorithms return the same list (or a new list with modified rectangles).
- Algorithms know **nothing** about file paths, image loading, or MCF coordinates.

## Usage Pattern

### 1. Create Rectangles (Domain Layer)

```python
from cewe_layout.algorithms.base import LayoutRectangle

rectangles = [
    LayoutRectangle(item_id="0", width=1920, height=1080, desired_weight=1.0),
    LayoutRectangle(item_id="1", width=1080, height=1080, desired_weight=1.5),
]
```

### 2. Call Algorithm (Algorithm Layer)

```python
from cewe_layout.algorithms.collage_generator import CollageGeneratorAlgorithm

algo = CollageGeneratorAlgorithm(temperature=1.0)

page_width = 2970.0
page_height = 4200.0
success, result_rects, error_msg = algo.generate_layout(
    page_width, page_height, rectangles
)

if success:
    for rect in result_rects:
        print(f"Item {rect.item_id} positioned at ({rect.x}, {rect.y})")
```

### 3. Translate to Domain Objects (Wrapper Layer)

In `collage_wrapper.py`:

```python
def _rectangles_to_photos(photos, rectangles):
    """Convert LayoutRectangle output back to MCF photo format."""
    updated_photos = []
    
    for rect in rectangles:
        item_id = rect.item_id
        photo_idx = int(item_id)
        
        if photo_idx < len(photos):
            photo = photos[photo_idx].copy()
            # Map abstract coordinates back to MCF units
            photo['area_left'] = rect.x
            photo['area_top'] = rect.y
            photo['area_width'] = rect.width
            photo['area_height'] = rect.height
            updated_photos.append(photo)
    
    return updated_photos
```

## Architecture Layers

```
┌─────────────────────────────────────────────────────┐
│ GUI Layer (gui.py)                                  │
│  - Calls generate_layout_for_page(photos, ...)      │
│  - Displays results, manages undo/save              │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ Wrapper Layer (collage_wrapper.py)                  │
│  - _photos_to_rectangles(): Load images, extract    │
│    dimensions, create LayoutRectangle objects       │
│  - Call algorithm.generate_layout()                 │
│  - _rectangles_to_photos(): Map results back to     │
│    MCF coordinates                                  │
└────────────────┬────────────────────────────────────┘
                 │
┌────────────────▼────────────────────────────────────┐
│ Algorithm Layer (algorithms/)                       │
│  - LayoutAlgorithm: Abstract interface              │
│  - CollageGeneratorAlgorithm: Concrete impl.        │
│  - Future: GridAlgorithm, TextBlockAlgorithm, etc.  │
│                                                     │
│  Key: Knows ONLY abstract items + page dimensions.  │
│        No file paths, no MCF, no image loading.     │
└─────────────────────────────────────────────────────┘
```

## Concrete Implementation: `CollageGeneratorAlgorithm`

```python
from cewe_layout.algorithms.collage_generator import CollageGeneratorAlgorithm

algo = CollageGeneratorAlgorithm(temperature=1.0)

# Input rectangles with image dimensions
rects = [
    LayoutRectangle(item_id="0", width=1920, height=1080),
    LayoutRectangle(item_id="1", width=1080, height=1440),
]

# Run layout on 2970×4200 page
success, rects, error = algo.generate_layout(2970, 4200, rects)

# Output: rects[0].x, rects[0].y, rects[0].width, rects[0].height are set
```

**Algorithm Details:**
1. Creates synthetic images with the correct aspect ratio (width/height).
2. Runs Wu et al. 2016 collage-tree layout algorithm on synthetic images.
3. Maps pixel coordinates back to page coordinates.
4. Updates each rectangle's x, y, width, height, achieved_weight in-place.

## Adding New Algorithms

To add a new layout algorithm (e.g., grid-based, constraint-based):

```python
from cewe_layout.algorithms.base import LayoutAlgorithm, LayoutRectangle
from typing import List, Tuple

class GridAlgorithm(LayoutAlgorithm):
    """Simple N×M grid layout."""
    
    def __init__(self, columns=2, rows=3):
        self.columns = columns
        self.rows = rows
    
    def generate_layout(
        self,
        page_width: float,
        page_height: float,
        rectangles: List[LayoutRectangle],
        **kwargs
    ) -> Tuple[bool, List[LayoutRectangle], str]:
        """Position rectangles in a grid."""
        
        if not rectangles:
            return False, [], "No rectangles to layout"
        
        cell_w = page_width / self.columns
        cell_h = page_height / self.rows
        
        for i, rect in enumerate(rectangles):
            row = i // self.columns
            col = i % self.columns
            
            if row >= self.rows:
                break  # Too many items for grid
            
            rect.x = col * cell_w
            rect.y = row * cell_h
            rect.width = cell_w
            rect.height = cell_h
            rect.achieved_weight = rect.desired_weight
        
        return True, rectangles, ""
```

Then use it:

```python
from cewe_layout.collage_wrapper import generate_layout_for_page
from cewe_layout.algorithms.grid import GridAlgorithm

algo = GridAlgorithm(columns=2, rows=3)
success, photos, error = generate_layout_for_page(
    photos, page_w, page_h, mcf_base_folder, algorithm=algo
)
```

## Key Design Benefits

1. **Separation of Concerns**: Algorithms don't know about MCF, file paths, or image loading.
2. **Unified I/O**: No separate input/output classes; one `LayoutRectangle` works for both.
3. **Extensible**: New algorithms can be added by subclassing `LayoutAlgorithm`.
4. **Testable**: Algorithms can be tested independently with synthetic rectangles.
5. **Type-Safe**: Full type hints enable IDE completion and static analysis.

## Testing

Run the integration test:

```bash
cd cewe-layout
python test_unified_api.py
```

Expected output:
```
============================================================
Integration Test: Unified LayoutRectangle API
============================================================
Testing LayoutRectangle...
  ✅ LayoutRectangle(...)

Testing CollageGeneratorAlgorithm...
  ✅ Rectangle 0: ...
  ✅ Rectangle 1: ...
  ✅ Rectangle 2: ...

Testing in-place modification...
  ✅ Algorithm modified 3 rectangles in-place

============================================================
✅ All tests passed!
============================================================
```
