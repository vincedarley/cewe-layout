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
from .gap_utils import (
    transform_page_to_gapfree,
    transform_item_to_gapfree,
    transform_item_from_gapfree
)


def generate_layout_for_page(photos, page_width_mcf, page_height_mcf, mcf_base_folder, 
                           algorithm=None, temperature=1.0, preferred_sizes=None, gap=None,
                           edge_gap=0.0, internal_gap=0.0,
                           texts=None, use_slot_aspect=None, original_photos=None, **kwargs):
    """
    High-level function to generate a new layout for a page.
    
    Translates MCF photos and texts to abstract layout rectangles, runs the algorithm,
    and translates results back to MCF coordinates.
    
    Args:
        photos: List of MCF photo dicts (with 'filename' key).
        page_width_mcf: Page width in MCF units (0.1mm).
        page_height_mcf: Page height in MCF units (0.1mm).
        mcf_base_folder: Base folder for resolving image paths.
        algorithm: LayoutAlgorithm instance (defaults to CollageGeneratorAlgorithm).
        temperature: Temperature for randomness (if supported by algorithm).
        preferred_sizes: Optional dict mapping filename or TEXT_<idx> -> preferred_size (0.5 to 2.0).
        gap: DEPRECATED. Use edge_gap and internal_gap instead. If provided, used for both.
        edge_gap: Edge gap (margin) in MCF units. Default 0.0.
        internal_gap: Internal gap (spacing between items) in MCF units. Default 0.0.
        texts: Optional list of MCF text block dicts (with 'area_width', 'area_height').
        use_slot_aspect: Optional dict mapping photo_idx -> bool. If True, use slot aspect ratio instead of image aspect ratio.
        original_photos: Optional list of original MCF photo dicts (for slot dimensions when use_slot_aspect=True).
        **kwargs: Additional algorithm-specific parameters.
    
    Returns:
        Tuple (success: bool, updated_photos: list, updated_texts: list, error_msg: str).
    """
    if algorithm is None:
        algorithm = CollageGeneratorAlgorithm(temperature=temperature)
    
    if texts is None:
        texts = []
    
    if use_slot_aspect is None:
        use_slot_aspect = {}
    
    # TreeBuilderAlgorithm MUST use slot dimensions (rectangle dimensions) to reconstruct the tree
    # It operates on the layout structure, not on individual image aspect ratios
    # Cost evaluation happens separately and can use image dimensions if needed
    from .algorithms.tree_builder import TreeBuilderAlgorithm
    if isinstance(algorithm, TreeBuilderAlgorithm):
        # Force all photos to use slot aspect ratio for tree building
        # The tree structure is based on layout slots, not image aspect ratios
        use_slot_aspect = {i: True for i in range(len(photos))}
    
    # Handle deprecated gap parameter
    if gap is not None:
        edge_gap = gap
        internal_gap = gap
    
    # Transform page to gap-free space (algorithm operates in gap-free coordinates)
    algo_page_width, algo_page_height = transform_page_to_gapfree(
        page_width_mcf, page_height_mcf, edge_gap, internal_gap
    )
    
    # Step 1: Translate MCF photos and texts to abstract layout rectangles
    photo_rects, error = _photos_to_rectangles(
        photos, mcf_base_folder, preferred_sizes, edge_gap, internal_gap, use_slot_aspect, original_photos
    )
    if error:
        return False, [], [], error
    
    text_rects, error = _texts_to_rectangles(texts, preferred_sizes, edge_gap, internal_gap)
    if error:
        return False, [], [], error
    
    # Combine photos and texts for layout algorithm
    all_rectangles = photo_rects + text_rects
    if not all_rectangles:
        return False, [], [], "No photos or texts to layout"
    
    # Step 2: Run the layout algorithm (operates on gap-adjusted page coordinates)
    success, positioned_rects, error_msg = algorithm.generate_layout(
        algo_page_width, algo_page_height, all_rectangles, **kwargs
    )
    if not success:
        return False, [], [], error_msg
    
    # CRITICAL: Validate that algorithm positioned ALL items (no silent photo losses)
    if len(positioned_rects) != len(all_rectangles):
        return False, [], [], f"Algorithm error: {len(all_rectangles)} items given, only {len(positioned_rects)} positioned. Items were lost!"
    
    # Validate all rectangles have positions
    for rect in positioned_rects:
        if rect.x is None or rect.y is None:
            return False, [], [], f"Algorithm error: Item {rect.item_id} was not positioned (x={rect.x}, y={rect.y})"
    
    # Step 3: Translate results back to MCF coordinates (apply gaps)
    # Split by item_id prefix: numeric = photo, TEXT_ = text
    photo_positioned = [r for r in positioned_rects if r.item_id.isdigit()]
    text_positioned = [r for r in positioned_rects if r.item_id.startswith('TEXT_')]
    
    updated_photos = _rectangles_to_photos(photos, photo_positioned, edge_gap, internal_gap)
    updated_texts = _rectangles_to_texts(texts, text_positioned, edge_gap, internal_gap)
    
    return True, updated_photos, updated_texts, ""


