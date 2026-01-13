"""PDF content extraction for photobook conversion.

API Overview:
=============

This module provides two modes for working with PDF content:

1. **Full Extraction Mode** (for initial conversion):
   Use `extract_pdf_content()` to extract all pages upfront.
   Returns dict with 'pages' list fully populated.

2. **On-Demand Reader Mode** (for GUI with existing MCF):
   Use `create_pdf_reader()` to create a lightweight reader.
   Returns dict with empty 'pages' list and a 'reader' for on-demand access.

Public API Functions:
=====================

- `extract_pdf_content(pdf_path, page_range=None, verbose=False, debug=False)`
  Extract all PDF pages upfront. Use for initial PDF→MCF conversion.
  Returns: Dict with 'pages', 'metadata', 'page_size', 'page_count'

- `create_pdf_reader(pdf_path, verbose=False)`
  Create lightweight on-demand reader. Use when MCF already exists.
  Returns: Dict with 'reader', 'metadata', 'page_size', 'page_count', 'pages'=[]

- `get_page_content(pdf_content, pageno)`
  **Primary API for accessing pages** - works with both modes.
  Returns: Page data dict or None on error (errors are logged).
  Automatically caches extracted pages in the 'pages' list.

Usage Examples:
===============

# Full extraction (initial conversion):
pdf_content = extract_pdf_content(Path('album.pdf'))
page_data = pdf_content['pages'][0]  # Direct access

# On-demand mode (GUI with existing MCF):
pdf_content = create_pdf_reader(Path('album.pdf'))
page_data = get_page_content(pdf_content, 0)  # Unified API

# The unified API works with both modes:
for pageno in range(pdf_content['page_count']):
    page_data = get_page_content(pdf_content, pageno)
    if page_data:
        composite = page_data.get('composite_image')
        # ... use composite ...
"""

import fitz  # PyMuPDF
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from .image_segmenter import segment_composite_image, should_segment_image, ImageSegmenter
from .pdf_photobook import PDFPhotobook

logger = logging.getLogger(__name__)




def create_pdf_reader(pdf_path: Path, pdf_page_count: int, verbose: bool = False, insidecovers: bool = False) -> PDFPhotobook:
    """Create a PDFPhotobook with on-demand page loading.
    
    This is used when the MCF project already exists and we just need
    to be able to query individual pages without pre-loading everything.
    
    Args:
        pdf_path: Path to PDF file
        verbose: Print detailed extraction info
        pdf_page_count: int
        insidecovers: Whether PDF includes inside cover pages
        
    Returns:
        PDFPhotobook instance configured for on-demand page extraction
    """

    # Create page mapping for coordinate positioning

    ui_to_pdf = _create_page_mapping(pdf_page_count, insidecovers)
    page_to_ui = {v: k for k, v in ui_to_pdf.items() if v is not None}

    if not page_to_ui:
        raise ValueError(
            "page_to_ui mapping is required for create_pdf_reader(). "
            "On-demand extraction needs UI page context for correct coordinate positioning."
        )
    
    # Create PDFPhotobook in on-demand mode (pages=None triggers lazy loading)
    return PDFPhotobook(
        pages=None,
        metadata=None,  # Will be lazy-loaded from PDF
        pdf_path=pdf_path,
        page_to_ui=page_to_ui,
        verbose=verbose,
        insidecovers=insidecovers
    )


def get_page_content(pdf_originalBook, pageno: int) -> Optional[Dict[str, Any]]:
    """Get page content, abstracting on-demand vs pre-loaded modes.
    
    This is the primary API for accessing page data. It works with both:
    - PDFPhotobook objects (new OOP API, both batch and on-demand)
    - Legacy dict mode (for backward compatibility)
    
    Args:
        pdf_content: PDFPhotobook object or legacy dict from old code
        pageno: Page number (0-indexed)
        
    Returns:
        Page data dict with keys like 'composite_image', 'photos', 'texts', etc.
        Returns None if page doesn't exist or extraction fails (errors logged).
        
    Example:
        >>> photobook = extract_pdf_content(Path('album.pdf'))
        >>> page = photobook.get_page(0)
        >>> images = page.get_images()
    """
    if not pdf_originalBook:
        return None

    # TODO - clean up this mess below.

    try:
        page_count = pdf_originalBook.get_page_count()
        if pageno < 0 or pageno >= page_count:
            logger.warning(f"Page {pageno} out of range (page_count={page_count})")
            return None
        page = pdf_originalBook.get_page(pageno)
        if (page is None):
            logger.warning(f"Page {pageno} is None")
            return None
        # Return the underlying page data dict for backward compatibility
        return page._page_data
    except (IndexError, ValueError) as e:
        logger.error(f"Failed to get page {pageno}: {e}")
        return None



