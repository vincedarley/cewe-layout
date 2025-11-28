"""
Gap estimation and handling utilities.

Handles uniform spacing (gaps) between photos and page edges.
Separates edge gaps (margins) from inter-photo gaps.
"""

from typing import List, Dict, Any, Tuple, NamedTuple


class GapAnalysis(NamedTuple):
    """Result of gap analysis."""
    edge_gap: float  # Average positive edge gap (margin) in MCF units
    inter_photo_gap: float  # Average inter-photo gap in MCF units
    bleed: float  # Maximum negative edge margin (bleed beyond page) in MCF units, always >= 0
    edge_gaps: List[float]  # All detected positive edge gaps
    inter_photo_gaps: List[float]  # All detected inter-photo gaps
    bleed_margins: List[float]  # All negative edge margins (absolute values)


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
    analysis = analyze_gaps(photos, page_width, page_height, origin_left)
    return analysis.edge_gap, analysis.inter_photo_gap


def analyze_gaps(photos: List[Dict[str, Any]], page_width: float, page_height: float,
                 origin_left: float = 0.0) -> GapAnalysis:
    """
    Analyze gaps in detail, including bleed (negative margins).
    
    Args:
        photos: List of photo dicts with area_left, area_top, area_width, area_height.
        page_width: Page width in MCF units.
        page_height: Page height in MCF units.
        origin_left: For right-hand pages, the absolute X offset of this page (default 0.0).
    
    Returns:
        GapAnalysis with edge_gap, inter_photo_gap, bleed, and all detected gaps.
    """
    if not photos:
        return GapAnalysis(0.0, 0.0, 0.0, [], [], [])
    
    # Calculate page bounds in absolute coordinates
    page_left = origin_left
    page_right = origin_left + page_width
    page_top = 0.0
    page_bottom = page_height
    
    edge_gaps = []
    bleed_margins = []
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
        if left_margin < 0:
            # Negative margin = bleed beyond page edge
            bleed_margins.append(abs(left_margin))
        elif 10 < left_margin < page_width * 0.05:  # Between 1mm and 5% of page width
            edge_gaps.append(left_margin)
        
        # Right edge (distance from page right boundary)
        right_margin = page_right - right
        if right_margin < 0:
            bleed_margins.append(abs(right_margin))
        elif 10 < right_margin < page_width * 0.05:
            edge_gaps.append(right_margin)
        
        # Top edge (distance from page top)
        top_margin = top - page_top
        if top_margin < 0:
            bleed_margins.append(abs(top_margin))
        elif 10 < top_margin < page_height * 0.05:
            edge_gaps.append(top_margin)
        
        # Bottom edge (distance from page bottom)
        bottom_margin = page_bottom - bottom
        if bottom_margin < 0:
            bleed_margins.append(abs(bottom_margin))
        elif 10 < bottom_margin < page_height * 0.05:
            edge_gaps.append(bottom_margin)
    
    # Collect inter-photo gaps (spacing between adjacent photos)
    # For each photo, find the closest photo to the right and below
    min_overlap = 200.0  # Minimum 20mm overlap to consider photos adjacent
    
    for i, p1 in enumerate(photos):
        left1 = p1.get('area_left', 0)
        top1 = p1.get('area_top', 0)
        width1 = p1.get('area_width', 0)
        height1 = p1.get('area_height', 0)
        right1 = left1 + width1
        bottom1 = top1 + height1
        
        # Find closest photo to the right (with sufficient Y-overlap)
        closest_right_gap = None
        for j, p2 in enumerate(photos):
            if i == j:
                continue
            left2 = p2.get('area_left', 0)
            top2 = p2.get('area_top', 0)
            width2 = p2.get('area_width', 0)
            height2 = p2.get('area_height', 0)
            right2 = left2 + width2
            bottom2 = top2 + height2
            
            # Check Y-overlap (at least 20mm)
            y_overlap_start = max(top1, top2)
            y_overlap_end = min(bottom1, bottom2)
            y_overlap = max(0, y_overlap_end - y_overlap_start)
            
            if y_overlap >= min_overlap:
                # Photo has sufficient Y-overlap, check if it's to the right
                gap = left2 - right1
                # Allow mild overlap (negative gap up to -10mm) or positive gap
                if -100 < gap:  # -10mm to infinity
                    if closest_right_gap is None or abs(gap) < abs(closest_right_gap):
                        closest_right_gap = gap
        
        # Record the gap if it's positive and significant (>1mm)
        if closest_right_gap is not None and closest_right_gap > 10:
            inter_photo_gaps.append(closest_right_gap)
        
        # Find closest photo below (with sufficient X-overlap)
        closest_below_gap = None
        for j, p2 in enumerate(photos):
            if i == j:
                continue
            left2 = p2.get('area_left', 0)
            top2 = p2.get('area_top', 0)
            width2 = p2.get('area_width', 0)
            height2 = p2.get('area_height', 0)
            right2 = left2 + width2
            bottom2 = top2 + height2
            
            # Check X-overlap (at least 20mm)
            x_overlap_start = max(left1, left2)
            x_overlap_end = min(right1, right2)
            x_overlap = max(0, x_overlap_end - x_overlap_start)
            
            if x_overlap >= min_overlap:
                # Photo has sufficient X-overlap, check if it's below
                gap = top2 - bottom1
                # Allow mild overlap (negative gap up to -10mm) or positive gap
                if -100 < gap:  # -10mm to infinity
                    if closest_below_gap is None or abs(gap) < abs(closest_below_gap):
                        closest_below_gap = gap
        
        # Record the gap if it's positive and significant (>1mm)
        if closest_below_gap is not None and closest_below_gap > 10:
            inter_photo_gaps.append(closest_below_gap)
    
    # Calculate average edge gap
    edge_gap = sum(edge_gaps) / len(edge_gaps) if edge_gaps else 0.0
    
    # Calculate average inter-photo gap, removing outliers
    if len(inter_photo_gaps) > 3:
        # Remove outliers beyond 1 standard deviation
        import statistics
        mean = statistics.mean(inter_photo_gaps)
        stdev = statistics.stdev(inter_photo_gaps)
        # Filter out values more than 1 stdev away
        filtered_gaps = [g for g in inter_photo_gaps if abs(g - mean) <= stdev]
        inter_gap = sum(filtered_gaps) / len(filtered_gaps) if filtered_gaps else 0.0
    else:
        # Too few samples for outlier detection
        inter_gap = sum(inter_photo_gaps) / len(inter_photo_gaps) if inter_photo_gaps else 0.0
    
    # Maximum bleed (largest negative margin)
    bleed = max(bleed_margins) if bleed_margins else 0.0
    
    return GapAnalysis(edge_gap, inter_gap, bleed, edge_gaps, inter_photo_gaps, bleed_margins)


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
