"""Utilities for transforming photobooks (rearranging, merging, etc.).

This module provides shared infrastructure for photobook transformations like:
- Moving inside cover content to regular content pages
- Merging multiple photobooks into one
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Tuple

from .photobook import Photobook, PhotobookPage
from .cewe_photobook import CEWEPhotobook
from ..file_utils import extract_metadata_from_filename, encode_metadata_in_filename

logger = logging.getLogger(__name__)


def _has_content(page: PhotobookPage) -> bool:
    """Check if a page has any photos or text content."""
    page_info = page.get_page_info()
    return (len(page_info.get('photos', [])) > 0 or 
            len(page_info.get('texts', [])) > 0)


def _copy_image_file(old_filename: str, new_filename: str, source_dir: Path, output_dir: Path):
    """Copy an image file from source to output directory.
    
    Args:
        old_filename: Original filename (may have safecontainer:/ prefix)
        new_filename: New filename (may have safecontainer:/ prefix)
        source_dir: Directory containing source image
        output_dir: Directory to copy image to
    """
    # Strip safecontainer prefix for file operations
    old_clean = old_filename.replace('safecontainer:/', '')
    new_clean = new_filename.replace('safecontainer:/', '')
    
    source_path = source_dir / old_clean
    dest_path = output_dir / new_clean
    
    if source_path.exists():
        shutil.copy2(source_path, dest_path)
        logger.debug(f"Copied image: {old_clean} -> {new_clean}")
    else:
        logger.warning(f"Source image not found: {source_path}")


def copy_page_data(
    page_data: Dict[str, Any],
    old_page_number: Union[str, int],
    new_page_number: Union[str, int],
    source_dir: Path,
    output_dir: Path
) -> Dict[str, Any]:
    """Copy page data, updating image filenames and copying image files.
    
    Works for both renumbered pages and unchanged page numbers. When page number
    is unchanged, images are still copied from source_dir to output_dir.
    
    Args:
        page_data: Original page data dict
        old_page_number: Original page number (for filename parsing/validation)
        new_page_number: New page number (for filename encoding, may equal old_page_number)
        source_dir: Directory containing source images
        output_dir: Directory to copy images to
        
    Returns:
        Updated page data dict with new filenames
    """
    # Deep copy page data (except photos and texts which we'll rebuild)
    new_data = {k: v for k, v in page_data.items() if k not in ('photos', 'texts')}
    new_data['photos'] = []
    new_data['texts'] = list(page_data.get('texts', []))  # Text blocks don't have files
    
    for photo in page_data.get('photos', []):
        new_photo = photo.copy()
        old_filename = photo['filename']
        
        if (old_filename is None):
            # This is an empty photo slot - not a problem - the user is likely to fill it later
            new_photo['filename'] = None
            logger.warning(f"Empty photo slot on page {old_page_number}.")

        else:
            # Parse and update filename
            base_name, size, page_from_filename = extract_metadata_from_filename(old_filename)
            
            # Validation: if filename has page number, it should match expected old_page_number
            if page_from_filename is not None and page_from_filename != old_page_number:
                logger.warning(f"Page number mismatch: filename {old_filename} has {page_from_filename}, expected {old_page_number}. This can happen if you've been re-arranging pages with CEWE. We will automatically adjust.")
            
            new_filename = encode_metadata_in_filename(base_name, size, new_page_number)
            
            # Handle safecontainer prefix
            if old_filename.startswith('safecontainer:/'):
                new_filename = f'safecontainer:/{new_filename}'
            
            new_photo['filename'] = new_filename
            
            # Copy physical file
            _copy_image_file(old_filename, new_filename, source_dir, output_dir)
        
        new_data['photos'].append(new_photo)
    
    return new_data


def build_cewe_photobook(
    pages: List[Tuple[Union[str, int], Dict[str, Any]]],
    metadata: Optional[Dict[str, str]] = None
) -> CEWEPhotobook:
    """Build a CEWEPhotobook from a list of (page_number, page_data) tuples.
    
    Args:
        pages: List of (page_number, page_data) tuples
        metadata: Optional metadata dict
        
    Returns:
        CEWEPhotobook instance
    """
    return CEWEPhotobook(pages, metadata)


def create_photobook_copy(
    source_photobook: Photobook,
    source_dir: Path,
    output_dir: Path
) -> CEWEPhotobook:
    """Create a copy of a photobook with all images copied to output directory.
    
    This copies all pages without rearrangement, copying image files and updating
    filenames in the page data to point to the output directory.
    
    Args:
        source_photobook: Source photobook to copy
        source_dir: Directory containing source images
        output_dir: Directory to copy images to (should already exist)
        
    Returns:
        New CEWEPhotobook with copied pages and images
    """
    logger.info(f"Creating photobook copy: {source_photobook.get_page_count()} pages")
    
    pages = []
    
    # Copy all pages in order, using copy_page_data to handle images
    for index, page in source_photobook.enumerate_pages():
        if page is None:
            raise ValueError(f"Encountered None page at index {index}. CEWE photobooks should never have None pages.")
            
        page_info = page.get_page_info()
        page_num = page.get_page_number()
        
        # Use copy_page_data with same page number (no renumbering, just copying)
        new_data = copy_page_data(
            page_info, page_num, page_num, source_dir, output_dir
        )
        pages.append((page_num, new_data))
    
    logger.info(f"Photobook copy complete: {len(pages)} pages")
    
    return build_cewe_photobook(pages, source_photobook.get_metadata())


def create_photobook_with_inside_covers_at_end(
    source_photobook: Photobook,
    source_dir: Path,
    output_dir: Path
) -> CEWEPhotobook:
    """Create new photobook with inside cover content moved to new pages at end.
    
    This transforms a photobook with N content pages (N must be even) into one with
    N+4 content pages. The old inside cover pages (if they have content) are moved to
    new content pages N+2 and N+3. Four new pages are inserted after page N:
    - Page N+1: empty
    - Page N+2: old inside front cover content
    - Page N+3: old inside back cover content  
    - Page N+4: empty
    
    This ensures content from inside covers (which CEWE Creator ignores) becomes
    visible and editable as regular content pages.
    
    Args:
        source_photobook: Source photobook to transform
        source_dir: Directory containing source images
        output_dir: Directory to copy images to (should already exist)
        
    Returns:
        New CEWEPhotobook with rearranged pages
        
    Raises:
        ValueError: If N is not even (violates photobook invariant)
    """
    N = source_photobook.get_content_page_count()
    
    # Assert that N is even (pages come in spreads)
    if N % 2 != 0:
        raise ValueError(f"Content page count must be even (got N={N}). Photobook structure is invalid.")
    
    logger.info(f"Transforming photobook: moving inside covers to end (N={N} -> N+4={N+4})")
    
    pages = []
    
    # 1. Copy front cover (and its images)
    front = source_photobook.get_front_cover_page()
    if front is None:
        raise ValueError("Source photobook must have a front cover")
    front_data = copy_page_data(
        front.get_page_info(), "F", "F", source_dir, output_dir
    )
    pages.append(("F", front_data))
    
    # 2. Create new empty inside front
    empty_template = source_photobook.create_empty_page_template()
    pages.append((0, empty_template.copy()))
    logger.debug("Created new empty inside front cover")
    
    # 3. Copy all content pages (1..N) and their images
    for i in range(1, N+1):
        page = source_photobook.find_page_by_ui_num(i)
        if page is None:
            raise ValueError(f"Missing content page {i}")
        page_data = copy_page_data(
            page.get_page_info(), i, i, source_dir, output_dir
        )
        pages.append((i, page_data))
    logger.debug(f"Copied content pages 1..{N} with images")
    
    # 4-7. Add 4 new pages: empty, old-inside-front, old-inside-back, empty
    # This preserves left/right alternation
    
    # Page N+1: empty (continues alternation from page N)
    pages.append((N+1, empty_template.copy()))
    logger.debug(f"Created empty page {N+1}")
    
    # Page N+2: old inside front content (if it exists)
    old_inside_front = source_photobook.get_inside_front_page()
    if old_inside_front and _has_content(old_inside_front):
        new_data = copy_page_data(
            old_inside_front.get_page_info(), 0, N+2, source_dir, output_dir
        )
        pages.append((N+2, new_data))
        logger.info(f"Moved old inside front cover content to page {N+2}")
    else:
        pages.append((N+2, empty_template.copy()))
        logger.debug(f"No content on old inside front, created empty page {N+2}")
    
    # Page N+3: old inside back content (if it exists)
    old_inside_back = source_photobook.get_inside_back_page()
    if old_inside_back and _has_content(old_inside_back):
        new_data = copy_page_data(
            old_inside_back.get_page_info(), N+1, N+3, source_dir, output_dir
        )
        pages.append((N+3, new_data))
        logger.info(f"Moved old inside back cover content to page {N+3}")
    else:
        pages.append((N+3, empty_template.copy()))
        logger.debug(f"No content on old inside back, created empty page {N+3}")
    
    # Page N+4: empty
    pages.append((N+4, empty_template.copy()))
    logger.debug(f"Created empty page {N+4}")
    
    # 8. Create new empty inside back
    pages.append((N+5, empty_template.copy()))
    logger.debug("Created new empty inside back cover")
    
    # 9. Copy back cover (and its images)
    back = source_photobook.get_back_cover_page()
    if back is None:
        raise ValueError("Source photobook must have a back cover")
    back_data = copy_page_data(
        back.get_page_info(), "B", "B", source_dir, output_dir
    )
    pages.append(("B", back_data))
    
    logger.info(f"Transformation complete: {len(pages)} pages total (was {source_photobook.get_page_count()})")
    
    return build_cewe_photobook(pages, source_photobook.get_metadata())


def merge_photobooks(
    book1: Photobook,
    book2: Photobook,
    source_dir1: Path,
    source_dir2: Path,
    output_dir: Path
) -> CEWEPhotobook:
    """Merge two photobooks by inserting book2's content into book1.
    
    Book2's covers are converted to content pages. All of book2's pages are inserted
    after book1's last content page. A blank page may be inserted before book2's content
    to ensure pages maintain their left/right orientation (book2's front cover must be
    on a right-hand page, i.e., odd numbered).
    
    The result uses book1's covers and metadata.
    
    Args:
        book1: First photobook (provides covers and initial content)
        book2: Second photobook (content will be inserted into book1)
        source_dir1: Directory containing book1's images
        source_dir2: Directory containing book2's images
        output_dir: Directory to copy images to (should already exist)
        
    Returns:
        New CEWEPhotobook with merged content
        
    Raises:
        ValueError: If N1 or N2 is not even (violates photobook invariant)
    """
    N1 = book1.get_content_page_count()
    N2 = book2.get_content_page_count()
    
    # Assert that both N values are even
    if N1 % 2 != 0:
        raise ValueError(f"Book1 content page count must be even (got N1={N1})")
    if N2 % 2 != 0:
        raise ValueError(f"Book2 content page count must be even (got N2={N2})")
    
    logger.info(f"Merging photobooks: book1 (N={N1}) + book2 (N={N2})")
    
    pages = []
    
    # Copy book1's front cover and its images
    front1 = book1.get_front_cover_page()
    if front1 is None:
        raise ValueError("Book1 must have a front cover")
    front1_data = copy_page_data(
        front1.get_page_info(), "F", "F", source_dir1, output_dir
    )
    pages.append(("F", front1_data))
    
    # Copy book1's inside front (or create empty if not present)
    if book1.has_inside_covers():
        inside = book1.get_inside_front_page()
        if inside:
            inside_data = copy_page_data(
                inside.get_page_info(), 0, 0, source_dir1, output_dir
            )
            pages.append((0, inside_data))
        else:
            pages.append((0, book1.create_empty_page_template()))
    else:
        pages.append((0, book1.create_empty_page_template()))
    
    # Copy book1's content pages and their images
    for i in range(1, N1+1):
        page = book1.find_page_by_ui_num(i)
        if page is None:
            raise ValueError(f"Missing content page {i} in book1")
        page_data = copy_page_data(
            page.get_page_info(), i, i, source_dir1, output_dir
        )
        pages.append((i, page_data))
    logger.debug(f"Copied book1 pages 1..{N1} with images")
    
    # Ensure book2's front cover goes on a RIGHT page (odd numbered)
    # Book2's front cover was originally a RIGHT page, so we need to preserve that
    next_page_num = N1 + 1
    if next_page_num % 2 == 0:
        # Next page is even (LEFT), so insert a blank page first
        empty_template = book1.create_empty_page_template()
        pages.append((next_page_num, empty_template))
        logger.info(f"Inserted blank page {next_page_num} to maintain left/right orientation")
        next_page_num += 1
    
    # Copy all pages from book2, converting them to content pages
    for index, page in book2.enumerate_pages():
        if page is None:
            raise ValueError(f"Encountered None page at index {index} in book2. CEWE photobooks should never have None pages.")
        
        old_page_num = page.get_page_number()
        new_data = copy_page_data(
            page.get_page_info(), old_page_num, next_page_num, source_dir2, output_dir
        )
        pages.append((next_page_num, new_data))
        next_page_num += 1
    
    logger.info(f"Converted all {book2.get_page_count()} pages from book2 to content pages")
    
    # Ensure book1's inside back cover goes on a RIGHT page (odd numbered)
    # Inside back covers are originally RIGHT pages
    if next_page_num % 2 == 0:
        # Next page is even (LEFT), so insert a blank page first
        empty_template = book1.create_empty_page_template()
        pages.append((next_page_num, empty_template))
        logger.info(f"Inserted blank page {next_page_num} to maintain left/right orientation before inside back")
        next_page_num += 1
    
    # Copy book1's inside back and its images
    if book1.has_inside_covers():
        inside = book1.get_inside_back_page()
        if inside:
            inside_data = copy_page_data(
                inside.get_page_info(), N1+1, next_page_num, source_dir1, output_dir
            )
            pages.append((next_page_num, inside_data))
        else:
            pages.append((next_page_num, book1.create_empty_page_template()))
    else:
        pages.append((next_page_num, book1.create_empty_page_template()))
    
    # Copy book1's back cover and its images
    back1 = book1.get_back_cover_page()
    if back1 is None:
        raise ValueError("Book1 must have a back cover")
    back1_data = copy_page_data(
        back1.get_page_info(), "B", "B", source_dir1, output_dir
    )
    pages.append(("B", back1_data))
    
    logger.info(f"Merge complete: {len(pages)} pages total")
    
    return build_cewe_photobook(pages, book1.get_metadata())
