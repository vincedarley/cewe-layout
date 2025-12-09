"""Utility functions for layout operations.

Helpers for building photo dimensions, evaluating layouts, etc.
"""
import os
from pathlib import Path
from .photos import get_image_dimensions
from .algorithms.base import LayoutRectangle
from .algorithms.evaluator import evaluate_layout
from .gap_utils import transform_page_to_gapfree, transform_item_to_gapfree


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
                                      preferred_sizes, edge_gap, internal_gap,
                                      size_importance=100.0, acceptable_empty_fraction=0.05,
                                      undersized_threshold=0.5, undersized_penalty=5.0):
    """Evaluate a layout from photos and texts dicts.
    
    Args:
        photos: List of photo dicts with area_left, area_top, area_width, area_height, filename
        texts: List of text dicts with area_left, area_top, area_width, area_height
        page_w: Page width in MCF units
        page_h: Page height in MCF units
        origin_left: Origin offset for right pages
        preferred_sizes: Dict mapping filename/TEXT_n -> preferred size
        edge_gap: Edge gap in MCF units
        internal_gap: Internal gap in MCF units
        size_importance: Size importance factor
        acceptable_empty_fraction: Acceptable empty space fraction
        undersized_threshold: Undersized threshold ratio
        undersized_penalty: Undersized penalty factor
        
    Returns:
        LayoutCost object with evaluation results
    """
    # Transform to gap-free for evaluation
    gapfree_w, gapfree_h = transform_page_to_gapfree(page_w, page_h, edge_gap, internal_gap, False)
    
    # Build rectangles for evaluation
    eval_rects = []
    
    for p in photos:
        fn = p.get('filename', '')
        if not fn:
            continue
        gapfree_rect = transform_item_to_gapfree(
            p['area_left'] - origin_left, p['area_top'],
            p['area_width'], p['area_height'],
            edge_gap, internal_gap, False, True
        )
        x, y, w, h = gapfree_rect
        rect = LayoutRectangle(fn, w, h, preferred_sizes.get(fn, 1.0))
        rect.x = x
        rect.y = y
        eval_rects.append(rect)
    
    for i, t in enumerate(texts):
        text_id = f'TEXT_{i}'
        gapfree_rect = transform_item_to_gapfree(
            t['area_left'] - origin_left, t['area_top'],
            t['area_width'], t['area_height'],
            edge_gap, internal_gap, False, True
        )
        x, y, w, h = gapfree_rect
        rect = LayoutRectangle(text_id, w, h, preferred_sizes.get(text_id, 1.0), preserve_aspect_ratio=False)
        rect.x = x
        rect.y = y
        eval_rects.append(rect)
    
    return evaluate_layout(
        gapfree_w, gapfree_h, eval_rects,
        size_importance=size_importance,
        acceptable_empty_fraction=acceptable_empty_fraction,
        undersized_threshold=undersized_threshold,
        undersized_penalty=undersized_penalty
    )