def extract_pdf_content(pdf_path: Path, pdf_page_count: int, page_range: Optional[List[int]] = None, verbose: bool = False, debug: bool = False, insidecovers: bool = False) -> PDFPhotobook:
    """Extract all images and text from a PDF file.
    
    Args:
        pdf_path: Path to PDF file
        page_range: Optional list of 0-indexed page numbers to process
        verbose: Print detailed extraction info
        page_to_ui: Optional mapping from PDF page index to UI page number (for correct positioning)
        insidecovers: Whether the PDF includes inside cover pages
        
    Returns:
        PDFPhotobook object containing all extracted page data
    """
    doc = fitz.open(pdf_path)
    
    # Get metadata
    metadata = {
        'title': doc.metadata.get('title', ''),
        'author': doc.metadata.get('author', ''),
        'subject': doc.metadata.get('subject', ''),
        'producer': doc.metadata.get('producer', ''),
    }

    # Create UI-to-PDF mapping, then invert it
    ui_to_pdf = _create_page_mapping(pdf_page_count, insidecovers)
    page_to_ui = {v: k for k, v in ui_to_pdf.items() if v is not None}

    print(f"DEBUG: PDF-to-UI mapping (first 5 and last 5):")
    sorted_keys = sorted([k for k in page_to_ui.keys() if isinstance(k, int)])
    for pdf_idx in sorted_keys[:5]:
        print(f"  PDF page {pdf_idx} → UI page {page_to_ui[pdf_idx]}")
    for pdf_idx in sorted_keys[-5:]:
        print(f"  PDF page {pdf_idx} → UI page {page_to_ui[pdf_idx]}")

    # Determine which pages to process
    if page_range is None:
        page_range = list(range(len(doc)))
    
    pages = []
    for page_num in page_range:
        if page_num >= len(doc):
            if verbose:
                print(f"Warning: Page {page_num + 1} does not exist, skipping")
            continue

        if page_num == len(doc) -1 and not insidecovers:
            # Add empty inside back cover
            print("Adding empty inside back cover")
            pages.append(None)
        page = doc[page_num]
        # Get UI page number for this PDF page (for correct coordinate positioning)
        ui_page = page_to_ui.get(page_num)
        page_data = extract_page_content(page, page_num, len(doc), verbose, debug, ui_page)
        pages.append(page_data)
        if page_num == 0 and not insidecovers:
            # Add empty inside front cover
            print("Adding empty inside front cover")
            pages.append(None)

    doc.close()
    
    return PDFPhotobook(pages, metadata, insidecovers=insidecovers)


