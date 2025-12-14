"""Utilities to modify and write .mcf files safely with backups.

This module provides utilities to:
1. Update specific page layouts in .mcf files (update_page_layout)
2. Restore from backups (restore_mcf_backup)
"""
from lxml import etree
import os
from typing import List, Dict, Any
import re
import logging
from .page_utils import determine_page_owner_of_area
from .parser import is_canvas_format, is_calendar_format

logger = logging.getLogger(__name__)


def _extract_base_filename(filename: str) -> str:
    """Extract base filename without -szXX-pgYY suffix.
    
    Args:
        filename: Filename possibly with metadata suffix
    
    Returns:
        Base filename without suffix
    
    Example:
        'safecontainer:/photo-sz10-pg5.jpeg' -> 'safecontainer:/photo.jpeg'
        'photo.jpeg' -> 'photo.jpeg'
    """
    # Split into prefix and filename
    if ':/' in filename:
        prefix, name = filename.split(':/', 1)
        prefix_with_sep = prefix + ':/'
    else:
        prefix_with_sep = ''
        name = filename
    
    # Remove -szXX-pgYY suffix
    # Pattern: -sz followed by digits/decimal, -pg followed by digits, before the extension
    pattern = r'-sz[\d.]+-pg\d+(?=\.[^.]+$)'
    base_name = re.sub(pattern, '', name)
    
    return prefix_with_sep + base_name


def _calculate_cutout(slot_width_mcf, slot_height_mcf, image_width_px, image_height_px):
    """Calculate scale and cutout offsets for fitting an image into a slot.
    
    CEWE uses a scale factor that determines how image pixels map to MCF units.
    The formula is: image_pixel_width × scale = slot_width_mcf
    
    When the aspect ratios differ, the image must be scaled to COVER the entire slot,
    then cropped (cutout offsets determine which part is visible).
    
    Args:
        slot_width_mcf: Slot width in MCF units (0.1mm)
        slot_height_mcf: Slot height in MCF units (0.1mm)
        image_width_px: Image width in pixels
        image_height_px: Image height in pixels
    
    Returns:
        tuple: (scale, cutout_left, cutout_top) where:
            - scale: scale factor (MCF units per pixel)
            - cutout_left: horizontal offset in MCF units (negative = crop from left)
            - cutout_top: vertical offset in MCF units (negative = crop from top)
    
    Raises:
        ValueError: If image dimensions are invalid (<=0)
    """
    if image_width_px <= 0 or image_height_px <= 0:
        raise ValueError(f"Invalid image dimensions: {image_width_px}x{image_height_px} pixels")
    
    # Calculate scale factors needed to fill slot width and height
    scale_for_width = slot_width_mcf / image_width_px
    scale_for_height = slot_height_mcf / image_height_px
    
    # Use the LARGER scale so image covers the entire slot
    # (smaller scale would leave gaps)
    scale = max(scale_for_width, scale_for_height)
    
    # Calculate scaled image dimensions in MCF units
    scaled_width_mcf = image_width_px * scale
    scaled_height_mcf = image_height_px * scale
    
    # Calculate how much to crop (center the image in the slot)
    # cutout values are NEGATIVE when cropping from left/top edge
    cutout_left = -(scaled_width_mcf - slot_width_mcf) / 2.0
    cutout_top = -(scaled_height_mcf - slot_height_mcf) / 2.0
    
    return (scale, cutout_left, cutout_top)


def _next_backup_name(path: str) -> str:
    base, ext = os.path.splitext(path)
    for i in range(1, 10000):
        cand = f"{base}-{i}{ext}"
        if not os.path.exists(cand):
            return cand
    raise RuntimeError('Unable to find backup name')