def _photos_to_rectangles(photos, mcf_base_folder, preferred_sizes=None, edge_gap=0.0, internal_gap=0.0, use_slot_aspect=None, original_photos=None):
    """
    Convert MCF photo list to abstract LayoutRectangle objects in gap-free space.
    
    For each photo, load the image, extract its dimensions, and create a LayoutRectangle.
    Dimensions are in image pixels; the algorithm will handle aspect ratios.
    
    Args:
        photos: List of MCF photo dicts.
        mcf_base_folder: Base folder for image paths.
        preferred_sizes: Optional dict mapping filename -> preferred_size.
        edge_gap: Edge gap (margin) in MCF units.
        internal_gap: Internal gap (spacing between items) in MCF units.
        use_slot_aspect: Optional dict mapping photo_idx -> bool. If True, use slot dimensions instead of image dimensions.
        original_photos: Optional list of original MCF photo dicts (used for slot dimensions when use_slot_aspect=True).
    
    Returns:
        Tuple (rectangles: list, error: str).
    """
    rectangles = []
    mcf_base = Path(mcf_base_folder)
    
    if use_slot_aspect is None:
        use_slot_aspect = {}
    
    for photo_idx, photo in enumerate(photos):
        fn = photo.get('filename', '')
        if not fn:
            return [], f"Photo {photo_idx} has no filename"
        
        # Determine if we should use slot aspect ratio for this photo
        use_slot = use_slot_aspect.get(photo_idx, False)
        
        # Try to use slot dimensions if requested, but fall back to image if invalid
        rect_width = None
        rect_height = None
        
        if use_slot:
            # Use ORIGINAL slot dimensions to preserve aspect ratio across iterations
            # (current photo dimensions may have been modified by previous layout runs)
            source_photo = original_photos[photo_idx] if original_photos and photo_idx < len(original_photos) else photo
            slot_width = source_photo.get('area_width', 0)
            slot_height = source_photo.get('area_height', 0)
            if slot_width > 0 and slot_height > 0:
                # Convert to gap-free space: add internal_gap to match evaluation coordinate system
                rect_width = float(slot_width) + internal_gap
                rect_height = float(slot_height) + internal_gap
            # else: fall through to use image dimensions
        
        # If not using slot, or slot dimensions were invalid, use image file dimensions
        if rect_width is None or rect_height is None:
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
            
            rect_width = float(img_width)
            rect_height = float(img_height)
        
        # Create LayoutRectangle
        item_id = str(photo_idx)
        preferred_size = 1.0
        if preferred_sizes and fn in preferred_sizes:
            preferred_size = preferred_sizes[fn]
        
        # Extract position from MCF if available (needed for TreeBuilder)
        # Use original_photos if available (for consistent positions across iterations)
        source_photo = original_photos[photo_idx] if original_photos and photo_idx < len(original_photos) else photo
        rect_x = None
        rect_y = None
        if 'area_left' in source_photo and 'area_top' in source_photo:
            # Adjust from MCF coordinates (with edge gap) to algorithm coordinates (gap-free)
            rect_x = float(source_photo['area_left']) - edge_gap
            rect_y = float(source_photo['area_top']) - edge_gap
        
        # Use determined dimensions (either image or slot)
        rect = LayoutRectangle(
            item_id=item_id,
            x=rect_x,
            y=rect_y,
            width=rect_width,
            height=rect_height,
            preferred_size=preferred_size,
            preserve_aspect_ratio=True  # Photos must preserve aspect ratio
        )
        rectangles.append(rect)
    
    return rectangles, ""


