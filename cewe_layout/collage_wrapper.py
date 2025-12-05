"""
Layout generation wrapper for cewe-layout GUI.

This module bridges MCF photobook metadata and generic layout algorithms.
It translates:
- MCF photos to abstract LayoutRectangle objects (with dimensions from image metadata).
- Page dimensions from MCF units to page coordinates.
- Algorithm output (LayoutRectangle with positioned x, y) back to MCF area coordinates.

Layout algorithms themselves know nothing about files, MCF, or paths.
"""

from .algorithms.base import LayoutRectangle
from .gap_utils import (
    transform_page_to_gapfree,
    transform_item_to_gapfree,
    transform_item_from_gapfree
)


def generate_layout_for_page(photos, page_width_mcf, page_height_mcf, photo_dimensions,
                           algorithm, preferred_sizes=None,
                           edge_gap=0.0, internal_gap=0.0,
                           texts=None, use_slot_aspect=None, slot_aspect_ratios=None,
                           origin_left=0.0, pageno=None, **kwargs):
    """
    High-level function to generate a new layout for a page.
    
    Translates MCF photos and texts to abstract layout rectangles, runs the algorithm,
    and translates results back to MCF coordinates.
    
    Args:
        photos: List of MCF photo dicts (with 'filename' key).
        page_width_mcf: Page width in MCF units (0.1mm).
        page_height_mcf: Page height in MCF units (0.1mm).
        photo_dimensions: Dict mapping filename -> (width, height) in pixels. Required.
        algorithm: LayoutAlgorithm instance.
        preferred_sizes: Optional dict mapping filename or TEXT_<idx> -> preferred_size (0.5 to 2.0).
        edge_gap: Edge gap (margin) in MCF units. Default 0.0.
        internal_gap: Internal gap (spacing between items) in MCF units. Default 0.0.
        texts: Optional list of MCF text block dicts (with 'area_width', 'area_height').
        use_slot_aspect: Optional dict mapping photo_idx -> bool. If True, use slot aspect ratio instead of image aspect ratio.
        slot_aspect_ratios: Optional dict mapping item_idx -> aspect_ratio. Custom aspect ratios for slots.
        origin_left: Origin offset for right-side pages in MCF units. Default 0.0.
        pageno: Optional page number for error messages. Default None.
        **kwargs: Additional algorithm-specific parameters.
    
    Returns:
        Tuple (success: bool, updated_photos: list, updated_texts: list, error_msg: str).
    """
    
    if texts is None:
        texts = []
    
    if use_slot_aspect is None:
        use_slot_aspect = {}
    
    if slot_aspect_ratios is None:
        slot_aspect_ratios = {}
    
    # TreeBuilderAlgorithm and GridifyAlgorithm MUST use slot dimensions
    # TreeBuilder: operates on layout structure, not image aspect ratios
    # Gridify: refines existing layout by snapping to grid, needs actual slot dimensions
    # 
    # TODO: DESIGN ISSUE - This violates separation of concerns. The wrapper should not
    # need to know what each algorithm requires. Instead, algorithms should declare their
    # requirements (e.g., via a property like algorithm.requires_slot_dimensions or
    # algorithm.requires_current_layout) and the wrapper should query those properties.
    # Currently the wrapper must special-case TreeBuilder/Gridify behavior.
    from .algorithms.tree_builder import TreeBuilderAlgorithm
    from .algorithms.gridify import GridifyAlgorithm
    if isinstance(algorithm, (TreeBuilderAlgorithm, GridifyAlgorithm)):
        # Force all photos to use slot dimensions from CURRENT layout
        use_slot_aspect = {i: True for i in range(len(photos))}
    
    # Transform page to gap-free space (algorithm operates in gap-free coordinates)
    algo_page_width, algo_page_height = transform_page_to_gapfree(
        page_width_mcf, page_height_mcf, edge_gap, internal_gap
    )
    
    # Step 1: Translate MCF photos and texts to abstract layout rectangles
    photo_rects, error = _photos_to_rectangles(
        photos, photo_dimensions, preferred_sizes, edge_gap, internal_gap, 
        use_slot_aspect, slot_aspect_ratios, origin_left
    )
    if error:
        return False, [], [], error
    
    text_rects, error = _texts_to_rectangles(texts, preferred_sizes, edge_gap, internal_gap, origin_left, pageno)
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
    
    # VALIDATION: Check algorithm output quality
    warnings = []
    
    # 1. Check page bounds (critical - should not exceed page)
    for rect in positioned_rects:
        if rect.x < 0 or rect.y < 0:
            page_context = f"Page {pageno}: " if pageno else ""
            warnings.append(f"{page_context}WARNING: Item {rect.item_id} has negative position ({rect.x:.1f}, {rect.y:.1f})")
        if rect.x + rect.width > algo_page_width + 1.0:  # Allow 0.1mm tolerance
            page_context = f"Page {pageno}: " if pageno else ""
            warnings.append(f"{page_context}WARNING: Item {rect.item_id} exceeds page width (right edge at {rect.x + rect.width:.1f}, page width {algo_page_width:.1f})")
        if rect.y + rect.height > algo_page_height + 1.0:  # Allow 0.1mm tolerance
            page_context = f"Page {pageno}: " if pageno else ""
            warnings.append(f"{page_context}WARNING: Item {rect.item_id} exceeds page height (bottom edge at {rect.y + rect.height:.1f}, page height {algo_page_height:.1f})")
    
    # 2. Check aspect ratio preservation (informative - some algorithms may intentionally distort)
    for rect in positioned_rects:
        if rect.preserve_aspect_ratio and hasattr(rect, '_original_width') and hasattr(rect, '_original_height'):
            original_aspect = rect._original_width / rect._original_height if rect._original_height > 0 else 1.0
            final_aspect = rect.width / rect.height if rect.height > 0 else 1.0
            aspect_diff = abs(original_aspect - final_aspect) / original_aspect if original_aspect > 0 else 0
            if aspect_diff > 0.01:  # More than 1% aspect ratio change
                page_context = f"Page {pageno}: " if pageno else ""
                warnings.append(f"{page_context}INFO: Item {rect.item_id} aspect ratio changed by {aspect_diff*100:.1f}% (may be intentional)")
    
    # 3. Check for overlaps (informative - some layouts may intentionally overlap)
    overlap_count = 0
    for i, rect1 in enumerate(positioned_rects):
        for rect2 in positioned_rects[i+1:]:
            # Check for rectangle overlap (allowing small tolerance for floating point)
            if (rect1.x < rect2.x + rect2.width - 1.0 and
                rect1.x + rect1.width > rect2.x + 1.0 and
                rect1.y < rect2.y + rect2.height - 1.0 and
                rect1.y + rect1.height > rect2.y + 1.0):
                overlap_count += 1
    
    if overlap_count > 0:
        page_context = f"Page {pageno}: " if pageno else ""
        warnings.append(f"{page_context}INFO: {overlap_count} overlapping item pair(s) detected (may be intentional)")
    
    # Log warnings if any
    if warnings:
        import logging
        logger = logging.getLogger(__name__)
        for warning in warnings:
            logger.warning(warning)
    
    # Step 3: Translate results back to MCF coordinates (apply gaps)
    # Split by item_id prefix: numeric = photo, TEXT_ = text
    photo_positioned = [r for r in positioned_rects if r.item_id.isdigit()]
    text_positioned = [r for r in positioned_rects if r.item_id.startswith('TEXT_')]
    
    updated_photos = _rectangles_to_photos(photos, photo_positioned, edge_gap, internal_gap)
    updated_texts = _rectangles_to_texts(texts, text_positioned, edge_gap, internal_gap)
    
    return True, updated_photos, updated_texts, ""


