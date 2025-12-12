# Image Segmentation for Photo Extraction

## Problem

Many PDFs (especially from Mimeo Photos and similar services) contain composite images where multiple individual photos are laid out on a single page but stored as one large rasterized image. We need to segment these composite images into individual photos.

## Open Source Solutions

### Scanned Photo Album Projects

**Highly Relevant:**

1. **File_Parser** - https://github.com/LeeNPham/File_Parser
   - 3 stars, Python, OpenCV-based
   - **Specifically designed for extracting individual photos from scanned images**
   - Uses adaptive thresholding + contour detection
   - Handles both rectangular and skewed photos
   - Includes perspective transform for straightening
   - Automatic white margin cropping
   - **Most relevant to our use case!**

2. **scanned-photos-extractor** - https://github.com/guidanoli/scanned-photos-extractor
   - Python, extracts multiple photos from single scanned image

3. **photo-album-extractor** - https://github.com/alejandroviera/photo-album-extractor
   - Python, scripts to extract photos from scanned photo album

4. **photoscan-splitter** - https://github.com/rkj/photoscan-splitter
   - C++, extracts photos from scans including multiple photos

5. **wycinarka** - https://github.com/qwercik/wycinarka
   - Python, command line tool for extracting photos from scans

### Document Layout Analysis (Less Relevant)

1. **Layout-Parser** - https://github.com/Layout-Parser/layout-parser
   - 5.6k stars
   - Unified toolkit for deep learning based document image analysis
   - Supports object detection for layout elements
   - Pre-trained models available
   - **Pros**: Well-maintained, comprehensive, good for documents
   - **Cons**: Heavy-weight, may be overkill for simple photo layouts

2. **DocLayout-YOLO** - https://github.com/opendatalab/DocLayout-YOLO
   - 1.8k stars  
   - YOLO-based document layout analysis
   - Fast and accurate
   - **Pros**: State-of-the-art, fast inference
   - **Cons**: Requires training/fine-tuning for photo layouts

3. **pdf-document-layout-analysis** - https://github.com/huridocs/pdf-document-layout-analysis
   - 777 stars
   - Docker-powered service
   - **Pros**: Simple API, ready to use
   - **Cons**: Requires Docker, external service

### Simple Custom Solutions

For photobooks with clear white borders between photos, a simpler OpenCV-based approach may be sufficient:

1. **Edge Detection + Contour Finding** (Our current implementation)
   - Use Canny edge detection
   - Find contours with flood fill
   - Filter by size and aspect ratio
   - **Pros**: Fast, no ML required, works well with clear borders
   - **Cons**: May fail with unclear boundaries

2. **Adaptive Thresholding + Contours** (File_Parser approach)
   - Adaptive thresholding to handle varying backgrounds
   - Dilation/erosion to connect edges
   - Contour approximation to find photo boundaries
   - Perspective transform for skewed photos
   - **Pros**: Handles skewed photos, robust to background variations
   - **Cons**: Requires tuning parameters

## Current Implementation

We've implemented a simple OpenCV-based solution in `image_segmenter.py`:
- Edge detection with Canny
- Flood fill to find enclosed regions
- Morphological operations to clean up masks
- Size and aspect ratio filtering

## Recommended Next Steps

1. **Test our current implementation** on sample pages
2. **Study File_Parser's approach** - their adaptive thresholding method may be more robust
3. **Consider hybrid approach**: Try our method first, fall back to File_Parser's technique if needed
4. **Evaluate results** - if current method works well, no need for complexity

## TODO

- [ ] Test current implementation on sample pages
- [ ] Compare with File_Parser's adaptive thresholding approach
- [ ] Handle edge cases (photos without clear borders)
- [ ] Add option to disable segmentation for already-separated images
- [ ] Implement quality checks (verify segmentation didn't miss photos)
- [ ] Add perspective transform for skewed photos

## Configuration

The segmentation can be tuned with:
- `min_area_ratio`: Minimum photo size as fraction of page (default: 1%)
- `coverage_threshold`: When to trigger segmentation (default: 80% page coverage)
- Edge detection parameters (Canny thresholds)
- Morphological kernel sizes