def extract_page_content(page: fitz.Page, page_num: int, total_pages: int, verbose: bool = False, debug: bool = False, ui_page: Any = None) -> Dict[str, Any]:
    """Extract content from a single PDF page.
    
    Args:
        page: PyMuPDF Page object
        page_num: Page number (0-indexed)
        total_pages: Total number of pages in PDF
        verbose: Print detailed info
        debug: Save composite images for debugging
        ui_page: UI page number/identifier for coordinate positioning ("F", "B", 0, 1, 2, ...) - REQUIRED
        
    Returns:
        Dictionary with 'images' and 'text_blocks' lists
        
    Raises:
        ValueError: If ui_page is None (required for correct coordinate positioning)
    """
    if ui_page is None:
        raise ValueError(
            f"ui_page parameter is required for extract_page_content(). "
            f"Cannot determine coordinate positioning without UI page context. "
            f"PDF page {page_num} has no associated UI page identifier."
        )
    
    if verbose:
        print(f"Processing PDF page index {page_num} (CEWE page {ui_page})...")
    
    page_rect = page.rect
    page_rotation = page.rotation  # Get page rotation: 0, 90, 180, or 270 degrees
    
    if verbose and page_rotation != 0:
        print(f"  Page has {page_rotation}° rotation")
    
    page_data = {
        'page_num': page_num,
        'width': page_rect.width,
        'height': page_rect.height,
        'photos': [],
        'texts': [],
        'rotation': page_rotation,  # Store for reference
    }
    
    # Extract images
    image_list = page.get_images(full=True)
    for img_index, img_info in enumerate(image_list):
        xref = img_info[0]
        
        # Extract the actual image data FIRST
        try:
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]  # jpeg, png, etc.
            
            # Apply page rotation to the image BEFORE getting rectangle
            if page_rotation != 0:
                image_bytes = _rotate_image(image_bytes, page_rotation, image_ext, verbose)
            
            # Now get image position and size from PDF
            img_rects = page.get_image_rects(xref)
            
            if not img_rects:
                if verbose:
                    print(f"  Warning: Could not find position for image {img_index}")
                continue
            
            # Use first rectangle (there may be multiple if image is reused)
            rect = img_rects[0]
            
            # Adjust rectangle dimensions if image was rotated 90 or 270 degrees
            # (rotation swaps width and height)
            if page_rotation in [90, 270]:
                # Swap width and height to match rotated image dimensions
                original_width = rect.width
                original_height = rect.height
                rect = fitz.Rect(rect.x0, rect.y0, rect.x0 + original_height, rect.y0 + original_width)
                if verbose:
                    print(f"  Image {img_index}: Swapped rect dimensions due to {page_rotation}° rotation: {original_width:.1f}x{original_height:.1f} → {rect.width:.1f}x{rect.height:.1f}")
            
            # Check if this image should be segmented into multiple photos
            if should_segment_image(rect.width, rect.height, page_rect.width, page_rect.height):
                if verbose:
                    print(f"  Image {img_index}: Large composite image, segmenting...")
                
                # Store the original composite image data for later GUI access
                composite_data = {
                    'index': img_index,
                    'xref': xref,
                    'area_left': rect.x0,
                    'area_top': rect.y0,
                    'area_width': rect.width,
                    'area_height': rect.height,
                    'data': image_bytes,
                    'format': image_ext,
                    'is_composite': True  # Mark as the original composite image
                }
                page_data['composite_image'] = composite_data
                
                # Segment the image
                segments = segment_composite_image(image_bytes, image_ext, verbose=verbose)
                
                # Get the actual image dimensions
                from PIL import Image as PILImage
                from io import BytesIO
                temp_img = PILImage.open(BytesIO(image_bytes))
                
                # Save composite image if debug mode enabled (after loading temp_img)
                if debug:
                    debug_path = f"/tmp/composite_build_page{ui_page if ui_page is not None else page_num}.{image_ext}"
                    temp_img.save(debug_path)
                    print(f"  DEBUG: Saved composite image to {debug_path}")
                img_width_pixels = temp_img.width
                img_height_pixels = temp_img.height
                
                # Calculate scale factors from image pixels to PDF points
                # The image is displayed at rect.width x rect.height on the page
                # But the actual image is img_width_pixels x img_height_pixels
                scale_x = rect.width / img_width_pixels
                scale_y = rect.height / img_height_pixels
                
                # Add each segment as a separate image
                for seg_index, segment in enumerate(segments):
                    # Convert segment coordinates from image pixels to PDF points
                    segment_left_points = segment['left'] * scale_x
                    segment_top_points = segment['top'] * scale_y
                    segment_width_points = segment['width'] * scale_x
                    segment_height_points = segment['height'] * scale_y
                    
                    # Calculate absolute position on page
                    abs_left = rect.x0 + segment_left_points
                    abs_top = rect.y0 + segment_top_points
                    
                    seg_data = {
                        'index': img_index * 1000 + seg_index,  # Unique index
                        'xref': xref,
                        'area_left': abs_left,
                        'area_top': abs_top,
                        'area_width': segment_width_points,
                        'area_height': segment_height_points,
                        'data': segment['data'],
                        'format': segment['format'],
                    }
                    
                    page_data['photos'].append(seg_data)
                    
                    if verbose:
                        print(f"    Segment {seg_index}: {segment_width_points:.1f}x{segment_height_points:.1f} at ({abs_left:.1f}, {abs_top:.1f})")
            else:
                # Small image, use as-is
                image_data = {
                    'index': img_index,
                    'xref': xref,
                    'area_left': rect.x0,
                    'area_top': rect.y0,
                    'area_width': rect.width,
                    'area_height': rect.height,
                    'data': image_bytes,
                    'format': image_ext,
                }
                
                page_data['photos'].append(image_data)
                
                if verbose:
                    print(f"  Image {img_index}: {rect.width:.1f}x{rect.height:.1f} at ({rect.x0:.1f}, {rect.y0:.1f})")
                
        except Exception as e:
            if verbose:
                print(f"  Warning: Could not extract image {img_index}: {e}")
    
    # Extract text blocks
    blocks = page.get_text("dict")["blocks"]
    text_block_index = 0
    
    for block in blocks:
        if block['type'] == 0:  # Text block (type 1 is image)
            for line in block.get('lines', []):
                for span in line.get('spans', []):
                    text = span['text'].strip()
                    if not text:
                        continue
                    
                    bbox = span['bbox']
                    
                    text_data = {
                        'index': text_block_index,
                        'text': text,
                        'area_left': bbox[0],
                        'area_top': bbox[1],
                        'area_width': bbox[2] - bbox[0],
                        'area_height': bbox[3] - bbox[1],
                        'font': span['font'],
                        'size': span['size'],
                        'color': span.get('color', 0),  # RGB color as integer
                        'flags': span['flags'],  # Font flags (bold, italic, etc.)
                    }
                    
                    page_data['texts'].append(text_data)
                    text_block_index += 1
                    
                    if verbose:
                        print(f"  Text: '{text[:50]}...' font={span['font']} size={span['size']:.1f}")
    
    # Merge adjacent text blocks (touching or very close vertically)
    page_data['texts'] = merge_adjacent_text_blocks(page_data['texts'], verbose)
    
    if verbose:
        print(f"  Found {len(page_data['photos'])} images and {len(page_data['texts'])} text blocks (after merging)")
    
    # Convert all coordinates from PDF points to MCF spread coordinates
    # This is the ONLY place PDF points are converted - everything downstream uses MCF
    page_rect = page.rect
    page_width_pdf = page_rect.width
    # Use ui_page for positioning if provided (determines LEFT/RIGHT side)
    positioning_page = ui_page if ui_page is not None else page_num
    page_data = _convert_page_to_mcf_coordinates(page_data, positioning_page, total_pages, page_width_pdf)
    
    return page_data