def _photos_to_rectangles(photos, photo_dimensions, preferred_sizes=None, edge_gap=0.0, internal_gap=0.0, use_slot_aspect=None, slot_aspect_ratios=None, origin_left=0.0):
    """
    Convert MCF photo list to abstract LayoutRectangle objects in gap-free space.
    
    Uses pre-loaded photo dimensions from cache. Does not load images.
    Positions are ALWAYS taken from current layout (photos parameter).
    Dimensions (aspect ratio) come from either current slot or image file based on use_slot_aspect.
    
    Args:
        photos: List of MCF photo dicts (current layout).
        photo_dimensions: Dict mapping filename -> (width, height) in pixels. Required.
        preferred_sizes: Optional dict mapping filename -> preferred_size.
        edge_gap: Edge gap (margin) in MCF units.
        internal_gap: Internal gap (spacing between items) in MCF units.
        use_slot_aspect: Optional dict mapping photo_idx -> bool. If True, use current slot aspect ratio instead of image aspect ratio.
        slot_aspect_ratios: Optional dict mapping item_idx -> aspect_ratio. Custom aspect ratios for slots.
        origin_left: Origin offset for right-side pages in MCF units.
    
    Returns:
        Tuple (rectangles: list, error: str).
    """
    rectangles = []
    
    if use_slot_aspect is None:
        use_slot_aspect = {}
    
    if slot_aspect_ratios is None:
        slot_aspect_ratios = {}
    
    for photo_idx, photo in enumerate(photos):
        fn = photo.get('filename', '')
        if not fn:
            return [], f"Photo {photo_idx} has no filename"
        
        # Determine dimensions based on user's aspect ratio choice
        use_slot = use_slot_aspect.get(photo_idx, False)
        rect_width = None
        rect_height = None
        
        if use_slot:
            # User wants slot aspect ratio
            # Check if we have a custom aspect ratio for this item
            if photo_idx in slot_aspect_ratios:
                # Use custom aspect ratio with area from CURRENT slot
                slot_width = photo.get('area_width', 0)
                slot_height = photo.get('area_height', 0)
                if slot_width > 0 and slot_height > 0:
                    # Calculate area in gap-free space
                    slot_area = (float(slot_width) + internal_gap) * (float(slot_height) + internal_gap)
                    custom_aspect = slot_aspect_ratios[photo_idx]
                    # Compute dimensions from area and aspect ratio
                    # area = w * h, aspect = w / h
                    # => w = sqrt(area * aspect), h = sqrt(area / aspect)
                    import math
                    rect_width = math.sqrt(slot_area * custom_aspect)
                    rect_height = math.sqrt(slot_area / custom_aspect)
                # else: fall through to use current slot dimensions
            
            # If no custom aspect ratio or calculation failed, use current slot dimensions
            if rect_width is None or rect_height is None:
                slot_width = photo.get('area_width', 0)
                slot_height = photo.get('area_height', 0)
                if slot_width > 0 and slot_height > 0:
                    # Convert to gap-free space: add internal_gap to match evaluation coordinate system
                    rect_width = float(slot_width) + internal_gap
                    rect_height = float(slot_height) + internal_gap
                # else: fall through to use image dimensions
        
        # If not using slot, or slot dimensions were invalid, use image file dimensions
        if rect_width is None or rect_height is None:
            # User wants photo's natural aspect ratio
            # Dimensions must be in cache
            if not photo_dimensions or fn not in photo_dimensions:
                return [], f"Photo dimensions not found in cache for: {fn}. All photo dimensions must be provided."
            
            img_width, img_height = photo_dimensions[fn]
            rect_width = float(img_width)
            rect_height = float(img_height)
        
        # Create LayoutRectangle
        item_id = str(photo_idx)
        preferred_size = 1.0
        if preferred_sizes and fn in preferred_sizes:
            preferred_size = preferred_sizes[fn]
        
        # Extract position from CURRENT layout (always use current photo, never original_photos)
        rect_x = None
        rect_y = None
        if 'area_left' in photo and 'area_top' in photo:
            # Adjust from MCF coordinates (with edge gap and origin offset) to algorithm coordinates (gap-free, page-relative)
            # Subtract origin_left to convert from spread coordinates to page coordinates
            rect_x = float(photo['area_left']) - origin_left - edge_gap
            rect_y = float(photo['area_top']) - edge_gap
        
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


