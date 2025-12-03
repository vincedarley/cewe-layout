"""Utilities to modify and write .mcf files safely with backups.

This module provides utilities to:
1. Update specific page layouts in .mcf files (update_page_layout)
2. Restore from backups (restore_mcf_backup)
"""
from lxml import etree
import os
from typing import List, Dict, Any


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
    """
    if image_width_px <= 0 or image_height_px <= 0:
        # Fallback for invalid dimensions
        return (1.0, 0.0, 0.0)
    
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


def update_page_layout(path: str, pageno: int, photos: List[Dict[str, Any]], 
                       texts: List[Dict[str, Any]], make_backup: bool = True,
                       new_photos: List[str] = None, deleted_photos: List[str] = None) -> dict:
    """Update a specific page's photo and text layout in the MCF file.
    
    This function handles the MCF structure where a single <page> element can represent
    a two-page spread. Photos and texts are updated based on their x-coordinates:
    - Even pagenr: left side = pagenr, right side = pagenr+1
    - Odd pagenr: left side = pagenr-1, right side = pagenr
    
    Args:
        path: Path to the .mcf file
        pageno: Logical page number to update (1-indexed)
        photos: List of photo dicts with keys: filename, area_left, area_top, area_width, area_height
        texts: List of text dicts with keys: area_left, area_top, area_width, area_height
        make_backup: If True, rename original file to path-N.mcf before writing
        new_photos: Optional list of filenames that are newly added (need new <area> elements)
        deleted_photos: Optional list of filenames that were deleted (remove <area> elements)
    
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
    new_photos_set = set(new_photos)
    deleted_photos_set = set(deleted_photos)
    
    # Parse the MCF file
    tree = etree.parse(path)
    root = tree.getroot()
    
    # Find the <page> element that contains this logical page
    # A <page> with pagenr=N can contain logical pages based on even/odd:
    # - Even N: contains logical pages N (left) and N+1 (right)
    # - Odd N: contains logical pages N-1 (left) and N (right)
    page_elem = None
    is_right_page = False
    spread_width = 4200.0  # default
    
    for page in root.findall('.//page'):
        try:
            page_nr = int(page.get('pagenr', '0'))
        except ValueError:
            continue
        
        # Determine which logical pages this <page> element contains
        if page_nr % 2 == 0:
            # Even pagenr: left=page_nr, right=page_nr+1
            left_owner = page_nr
            right_owner = page_nr + 1
        else:
            # Odd pagenr: left=page_nr-1, right=page_nr
            left_owner = max(1, page_nr - 1)
            right_owner = page_nr
        
        if pageno == left_owner:
            page_elem = page
            is_right_page = False
            break
        elif pageno == right_owner:
            page_elem = page
            is_right_page = True
            break
    
    if page_elem is None:
        raise ValueError(f'Logical page {pageno} not found in {path}')
    
    # Get spread dimensions to determine which areas belong to this page
    bundlesize = page_elem.find('./bundlesize')
    try:
        spread_width = float(bundlesize.get('width')) if bundlesize is not None else 4200.0
    except Exception:
        spread_width = 4200.0
    
    half_width = spread_width / 2.0
    
    # Determine x-coordinate range for areas on this logical page
    # Left page: [0, half_width), Right page: [half_width, spread_width]
    if is_right_page:
        x_min = half_width
        x_max = spread_width
    else:
        x_min = 0.0
        x_max = half_width
    
    # Helper function to check if an area belongs to this logical page
    def belongs_to_page(area_left: float, area_width: float) -> bool:
        """Check if an area's center is within this page's x-range."""
        center_x = area_left + area_width / 2.0
        return x_min <= center_x < x_max
    
    # Track statistics
    modified_photos = 0
    added_photos = 0
    deleted_photos_count = 0
    
    # First pass: Update existing photo areas and mark deleted ones for removal
    areas_to_remove = []
    
    for area in page_elem.findall('.//area'):
        # Check if this area belongs to our logical page
        pos = area.find('position')
        if pos is None:
            continue
        
        try:
            current_left = float(pos.get('left', '0').replace(',', '.'))
            current_width = float(pos.get('width', '0').replace(',', '.'))
        except Exception:
            continue
        
        if not belongs_to_page(current_left, current_width):
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
        
        # Check if this photo was deleted
        if filename in deleted_photos_set:
            areas_to_remove.append(area)
            deleted_photos_count += 1
            continue
        
        # Find matching photo in our layout
        matching_photo = None
        for p in photos:
            if p.get('filename', '') == filename:
                matching_photo = p
                break
        
        if matching_photo is None:
            # Photo not in current layout - could be deleted or error
            continue
        
        # Get image dimensions for scale calculation
        image_width = matching_photo.get('image_width', 4000)
        image_height = matching_photo.get('image_height', 3000)
        
        # Get new slot dimensions
        slot_width = matching_photo.get('area_width', 0)
        slot_height = matching_photo.get('area_height', 0)
        
        # Calculate correct scale and cutout values
        scale, cutout_left, cutout_top = _calculate_cutout(
            slot_width, slot_height, image_width, image_height
        )
        
        # Update position with new values
        pos.set('left', f"{matching_photo.get('area_left', 0):.2f}")
        pos.set('top', f"{matching_photo.get('area_top', 0):.2f}")
        pos.set('width', f"{matching_photo.get('area_width', 0):.2f}")
        pos.set('height', f"{matching_photo.get('area_height', 0):.2f}")
        
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
    
    for photo in photos:
        filename = photo.get('filename', '')
        if not filename or filename not in new_photos_set:
            continue
        
        # Get image dimensions for scale calculation
        image_width = photo.get('image_width', 4000)  # fallback to reasonable default
        image_height = photo.get('image_height', 3000)
        
        # Get slot dimensions
        slot_width = photo.get('area_width', 0)
        slot_height = photo.get('area_height', 0)
        
        # Calculate correct scale and cutout values
        scale, cutout_left, cutout_top = _calculate_cutout(
            slot_width, slot_height, image_width, image_height
        )
        
        # Create new <area> element
        new_area = etree.Element('area', areatype='imagearea')
        new_area.text = '\n            '  # Indent for <position>
        
        # Create <position> child (MCF format: height, left, rotation, top, width, zposition)
        position = etree.SubElement(new_area, 'position')
        position.set('height', f"{photo.get('area_height', 0):.2f}")
        position.set('left', f"{photo.get('area_left', 0):.2f}")
        position.set('rotation', '0')
        position.set('top', f"{photo.get('area_top', 0):.2f}")
        position.set('width', f"{photo.get('area_width', 0):.2f}")
        position.set('zposition', '100')  # Default z-position
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
            current_width = float(pos.get('width', '0').replace(',', '.'))
        except Exception:
            continue
        
        if not belongs_to_page(current_left, current_width):
            continue
        
        text_areas.append(area)
    
    # Update each text area with corresponding layout (by order)
    for i, (area, text_layout) in enumerate(zip(text_areas, texts)):
        pos = area.find('position')
        if pos is None:
            continue
        
        pos.set('left', f"{text_layout.get('area_left', 0):.2f}")
        pos.set('top', f"{text_layout.get('area_top', 0):.2f}")
        pos.set('width', f"{text_layout.get('area_width', 0):.2f}")
        pos.set('height', f"{text_layout.get('area_height', 0):.2f}")
        modified_texts += 1
    
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
    
    # Check for photos with missing dimensions
    for photo in photos:
        filename = photo.get('filename', '')
        if not filename:
            continue
        if 'image_width' not in photo or 'image_height' not in photo:
            msg = f"WARNING: Photo {filename} missing image dimensions, may have incorrect scale"
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
    
    result = {
        'path': path,
        'backup_path': backup_path,
        'modified_photos': modified_photos,
        'modified_texts': modified_texts,
        'added_photos': added_photos,
        'deleted_photos_count': deleted_photos_count,
        'warnings': warnings
    }
    
    return result