def merge_adjacent_text_blocks(text_blocks: List[Dict[str, Any]], verbose: bool = False) -> List[Dict[str, Any]]:
    """Merge text blocks that are vertically adjacent (touching or very close).
    
    Args:
        text_blocks: List of text block dictionaries
        verbose: Print debug info
        
    Returns:
        List of merged text blocks
    """
    if not text_blocks:
        return text_blocks
    
    # Sort by vertical position (top), then horizontal position (left)
    sorted_blocks = sorted(text_blocks, key=lambda b: (b['area_top'], b['area_left']))
    
    merged = []
    current_group = [sorted_blocks[0]]
    
    for block in sorted_blocks[1:]:
        # Check if this block is adjacent to the last block in current group
        last_block = current_group[-1]
        
        # Calculate vertical gap (positive = gap, negative = overlap)
        gap = block['area_top'] - (last_block['area_top'] + last_block['area_height'])
        
        # Check horizontal overlap (are they in roughly the same column?)
        horizontal_overlap = not (block['area_left'] > last_block['area_left'] + last_block['area_width'] or
                                 last_block['area_left'] > block['area_left'] + block['area_width'])
        
        # Merge threshold: within 5 pixels vertically and horizontally overlapping
        if abs(gap) <= 5 and horizontal_overlap:
            # Add to current group
            current_group.append(block)
        else:
            # Start new group - first merge current group if it has multiple blocks
            if len(current_group) > 1:
                merged.append(merge_text_group(current_group))
            else:
                merged.append(current_group[0])
            current_group = [block]
    
    # Don't forget the last group
    if len(current_group) > 1:
        merged.append(merge_text_group(current_group))
    else:
        merged.append(current_group[0])
    
    if verbose and len(merged) < len(text_blocks):
        print(f"  Merged {len(text_blocks)} text blocks into {len(merged)}")
    
    return merged


