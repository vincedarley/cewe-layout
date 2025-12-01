"""
Gap estimation and handling utilities.

Handles uniform spacing (gaps) between photos and page edges.
Separates edge gaps (margins) from internal gaps.

KEY CONCEPT - Gaps and Coordinate Spaces:
- MCF space: Coordinates as stored in the .mcf file, with actual gaps/margins
- Gap-free space: Algorithm coordinate space where gaps are removed (items touch)

Gaps are PARAMETERS that define transformations between these spaces:
- edge_gap: Margin from page edge to first item (can be negative for bleed)
- internal_gap: Spacing between adjacent items

Cost calculations operate in GAP-FREE space and are unaware of gaps.
Visual rendering operates in MCF space with gaps applied.
Changing gaps transforms positions WITHOUT affecting gap-free coordinates or costs.
"""

from typing import List, Dict, Any, Tuple, NamedTuple


class GapAnalysis(NamedTuple):
    """Result of gap analysis."""
    edge_gap: float  # Average positive edge gap (margin) in MCF units
    internal_gap: float  # Average internal gap in MCF units
    bleed: float  # Maximum negative edge margin (bleed beyond page) in MCF units, always >= 0
    edge_gaps: List[float]  # All detected positive edge gaps
    internal_gaps: List[float]  # All detected internal gaps
    bleed_margins: List[float]  # All negative edge margins (absolute values)


def estimate_gaps(photos: List[Dict[str, Any]], page_width: float, page_height: float, 
                  origin_left: float = 0.0) -> Tuple[float, float]:
    """
    Estimate edge gap and internal gap separately.
    
    Args:
        photos: List of photo dicts with area_left, area_top, area_width, area_height.
        page_width: Page width in MCF units.
        page_height: Page height in MCF units.
        origin_left: For right-hand pages, the absolute X offset of this page (default 0.0).
    
    Returns:
        Tuple (edge_gap, internal_gap) in MCF units (0.1mm).
        Returns (0.0, 0.0) if gaps cannot be reliably estimated.
    """
    analysis = analyze_gaps(photos, page_width, page_height, origin_left)
    return analysis.edge_gap, analysis.internal_gap


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
        GapAnalysis with edge_gap, internal_gap, bleed, and all detected gaps.
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
    internal_gaps = []
    
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
    
    # Collect internal gaps (spacing between adjacent photos)
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
            internal_gaps.append(closest_right_gap)
        
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
            internal_gaps.append(closest_below_gap)
    
    # Calculate average edge gap
    edge_gap = sum(edge_gaps) / len(edge_gaps) if edge_gaps else 0.0
    
    # Calculate average internal gap, removing outliers
    if len(internal_gaps) > 3:
        # Remove outliers beyond 1 standard deviation
        import statistics
        mean = statistics.mean(internal_gaps)
        stdev = statistics.stdev(internal_gaps)
        # Filter out values more than 1 stdev away
        filtered_gaps = [g for g in internal_gaps if abs(g - mean) <= stdev]
        inter_gap = sum(filtered_gaps) / len(filtered_gaps) if filtered_gaps else 0.0
    else:
        # Too few samples for outlier detection
        inter_gap = sum(internal_gaps) / len(internal_gaps) if internal_gaps else 0.0
    
    # Maximum bleed (largest negative margin)
    bleed = max(bleed_margins) if bleed_margins else 0.0
    
    return GapAnalysis(edge_gap, inter_gap, bleed, edge_gaps, internal_gaps, bleed_margins)


def transform_page_to_gapfree(page_width: float, page_height: float,
                               edge_gap: float, internal_gap: float) -> Tuple[float, float]:
    """
    Transform page dimensions from MCF space to gap-free space for algorithms.
    
    Gap-free space is where the algorithm operates:
    - edge_gap is removed from all four edges (margins)
    - internal_gap is added back once (items expand by internal_gap to touch)
    
    Formula: page - 2*edge_gap + internal_gap
    
    Rationale:
    - Remove edge_gap from top/left (margins)
    - Remove (edge_gap - internal_gap) from bottom/right (margin minus touching expansion)
    - Simplifies to: page - 2*edge_gap + internal_gap
    
    Args:
        page_width: Page width in MCF units.
        page_height: Page height in MCF units.
        edge_gap: Edge gap (margin) in MCF units.
        internal_gap: Internal gap (spacing between items) in MCF units.
    
    Returns:
        Tuple (gapfree_width, gapfree_height) in MCF units.
    """
    gapfree_width = page_width - 2 * edge_gap + internal_gap
    gapfree_height = page_height - 2 * edge_gap + internal_gap
    return gapfree_width, gapfree_height


