"""Photo Improver Module

This module provides functionality to search for and replace low-quality photos
in a CEWE photobook with higher-quality versions.

## Architecture

The photo improver is organized into a clean subdirectory structure:

```
cewe_layout/photoimprover/
├── __init__.py              # Package exports
├── interface.py             # High-level API for GUI
├── photo_improver.py        # Core matching logic
└── photo_comparison_window.py  # UI for reviewing matches
```

## How It Works

1. **Perceptual Hashing**: Uses imagehash library to compute perceptual hashes
   (average hash by default) for all candidate photos.

2. **Similarity Search**: Compares photobook images against candidates using
   hash difference as a similarity metric (0 = identical, 64 = completely different).

3. **Quality Metrics**: Evaluates resolution, file size, and megapixels to
   determine if a candidate is an improvement.

4. **User Review**: Shows side-by-side comparison with metrics, allowing user
   to accept or reject each match.

5. **Photo Replacement**: Copies accepted photos to album directory with -up
   suffix, updates layout in memory (saved when user clicks "Save Modified").

## GUI Integration

The GUI integration is minimal - just one method in gui.py:

```python
def _search_photo_improvements(self):
    \"\"\"Search for higher-quality versions of photos on current page.\"\"\"
    # ... minimal code that calls photoimprover.search_and_show_improvements()
```

## Usage

1. Ensure photos are in the Album-name-photos directory (standard location)
2. Open a photobook page with photos
3. Click "Improve: Search" button
4. Review matches in Photo Comparison window
5. Accept improvements with Enter key or "Accept" button
6. Click "Save Modified" to write changes to disk

## Hash Algorithms

The module uses `imagehash.average_hash()` by default for speed. For more
accurate matching, you can switch to:

- `imagehash.phash()` - Perceptual hash (more accurate, slower)
- `imagehash.dhash()` - Difference hash (rotation-sensitive)
- `imagehash.whash()` - Wavelet hash (most accurate, slowest)

Edit photo_improver.py:_load_candidates() to change the algorithm.

## Threshold Values

The `threshold` parameter in find_matches() controls sensitivity:

- 0: Exact match only
- 5: Very similar (recommended for duplicates)
- 10: Similar (default - good balance)
- 15: Somewhat similar
- 20+: Quite different

Lower values = fewer but more accurate matches.
Higher values = more matches but may include false positives.

## File Naming Convention

Improved photos are named with -up suffix:

- `photo.jpg` → `photo-up.jpg`
- `photo-sz10.0-pg5.jpg` → `photo-up-sz10.0-pg5.jpg`

This allows tracking which photos have been improved and prevents
re-processing the same photo multiple times.

## Future Enhancements

- [ ] Batch mode: search entire album at once
- [ ] Auto-accept if quality metrics strongly favor candidate
- [ ] Compare EXIF data (camera model, date taken, etc.)
- [ ] Detect and handle rotated duplicates
- [ ] Use neural network embeddings for better similarity
- [ ] Support for RAW image matching
"""
