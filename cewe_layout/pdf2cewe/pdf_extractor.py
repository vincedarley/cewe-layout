"""Extract images and text content from PDF files using PyMuPDF."""

import fitz  # PyMuPDF
from pathlib import Path
from typing import Dict, List, Optional, Any
from io import BytesIO
from .image_segmenter import segment_composite_image, should_segment_image


def extract_pdf_content(pdf_path: Path, page_range: Optional[List[int]] = None, verbose: bool = False) -> Dict[str, Any]:
    """Extract all images and text from a PDF file.
    
    Args:
        pdf_path: Path to PDF file
        page_range: Optional list of 0-indexed page numbers to process
        verbose: Print detailed extraction info
        
    Returns:
        Dictionary containing:
            - 'metadata': PDF metadata (title, author, etc.)
            - 'page_size': (width, height) in points
            - 'pages': List of page data dictionaries
    """
    doc = fitz.open(pdf_path)
    
    # Get metadata
    metadata = {
        'title': doc.metadata.get('title', ''),
        'author': doc.metadata.get('author', ''),
        'subject': doc.metadata.get('subject', ''),
        'producer': doc.metadata.get('producer', ''),
    }
    
    # Determine which pages to process
    if page_range is None:
        page_range = list(range(len(doc)))
    
    pages = []
    for page_num in page_range:
        if page_num >= len(doc):
            if verbose:
                print(f"Warning: Page {page_num + 1} does not exist, skipping")
            continue
            
        page = doc[page_num]
        page_data = extract_page_content(page, page_num, verbose)
        pages.append(page_data)
    
    # Get consistent page size from first page
    first_page = doc[page_range[0]] if page_range else doc[0]
    page_size = (first_page.rect.width, first_page.rect.height)
    
    doc.close()
    
    return {
        'metadata': metadata,
        'page_size': page_size,
        'pages': pages,
    }


def extract_page_content(page: fitz.Page, page_num: int, verbose: bool = False) -> Dict[str, Any]:
    """Extract content from a single PDF page.
    
    Args:
        page: PyMuPDF Page object
        page_num: Page number (0-indexed)
        verbose: Print detailed info
        
    Returns:
        Dictionary with 'images' and 'text_blocks' lists
    """
    if verbose:
        print(f"Processing page {page_num + 1}...")
    
    page_rect = page.rect
    page_data = {
        'page_num': page_num,
        'width': page_rect.width,
        'height': page_rect.height,
        'images': [],
        'text_blocks': [],
    }
    
    # Extract images
    image_list = page.get_images(full=True)
    for img_index, img_info in enumerate(image_list):
        xref = img_info[0]
        
        # Get image position and size
        img_rects = page.get_image_rects(xref)
        
        if not img_rects:
            if verbose:
                print(f"  Warning: Could not find position for image {img_index}")
            continue
        
        # Use first rectangle (there may be multiple if image is reused)
        rect = img_rects[0]
        
        # Extract the actual image data
        try:
            base_image = page.parent.extract_image(xref)
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]  # jpeg, png, etc.
            
            # Check if this image should be segmented into multiple photos
            if should_segment_image(rect.width, rect.height, page_rect.width, page_rect.height):
                if verbose:
                    print(f"  Image {img_index}: Large composite image, segmenting...")
                
                # Segment the image
                segments = segment_composite_image(image_bytes, image_ext, verbose=verbose)
                
                # Get the actual image dimensions
                from PIL import Image as PILImage
                temp_img = PILImage.open(BytesIO(image_bytes))
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
                        'left': abs_left,
                        'top': abs_top,
                        'width': segment_width_points,
                        'height': segment_height_points,
                        'data': segment['data'],
                        'format': segment['format'],
                    }
                    
                    page_data['images'].append(seg_data)
                    
                    if verbose:
                        print(f"    Segment {seg_index}: {segment_width_points:.1f}x{segment_height_points:.1f} at ({abs_left:.1f}, {abs_top:.1f})")
            else:
                # Small image, use as-is
                image_data = {
                    'index': img_index,
                    'xref': xref,
                    'left': rect.x0,
                    'top': rect.y0,
                    'width': rect.width,
                    'height': rect.height,
                    'data': image_bytes,
                    'format': image_ext,
                }
                
                page_data['images'].append(image_data)
                
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
                        'left': bbox[0],
                        'top': bbox[1],
                        'width': bbox[2] - bbox[0],
                        'height': bbox[3] - bbox[1],
                        'font': span['font'],
                        'size': span['size'],
                        'color': span.get('color', 0),  # RGB color as integer
                        'flags': span['flags'],  # Font flags (bold, italic, etc.)
                    }
                    
                    page_data['text_blocks'].append(text_data)
                    text_block_index += 1
                    
                    if verbose:
                        print(f"  Text: '{text[:50]}...' font={span['font']} size={span['size']:.1f}")
    
    # Merge adjacent text blocks (touching or very close vertically)
    page_data['text_blocks'] = merge_adjacent_text_blocks(page_data['text_blocks'], verbose)
    
    if verbose:
        print(f"  Found {len(page_data['images'])} images and {len(page_data['text_blocks'])} text blocks (after merging)")
    
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
    sorted_blocks = sorted(text_blocks, key=lambda b: (b['top'], b['left']))
    
    merged = []
    current_group = [sorted_blocks[0]]
    
    for block in sorted_blocks[1:]:
        # Check if this block is adjacent to the last block in current group
        last_block = current_group[-1]
        
        # Calculate vertical gap (positive = gap, negative = overlap)
        gap = block['top'] - (last_block['top'] + last_block['height'])
        
        # Check horizontal overlap (are they in roughly the same column?)
        horizontal_overlap = not (block['left'] > last_block['left'] + last_block['width'] or
                                 last_block['left'] > block['left'] + block['width'])
        
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
    left = min(b['left'] for b in blocks)
    top = min(b['top'] for b in blocks)
    right = max(b['left'] + b['width'] for b in blocks)
    bottom = max(b['top'] + b['height'] for b in blocks)
    
    # Concatenate text with spaces
    text = ' '.join(b['text'] for b in blocks)
    
    # Use properties from first block as base
    merged = blocks[0].copy()
    merged.update({
        'left': left,
        'top': top,
        'width': right - left,
        'height': bottom - top,
        'text': text,
    })
    
    return merged