def transform_item_to_gapfree(left: float, top: float, width: float, height: float,
                               edge_gap: float, internal_gap: float) -> Tuple[float, float, float, float]:
    """
    Transform an item (photo or text) from MCF space to gap-free space for algorithms.
    
    Gap-free space is where the algorithm operates:
    - Positions subtract edge_gap (remove margins)
    - Dimensions add internal_gap (items expand to touch neighbors)
    
    This ensures items in gap-free space perfectly fill the gap-free page with no gaps.
    
    Args:
        left: Item left position in MCF units.
        top: Item top position in MCF units.
        width: Item width in MCF units.
        height: Item height in MCF units.
        edge_gap: Edge gap (margin) in MCF units.
        internal_gap: Internal gap (spacing between items) in MCF units.
    
    Returns:
        Tuple (gapfree_left, gapfree_top, gapfree_width, gapfree_height) in MCF units.
    """
    gapfree_left = left - edge_gap
    gapfree_top = top - edge_gap
    gapfree_width = width + internal_gap
    gapfree_height = height + internal_gap
    return gapfree_left, gapfree_top, gapfree_width, gapfree_height


def transform_item_from_gapfree(gapfree_left: float, gapfree_top: float,
                                 gapfree_width: float, gapfree_height: float,
                                 edge_gap: float, internal_gap: float) -> Tuple[float, float, float, float]:
    """
    Transform an item from gap-free space back to MCF space.
    
    Inverse of transform_item_to_gapfree:
    - Positions add edge_gap (restore margins)
    - Dimensions subtract internal_gap (items shrink to create gaps)
    
    Args:
        gapfree_left: Item left position in gap-free space.
        gapfree_top: Item top position in gap-free space.
        gapfree_width: Item width in gap-free space.
        gapfree_height: Item height in gap-free space.
        edge_gap: Edge gap (margin) in MCF units.
        internal_gap: Internal gap (spacing between items) in MCF units.
    
    Returns:
        Tuple (left, top, width, height) in MCF units.
    """
    left = gapfree_left + edge_gap
    top = gapfree_top + edge_gap
    width = max(0, gapfree_width - internal_gap)
    height = max(0, gapfree_height - internal_gap)
    return left, top, width, height


def transform_item_for_gap_change(
    mcf_left: float, mcf_top: float, mcf_width: float, mcf_height: float,
    page_width: float, page_height: float,
    old_edge_gap: float, old_internal_gap: float,
    new_edge_gap: float, new_internal_gap: float
) -> Tuple[float, float, float, float]:
    """
    Transform an item when gap parameters change.
    
    When gaps change, the gap-free page size changes:
    - Gap-free page = page - 2*edge_gap + internal_gap
    - Changing edge_gap or internal_gap changes this size
    
    To maintain the same relative layout in gap-free space, items must scale
    proportionally with the gap-free page size change.
    
    Transformation process:
    1. Transform MCF → gap-free using OLD gaps
    2. Scale gap-free coordinates by (new_gf_page / old_gf_page)
    3. Transform gap-free → MCF using NEW gaps
    
    This preserves the relative layout while adapting to new gap parameters.
    
    Args:
        mcf_left: Item left in MCF space (with old gaps)
        mcf_top: Item top in MCF space (with old gaps)
        mcf_width: Item width in MCF space (with old gaps)
        mcf_height: Item height in MCF space (with old gaps)
        page_width: Page width in MCF units
        page_height: Page height in MCF units
        old_edge_gap: Previous edge gap in MCF units
        old_internal_gap: Previous internal gap in MCF units
        new_edge_gap: New edge gap in MCF units
        new_internal_gap: New internal gap in MCF units
    
    Returns:
        Tuple (new_left, new_top, new_width, new_height) in MCF units with new gaps
    """
    # Calculate old and new gap-free page sizes
    old_gf_page_w, old_gf_page_h = transform_page_to_gapfree(
        page_width, page_height, old_edge_gap, old_internal_gap
    )
    new_gf_page_w, new_gf_page_h = transform_page_to_gapfree(
        page_width, page_height, new_edge_gap, new_internal_gap
    )
    
    # Calculate scale factors
    scale_w = new_gf_page_w / old_gf_page_w if old_gf_page_w > 0 else 1.0
    scale_h = new_gf_page_h / old_gf_page_h if old_gf_page_h > 0 else 1.0
    
    # Step 1: Transform to gap-free space using OLD gaps
    gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
        mcf_left, mcf_top, mcf_width, mcf_height, old_edge_gap, old_internal_gap
    )
    
    # Step 2: Scale to fit new gap-free page size
    scaled_gf_left = gf_left * scale_w
    scaled_gf_top = gf_top * scale_h
    scaled_gf_width = gf_width * scale_w
    scaled_gf_height = gf_height * scale_h
    
    # Step 3: Transform back to MCF space using NEW gaps
    new_left, new_top, new_width, new_height = transform_item_from_gapfree(
        scaled_gf_left, scaled_gf_top, scaled_gf_width, scaled_gf_height,
        new_edge_gap, new_internal_gap
    )
    
    return new_left, new_top, new_width, new_height
