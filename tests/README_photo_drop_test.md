# Photo Drop Test - File Promises from Photos App

## Problem

When dragging photos from macOS Photos app into Tkinter applications, only thumbnail images are received, not the full-resolution originals. This is because Photos uses "file promises" instead of sending actual file paths.

## Solution

Use PyObjC to intercept the drag-and-drop operation at the native macOS level and properly resolve file promises.

## Setup

1. Install PyObjC (macOS only):
```bash
cd /Volumes/ExternalSSD/VinceData/Documents/GitHub-photostuff/cewe-layout
source ../.env/bin/activate
pip install pyobjc-framework-Cocoa
```

2. Run the test:
```bash
python tests/test_photo_drop.py
```

## How to Test

1. A window will appear titled "Photo Drop Test - Drop Photos Here"
2. Open the Photos app
3. Select one or more photos
4. Drag them into the test window
5. Watch the console output - it will show:
   - File promise types detected
   - Temporary directory where files are created
   - Full paths to the created files
   - File sizes and dimensions

## Expected Results

**From Photos app (file promise):**
- Console shows "File promise detected"
- Photos app creates full-resolution images in temp directory
- File sizes should be several MB for typical photos
- Dimensions match the original photo resolution

**From Finder (regular file drop):**
- Console shows "Regular files detected"
- Files are already on disk, paths are passed directly
- This is the current behavior that works

## Key Differences

| Source | Method | Result |
|--------|--------|--------|
| Photos app | File Promise | Full resolution (~5-10 MB) |
| Finder | Regular file | Full resolution (~5-10 MB) |
| ~~Photos app via Tkinter~~ | ~~Thumbnail~~ | ~~Small (~100 KB)~~ ❌ |

## Next Steps

If this test works correctly (shows full-resolution files from Photos), we can integrate this approach into the main GUI by:

1. Creating a native macOS drop handler using PyObjC
2. Bridging it to the Tkinter application
3. Replacing or supplementing the tkinterdnd2 implementation

## Technical Details

The critical PyObjC call is:
```python
filenames = sender.namesOfPromisedFilesDroppedAtDestination_(destURL)
```

This tells Photos (or any app using file promises) to materialize the actual files at the specified destination URL. Photos will then write the full-resolution images to that location.