def _texts_to_rectangles(texts, preferred_sizes=None, edge_gap=0.0, internal_gap=0.0, origin_left=0.0, pageno=None):
    """
    Convert MCF text block list to abstract LayoutRectangle objects in gap-free space.
    
    Text blocks do not preserve aspect ratio, so they can be stretched
    to fit layout slots without distortion concerns.
    
    Args:
        texts: List of MCF text block dicts (with 'area_width', 'area_height').
        preferred_sizes: Optional dict mapping TEXT_<idx> -> preferred_size.
        edge_gap: Edge gap (margin) in MCF units.
        internal_gap: Internal gap (spacing between items) in MCF units.
        origin_left: Origin offset for right-side pages in MCF units.
        pageno: Optional page number for error messages.
    
    Returns:
        Tuple (rectangles: list, error: str).
    """
    rectangles = []
    
    for text_idx, text in enumerate(texts):
        area_width = text.get('area_width', 0)
        area_height = text.get('area_height', 0)
        
        if area_width <= 0 or area_height <= 0:
            page_context = f"Page {pageno}: " if pageno else ""
            return [], f"{page_context}Text block {text_idx} has invalid dimensions: {area_width}x{area_height}"
        
        # Use TEXT_<idx> as item_id for reversal later
        item_id = f"TEXT_{text_idx}"
        preferred_size = 1.0
        if preferred_sizes and item_id in preferred_sizes:
            preferred_size = preferred_sizes[item_id]
        
        # Extract position from MCF if available (needed for TreeBuilder and Gridify)
        rect_x = None
        rect_y = None
        if 'area_left' in text and 'area_top' in text:
            # Adjust from MCF coordinates (with edge gap and origin offset) to algorithm coordinates (gap-free, page-relative)
            # Subtract origin_left to convert from spread coordinates to page coordinates
            rect_x = float(text['area_left']) - origin_left - edge_gap
            rect_y = float(text['area_top']) - edge_gap
        
        # Transform dimensions to gap-free space (same as photos for consistency)
        # MCF dimensions need internal_gap added to match gap-free coordinate system
        rect = LayoutRectangle(
            item_id=item_id,
            x=rect_x,
            y=rect_y,
            width=float(area_width) + internal_gap,
            height=float(area_height) + internal_gap,
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
        Updated photos list with new area_left/top/width/height in same order as input.
    """
    # Pre-allocate list to ensure output order matches input order
    updated_photos = [None] * len(photos)
    
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
            updated_photos[photo_idx] = photo
    
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
        Updated texts list with new area_left/top/width/height in same order as input.
    """
    # Pre-allocate list to ensure output order matches input order
    updated_texts = [None] * len(texts)
    
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
            updated_texts[text_idx] = text
    
    return updated_texts
