# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2026-?

Layout:
- Fix to using original photo aspect ratio instead of saved slot.

Page Viewer:
- Functional rendering on/off toggle
- When off the UI will now render text background and foreground colour correctly, and will render border decorations
  for photos and texts.

## [1.0.0] - 2026-01-20

### Many new features

Layout:
- Several different layout creation and layout-tweaking algorithms
- Good handling and control of gaps between photos and edge-gaps on the page
- Size control, aspect ratio control of all photos
- DPI calculations to ensure good quality

Page Viewer:
- Drag to swap 2 photos
- X to delete photo or text blocks
- Toggle between 1-page and Spread views
- Toggle to show photos zoomed appropriately in their frames
- Can drag'n'drop photos from your file-system and from MacOS photos to the page
- Can dynamically rescale the view

Book Transformations:
- Resize/scale a book to a new size
- Merge 2 books
- Bulk rename all photo-files inside a photobook

Import:
- PDF and Mimeo legacy book imports
- HEIF/HEIC file formats supported (as well as jpeg, png, etc)

## [0.1.0] — 2025-11-27

### Added

- Initial release of `cewe-layout`.
- Parser for CEWE `.mcf` / `.xmcf` photobook XML files.
- Tkinter GUI viewer to browse pages and inspect photo slot layouts.
- Integration with collage-generator for automatic layout generation.
- Per-photo weight adjustment UI for layout tuning.
- Diagnostic thumbnail button for troubleshooting image loading.
- OpenCV fallback for image loading when Pillow fails.
- Layout history (undo/back) and original layout restoration.
- Pluggable layout algorithm abstraction for future algorithm variants.

### Technical Notes

- Handles two-page spreads correctly by splitting areas by horizontal center.
- Supports both relative and absolute image path resolution.
- Graceful fallback for older Pillow versions (ImageOps.exif_transpose).
