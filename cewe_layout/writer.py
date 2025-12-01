"""Utilities to modify and write .mcf files safely with backups.

This module provides utilities to:
1. Update specific page layouts in .mcf files (update_page_layout)
2. Scale all areas by a factor (patch_mcf_file) 
3. Restore from backups (restore_mcf_backup)
"""
from lxml import etree
import os
from typing import List, Dict, Any, Optional


def _next_backup_name(path: str) -> str:
    base, ext = os.path.splitext(path)
    for i in range(1, 10000):
        cand = f"{base}-{i}{ext}"
        if not os.path.exists(cand):
            return cand
    raise RuntimeError('Unable to find backup name')


def _scale_positions_in_tree(tree: etree._ElementTree, scale: float = 0.9) -> int:
    """Scale area positions by `scale`. Returns number of areas modified."""
    root = tree.getroot()
    modified = 0
    for area in root.findall('.//area'):
        pos = area.find('position')
        if pos is None:
            continue
        try:
            left = float(pos.get('left').replace(',', '.'))
            top = float(pos.get('top').replace(',', '.'))
            width = float(pos.get('width').replace(',', '.'))
            height = float(pos.get('height').replace(',', '.'))
        except Exception:
            continue

        new_w = width * scale
        new_h = height * scale
        new_left = left + (width - new_w) / 2.0
        new_top = top + (height - new_h) / 2.0

        # keep numeric formatting similar to input (2 decimal places)
        pos.set('left', f"{new_left:.2f}")
        pos.set('top', f"{new_top:.2f}")
        pos.set('width', f"{new_w:.2f}")
        pos.set('height', f"{new_h:.2f}")
        modified += 1
    return modified


def patch_mcf_file(path: str, scale: float = 0.9, make_backup: bool = True) -> dict:
    """Parse `path`, backup original file, scale area sizes and overwrite the file.

    Returns a dict with keys: `path`, `backup_path` (or None), `modified_areas`.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    # parse as tree so we can write back preserving xml declaration
    tree = etree.parse(path)

    modified = _scale_positions_in_tree(tree, scale)

    backup_path = None
    if make_backup:
        backup_path = _next_backup_name(path)
        os.rename(path, backup_path)

    # write updated tree to original path
    tree.write(path, encoding='utf-8', xml_declaration=True, pretty_print=True)

    return {'path': path, 'backup_path': backup_path, 'modified_areas': modified}


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
                       texts: List[Dict[str, Any]], make_backup: bool = True) -> dict:
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
    
    Returns:
        Dict with keys: path, backup_path (or None), modified_photos, modified_texts
    
    Raises:
        FileNotFoundError: If path doesn't exist
        ValueError: If page not found or structure is unexpected
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    
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
    
    # Update photo positions
    modified_photos = 0
    
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
            continue
        
        # Find matching photo in our layout
        matching_photo = None
        for p in photos:
            if p.get('filename', '') == filename:
                matching_photo = p
                break
        
        if matching_photo is None:
            continue  # Photo not in our layout
        
        # Update position with new values
        pos.set('left', f"{matching_photo.get('area_left', 0):.2f}")
        pos.set('top', f"{matching_photo.get('area_top', 0):.2f}")
        pos.set('width', f"{matching_photo.get('area_width', 0):.2f}")
        pos.set('height', f"{matching_photo.get('area_height', 0):.2f}")
        modified_photos += 1
    
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
    
    # Write updated tree back to original path
    tree.write(path, encoding='utf-8', xml_declaration=True, pretty_print=True)
    
    return {
        'path': path,
        'backup_path': backup_path,
        'modified_photos': modified_photos,
        'modified_texts': modified_texts
    }