def _getXmlPageForUiPage(root, uiPage: Any, single_page_mode: bool):
    """Find the XML <page> element for a given UI page identifier.
    
    CRITICAL: In photobook mode (spreads), there are TWO XML <page> elements per spread:
    1. PRIMARY element (left page's pagenr): Contains ALL <area> elements for both left 
       and right logical pages of the spread. This is the element returned by this function.
    2. SECONDARY element (right page's pagenr): Mostly empty, but contains page-level 
       metadata like background color. NOT returned by this function.
    
    This function ALWAYS returns the PRIMARY element (labeled with the left page's pagenr)
    regardless of whether you request the left or right logical page. The areas within 
    this element are distinguished by their x-coordinates:
    - Areas with x < (spread_width / 2) belong to the left logical page
    - Areas with x >= (spread_width / 2) belong to the right logical page
    
    The determine_page_owner_of_area() function uses left_owner/right_owner to identify
    which logical page each area belongs to based on its x-coordinate.
    
    Args:
        root: XML root element
        uiPage: UI page identifier ('F', 'B', or integer)
        single_page_mode: Whether this is Canvas/Calendar mode (no spreads)
    
    Returns:
        Tuple of (page_elem, is_page_on_right, left_owner, right_owner) where:
        - page_elem: The PRIMARY XML <page> element (with left page's pagenr) containing 
                     ALL areas for both left and right pages
        - is_page_on_right: True if uiPage is the right page of the spread
        - left_owner: UI page identifier for the left side of this spread
        - right_owner: UI page identifier for the right side of this spread
    
    Raises:
        ValueError: If page not found
    """
    page_elem = None
    is_page_on_right = False
    left_owner = None
    right_owner = None
    
    # Special handling for cover pages 
    # According to PHOTOBOOK_STRUCTURE.md:
    # - First pagenr="0" type="fullcover" = Back cover (left side)
    # - pagenr="0" type="spine" = Spine
    # - Second pagenr="0" type="fullcover" = Front cover (right side)
    # CRITICAL: For spread pages, BOTH left and right content goes into the LEFT page's XML element
    # The first fullcover element contains areas for BOTH back cover (left) and front cover (right)
    if uiPage == 'F' or uiPage == 'B':
        # Find all fullcover pages with pagenr="0" in document order
        fullcover_pages = []
        for page in root.findall('.//page'):
            if page.get('pagenr') == '0' and page.get('type') == 'fullcover':
                fullcover_pages.append(page)
        
        if len(fullcover_pages) >= 1:
            # BOTH back and front covers use the FIRST fullcover element (the spread)
            page_elem = fullcover_pages[0]
            is_page_on_right = (uiPage == 'F')
            
            # Covers share same spread: back cover (left) | front cover (right)
            left_owner = 'B'
            right_owner = 'F'
        else:
            logger.error(f"No fullcover pages found for cover {uiPage}")
    
    # Special handling for page 1 in photobooks: find the LAST pagenr="0" type="emptypage" before pagenr="1"
    if page_elem is None and uiPage == 1 and not single_page_mode:
        all_pages = root.findall('.//page')
        page1_index = None
        
        # Find the index of pagenr="1"
        for i, page in enumerate(all_pages):
            if page.get('pagenr') == '1':
                page1_index = i
                break
        
        if page1_index is not None:
            # Search backwards from pagenr="1" to find the closest pagenr="0" type="emptypage"
            for i in range(page1_index - 1, -1, -1):
                page = all_pages[i]
                if page.get('pagenr') == '0' and page.get('type') == 'emptypage':
                    page_elem = page
                    is_page_on_right = True  # Page 1 is on the right side of the spread
                    # Page 0 (inside front cover) is on left, page 1 is on right
                    left_owner = 0
                    right_owner = 1
                    break
    
    # Standard page finding logic for all other pages
    if page_elem is None:
        for page in root.findall('.//page'):
            try:
                page_nr = int(page.get('pagenr', '0'))
            except ValueError:
                continue
            
            if single_page_mode:
                # Canvas/Calendar: direct page number match, no splitting
                if page_nr == uiPage:
                    page_elem = page
                    is_page_on_right = False
                    # Single page owns entire spread
                    left_owner = uiPage
                    right_owner = uiPage
                    break
            else:
                # Photobook: ONLY even pagenr elements are PRIMARY (contain all areas)
                # Odd pagenr elements are SECONDARY (mostly empty, just metadata)
                # We must ALWAYS return the PRIMARY (even pagenr) element
                if page_nr % 2 != 0:
                    # Skip odd pagenr (SECONDARY elements) - they don't contain areas
                    continue
                
                # This is a PRIMARY element (even pagenr) - it contains areas for both pages
                candidate_left = page_nr
                candidate_right = page_nr + 1
                
                if uiPage == candidate_left:
                    page_elem = page
                    is_page_on_right = False
                    left_owner = candidate_left
                    right_owner = candidate_right
                    break
                elif uiPage == candidate_right:
                    page_elem = page
                    is_page_on_right = True
                    left_owner = candidate_left
                    right_owner = candidate_right
                    break
    
    return page_elem, is_page_on_right, left_owner, right_owner


