# Drag-and-Drop Photo Implementation

## Overview

Users can now add photos to the current page by dragging JPEG files from Finder onto the main QLayout window, or by using the `Cmd+O` keyboard shortcut.

## How It Works

### 1. Photo Addition Workflow

When photos are dragged onto the window:

1. **File Validation**: Only JPEG files (`.jpg`, `.jpeg`) are accepted
2. **File Copying**: Photos are copied to the album's image folder with unique filenames
3. **Initial Layout**: Layout rectangles are created for all photos (existing + new)
4. **Preferred Sizes**: Size preferences are determined (placeholder: currently 1.0 for all)
5. **Rendering**: Page is re-rendered showing all photos in overlapping initial positions

### 2. Initial Layout Algorithm

The initial layout places photos in overlapping positions for easy visibility:

- **Base size**: Approximately `page_width/10 × page_height/10` for size multiplier 1.0
- **Aspect ratio**: Maintains photo's original aspect ratio
- **Size scaling**: Multiplier of 1.0, 3.0, or 5.0 based on photo importance
- **Positioning**: 
  - All photos at `y = edge_gap` (5mm from top)
  - `x` starts at `edge_gap` and increments by 10mm per photo (creating overlap)

### 3. Size Calculation Math

For a photo with aspect ratio `AR` and size multiplier `M`:

```
target_area = base_width × base_height × M
slot_width = sqrt(target_area × AR)
slot_height = slot_width / AR
```

Example for 4:3 landscape photo on 210mm × 297mm page:
- Size 1.0: 288mm × 216mm
- Size 3.0: 500mm × 375mm
- Size 5.0: 644mm × 483mm

## Implementation Details

### Files Modified

1. **`cewe_layout/gui.py`**:
   - Added `_setup_drag_and_drop()` - configures drag-drop handlers
   - Added `_on_drop()` - handles drop events from tkinterdnd2
   - Added `_prompt_add_photos()` - fallback file picker (Cmd+O)
   - Added `_handle_dropped_files()` - processes dropped/selected files
   - Added `_copy_photos_to_album()` - copies photos to image folder
   - Added `_create_initial_layout()` - creates overlapping initial rectangles

2. **`cewe_layout/photos.py`**:
   - Added `get_photo_preferred_size()` - placeholder for EXIF-based sizing

3. **`requirements.txt`**:
   - Added optional `tkinterdnd2` for native drag-and-drop support

### Drag-and-Drop Support

The implementation supports two modes:

1. **Native drag-and-drop** (if `tkinterdnd2` is installed):
   - Drag JPEG files from Finder directly onto the window
   - Files are automatically processed

2. **Keyboard shortcut** (always available):
   - Press `Cmd+O` to open file picker
   - Select multiple JPEG files
   - Files are processed the same way

## Future Enhancements

### EXIF-Based Photo Importance

Currently `get_photo_preferred_size()` returns 1.0 for all photos. Future implementation:

```python
def get_photo_preferred_size(img_path: Path) -> float:
    # Read EXIF rating (0-5 stars)
    rating = read_exif_rating(img_path)
    
    # Map rating to size multiplier
    if rating >= 4:
        return 5.0  # Featured/important photos
    elif rating == 3:
        return 3.0  # Medium importance
    else:
        return 1.0  # Normal size
```

Alternative approach: Read EXIF keywords for tags like "featured", "hero", "important".

## Testing

Run `tests/test_drag_drop.py` to verify the initial layout algorithm:

```bash
python tests/test_drag_drop.py
```

## Usage Example

1. Open a photobook in QLayout GUI
2. Navigate to desired page
3. Drag 5-10 JPEG files from Finder onto the main window
4. Photos appear overlapping at top of page
5. Click "Generate Layout" with desired algorithm (e.g., Fan-GA)
6. Photos are arranged into a nice layout
7. Click "Save" to write changes to disk