def _texts_to_rectangles(texts, preferred_sizes=None, edge_gap=0.0, internal_gap=0.0):
    """
    Convert MCF text block list to abstract LayoutRectangle objects in gap-free space.
    
    Text blocks do not preserve aspect ratio, so they can be stretched
    to fit layout slots without distortion concerns.
    
    Args:
        texts: List of MCF text block dicts (with 'area_width', 'area_height').
        preferred_sizes: Optional dict mapping TEXT_<idx> -> preferred_size.
        edge_gap: Edge gap (margin) in MCF units.
        internal_gap: Internal gap (spacing between items) in MCF units.
    
    Returns:
        Tuple (rectangles: list, error: str).
    """
    rectangles = []
    
    for text_idx, text in enumerate(texts):
        area_width = text.get('area_width', 0)
        area_height = text.get('area_height', 0)
        
        if area_width <= 0 or area_height <= 0:
            return [], f"Text block {text_idx} has invalid dimensions: {area_width}x{area_height}"
        
        # Use TEXT_<idx> as item_id for reversal later
        item_id = f"TEXT_{text_idx}"
        preferred_size = 1.0
        if preferred_sizes and item_id in preferred_sizes:
            preferred_size = preferred_sizes[item_id]
        
        # Extract position from MCF if available (needed for TreeBuilder)
        rect_x = None
        rect_y = None
        if 'area_left' in text and 'area_top' in text:
            # Adjust from MCF coordinates (with edge gap) to algorithm coordinates (gap-free)
            rect_x = float(text['area_left']) - edge_gap
            rect_y = float(text['area_top']) - edge_gap
        
        # Use MCF dimensions directly (algorithm will scale to fit)
        rect = LayoutRectangle(
            item_id=item_id,
            x=rect_x,
            y=rect_y,
            width=float(area_width),
            height=float(area_height),
            preferred_size=preferred_size,
            preserve_aspect_ratio=False  # Text blocks can stretch
        )
        rectangles.append(rect)
    
    return rectangles, ""


def _rectangles_to_photos(photos, rectangles, edge_gap=0.0, internal_gap=0.0):
    """
    Convert algorithm output (positioned LayoutRectangle) back to MCF photo format.
    
    Transforms from gap-free space back to MCF space using edge_gap and internal_gap.
    
    Args:
        photos: Original MCF photo list.
        rectangles: List of positioned LayoutRectangle objects from algorithm.
        edge_gap: Edge gap (margin) in MCF units.
        internal_gap: Internal gap (spacing between items) in MCF units.
    
    Returns:
        Updated photos list with new area_left/top/width/height.
    """
    updated_photos = []
    
    for rect in rectangles:
        item_id = rect.item_id
        photo_idx = int(item_id)
        
        if photo_idx < len(photos):
            photo = photos[photo_idx].copy()
            # Transform from gap-free space back to MCF space
            left, top, width, height = transform_item_from_gapfree(
                rect.x, rect.y, rect.width, rect.height,
                edge_gap, internal_gap
            )
            photo['area_left'] = left
            photo['area_top'] = top
            photo['area_width'] = width
            photo['area_height'] = height
            # CRITICAL: Preserve original preferred_size - do NOT use rect.preferred_size
            # which may have been modified by the algorithm
            # Preferred sizes can only be changed by user, never by algorithm
            updated_photos.append(photo)
    
    return updated_photos


def _rectangles_to_texts(texts, rectangles, edge_gap=0.0, internal_gap=0.0):
    """
    Convert algorithm output (positioned LayoutRectangle) back to MCF text block format.
    
    Transforms from gap-free space back to MCF space using edge_gap and internal_gap.
    
    Args:
        texts: Original MCF text block list.
        rectangles: List of positioned LayoutRectangle objects from algorithm.
        edge_gap: Edge gap (margin) in MCF units.
        internal_gap: Internal gap (spacing between items) in MCF units.
    
    Returns:
        Updated texts list with new area_left/top/width/height.
    """
    updated_texts = []
    
    for rect in rectangles:
        item_id = rect.item_id
        if not item_id.startswith('TEXT_'):
            continue
        
        text_idx = int(item_id.split('_')[1])
        
        if text_idx < len(texts):
            text = texts[text_idx].copy()
            # Transform from gap-free space back to MCF space
            left, top, width, height = transform_item_from_gapfree(
                rect.x, rect.y, rect.width, rect.height,
                edge_gap, internal_gap
            )
            text['area_left'] = left
            text['area_top'] = top
            text['area_width'] = width
            text['area_height'] = height
            updated_texts.append(text)
    
    return updated_texts
