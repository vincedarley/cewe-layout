"""
Gap estimation and handling utilities.

Handles uniform spacing (gaps) between photos and page edges.
Separates edge gaps (margins) from inter-photo gaps.
"""

from typing import List, Dict, Any, Tuple


def estimate_gaps(photos: List[Dict[str, Any]], page_width: float, page_height: float, 
                  origin_left: float = 0.0) -> Tuple[float, float]:
    """
    Estimate edge gap and inter-photo gap separately.
    
    Args:
        photos: List of photo dicts with area_left, area_top, area_width, area_height.
        page_width: Page width in MCF units.
        page_height: Page height in MCF units.
        origin_left: For right-hand pages, the absolute X offset of this page (default 0.0).
    
    Returns:
        Tuple (edge_gap, inter_photo_gap) in MCF units (0.1mm).
        Returns (0.0, 0.0) if gaps cannot be reliably estimated.
    """
    if not photos:
        return 0.0, 0.0
    
    # Calculate page bounds in absolute coordinates
    page_left = origin_left
    page_right = origin_left + page_width
    page_top = 0.0
    page_bottom = page_height
    
    edge_gaps = []
    inter_photo_gaps = []
    
    # Collect all edge gaps (margins from page boundaries)
    for p in photos:
        left = p.get('area_left', 0)
        top = p.get('area_top', 0)
        width = p.get('area_width', 0)
        height = p.get('area_height', 0)
        right = left + width
        bottom = top + height
        
        # Left edge (distance from page left boundary)
        left_margin = left - page_left
        if 0 < left_margin < page_width * 0.2:  # Within 20% of page width
            edge_gaps.append(left_margin)
        
        # Right edge (distance from page right boundary)
        right_margin = page_right - right
        if 0 < right_margin < page_width * 0.2:
            edge_gaps.append(right_margin)
        
        # Top edge (distance from page top)
        top_margin = top - page_top
        if 0 < top_margin < page_height * 0.2:
            edge_gaps.append(top_margin)
        
        # Bottom edge (distance from page bottom)
        bottom_margin = page_bottom - bottom
        if 0 < bottom_margin < page_height * 0.2:
            edge_gaps.append(bottom_margin)
    
    # Collect inter-photo gaps (spacing between adjacent photos)
    for i, p1 in enumerate(photos):
        left1 = p1.get('area_left', 0)
        top1 = p1.get('area_top', 0)
        width1 = p1.get('area_width', 0)
        height1 = p1.get('area_height', 0)
        right1 = left1 + width1
        bottom1 = top1 + height1
        
        for p2 in photos[i+1:]:
            left2 = p2.get('area_left', 0)
            top2 = p2.get('area_top', 0)
            width2 = p2.get('area_width', 0)
            height2 = p2.get('area_height', 0)
            right2 = left2 + width2
            bottom2 = top2 + height2
            
            # Check horizontal adjacency (p2 to the right of p1)
            vertical_overlap = not (bottom1 <= top2 or bottom2 <= top1)
            if vertical_overlap and left2 > right1:
                gap = left2 - right1
                if 0 < gap < page_width * 0.1:  # Reasonable gap
                    inter_photo_gaps.append(gap)
            
            # Check horizontal adjacency (p1 to the right of p2)
            if vertical_overlap and left1 > right2:
                gap = left1 - right2
                if 0 < gap < page_width * 0.1:
                    inter_photo_gaps.append(gap)
            
            # Check vertical adjacency (p2 below p1)
            horizontal_overlap = not (right1 <= left2 or right2 <= left1)
            if horizontal_overlap and top2 > bottom1:
                gap = top2 - bottom1
                if 0 < gap < page_height * 0.1:
                    inter_photo_gaps.append(gap)
            
            # Check vertical adjacency (p1 below p2)
            if horizontal_overlap and top1 > bottom2:
                gap = top1 - bottom2
                if 0 < gap < page_height * 0.1:
                    inter_photo_gaps.append(gap)
    
    # Calculate average edge gap
    edge_gap = sum(edge_gaps) / len(edge_gaps) if edge_gaps else 0.0
    
    # Calculate average inter-photo gap
    inter_gap = sum(inter_photo_gaps) / len(inter_photo_gaps) if inter_photo_gaps else 0.0
    
    return edge_gap, inter_gap


def estimate_gap(photos: List[Dict[str, Any]], page_width: float, page_height: float) -> float:
    """
    Legacy function for backward compatibility.
    Returns the inter-photo gap (or edge gap if no inter-photo gaps found).
    
    Args:
        photos: List of photo dicts with area_left, area_top, area_width, area_height.
        page_width: Page width in MCF units.
        page_height: Page height in MCF units.
    
    Returns:
        Estimated gap in MCF units (0.1mm).
    """
    edge_gap, inter_gap = estimate_gaps(photos, page_width, page_height)
    # Prefer inter-photo gap; fall back to edge gap
    return inter_gap if inter_gap > 0 else edge_gap


def apply_gap_to_layout(page_width: float, page_height: float, 
                       photos: List[Dict[str, Any]], gap: float) -> List[Dict[str, Any]]:
    """
    Apply uniform gap to a layout by adjusting photo positions and sizes.
    
    This is used to add gaps to a layout generated by an algorithm that doesn't
    know about gaps. Each photo's position is increased by gap, and size is
    decreased by gap.
    
    Args:
        page_width: Page width in MCF units.
        page_height: Page height in MCF units.
        photos: List of photo dicts to adjust.
        gap: Gap value in MCF units.
    
    Returns:
        New list of photo dicts with adjusted positions/sizes.
    """
    if gap <= 0:
        return photos
    
    adjusted = []
    for p in photos:
        adj = p.copy()
        
        # Increase position by gap (margin from edges and other photos)
        adj['area_left'] = p.get('area_left', 0) + gap
        adj['area_top'] = p.get('area_top', 0) + gap
        
        # Decrease size by gap (to create spacing between photos)
        adj['area_width'] = max(0, p.get('area_width', 0) - gap)
        adj['area_height'] = max(0, p.get('area_height', 0) - gap)
        
        adjusted.append(adj)
    
    return adjusted


def remove_gap_from_layout(photos: List[Dict[str, Any]], gap: float) -> List[Dict[str, Any]]:
    """
    Remove gap from a layout (inverse of apply_gap_to_layout).
    
    Used before passing photos to an algorithm that should work on gap-free coordinates.
    Each photo's position is decreased by gap, and size is increased by gap.
    
    Args:
        photos: List of photo dicts to adjust.
        gap: Gap value in MCF units.
    
    Returns:
        New list of photo dicts with gap removed.
    """
    if gap <= 0:
        return photos
    
    adjusted = []
    for p in photos:
        adj = p.copy()
        
        # Decrease position by gap
        adj['area_left'] = max(0, p.get('area_left', 0) - gap)
        adj['area_top'] = max(0, p.get('area_top', 0) - gap)
        
        # Increase size by gap
        adj['area_width'] = p.get('area_width', 0) + gap
        adj['area_height'] = p.get('area_height', 0) + gap
        
        adjusted.append(adj)
    
    return adjusted
