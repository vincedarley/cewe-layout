"""Pairing abstraction layer for layout algorithms.

This module provides the critical abstraction that allows algorithms to remain
completely unaware of photo-text pairing. It merges paired photo+text into single
LayoutRectangle units before algorithm execution, then splits results back.

The pairing wrapper follows the existing collage_wrapper.py philosophy:
algorithms know nothing about pairing relationships, MCF structure, or UI concepts.
"""

from cewe_layout.algorithms.base import LayoutRectangle


# Text height as fraction of page height (user decision: 3% for single-line captions)
TEXT_HEIGHT_FRACTION = 0.03


def merge_paired_items(photos, texts, pairings, photo_dimensions, preferred_sizes=None,
                      edge_gap=None, internal_gap=0.0, use_slot_aspect=None, 
                      slot_aspect_ratios=None, origin_left=0.0, is_left_page=True,
                      has_full_bleed=False, force_use_current_layout=False):
    """Merge paired photo+text into single LayoutRectangle units for algorithm processing.
    
    Creates compound items for paired photo+text combinations, using the photo's
    dimensions and properties. Paired texts are excluded from separate text list.
    
    This maintains algorithm abstraction: algorithms see standard LayoutRectangles
    and remain unaware of pairing relationships.
    
    Args:
        photos: List of MCF photo dicts
        texts: List of MCF text dicts
        pairings: Set of photo indices that have paired text
        photo_dimensions: Dict mapping filename -> (width, height) in pixels
        preferred_sizes: Optional dict mapping filename/TEXT_idx -> preferred_size
        edge_gap: Edge gap dict in MCF units
        internal_gap: Internal gap in MCF units
        use_slot_aspect: Dict mapping photo_idx -> bool for slot aspect usage
        slot_aspect_ratios: Dict mapping item_idx -> custom aspect ratio
        origin_left: Origin offset for right pages in MCF units
        is_left_page: True if left/even page, False if right/odd page
        has_full_bleed: True if cover/spread with bleed on all 4 sides
        force_use_current_layout: If True, use current layout dimensions
    
    Returns:
        Tuple (photo_rects: list, text_rects: list, paired_text_indices: set)
        Where paired_text_indices contains the text indices that were paired (for splitting later)
    """
    from cewe_layout.collage_wrapper import _photos_to_rectangles, _texts_to_rectangles
    
    if pairings is None:
        pairings = set()
    
    if use_slot_aspect is None:
        use_slot_aspect = {}
    
    if slot_aspect_ratios is None:
        slot_aspect_ratios = {}
    
    # Track which text indices are paired (for exclusion from text list)
    paired_text_indices = set()
    
    # Build mapping from photo_idx to text_idx for paired items
    photo_to_text = {}
    for photo_idx in pairings:
        if photo_idx < len(photos):
            photo = photos[photo_idx]
            photo_bottom = photo.get('area_top', 0) + photo.get('area_height', 0)
            photo_left = photo.get('area_left', 0)
            photo_width = photo.get('area_width', 0)
            
            # Find matching text (directly below with matching width)
            # Use same tolerance as detection (50 MCF units = 5mm)
            tolerance = 50
            for text_idx, text in enumerate(texts):
                text_top = text.get('area_top', 0)
                text_left = text.get('area_left', 0)
                text_width = text.get('area_width', 0)
                
                vertical_gap = abs(photo_bottom - text_top)
                width_diff = abs(photo_width - text_width)
                horizontal_offset = abs(photo_left - text_left)
                
                if (vertical_gap <= tolerance and 
                    width_diff <= tolerance and 
                    horizontal_offset <= tolerance):
                    photo_to_text[photo_idx] = text_idx
                    paired_text_indices.add(text_idx)
                    break
    
    # First, create rectangles for all photos using existing logic
    photo_rects, error = _photos_to_rectangles(
        photos, photo_dimensions, preferred_sizes, edge_gap, internal_gap,
        use_slot_aspect, slot_aspect_ratios, origin_left, is_left_page,
        has_full_bleed, force_use_current_layout
    )
    
    if error:
        return [], [], paired_text_indices, error
    
    # Modify item_ids for paired photos to indicate pairing
    for photo_idx in pairings:
        if photo_idx < len(photo_rects) and photo_idx in photo_to_text:
            text_idx = photo_to_text[photo_idx]
            # Change item_id to indicate paired unit: "{photo_idx}+TEXT_{text_idx}"
            photo_rects[photo_idx].item_id = f"{photo_idx}+TEXT_{text_idx}"
    
    # Create rectangles for unpaired texts only (exclude paired ones)
    unpaired_texts = [text for i, text in enumerate(texts) if i not in paired_text_indices]
    
    if unpaired_texts:
        text_rects, error = _texts_to_rectangles(
            unpaired_texts, preferred_sizes, edge_gap, internal_gap,
            origin_left, None, is_left_page, has_full_bleed
        )
        
        if error:
            return [], [], paired_text_indices, error
        
        # Remap text indices to account for excluded paired texts
        # Build mapping from unpaired list index to original text index
        unpaired_to_original = [i for i in range(len(texts)) if i not in paired_text_indices]
        for i, rect in enumerate(text_rects):
            if i < len(unpaired_to_original):
                original_idx = unpaired_to_original[i]
                rect.item_id = f"TEXT_{original_idx}"
    else:
        text_rects = []
    
    return photo_rects, text_rects, paired_text_indices, ""


def split_paired_results(rectangles, page_height_mcf, paired_text_indices):
    """Split algorithm results for paired units back into separate photo and text.
    
    Identifies paired items by "+" in item_id, splits them into:
    - Text: Fixed height (3% of page height), positioned below photo
    - Photo: Remaining height, keeps algorithm's position and width
    
    Args:
        rectangles: List of positioned LayoutRectangle objects from algorithm
        page_height_mcf: Page height in MCF units (for calculating text height)
        paired_text_indices: Set of original text indices that were paired
    
    Returns:
        Tuple (photo_rects: list, text_rects: list)
    """
    photo_rects = []
    text_rects = []
    
    # Calculate fixed text height in gap-free coordinates
    # Note: This is an approximation - ideally we'd use gap-free page height,
    # but for small text boxes the difference is negligible
    text_height_fixed = page_height_mcf * TEXT_HEIGHT_FRACTION
    
    for rect in rectangles:
        item_id = rect.item_id
        
        if '+TEXT_' in item_id:
            # This is a paired unit - split it
            parts = item_id.split('+TEXT_')
            photo_idx_str = parts[0]
            text_idx_str = parts[1]
            
            # Create separate photo rectangle (gets most of the height)
            photo_height = rect.height - text_height_fixed
            photo_rect = LayoutRectangle(
                item_id=photo_idx_str,
                x=rect.x,
                y=rect.y,
                width=rect.width,
                height=photo_height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=True
            )
            photo_rect.actual_size = rect.actual_size
            photo_rects.append(photo_rect)
            
            # Create separate text rectangle (fixed height at bottom)
            text_rect = LayoutRectangle(
                item_id=f"TEXT_{text_idx_str}",
                x=rect.x,
                y=rect.y + photo_height,
                width=rect.width,
                height=text_height_fixed,
                preferred_size=1.0,  # Text always uses default size
                preserve_aspect_ratio=False
            )
            text_rect.actual_size = 0.0  # Text doesn't have meaningful actual_size
            text_rects.append(text_rect)
        
        elif item_id.startswith('TEXT_'):
            # Unpaired text - keep as is
            text_rects.append(rect)
        
        else:
            # Unpaired photo - keep as is
            photo_rects.append(rect)
    
    return photo_rects, text_rects