def restore_mcf_backup(path: str) -> dict:
    """Restore the most recent backup for `path` (e.g. data-1.mcf -> data.mcf).

    Returns a dict with keys: `path`, `restored_from`, `index`.
    """
    if not os.path.exists(path):
        # still allow restoration into the same directory even if current file missing
        base_dir = os.path.dirname(path) or '.'
        base_name = os.path.splitext(os.path.basename(path))[0]
    else:
        base_dir = os.path.dirname(path) or '.'
        base_name = os.path.splitext(os.path.basename(path))[0]

    candidates = []
    for fn in os.listdir(base_dir):
        if not fn.startswith(base_name + '-'):
            continue
        root, ext = os.path.splitext(fn)
        if ext != os.path.splitext(path)[1]:
            continue
        suffix = root[len(base_name) + 1 :]
        try:
            idx = int(suffix)
        except Exception:
            continue
        candidates.append((idx, os.path.join(base_dir, fn)))

    if not candidates:
        raise FileNotFoundError(f'No backups found for {path}')

    candidates.sort(reverse=True)
    idx, backup_path = candidates[0]

    # remove current file if present, then restore
    if os.path.exists(path):
        os.remove(path)
    os.rename(backup_path, path)

    return {'path': path, 'restored_from': backup_path, 'index': idx}


def _validate_saved_page(path: str, pageno: int, expected_photos: List[Dict[str, Any]], 
                        expected_texts: List[Dict[str, Any]], is_right_page: bool, 
                        half_width: float, spread_width: float, validate_files: bool = True) -> List[str]:
    """Validate that the saved XML matches expectations.
    
    Args:
        path: Path to the .mcf file
        pageno: Logical page number that was saved
        expected_photos: List of photo dicts that should be in XML
        expected_texts: List of text dicts that should be in XML
        is_right_page: Whether this is the right page of the spread
        half_width: Half the spread width for determining page boundaries
        spread_width: Full spread width
        validate_files: If True, check that photo files exist on disk
    
    Returns:
        List of error messages (empty if validation passed)
    """
    errors = []
    
    # Re-parse the saved file
    try:
        tree = etree.parse(path)
        root = tree.getroot()
    except Exception as e:
        return [f"Failed to re-parse saved file: {e}"]
    
    # Detect Canvas or Calendar mode
    canvas_mode = is_canvas_format(root)
    calendar_mode = is_calendar_format(root)
    single_page_mode = canvas_mode or calendar_mode
    
    # Find the page element using the shared helper function
    page_elem, _, left_owner, right_owner = _getXmlPageForUiPage(root, pageno, single_page_mode)
    
    photo_count = 0
    photo_filenames = []
    text_count = 0
    
    if page_elem is None:
        return [f"Page {pageno} not found in saved XML"]
    
    # Verify that left_owner and right_owner were set
    if left_owner is None or right_owner is None:
        return [f"BUG: left_owner/right_owner not set for pageno={pageno}"]
    
    # Count photos and texts on this page using same logic as save
    for area in page_elem.findall('.//area'):
        pos = area.find('position')
        if pos is None:
            continue
        
        current_left = float(pos.get('left', '0').replace(',', '.'))
        
        # Use determine_page_owner_of_area to check if area belongs to our page
        area_owner = determine_page_owner_of_area(current_left, half_width, left_owner, right_owner)
        if area_owner != pageno:
            continue
        
        # Check if it's a photo or text
        image = area.find('image')
        if image is not None:
            filename = image.get('filename', '')
            if filename:
                photo_count += 1
                photo_filenames.append(filename)
        elif area.find('text') is not None:
            text_count += 1
    
    # Validate counts
    expected_photo_count = len(expected_photos)
    expected_text_count = len(expected_texts)
    
    if photo_count != expected_photo_count:
        errors.append(f"Expected {expected_photo_count} photos in XML, found {photo_count}")
    
    if text_count != expected_text_count:
        errors.append(f"Expected {expected_text_count} text blocks in XML, found {text_count}")
    
    # Validate photo files exist (only if requested)
    if validate_files:
        album_dir = os.path.dirname(path)
        for filename in photo_filenames:
            safefn = filename.replace('safecontainer:/', '').lstrip('/')
            # Try multiple possible locations
            possible_paths = [
                os.path.join(album_dir, safefn),
                os.path.join(album_dir, 'images', safefn),
            ]
            
            file_exists = any(os.path.exists(p) for p in possible_paths)
            if not file_exists:
                errors.append(f"Photo file not found: {filename} (checked {safefn})")
    
    return errors