def merge_text_group(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge multiple text blocks into one.
    
    Args:
        blocks: List of text blocks to merge
        
    Returns:
        Single merged text block
    """
    # Calculate bounding box
    left = min(b['area_left'] for b in blocks)
    top = min(b['area_top'] for b in blocks)
    right = max(b['area_left'] + b['area_width'] for b in blocks)
    bottom = max(b['area_top'] + b['area_height'] for b in blocks)
    
    # Concatenate text with spaces
    text = ' '.join(b['text'] for b in blocks)
    
    # Use properties from first block as base
    merged = blocks[0].copy()
    merged.update({
        'area_left': left,
        'area_top': top,
        'area_width': right - left,
        'area_height': bottom - top,
        'text': text,
    })
    
    return merged

def _get_page_positioning(page_num: Any, total_pages: int, page_width_mcf: float) -> tuple[bool, float]:
    """Determine if a page is on the right side and calculate x-offset.
    
    Page positioning rules based on UI page number:
    - "F" (front cover): RIGHT side of cover spread
    - "B" (back cover): LEFT side of cover spread
    - UI page 0 (inside front): LEFT side
    - Other odd UI pages (1,3,5...): RIGHT side of content spreads
    - Other even UI pages (2,4,6...): LEFT side of content spreads
    
    Args:
        page_num: UI page number (can be "F", "B", or integer 0, 1, 2, ...)
        total_pages: Total number of pages in PDF
        page_width_mcf: Single page width in MCF units
        
    Returns:
        (is_right_page, x_offset_mcf) tuple
    """
    # Handle string identifiers for covers
    if page_num == "F":
        # Front cover is on RIGHT side
        return True, page_width_mcf
    elif page_num == "B":
        # Back cover is on LEFT side
        return False, 0.0
    
    # Handle integer page numbers
    # Page 0 (inside front) is LEFT (even)
    # Odd pages (1,3,5...) are RIGHT
    # Even pages (2,4,6...) are LEFT
    is_right_page = (page_num % 2 == 1)
    x_offset_mcf = page_width_mcf if is_right_page else 0.0
    return is_right_page, x_offset_mcf


def _convert_page_to_mcf_coordinates(page_data: Dict[str, Any], page_num: int, total_pages: int, page_width_pdf: float) -> Dict[str, Any]:
    """Convert all coordinates in page_data from PDF points to MCF spread coordinates.
    
    This is the single point of conversion from PDF coordinate space to MCF coordinate space.
    After this conversion, all coordinates are in MCF units and positioned correctly
    in the spread (with right pages offset by page_width_mcf).
    
    Args:
        page_data: Page data dict with coordinates in PDF points
        page_num: PDF page number (0-indexed)
        page_width_pdf: Width of one page in PDF points
        
    Returns:
        Modified page_data with all coordinates in MCF spread units
        
    """
    PT_TO_MCF = 3.52778  # 1 PDF point = 25.4mm/72 = 0.352778mm = 3.52778 * 0.1mm

    # Calculate page dimensions in MCF units and round to nearest integer
    # This ensures consistent dimensions throughout the photobook and avoids
    # floating-point errors placing photos on wrong pages (e.g., 2825.8 vs 2826.0)
    #
    # FUTURE: Consider allowing user to override page size here to:
    #   (a) Scale the entire book to a different size (e.g., change aspect ratio)
    #   (b) Snap to one of CEWE's standard printable sizes (e.g., 21x28cm, 28x21cm)
    #       to ensure the resulting MCF can be physically printed
    page_width_mcf = round(page_width_pdf * PT_TO_MCF)
    # page_num here is the UI page identifier (from ui_page parameter in extract_page_content)
    is_right_page, x_offset_mcf = _get_page_positioning(page_num, total_pages, page_width_mcf)

    logger.info(f"Converting UI page {page_num} to MCF: is_right={is_right_page}, x_offset={x_offset_mcf:.1f} MCF")
    
    def convert_coords(item: Dict[str, Any]) -> None:
        """Convert area_left/area_top/area_width/area_height from PDF points to MCF spread coordinates in-place."""
        if 'area_left' in item:
            item['area_left'] = item['area_left'] * PT_TO_MCF + x_offset_mcf
        if 'area_top' in item:
            item['area_top'] = item['area_top'] * PT_TO_MCF
        if 'area_width' in item:
            item['area_width'] = item['area_width'] * PT_TO_MCF
        if 'area_height' in item:
            item['area_height'] = item['area_height'] * PT_TO_MCF
    
    # Convert composite image coordinates
    if 'composite_image' in page_data and page_data['composite_image']:
        convert_coords(page_data['composite_image'])
        logger.debug(f"  Composite: area_left={page_data['composite_image']['area_left']:.1f} MCF")
    
    # Convert all image coordinates
    for img in page_data.get('photos', []):
        convert_coords(img)
    
    # Convert all text block coordinates  
    for text in page_data.get('texts', []):
        convert_coords(text)
    
    # Convert page dimensions from PDF points to MCF units
    if 'width' in page_data:
        page_data['width'] = page_data['width'] * PT_TO_MCF
    if 'height' in page_data:
        page_data['height'] = page_data['height'] * PT_TO_MCF
    
    # Store the conversion info for reference
    page_data['_coordinate_system'] = 'mcf_spread'
    page_data['_mcf_x_offset'] = x_offset_mcf
    page_data['_is_right_page'] = is_right_page
    
    return page_data


    return is_right_page, x_offset_mcf


def _makeScaledSegments(composite_image, ui_page, image_data, image_format,
                        new_segments: list[dict[str, Any]]) -> list[Any]:
    """Scale segments from image pixels to PDF-based MCF coordinates.
    
    The composite_image dict has coordinates in PDF-based MCF spread units (converted by
    _convert_page_to_mcf_coordinates from the original PDF dimensions).
    
    This function stores TWO coordinate systems for each segment:
    1. PDF-based coordinates (for extracting photo data from composite image)
    2. Image-relative pixel coordinates (for scaling to CEWE book dimensions in GUI)
    
    The GUI will need to scale these coordinates to match the actual CEWE book dimensions,
    just like it does for the composite background image.
    
    Args:
        composite_image: Composite image dict with PDF-based MCF spread coordinates
        ui_page: UI page identifier ("F", "B", 0, 1, ...) for debugging
        image_data: Raw image bytes
        image_format: Image format (jpg, png, etc)
        new_segments: List of segments with coordinates in image pixels
        
    Returns:
        List of segments with both PDF-based MCF coords and original pixel coords
    """
    from PIL import Image as PILImage
    from io import BytesIO
    temp_img = PILImage.open(BytesIO(image_data))
    img_width_pixels = temp_img.width
    img_height_pixels = temp_img.height

    # DEBUG: Save composite image to see what we're segmenting
    debug_path = f"/tmp/composite_page{ui_page}.{image_format}"
    temp_img.save(debug_path)
    print(f"  DEBUG: Saved composite image to {debug_path}")

    print(
        f"  Composite image (PDF-based MCF coords): left={composite_image.get('area_left'):.1f}, top={composite_image.get('area_top'):.1f}, "
        f"width={composite_image.get('area_width'):.1f}, height={composite_image.get('area_height'):.1f}")

    # Calculate scale factors (pixels to PDF-based MCF units)
    scale_x = composite_image['area_width'] / img_width_pixels
    scale_y = composite_image['area_height'] / img_height_pixels

    print(
        f"  Image: {img_width_pixels}x{img_height_pixels} pixels -> {composite_image['area_width']:.1f}x{composite_image['area_height']:.1f} MCF")
    print(f"  Scale factors: x={scale_x:.4f}, y={scale_y:.4f} MCF/pixel")

    # Scale segment coordinates from image pixels to PDF-based MCF spread coordinates
    scaled_segments = []
    for i, seg in enumerate(new_segments):
        # Scale from image pixels to PDF-based MCF units (same scale as composite)
        seg_left_mcf = seg['left'] * scale_x
        seg_top_mcf = seg['top'] * scale_y
        seg_width_mcf = seg['width'] * scale_x
        seg_height_mcf = seg['height'] * scale_y

        # Add composite image position to make absolute PDF-based MCF spread coordinates
        abs_left_mcf = composite_image['area_left'] + seg_left_mcf
        abs_top_mcf = composite_image['area_top'] + seg_top_mcf

        print(f"  Segment {i} in pixels: ({seg['left']}, {seg['top']}) {seg['width']}x{seg['height']}")
        print(
            f"  Segment {i} (image-relative MCF): ({seg_left_mcf:.1f}, {seg_top_mcf:.1f}) {seg_width_mcf:.1f}x{seg_height_mcf:.1f}")
        print(
            f"  Segment {i} (PDF-based MCF spread coords): ({abs_left_mcf:.1f}, {abs_top_mcf:.1f}) {seg_width_mcf:.1f}x{seg_height_mcf:.1f}")

        scaled_seg = {
            # PDF-based MCF coordinates (for reference, but GUI will need to scale)
            'left': abs_left_mcf,
            'top': abs_top_mcf,
            'width': seg_width_mcf,
            'height': seg_height_mcf,
            # Original pixel coordinates relative to composite image (for extraction and scaling)
            'pixel_left': seg['left'],
            'pixel_top': seg['top'],
            'pixel_width': seg['width'],
            'pixel_height': seg['height'],
            # Image data
            'data': seg['data'],
            'format': seg['format'],
        }
        scaled_segments.append(scaled_seg)
    return scaled_segments


def _getPdfPage(pdf_originalBook: PDFPhotobook, current_pageno) -> Any:
    """Get PDF page data using the unified API.
    
    Args:
        pdf_originalBook: PDF PhotoBook
        current_pageno: Page number (0-indexed)
        
    Returns:
        Page data dict or None if page doesn't exist
    """
    page_count = pdf_originalBook.get_page_count()
    print(f"  PDF has {page_count} pages")
    
    if current_pageno >= page_count:
        print(f"Error: CEWE page {current_pageno} not found in PDF content (PDF has {page_count} pages)")
        return None
    
    # Use unified API - works for both on-demand and pre-loaded modes
    pdf_page = get_page_content(pdf_originalBook, current_pageno)
    if not pdf_page:
        print(f"Error: Failed to extract page {current_pageno}")
        return None
    
    return pdf_page


def _getImageToSegment(pages, index, status_var, current_pageno, pdf_page, specific_photo_index: int | None) -> tuple[Any, list[int]]:

    photos_to_replace = []  # Track which photos will be replaced

    if specific_photo_index is not None:
        # Mode 2: Re-segment a specific photo
        # Find the corresponding image in the PDF page
        _, page_info = pages[index]
        photos = page_info.get('photos', [])

        if specific_photo_index >= len(photos):
            print(f"Error: Photo #{specific_photo_index + 1} not found (page has {len(photos)} photos)")
            status_var.set(f'Error: Photo #{specific_photo_index + 1} not found')
            return None

        # Find the PDF image that corresponds to this photo
        # For now, use the image at the same index (this may need refinement)
        images_with_data = [img for img in pdf_page.get('photos', []) if img.get('data')]
        if specific_photo_index < len(images_with_data):
            image_to_segment = images_with_data[specific_photo_index]
            photos_to_replace = [specific_photo_index]
            print(
                f"  Re-segmenting photo #{specific_photo_index + 1}: {image_to_segment['area_width']:.1f}x{image_to_segment['area_height']:.1f}")
        else:
            print(f"Error: Cannot find PDF image for photo #{specific_photo_index + 1}")
            status_var.set(f'Error: Cannot find image for photo #{specific_photo_index + 1}')
            return None
    else:
        # Mode 1: Re-segment entire page from full PDF page
        # Extract the embedded composite image using explicit marker
        print(f"  Extracting embedded composite image from PDF page {current_pageno}...")

        # Get the explicitly marked composite image from PDF extraction
        image_to_segment = pdf_page.get('composite_image')

        if not image_to_segment:
            print("Error: No composite image found in PDF page data")
            print(f"  Available photos: {len(pdf_page.get('photos', []))}")
            status_var.set('Error: No composite image in page data')
            return None

        # Get actual pixel dimensions
        from PIL import Image as PILImage
        from io import BytesIO
        temp_img = PILImage.open(BytesIO(image_to_segment['data']))
        pixel_width = temp_img.width
        pixel_height = temp_img.height

        # All photos will be replaced
        ui_pageno, page_info = pages[index]
        photos = page_info.get('photos', [])
        photos_to_replace = list(range(len(photos)))
        print(
            f"  Using embedded composite image: {pixel_width}x{pixel_height} pixels ({image_to_segment['area_width']:.1f}x{image_to_segment['area_height']:.1f} MCF units)")

        # DEBUG: Save composite image for comparison
        debug_path = f"/tmp/composite_page{ui_pageno}.{image_to_segment.get('format', 'jpeg')}"
        temp_img.save(debug_path)
        print(f"  DEBUG: Saved composite image to {debug_path}")
    return image_to_segment, photos_to_replace


def _segmentPage(pdf_originalBook, pages, index, status_var, current_pageno, segmenter: ImageSegmenter,
                              specific_photo_index: int | None,
                              target_count: int) -> tuple[list[dict[str, Any]] | None, Any, Any, Any, list[int]]:
    pdf_page = _getPdfPage(pdf_originalBook, current_pageno)
    print(f"  PDF page has {len(pdf_page.get('images', []))} images")

    # Determine which image to re-segment
    image_to_segment, photos_to_replace = _getImageToSegment(pages, index, status_var,
                                                             current_pageno, pdf_page, specific_photo_index)

    if not image_to_segment:
        print(f"No image found to re-segment")
        status_var.set('No image to re-segment')
        return None

    # Get the original image data
    image_data = image_to_segment['data']
    image_format = image_to_segment['format']

    # Try to find segmentation with target count
    print(f"Searching for segmentation with {target_count} photos using {segmenter.get_name()}...")
    new_segments = segmenter.segment_for_count(
        image_data, image_format, target_count, verbose=True
    )

    if not new_segments:
        print(f"Could not achieve target count of {target_count} photos")
        status_var.set(f'❌ Could not find segmentation with {target_count} photos')
        return None

    return new_segments, image_data, image_format, image_to_segment, photos_to_replace


def performSegmentationOnPage(pdf_originalBook: PDFPhotobook, pages, index, status_var, current_pageno, segmenter: ImageSegmenter,
            specific_photo_index: int | None, target_count: int) -> \
tuple[list[int], list[Any], Any, list[dict[str, Any]] | None, Any]:
    result = _segmentPage(
        pdf_originalBook, pages, index, status_var,
        current_pageno, segmenter, specific_photo_index, target_count)
    
    # _segmentPage returns None on failure
    if result is None:
        return None
    
    new_segments, image_data, image_format, image_to_segment, photos_to_replace = result

    if new_segments:
        print(f"✅ Found segmentation with {len(new_segments)} photos")

        # Get UI page identifier for debug filenames
        ui_pageno = pages[index][0]
        scaled_segments = _makeScaledSegments(image_to_segment, ui_pageno, image_data, image_format,
                                          new_segments)
        return scaled_segments, image_data, image_format, image_to_segment, photos_to_replace
    else:
        return None

def _rotate_image(image_bytes: bytes, rotation: int, image_format: str, verbose: bool = False) -> bytes:
    """Rotate an image by the specified angle.
    
    PDF rotation values are clockwise, but PIL's rotate() is counter-clockwise,
    so we negate the angle. Also, PIL's rotate() with expand=True will adjust
    the canvas size to fit the rotated image.
    
    Args:
        image_bytes: Raw image data
        rotation: Rotation angle in degrees (0, 90, 180, 270) - PDF convention (clockwise)
        image_format: Image format (jpeg, png, etc.)
        verbose: Print debug info
        
    Returns:
        Rotated image bytes in the same format
    """
    if rotation == 0:
        return image_bytes
    
    if verbose:
        print(f"    Rotating image by {rotation}° (PDF rotation, applied counter-clockwise)")
    
    try:
        from PIL import Image as PILImage
        from io import BytesIO
        
        # Load image
        img = PILImage.open(BytesIO(image_bytes))
        
        # PDF rotation is clockwise, PIL.rotate() is counter-clockwise
        # So negate the angle: 90° CW = -90° = 270° CCW
        # Also expand=True adjusts canvas to fit rotated image
        pil_rotation = -rotation % 360
        rotated = img.rotate(pil_rotation, expand=True)
        
        # Save back to bytes
        output = BytesIO()
        # Preserve format and quality
        save_kwargs = {}
        if image_format.lower() in ['jpg', 'jpeg']:
            save_kwargs['quality'] = 95
            save_kwargs['optimize'] = True
        rotated.save(output, format=image_format if image_format.lower() != 'jpg' else 'JPEG', **save_kwargs)
        
        return output.getvalue()
        
    except Exception as e:
        logger.warning(f"Failed to rotate image: {e}, returning original")
        return image_bytes


def _create_page_mapping(input_page_count: int, insidecovers: bool = True) -> Dict[str, Optional[int]]:
    """Create mapping from logical page identifiers to PDF/Mimeo/import page indices.

    Args:
        input_page_count: Total number of pages in PDF/Mimeo/import
        insidecovers: Whether PDF includes inside cover pages (default True)

    Returns:
        Dictionary mapping page identifiers to PDF indices (0-based)
        Page identifiers: "F" (front cover), "B" (back cover), 0 (inside front),
                         1..N (content pages), N+1 (inside back)
    """
    mapping = {}

    if insidecovers:
        # WITH --insidecovers: PDF has [0=front, 1=inside_front, 2..N-2=content, N-1=inside_back, N=back]
        mapping["F"] = 0  # Front cover
        mapping[0] = 1    # Inside front cover

        # Content pages: UI pages 1..N-4 map to PDF pages 2..N-2
        content_pages = input_page_count - 4  # Exclude front, inside_front, inside_back, back
        for ui_page in range(1, content_pages + 1):
            mapping[ui_page] = ui_page + 1  # UI page 1 → PDF page 2, etc.

        mapping[content_pages + 1] = input_page_count - 2  # Inside back cover
        mapping["B"] = input_page_count - 1  # Back cover
    else:
        # WITHOUT --insidecovers: PDF has [0=front, 1..N-2=content, N-1=back]
        # Inside covers will be empty (None) pages added by extract code
        mapping["F"] = 0  # Front cover
        mapping[0] = None  # Inside front - will be added as empty page

        # Content pages: UI pages 1..N-2 map to PDF pages 1..N-2
        content_pages = input_page_count - 2  # Exclude front, back
        for ui_page in range(1, content_pages + 1):
            mapping[ui_page] = ui_page  # UI page 1 → PDF page 1, etc.

        mapping[content_pages + 1] = None  # Inside back - will be added as empty page
        mapping["B"] = input_page_count - 1  # Back cover

    return mapping
