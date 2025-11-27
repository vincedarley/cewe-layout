"""
Layout generation wrapper for cewe-layout GUI.

This module bridges MCF photobook metadata and generic layout algorithms.
It translates:
- MCF photos to abstract LayoutRectangle objects (with dimensions from image metadata).
- Page dimensions from MCF units to page coordinates.
- Algorithm output (LayoutRectangle with positioned x, y) back to MCF area coordinates.

Layout algorithms themselves know nothing about files, MCF, or paths.
"""

import cv2
from pathlib import Path
from .algorithms.base import LayoutRectangle
from .algorithms.collage_generator import CollageGeneratorAlgorithm


def generate_layout_for_page(photos, page_width_mcf, page_height_mcf, mcf_base_folder, 
                           algorithm=None, temperature=1.0, weights=None, **kwargs):
    """
    High-level function to generate a new layout for a page.
    
    Translates MCF photos to abstract layout rectangles, runs the algorithm,
    and translates results back to MCF coordinates.
    
    Args:
        photos: List of MCF photo dicts (with 'filename' key).
        page_width_mcf: Page width in MCF units (0.1mm).
        page_height_mcf: Page height in MCF units (0.1mm).
        mcf_base_folder: Base folder for resolving image paths.
        algorithm: LayoutAlgorithm instance (defaults to CollageGeneratorAlgorithm).
        temperature: Temperature for randomness (if supported by algorithm).
        weights: Optional dict mapping filename -> desired_weight (0.5 to 2.0).
        **kwargs: Additional algorithm-specific parameters.
    
    Returns:
        Tuple (success: bool, updated_photos: list, error_msg: str).
    """
    if algorithm is None:
        algorithm = CollageGeneratorAlgorithm(temperature=temperature)
    
    # Step 1: Translate MCF photos to abstract layout rectangles
    rectangles, error = _photos_to_rectangles(
        photos, mcf_base_folder, weights
    )
    if not rectangles:
        return False, [], error
    
    # Step 2: Run the layout algorithm (operates on page coordinates, not MCF)
    success, positioned_rects, error_msg = algorithm.generate_layout(
        page_width_mcf, page_height_mcf, rectangles, **kwargs
    )
    if not success:
        return False, [], error_msg
    
    # Step 3: Translate results back to MCF coordinates
    updated_photos = _rectangles_to_photos(photos, positioned_rects)
    
    return True, updated_photos, ""


def _photos_to_rectangles(photos, mcf_base_folder, weights=None):
    """
    Convert MCF photo list to abstract LayoutRectangle objects.
    
    For each photo, load the image, extract its dimensions, and create a LayoutRectangle
    with the correct width/height ratio.
    
    Args:
        photos: List of MCF photo dicts.
        mcf_base_folder: Base folder for image paths.
        weights: Optional dict mapping filename -> desired_weight.
    
    Returns:
        Tuple (rectangles: list, error: str).
    """
    rectangles = []
    mcf_base = Path(mcf_base_folder)
    
    for photo_idx, photo in enumerate(photos):
        fn = photo.get('filename', '')
        if not fn:
            return [], f"Photo {photo_idx} has no filename"
        
        # Resolve image path
        safefn = fn.replace('safecontainer:/', '').lstrip('/')
        img_path = mcf_base / safefn
        
        if not img_path.exists():
            return [], f"Image not found: {img_path}"
        
        # Load image to get its dimensions
        arr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if arr is None:
            return [], f"Failed to load image: {img_path}"
        
        # Image dimensions (height, width in OpenCV)
        img_height, img_width = arr.shape[:2]
        if img_height <= 0 or img_width <= 0:
            return [], f"Invalid image dimensions: {img_path}"
        
        # Create LayoutRectangle with image dimensions
        # Use photo index as item_id for reversal later
        item_id = str(photo_idx)
        desired_weight = 1.0
        if weights and fn in weights:
            desired_weight = weights[fn]
        
        rect = LayoutRectangle(
            item_id=item_id,
            width=float(img_width),
            height=float(img_height),
            desired_weight=desired_weight
        )
        rectangles.append(rect)
    
    return rectangles, ""


def _rectangles_to_photos(photos, rectangles):
    """
    Convert algorithm output (positioned LayoutRectangle) back to MCF photo format.
    
    Args:
        photos: Original MCF photo list.
        rectangles: List of positioned LayoutRectangle objects from algorithm.
    
    Returns:
        Updated photos list with new area_left/top/width/height.
    """
    updated_photos = []
    
    for rect in rectangles:
        item_id = rect.item_id
        photo_idx = int(item_id)
        
        if photo_idx < len(photos) and rect.x is not None and rect.y is not None:
            photo = photos[photo_idx].copy()
            photo['area_left'] = rect.x
            photo['area_top'] = rect.y
            photo['area_width'] = rect.width
            photo['area_height'] = rect.height
            updated_photos.append(photo)
    
    return updated_photos