def update_page_layout(path: str, uiPage: Any, photos: List[Dict[str, Any]], 
                       texts: List[Dict[str, Any]], make_backup: bool = True,
                       new_photos: List[str] = None, deleted_photos: List[str] = None,
                       rename_map: Dict[str, str] = None, validate_files: bool = True) -> dict:
    """Update a specific page's photo and text layout in the MCF file.
    
    This function handles the MCF structure where a single <page> element can represent
    a two-page spread. Photos and texts are updated based on their x-coordinates:
    - Even pagenr: left side = pagenr, right side = pagenr+1
    - Odd pagenr: left side = pagenr-1, right side = pagenr
    
    Args:
        path: Path to the .mcf file
        uiPage: F, 0 (inside front cover), 1....N-2 (main pages), N-1 (inside back cover), B
        photos: List of photo dicts with keys: filename, area_left, area_top, area_width, area_height
        texts: List of text dicts with keys: area_left, area_top, area_width, area_height
        make_backup: If True, rename original file to path-N.mcf before writing
        new_photos: Optional list of filenames that are newly added (need new <area> elements)
        deleted_photos: Optional list of filenames that were deleted (remove <area> elements)
        rename_map: Optional dict mapping old filenames to new filenames (e.g., after adding -sz suffix)
        validate_files: If True, validate that referenced photo files exist on disk
    
    Returns:
        Dict with keys: path, backup_path (or None), modified_photos, modified_texts, 
                       added_photos, deleted_photos
    
    Raises:
        FileNotFoundError: If path doesn't exist
        ValueError: If page not found or structure is unexpected
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    
    new_photos = new_photos or []
    deleted_photos = deleted_photos or []
    rename_map = rename_map or {}
    new_photos_set = set(new_photos)
    # Create set of base filenames for deleted photos (to match with/without metadata suffixes)
    deleted_photos_base_set = set(_extract_base_filename(fn) for fn in deleted_photos)
    
    # CRITICAL: Validate ALL photos have dimensions BEFORE making any changes
    for photo in photos:
        filename = photo.get('filename', '')
        if not filename:
            continue
        if 'image_width' not in photo or 'image_height' not in photo:
            raise ValueError(f"Photo {filename} missing image dimensions. All photos must have width/height before saving.")
        if photo['image_width'] <= 0 or photo['image_height'] <= 0:
            raise ValueError(f"Photo {filename} has invalid dimensions: {photo['image_width']}x{photo['image_height']}")
    
    # Parse the MCF file
    tree = etree.parse(path)
    root = tree.getroot()
    
    # Detect Canvas or Calendar mode (both use single pages, not 2-page spreads)
    canvas_mode = is_canvas_format(root)
    calendar_mode = is_calendar_format(root)
    single_page_mode = canvas_mode or calendar_mode
    
    # Find the <page> element for this UI page
    page_elem, is_page_on_right, left_owner, right_owner = _getXmlPageForUiPage(root, uiPage, single_page_mode)
    
    if page_elem is None:
        raise ValueError(f'Logical page {uiPage} not found in {path}')
    
    # Verify that left_owner and right_owner were set
    if left_owner is None or right_owner is None:
        raise ValueError(f'BUG: left_owner/right_owner not set for uiPage={uiPage}')
    
    # Get page rotation (for portrait Canvases)
    page_rotation = page_elem.get('rotation', '0')
    try:
        rotation_degrees = float(page_rotation)
    except (TypeError, ValueError):
        rotation_degrees = 0.0
    
    # Get spread dimensions to determine which areas belong to this page
    bundlesize = page_elem.find('./bundlesize')
    spread_width = float(bundlesize.get('width'))
    spread_height = float(bundlesize.get('height'))
    
    def apply_reverse_rotation(left, top, width, height, rot):
        """Reverse the rotation transformation applied during parsing.
        
        Parser rotates physical coords → logical coords for UI
        Writer must reverse: logical coords → physical coords for MCF file
        
        For 90° page rotation:
          Forward (parser):  physical (x,y,w,h) → logical rotated 90° clockwise: (y, W-x-w, h, w)
          Reverse (writer): logical (x',y',w',h') → physical rotated 90° counter-clockwise: (W-y'-h', x', h', w')
        
        Args:
            left, top, width, height: Logical coordinates (as used by UI)
            rot: Logical rotation of the area itself
            
        Returns:
            Tuple of (physical_left, physical_top, physical_width, physical_height, physical_rot)
        """
        if rotation_degrees == 90.0:
            # Reverse 90° clockwise by applying 90° counter-clockwise:
            # Transform: (x',y',w',h') → (W-y'-h', x', h', w')
            # Note: we also SWAP width and height
            physical_left = spread_width - top - height
            physical_top = left
            physical_width = height  # SWAPPED
            physical_height = width  # SWAPPED
            physical_rot = (rot - 90.0) % 360.0  # Subtract 90 to reverse
            return physical_left, physical_top, physical_width, physical_height, physical_rot
        elif rotation_degrees == 270.0:
            # Reverse 270° clockwise rotation by applying 90° transform
            # Transform: (x',y',w',h') → (y', W-x'-w', h', w')
            # Note: we also SWAP width and height
            physical_left = top
            physical_top = spread_width - left - width
            physical_width = height  # SWAPPED
            physical_height = width  # SWAPPED
            physical_rot = (rot + 90.0) % 360.0  # Add 90, not subtract
            return physical_left, physical_top, physical_width, physical_height, physical_rot
        else:
            # No rotation - coordinates are already physical
            return left, top, width, height, rot
    
    # Canvas/Calendar mode: no splitting (half_width = full width)
    # Photobook mode: split spread in half
    if single_page_mode:
        half_width = spread_width  # No splitting for Canvas/Calendar
    else:
        half_width = spread_width / 2.0
    
    # left_owner and right_owner were already set above when finding page_elem
    # They represent uiPage identifiers (not pagenr) for the left and right sides of this spread
    
    # Track statistics
    modified_photos = 0
    added_photos = 0
    deleted_photos_count = 0
    
    # Track which photos from our layout have been matched to existing XML areas
    matched_photos = set()
    
    # First pass: Update existing photo areas and mark deleted ones for removal
    areas_to_remove = []
    
    for area in page_elem.findall('.//area'):
        # Check if this area belongs to our logical page
        pos = area.find('position')
        if pos is None:
            continue
        
        current_left = float(pos.get('left', '0').replace(',', '.'))
        
        # Use determine_page_owner_of_area to check if area belongs to our page
        area_owner = determine_page_owner_of_area(current_left, half_width, left_owner, right_owner)
        if area_owner != uiPage:
            continue  # This area is on the other page of the spread
        
        # Find image element
        image = area.find('image')
        if image is None:
            continue
        
        # Get filename from image element
        filename = image.get('filename', '')
        if not filename:
            # Empty slot - mark for removal
            areas_to_remove.append(area)
            continue
        
        # Check if this photo was deleted (match by base filename to handle metadata suffixes)
        xml_base_filename = _extract_base_filename(filename)
        if xml_base_filename in deleted_photos_base_set:
            areas_to_remove.append(area)
            deleted_photos_count += 1
            continue
        
        # Find matching photo in our layout
        # Account for renamed files: old XML filename might map to new photo filename
        # Also account for metadata suffixes (-szXX-pgYY) that may be present in memory but not in XML
        matching_photo = None
        
        for p in photos:
            photo_filename = p.get('filename', '')
            photo_base_filename = _extract_base_filename(photo_filename)
            
            # Match if:
            # 1. Exact match (photo_filename == filename)
            # 2. Base filenames match (ignoring metadata suffixes)
            # 3. Rename map match (old XML name -> new photo name)
            if (photo_filename == filename or 
                photo_base_filename == xml_base_filename or
                (rename_map and rename_map.get(filename) == photo_filename)):
                matching_photo = p
                break
        
        if matching_photo is None:
            # Photo exists in XML but not in current layout - it was removed by algorithm
            # Mark it for deletion
            areas_to_remove.append(area)
            deleted_photos_count += 1
            logger.info(f"Page {uiPage}: Removing photo '{filename}' (not in current layout)")
            continue
        
        # Track that we've matched this photo (so we don't add it again)
        matched_photos.add(matching_photo['filename'])
        
        # Get image dimensions for scale calculation (validated at function entry)
        image_width = matching_photo['image_width']
        image_height = matching_photo['image_height']
        
        # Get logical layout dimensions (as used by UI)
        logical_left = matching_photo.get('area_left', 0)
        logical_top = matching_photo.get('area_top', 0)
        logical_width = matching_photo.get('area_width', 0)
        logical_height = matching_photo.get('area_height', 0)
        logical_rot = matching_photo.get('area_rot', 0)
        
        # Apply reverse rotation to convert logical coords → physical coords for MCF
        physical_left, physical_top, physical_width, physical_height, physical_rot = apply_reverse_rotation(
            logical_left, logical_top, logical_width, logical_height, logical_rot
        )
        
        # Calculate correct scale and cutout values using physical dimensions
        scale, cutout_left, cutout_top = _calculate_cutout(
            physical_width, physical_height, image_width, image_height
        )
        
        # Update XML filename if photo was renamed
        if rename_map and filename in rename_map:
            image.set('filename', rename_map[filename])
        
        # Update position with physical values (rotated back for MCF storage)
        pos.set('left', f"{physical_left:.2f}")
        pos.set('top', f"{physical_top:.2f}")
        pos.set('width', f"{physical_width:.2f}")
        pos.set('height', f"{physical_height:.2f}")
        pos.set('rotation', f"{physical_rot:.2f}")
        
        # Update cutout values in the image element
        cutout_elem = image.find('cutout')
        if cutout_elem is not None:
            cutout_elem.set('left', f"{cutout_left:.6f}")
            cutout_elem.set('scale', f"{scale:.6f}")
            cutout_elem.set('top', f"{cutout_top:.6f}")
        else:
            # Create cutout if it doesn't exist
            cutout_elem = etree.SubElement(image, 'cutout')
            cutout_elem.set('left', f"{cutout_left:.6f}")
            cutout_elem.set('scale', f"{scale:.6f}")
            cutout_elem.set('top', f"{cutout_top:.6f}")
        
        # Ensure proper formatting for existing elements
        if pos.tail is None or not pos.tail.strip():
            pos.tail = '\n            '
        
        decoration = area.find('decoration')
        if decoration is not None and (decoration.tail is None or not decoration.tail.strip()):
            decoration.tail = '\n            '
        
        if image.text is None or not image.text.strip():
            image.text = '\n                '
        if image.tail is None or not image.tail.strip():
            image.tail = '\n        '
        
        if cutout_elem.tail is None or not cutout_elem.tail.strip():
            cutout_elem.tail = '\n                '
        
        quality = image.find('quality')
        if quality is not None and (quality.tail is None or not quality.tail.strip()):
            quality.tail = '\n            '
        
        if area.tail is None or not area.tail.strip():
            area.tail = '\n        '
        
        modified_photos += 1
    
    # Remove deleted/empty photo areas
    for area in areas_to_remove:
        parent = area.getparent()
        if parent is not None:
            parent.remove(area)
    
    # Second pass: Add new photo areas
    # Find a template area to copy structure from
    template_area = None
    for area in page_elem.findall('.//area'):
        image = area.find('image')
        if image is not None:
            template_area = area
            break
    
    # Find the parent element to add new areas to
    areas_parent = template_area.getparent() if template_area is not None else page_elem
    
    # Add new photo areas (photos NOT matched in first pass)
    for photo in photos:
        filename = photo.get('filename', '')
        if not filename:
            raise ValueError(f"Page {uiPage}: Photo has no filename - this is a bug in the calling code")
        
        # Skip photos that were already updated in the first pass
        if filename in matched_photos:
            continue
        
        # This photo wasn't in the XML - it must be new
        if filename not in new_photos_set:
            raise ValueError(
                f"Page {uiPage}: Photo '{filename}' not in new_photos list.\n"
                f"This is a bug - photo wasn't in XML and isn't tracked as new.\n"
                f"Expected filenames (first 5): {sorted(list(new_photos_set)[:5])}"
            )
        
        # Get image dimensions for scale calculation (validated at function entry)
        image_width = photo['image_width']
        image_height = photo['image_height']
        
        # Get logical layout dimensions (as used by UI)
        logical_left = photo.get('area_left', 0)
        logical_top = photo.get('area_top', 0)
        logical_width = photo.get('area_width', 0)
        logical_height = photo.get('area_height', 0)
        logical_rot = photo.get('area_rot', 0)
        
        # Apply reverse rotation to convert logical coords → physical coords for MCF
        physical_left, physical_top, physical_width, physical_height, physical_rot = apply_reverse_rotation(
            logical_left, logical_top, logical_width, logical_height, logical_rot
        )
        
        # Calculate correct scale and cutout values using physical dimensions
        scale, cutout_left, cutout_top = _calculate_cutout(
            physical_width, physical_height, image_width, image_height
        )
        
        # Create new <area> element
        new_area = etree.Element('area', areatype='imagearea')
        new_area.text = '\n            '  # Indent for <position>
        
        # Create <position> child (MCF format: height, left, rotation, top, width, zposition)
        # Use physical coordinates (rotated back for MCF storage)
        position = etree.SubElement(new_area, 'position')
        position.set('height', f"{physical_height:.2f}")
        position.set('left', f"{physical_left:.2f}")
        position.set('rotation', f"{physical_rot:.2f}")
        position.set('top', f"{physical_top:.2f}")
        position.set('width', f"{physical_width:.2f}")
        # Z-position: calendars/canvases need higher values to appear above template elements
        zpos = '7500' if single_page_mode else '100'
        position.set('zposition', zpos)
        position.tail = '\n            '  # Newline after <position>
        
        # Create <decoration/> child (required in MCF format)
        decoration = etree.SubElement(new_area, 'decoration')
        decoration.tail = '\n            '  # Newline after <decoration/>
        
        # Create <image> child
        image_elem = etree.SubElement(new_area, 'image')
        image_elem.set('filename', filename)
        image_elem.set('useABK', '1')  # Standard attribute in MCF
        image_elem.text = '\n                '  # Indent for <cutout>
        image_elem.tail = '\n        '  # Newline after </image>
        
        # Create <cutout> child inside <image> with calculated values
        cutout = etree.SubElement(image_elem, 'cutout')
        cutout.set('left', f"{cutout_left:.6f}")
        cutout.set('scale', f"{scale:.6f}")
        cutout.set('top', f"{cutout_top:.6f}")
        cutout.tail = '\n                '  # Newline after <cutout/>
        
        # Create <quality> child inside <image> (default values)
        quality = etree.SubElement(image_elem, 'quality')
        quality.set('noise', '100')
        quality.set('sharpness', '100')
        quality.set('texture', '100')
        quality.tail = '\n            '  # Newline after <quality/>
        
        # Add to parent with proper tail indentation
        new_area.tail = '\n        '  # Newline after </area>
        areas_parent.append(new_area)
        added_photos += 1
    
    # Update text positions
    modified_texts = 0
    added_texts = 0
    
    # Collect text areas that belong to this logical page
    text_areas = []
    for area in page_elem.findall('.//area'):
        if area.get('areatype') != 'textarea':
            continue
        
        pos = area.find('position')
        if pos is None:
            continue
        
        try:
            current_left = float(pos.get('left', '0').replace(',', '.'))
        except Exception:
            continue
        
        # Use determine_page_owner_of_area to check if area belongs to our page
        area_owner = determine_page_owner_of_area(current_left, half_width, left_owner, right_owner)
        if area_owner != uiPage:
            continue
        
        text_areas.append(area)
    
    # Update existing text areas with corresponding layout (by order)
    for i, (area, text_layout) in enumerate(zip(text_areas, texts)):
        pos = area.find('position')
        if pos is None:
            continue
        
        # Get logical layout dimensions (as used by UI)
        logical_left = text_layout.get('area_left', 0)
        logical_top = text_layout.get('area_top', 0)
        logical_width = text_layout.get('area_width', 0)
        logical_height = text_layout.get('area_height', 0)
        logical_rot = text_layout.get('area_rot', 0)
        
        # Apply reverse rotation to convert logical coords → physical coords for MCF
        physical_left, physical_top, physical_width, physical_height, physical_rot = apply_reverse_rotation(
            logical_left, logical_top, logical_width, logical_height, logical_rot
        )
        
        pos.set('left', f"{physical_left:.2f}")
        pos.set('top', f"{physical_top:.2f}")
        pos.set('width', f"{physical_width:.2f}")
        pos.set('height', f"{physical_height:.2f}")
        pos.set('rotation', f"{physical_rot:.2f}")
        modified_texts += 1
    
    # Remove deleted text areas (if there are fewer texts than existing areas)
    if len(texts) < len(text_areas):
        for i in range(len(texts), len(text_areas)):
            area_to_remove = text_areas[i]
            area_to_remove.getparent().remove(area_to_remove)
    
    # Add new text areas if there are more texts than existing areas
    if len(texts) > len(text_areas):
        for i in range(len(text_areas), len(texts)):
            text_layout = texts[i]
            
            # Get logical layout dimensions (as used by UI)
            logical_left = text_layout.get('area_left', 0)
            logical_top = text_layout.get('area_top', 0)
            logical_width = text_layout.get('area_width', 0)
            logical_height = text_layout.get('area_height', 0)
            logical_rot = text_layout.get('area_rot', 0)
            
            # Apply reverse rotation to convert logical coords → physical coords for MCF
            physical_left, physical_top, physical_width, physical_height, physical_rot = apply_reverse_rotation(
                logical_left, logical_top, logical_width, logical_height, logical_rot
            )
            
            # Create new <area> element for text
            new_area = etree.Element('area', areatype='textarea')
            new_area.text = '\n            '  # Indent for <position>
            
            # Create <position> child using physical coordinates
            position = etree.SubElement(new_area, 'position')
            position.set('height', f"{physical_height:.2f}")
            position.set('left', f"{physical_left:.2f}")
            position.set('rotation', f"{physical_rot:.2f}")
            position.set('top', f"{physical_top:.2f}")
            position.set('width', f"{physical_width:.2f}")
            position.set('zposition', '7000')  # Default z-position for text
            position.tail = '\n            '  # Newline after <position>
            
            # Create <decoration/> child
            decoration = etree.SubElement(new_area, 'decoration')
            decoration.tail = '\n            '  # Newline after <decoration/>
            
            # Create <text> child with default empty HTML content
            text_elem = etree.SubElement(new_area, 'text')
            text_elem.set('applySpotColor', '0')
            text_elem.set('areaTextType', 'content')
            # Default empty HTML content
            default_html = ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">'
                          '<html><head><meta name="qrichtext" content="1" /><meta charset="utf-8" />'
                          '<style type="text/css">\n'
                          'p, li { white-space: pre-wrap; }\n'
                          'hr { height: 1px; border-width: 0; }\n'
                          'li.unchecked::marker { content: "\\2610"; }\n'
                          'li.checked::marker { content: "\\2612"; }\n'
                          '</style></head>'
                          '<body style=" font-family:\'CEWE Head\'; font-size:12pt; font-weight:400; font-style:normal;">'
                          '<p style="-qt-paragraph-type:empty; margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><br /></p>'
                          '</body></html>')
            text_elem.text = default_html
            text_elem.tail = '\n        '  # Newline after </text>
            
            # Add outline and textFormat children
            outline = etree.SubElement(text_elem, 'outline')
            outline.set('width', '0')
            outline.tail = '\n                    '
            
            textFormat = etree.SubElement(text_elem, 'textFormat')
            textFormat.set('Alignment', 'ALIGNLEADING')
            textFormat.set('IndentMargin', '4')
            textFormat.set('VerticalIndentMargin', '50')
            textFormat.set('backgroundColor', '#00000000')
            textFormat.set('font', 'CEWE Head,12,-1,5,400,0,0,0,0,0,0,1,0,0,0,1')
            textFormat.set('foregroundColor', '#ff000000')
            textFormat.set('hasOutline', '0')
            textFormat.set('hyphenation', '0')
            textFormat.set('letterSpacing', '0')
            textFormat.set('lineHeight', '100')
            textFormat.tail = '\n            '
            
            # Add to parent with proper tail indentation
            new_area.tail = '\n        '  # Newline after </area>
            areas_parent.append(new_area)
            added_texts += 1
    
    # Backup original file if requested
    backup_path = None
    if make_backup:
        backup_path = _next_backup_name(path)
        os.rename(path, backup_path)
    
    # Validate that we processed all expected photos
    warnings = []
    expected_photo_count = len(photos)
    processed_count = modified_photos + added_photos
    
    if processed_count != expected_photo_count:
        msg = f"WARNING: Expected to save {expected_photo_count} photos but only processed {processed_count} ({modified_photos} modified + {added_photos} added)"
        warnings.append(msg)
    
    # Write updated tree back to original path
    # Use pretty_print=False to preserve manual whitespace formatting
    try:
        tree.write(path, encoding='utf-8', xml_declaration=True, pretty_print=False)
    except Exception as e:
        # Restore backup if write failed
        if backup_path and os.path.exists(backup_path):
            os.rename(backup_path, path)
        raise RuntimeError(f"Failed to write MCF file: {e}") from e
    
    # Validate the saved XML matches expectations
    validation_errors = _validate_saved_page(path, uiPage, photos, texts, is_page_on_right, half_width, spread_width, validate_files)
    if validation_errors:
        for error in validation_errors:
            warnings.append(f"VALIDATION ERROR: {error}")
            logger.error(f"Page {uiPage} VALIDATION: {error}")
    else:
        if validate_files:
            logger.info(f"Page {uiPage}: Validated save - {len(photos)} photos, {len(texts)} texts (all files exist)")
        else:
            logger.info(f"Page {uiPage}: Validated save - {len(photos)} photos, {len(texts)} texts (file existence not checked)")
    
    result = {
        'path': path,
        'backup_path': backup_path,
        'modified_photos': modified_photos,
        'modified_texts': modified_texts,
        'added_photos': added_photos,
        'added_texts': added_texts,
        'deleted_photos_count': deleted_photos_count,
        'warnings': warnings
    }
    
    return result
