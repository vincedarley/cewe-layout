"""Utilities for detecting and managing photo-text pairing.

This module provides logic for detecting when a text box is positioned
directly underneath a photo in a way that suggests they should be paired
(e.g., photo captions).
"""


def detect_paired_text(photo, all_texts, tolerance=50):
    """Detect if a text box is paired with a photo.
    
    A text box is considered paired if it is:
    - Directly below the photo (bottom of photo ≈ top of text)
    - Same width as the photo
    - Both conditions within the specified tolerance
    
    Args:
        photo: Photo dict with area_left, area_top, area_width, area_height
        all_texts: List of all text dicts on the page
        tolerance: Maximum difference in MCF units (default 50 = 5mm)
    
    Returns:
        Index of paired text box in all_texts list, or None if no match found
    """
    photo_left = photo.get('area_left', 0)
    photo_top = photo.get('area_top', 0)
    photo_width = photo.get('area_width', 0)
    photo_height = photo.get('area_height', 0)
    photo_bottom = photo_top + photo_height
    
    for text_idx, text in enumerate(all_texts):
        text_left = text.get('area_left', 0)
        text_top = text.get('area_top', 0)
        text_width = text.get('area_width', 0)
        
        # Check if text is directly below photo (bottom of photo = top of text)
        vertical_gap = abs(photo_bottom - text_top)
        if vertical_gap > tolerance:
            continue
        
        # Check if widths match
        width_diff = abs(photo_width - text_width)
        if width_diff > tolerance:
            continue
        
        # Check if horizontal positions match (left edges align)
        horizontal_offset = abs(photo_left - text_left)
        if horizontal_offset > tolerance:
            continue
        
        # Found a match
        return text_idx
    
    return None


def is_paired_text(photo_idx, text_idx, photos, texts, tolerance=50):
    """Check if a specific photo-text pair is geometrically compatible.
    
    This is useful for validating existing pairings or manual pairing requests.
    
    Args:
        photo_idx: Index of photo in photos list
        text_idx: Index of text in texts list
        photos: List of all photo dicts
        texts: List of all text dicts
        tolerance: Maximum difference in MCF units (default 50 = 5mm)
    
    Returns:
        True if the photo and text are geometrically paired, False otherwise
    """
    if photo_idx < 0 or photo_idx >= len(photos):
        return False
    if text_idx < 0 or text_idx >= len(texts):
        return False
    
    photo = photos[photo_idx]
    text = texts[text_idx]
    
    photo_left = photo.get('area_left', 0)
    photo_top = photo.get('area_top', 0)
    photo_width = photo.get('area_width', 0)
    photo_height = photo.get('area_height', 0)
    photo_bottom = photo_top + photo_height
    
    text_left = text.get('area_left', 0)
    text_top = text.get('area_top', 0)
    text_width = text.get('area_width', 0)
    
    # Check all three conditions
    vertical_gap = abs(photo_bottom - text_top)
    width_diff = abs(photo_width - text_width)
    horizontal_offset = abs(photo_left - text_left)
    
    return (vertical_gap <= tolerance and 
            width_diff <= tolerance and 
            horizontal_offset <= tolerance)
