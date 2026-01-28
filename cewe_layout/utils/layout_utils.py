"""Utility functions for layout operations.

Reusable helpers for building photo dimensions, evaluating layouts, etc.
"""
import os
from pathlib import Path
from .photo_utils import get_image_dimensions
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.algorithms.evaluator import evaluate_layout
from .gap_utils import transform_page_to_gapfree, transform_item_to_gapfree
from typing import Dict

def build_photo_dimensions(photos, mcf_base_folder, image_folder_attr=''):
    """Build photo_dimensions dict from photo list.
    
    Args:
        photos: List of photo dicts with filename, optional image_width/image_height
        mcf_base_folder: Base folder for MCF file
        image_folder_attr: Image folder attribute from MCF root
        
    Returns:
        Dict mapping filename -> (width, height)
    """
    photo_dimensions = {}
    
    for p in photos:
        fn = p.get('filename', '')
        if not fn:
            continue
        
        # Try to get from photo metadata first
        img_w = p.get('image_width')
        img_h = p.get('image_height')
        
        if img_w and img_h:
            photo_dimensions[fn] = (img_w, img_h)
        else:
            # Load from file
            safefn = fn.replace('safecontainer:/', '').lstrip('/')
            img_path = None
            if image_folder_attr:
                candidate = os.path.join(mcf_base_folder, image_folder_attr, safefn)
                if os.path.exists(candidate):
                    img_path = candidate
            if img_path is None:
                candidate = os.path.join(mcf_base_folder, safefn)
                if os.path.exists(candidate):
                    img_path = candidate
            
            if img_path:
                dims = get_image_dimensions(Path(img_path))
                if dims:
                    photo_dimensions[fn] = dims
    
    return photo_dimensions


def evaluate_layout_from_photos_texts(photos, texts, page_w, page_h, origin_left,
                                      preferred_sizes, edge_gap: Dict[str, float], internal_gap,
                                      is_spread=False,
                                      size_importance=100.0, acceptable_empty_fraction=0.05,
                                      undersized_threshold=0.5, undersized_penalty=5.0):
    """Evaluate a layout from photos and texts dicts.
    
    This is a reusable helper that both GUI and tests can use. The GUI should pass
    preferred_sizes from self.layout_mgr.get_size(), while tests can pass a simple dict.
    
    Args:
        photos: List of photo dicts with area_left, area_top, area_width, area_height, filename
        texts: List of text dicts with area_left, area_top, area_width, area_height
        page_w: Page width in MCF units
        page_h: Page height in MCF units
        origin_left: Origin offset for right pages
        preferred_sizes: Dict mapping filename/TEXT_n -> preferred size (float)
        edge_gap: Edge gap in MCF units
        internal_gap: Internal gap in MCF units
        is_spread: Whether this is a spread (affects gap-free transform)
        size_importance: Size importance factor
        acceptable_empty_fraction: Acceptable empty space fraction
        undersized_threshold: Undersized threshold ratio
        undersized_penalty: Undersized penalty factor
        
    Returns:
        LayoutCost object with evaluation results
    """
    # Transform to gap-free for evaluation
    gapfree_w, gapfree_h = transform_page_to_gapfree(page_w, page_h, edge_gap, internal_gap, is_spread)
    
    # Build rectangles for evaluation
    eval_rects = []
    is_left_page = origin_left == 0

    for p in photos:
        fn = p.get('filename', '')
        if not fn:
            continue
        
        # Get coordinates (relative to origin)
        left = p['area_left'] - origin_left
        top = p['area_top']
        w = p['area_width']
        h = p['area_height']
        
        # Transform to gap-free
        gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
            left, top, w, h, edge_gap, internal_gap, is_left_page, is_spread
        )
        
        rect = LayoutRectangle(fn, gf_width, gf_height, preferred_sizes.get(fn, 1.0))
        rect.x = gf_left
        rect.y = gf_top
        eval_rects.append(rect)
    
    for i, t in enumerate(texts):
        text_id = f'TEXT_{i}'
        
        # Get coordinates (relative to origin)
        left = t['area_left'] - origin_left
        top = t['area_top']
        w = t['area_width']
        h = t['area_height']
        
        # Transform to gap-free
        gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
            left, top, w, h, edge_gap, internal_gap, is_left_page, is_spread
        )
        
        rect = LayoutRectangle(text_id, gf_width, gf_height, preferred_sizes.get(text_id, 1.0), preserve_aspect_ratio=False)
        rect.x = gf_left
        rect.y = gf_top
        eval_rects.append(rect)
    
    return evaluate_layout(
        gapfree_w, gapfree_h, eval_rects,
        size_importance=size_importance,
        acceptable_empty_fraction=acceptable_empty_fraction,
        undersized_threshold=undersized_threshold,
        undersized_penalty=undersized_penalty
    )


def slot_changed_significantly(old_width: float, old_height: float,
                               new_width: float, new_height: float,
                               threshold: float = 0.10) -> bool:
    """Check if slot dimensions changed significantly between old and new sizes.

    This is used to detect when a photo slot has been resized so drastically that
    the old cutout/scale values (which may include manual user adjustments) are
    no longer valid and should be recalculated.

    Even if aspect ratio stays the same, scaling up/down requires new cutout values
    because the scale factor changes.

    Args:
        old_width: Original slot width in MCF units
        old_height: Original slot height in MCF units
        new_width: New slot width in MCF units
        new_height: New slot height in MCF units
        threshold: Relative change threshold (default 10% = 0.10)

    Returns:
        True if width OR height changed by more than threshold
    """
    if old_width <= 0 or old_height <= 0 or new_width <= 0 or new_height <= 0:
        return True  # Invalid dimensions - treat as changed

    # Calculate relative change in width and height
    width_change = abs(new_width - old_width) / old_width
    height_change = abs(new_height - old_height) / old_height

    # Return True if EITHER dimension changed significantly
    return width_change > threshold or height_change > threshold
