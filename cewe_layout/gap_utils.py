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


def make_uniform_edge_gap(gap: float) -> Dict[str, float]:
    """Create edge gap dict with same value for all 4 edges."""
    return {'top': gap, 'bottom': gap, 'left': gap, 'right': gap}


def make_edge_gap(top: float, bottom: float, left: float, right: float) -> Dict[str, float]:
    """Create edge gap dict with specific values for each edge."""
    return {'top': top, 'bottom': bottom, 'left': left, 'right': right}


class GapAnalysis(NamedTuple):
    """Result of gap analysis."""
    edge_gap: Dict[str, float]  # Edge gaps by side: {'top': ..., 'bottom': ..., 'left': ..., 'right': ...} in MCF units
    internal_gap: float  # Average internal gap in MCF units
    bleed: float  # Maximum negative edge margin (bleed beyond page) in MCF units, always >= 0
    edge_gaps: List[float]  # All detected positive edge gaps
    internal_gaps: List[float]  # All detected internal gaps
    bleed_margins: List[float]  # All negative edge margins (absolute values)


def analyze_gaps(photos: List[Dict[str, Any]], page_width: float, page_height: float, 
                  origin_left: float, is_spread: bool) -> Tuple[Dict[str, float], float]:
    """
    Estimate edge gap and internal gap separately.
    
    Args:
        photos: List of photo dicts with area_left, area_top, area_width, area_height.
        page_width: Page width in MCF units.
        page_height: Page height in MCF units.
        origin_left: For right-hand pages, the absolute X offset of this page (default 0.0).
    
    Returns:
        Tuple (edge_gap_dict, internal_gap) where edge_gap_dict has keys 'top', 'bottom', 'left', 'right'.
        Returns (make_uniform_edge_gap(0.0), 0.0) if gaps cannot be reliably estimated.
    """
    analysis = analyze_gap_details(photos, page_width, page_height, origin_left, is_spread)
    return analysis.edge_gap, analysis.internal_gap


def analyze_gap_details(photos: List[Dict[str, Any]], page_width: float, page_height: float,
                 origin_left: float, is_spread: bool) -> GapAnalysis:
    """
    Analyze gaps in detail, including bleed (negative margins).
    
    Args:
        photos: List of photo dicts with area_left, area_top, area_width, area_height.
        page_width: Page width in MCF units.
        page_height: Page height in MCF units.
        origin_left: For right-hand pages, the absolute X offset of this page (default 0.0).
    
    Returns:
        GapAnalysis with edge_gap (dict), internal_gap, bleed, and all detected gaps.
    """
    if not photos:
        return GapAnalysis(make_uniform_edge_gap(0.0), 0.0, 0.0, [], [], [])
    
    # Calculate page bounds in absolute coordinates
    page_left = origin_left
    page_right = origin_left + page_width
    page_top = 0.0
    page_bottom = page_height
    
    # Separate edge gaps by side
    top_gaps = []
    bottom_gaps = []
    left_gaps = []
    right_gaps = []
    bleed_margins = []
    internal_gaps = []
    
    # Collect all edge gaps (margins from page boundaries)
    # In spread mode (double-width), apply bleed to all four edges
    # In single page mode, apply bleed only to three outer edges (not center fold)
    for p in photos:
        left = p.get('area_left', 0)
        top = p.get('area_top', 0)
        width = p.get('area_width', 0)
        height = p.get('area_height', 0)
        right = left + width
        bottom = top + height

        # Top edge (distance from page top)
        top_margin = top - page_top
        if top_margin < 0:
            bleed_margins.append(abs(top_margin))
        elif 10 < top_margin < page_height * 0.05:
            top_gaps.append(top_margin)

        # Bottom edge (distance from page bottom)
        bottom_margin = page_bottom - bottom
        if bottom_margin < 0:
            bleed_margins.append(abs(bottom_margin))
        elif 10 < bottom_margin < page_height * 0.05:
            bottom_gaps.append(bottom_margin)

        left_margin = left - page_left
        right_margin = page_right - right

        if is_spread:
            # Spread mode: apply bleed to both left and right edges
            if left_margin < 0:
                bleed_margins.append(abs(left_margin))
            elif 10 < left_margin < page_width * 0.05:
                left_gaps.append(left_margin)
            if right_margin < 0:
                bleed_margins.append(abs(right_margin))
            elif 10 < right_margin < page_width * 0.05:
                right_gaps.append(right_margin)
        else:
            # Single page: apply bleed to left, right, top, bottom except center fold
            # Assume center fold is right edge for left page, left edge for right page (handled by caller)
            # Here, only apply bleed to left, right, top, bottom
            # If caller wants to skip center fold, they must set up page_left/page_right accordingly
            # For now, apply bleed to left and right edges as before
            if left_margin < 0:
                bleed_margins.append(abs(left_margin))
            elif 10 < left_margin < page_width * 0.05:
                left_gaps.append(left_margin)
            if right_margin < 0:
                bleed_margins.append(abs(right_margin))
            elif 10 < right_margin < page_width * 0.05:
                right_gaps.append(right_margin)
    
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
    
    # Helper to find modal value (most common value)
    def find_modal_value(gaps, tolerance=2.0):
        """Find the most common gap value, grouping within tolerance."""
        if not gaps:
            return 0.0
        
        # Round to tolerance to group similar values
        rounded = [round(g / tolerance) * tolerance for g in gaps]
        
        # Find modal value (most common)
        from collections import Counter
        counts = Counter(rounded)
        modal_value = counts.most_common(1)[0][0]
        return modal_value
    
    # Calculate MODAL gap for each edge separately
    top_gap = find_modal_value(top_gaps, tolerance=2.0) if top_gaps else 0.0
    bottom_gap = find_modal_value(bottom_gaps, tolerance=2.0) if bottom_gaps else 0.0
    left_gap = find_modal_value(left_gaps, tolerance=2.0) if left_gaps else 0.0
    right_gap = find_modal_value(right_gaps, tolerance=2.0) if right_gaps else 0.0
    
    # Create edge_gap dict
    edge_gap_dict = make_edge_gap(top_gap, bottom_gap, left_gap, right_gap)
    
    # Calculate MODAL internal gap (most common value, not average)
    inter_gap = find_modal_value(internal_gaps, tolerance=2.0) if internal_gaps else 0.0
    
    # Maximum bleed (largest negative margin)
    bleed = max(bleed_margins) if bleed_margins else 0.0
    
    # Combine all edge gaps for legacy edge_gaps list
    all_edge_gaps = top_gaps + bottom_gaps + left_gaps + right_gaps
    
    return GapAnalysis(edge_gap_dict, inter_gap, bleed, all_edge_gaps, internal_gaps, bleed_margins)


def report_gap_variations(analysis: GapAnalysis, pageno: int = None) -> None:
    """
    Report variations in edge gaps and internal gaps if they exist.
    
    Only outputs messages if there are variations greater than 0.2mm (2 MCF units).
    Reports the modal value (most common) and lists exceptions.
    If all gaps are equal, reports that fact.
    
    Args:
        analysis: GapAnalysis result from analyze_gap_details.
        pageno: Optional page number for context in message.
    """
    TOLERANCE = 2.0  # 0.2mm in MCF units - ignore smaller differences
    
    page_context = f"Page {pageno}: " if pageno is not None else ""
    
    # Helper to find modal value and exceptions
    def find_modal_and_exceptions(gaps, tolerance):
        if not gaps:
            return None, []
        
        # Round to tolerance to group similar values
        rounded = [round(g / tolerance) * tolerance for g in gaps]
        
        # Find modal value (most common)
        from collections import Counter
        counts = Counter(rounded)
        modal_value = counts.most_common(1)[0][0]
        modal_count = counts[modal_value]
        
        # Find exceptions (values that differ from modal by more than tolerance)
        exceptions = []
        for g in rounded:
            if abs(g - modal_value) > tolerance and g not in exceptions:
                exceptions.append(g)
        
        return modal_value, sorted(exceptions)
    
    # Check internal gap variations
    has_internal_variations = False
    if analysis.internal_gaps:
        modal_internal, exceptions = find_modal_and_exceptions(analysis.internal_gaps, TOLERANCE)
        if exceptions:
            has_internal_variations = True
            # Convert to mm for display
            modal_mm = modal_internal / 10.0
            exceptions_mm = [e / 10.0 for e in exceptions]
            exception_str = ", ".join(f"{e:.1f}" for e in exceptions_mm)
            count_modal = sum(1 for g in analysis.internal_gaps if abs(g - modal_internal) <= TOLERANCE)
            print(f"{page_context}Internal gaps: {count_modal} gaps are {modal_mm:.1f}mm, other gaps are {exception_str}mm")
    
    # Check edge gap variations
    has_edge_variations = False
    if analysis.edge_gaps:
        modal_edge, exceptions = find_modal_and_exceptions(analysis.edge_gaps, TOLERANCE)
        if exceptions:
            has_edge_variations = True
            # Convert to mm for display
            modal_mm = modal_edge / 10.0
            exceptions_mm = [e / 10.0 for e in exceptions]
            exception_str = ", ".join(f"{e:.1f}" for e in exceptions_mm)
            count_modal = sum(1 for g in analysis.edge_gaps if abs(g - modal_edge) <= TOLERANCE)
            print(f"{page_context}Edge gaps: {count_modal} gaps are {modal_mm:.1f}mm, other gaps are {exception_str}mm")
    
    # If no variations detected, report that all gaps are equal
    if not has_internal_variations and not has_edge_variations and (analysis.internal_gaps or analysis.edge_gaps):
        print(f"{page_context}Equal edge gaps and equal internal gaps")


def transform_page_to_gapfree(page_width: float, page_height: float,
                               edge_gap: Dict[str, float], internal_gap: float, is_spread: bool,
                               has_full_bleed: bool = False) -> Tuple[float, float]:
    """
    Transform page dimensions from MCF space to gap-free space for algorithms.
    
    Gap-free space is where the algorithm operates:
    - edge_gap is removed from edges (margins) or added back if negative (bleed)
    - internal_gap is added back once (items expand by internal_gap to touch)
    
    For single page mode with negative edge_gap (bleed):
    - Width: page_width - left_gap - right_gap + internal_gap (but skip centerfold for bleed)
    - Height: page_height - top_gap - bottom_gap + internal_gap
    
    For spread mode or positive edge_gap:
    - Formula: page - left_gap - right_gap + internal_gap
    
    For covers with full bleed (has_full_bleed=True):
    - All 4 edges have bleed (no centerfold), so apply left_gap even in single page mode
    
    Args:
        page_width: Page width in MCF units.
        page_height: Page height in MCF units.
        edge_gap: Edge gap dict with 'top', 'bottom', 'left', 'right' keys.
        internal_gap: Internal gap (spacing between items) in MCF units.
        is_spread: True if spread mode (double page), False if single page mode.
        has_full_bleed: True if this is a cover page with bleed on all 4 sides.
    
    Returns:
        Tuple (gapfree_width, gapfree_height) in MCF units.
    """
    left_gap = edge_gap['left']
    right_gap = edge_gap['right']
    top_gap = edge_gap['top']
    bottom_gap = edge_gap['bottom']
    
    # Check if we should avoid centerfold bleed (negative gap on one edge in single-page mode)
    # Covers have bleed on all 4 sides, so they don't avoid centerfold
    avoid_centerfold = (left_gap < 0 or right_gap < 0) and not is_spread and not has_full_bleed
    if avoid_centerfold:
        # In single page mode with bleed, don't apply left gap (it's the centerfold)
        gapfree_width = page_width - right_gap + internal_gap
    else:
        gapfree_width = page_width - left_gap - right_gap + internal_gap
    
    gapfree_height = page_height - top_gap - bottom_gap + internal_gap
    return gapfree_width, gapfree_height


def transform_item_to_gapfree(left: float, top: float, width: float, height: float,
                               edge_gap: Dict[str, float], internal_gap: float, 
                               is_spread: bool, is_left_page: bool, has_full_bleed: bool = False) -> Tuple[float, float, float, float]:
    """
    Transform an item (photo or text) from MCF space to gap-free space for algorithms.
    
    Gap-free space is where the algorithm operates:
    - Positions subtract edge_gap (remove margins)
    - Dimensions add internal_gap (items expand to touch neighbors)
    
    For single page mode with negative edge_gap (bleed):
    - Right page: left position stays at 0 (no bleed at centerfold on left edge)
    - Left page: left position subtracts left_gap normally (bleed on left edge)
    
    For covers with full bleed (has_full_bleed=True):
    - All 4 edges have bleed (no centerfold), so always subtract left_gap
    
    This ensures items in gap-free space perfectly fill the gap-free page with no gaps.
    
    Args:
        left: Item left position in MCF units.
        top: Item top position in MCF units.
        width: Item width in MCF units.
        height: Item height in MCF units.
        edge_gap: Edge gap dict with 'top', 'bottom', 'left', 'right' keys.
        internal_gap: Internal gap (spacing between items) in MCF units.
        is_spread: True if spread mode (double page), False if single page mode.
        is_left_page: True if this is the left/even page, False if right/odd page.
        has_full_bleed: True if this is a cover page with bleed on all 4 sides.

    
    Returns:
        Tuple (gapfree_left, gapfree_top, gapfree_width, gapfree_height) in MCF units.
    """
    left_gap = edge_gap['left']
    top_gap = edge_gap['top']
    
    has_no_left_edge = left_gap < 0 and not is_spread and not is_left_page and not has_full_bleed
    if has_no_left_edge:
        gapfree_left = left  # Do not subtract left_gap at center fold
    else:
        gapfree_left = left - left_gap
    gapfree_top = top - top_gap
    gapfree_width = width + internal_gap
    gapfree_height = height + internal_gap
    return gapfree_left, gapfree_top, gapfree_width, gapfree_height


def transform_item_from_gapfree(gapfree_left: float, gapfree_top: float,
                                 gapfree_width: float, gapfree_height: float,
                                 edge_gap: Dict[str, float], internal_gap: float, 
                                 is_spread: bool, is_left_page: bool, has_full_bleed: bool = False) -> Tuple[float, float, float, float]:
    """
    Transform an item from gap-free space back to MCF space.
    
    Inverse of transform_item_to_gapfree:
    - Positions add edge_gap (restore margins)
    - Dimensions subtract internal_gap (items shrink to create gaps)
    
    For single page mode with negative edge_gap (bleed):
    - Right page: left position stays at 0 (no bleed at centerfold on left edge)
    - Left page: left position adds left_gap normally (bleed on left edge)
    
    For covers with full bleed (has_full_bleed=True):
    - All 4 edges have bleed (no centerfold), so always add left_gap
    
    Args:
        gapfree_left: Item left position in gap-free space.
        gapfree_top: Item top position in gap-free space.
        gapfree_width: Item width in gap-free space.
        gapfree_height: Item height in gap-free space.
        edge_gap: Edge gap dict with 'top', 'bottom', 'left', 'right' keys.
        internal_gap: Internal gap (spacing between items) in MCF units.
        is_spread: True if spread mode (double page), False if single page mode.
        is_left_page: True if this is the left/even page, False if right/odd page.
        has_full_bleed: True if this is a cover page with bleed on all 4 sides.

    Returns:
        Tuple (left, top, width, height) in MCF units.
    """
    left_gap = edge_gap['left']
    top_gap = edge_gap['top']
    
    has_no_left_edge = left_gap < 0 and not is_spread and not is_left_page and not has_full_bleed
    if has_no_left_edge:
        left = gapfree_left  # Do not add left_gap at center fold
    else:
        left = gapfree_left + left_gap
    top = gapfree_top + top_gap
    width = max(0, gapfree_width - internal_gap)
    height = max(0, gapfree_height - internal_gap)
    return left, top, width, height


def transform_item_for_gap_change(
    mcf_left: float, mcf_top: float, mcf_width: float, mcf_height: float,
    page_width: float, page_height: float,
    old_edge_gap: Dict[str, float], old_internal_gap: float,
    new_edge_gap: Dict[str, float], new_internal_gap: float,
    is_spread: bool, is_left_page: bool, has_full_bleed: bool = False
) -> Tuple[float, float, float, float]:
    """
    Transform an item when gap parameters change.
    
    When gaps change, the gap-free page size changes:
    - Gap-free page = page - left_gap - right_gap + internal_gap (width)
    - Gap-free page = page - top_gap - bottom_gap + internal_gap (height)
    - Changing edge_gap or internal_gap changes this size
    
    To maintain the same relative layout in gap-free space, items must scale
    proportionally with the gap-free page size change.
    
    Transformation process:
    1. Transform MCF → gap-free using OLD gaps
    2. Scale gap-free coordinates (from origin 0,0) by new_page/old_page ratio
    3. Transform gap-free → MCF using NEW gaps
    
    This preserves the relative layout proportions and keeps everything centered.
    
    Args:
        mcf_left: Item left in MCF space (with old gaps)
        mcf_top: Item top in MCF space (with old gaps)
        mcf_width: Item width in MCF space (with old gaps)
        mcf_height: Item height in MCF space (with old gaps)
        page_width: Page width in MCF units
        page_height: Page height in MCF units
        old_edge_gap: Previous edge gap dict
        old_internal_gap: Previous internal gap in MCF units
        new_edge_gap: New edge gap dict
        new_internal_gap: New internal gap in MCF units
        is_spread: True if spread mode, False if single page mode.
        is_left_page: True if left page, False if right page.
        has_full_bleed: True if this is a cover page with bleed on all 4 sides.
    
    Returns:
        Tuple (new_left, new_top, new_width, new_height) in MCF units with new gaps
    """
    # Key insight: When gaps change, the gap-free page size changes.
    # Scale all gap-free coordinates (positions and sizes) to fit the new gap-free page,
    # scaling relative to top-left corner (0,0). Then transform back to MCF.
    
    # Step 1: Calculate old and new gap-free page sizes
    old_gf_page_w, old_gf_page_h = transform_page_to_gapfree(
        page_width, page_height, old_edge_gap, old_internal_gap, is_spread, has_full_bleed
    )
    new_gf_page_w, new_gf_page_h = transform_page_to_gapfree(
        page_width, page_height, new_edge_gap, new_internal_gap, is_spread, has_full_bleed
    )
    
    # Step 2: Calculate scale factors
    scale_w = new_gf_page_w / old_gf_page_w if old_gf_page_w > 0 else 1.0
    scale_h = new_gf_page_h / old_gf_page_h if old_gf_page_h > 0 else 1.0
    
    # Step 3: Transform to gap-free space using old gaps
    gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
        mcf_left, mcf_top, mcf_width, mcf_height, old_edge_gap, old_internal_gap, is_spread, is_left_page, has_full_bleed
    )
    
    # Step 4: Scale gap-free coordinates (relative to top-left origin)
    scaled_gf_left = gf_left * scale_w
    scaled_gf_top = gf_top * scale_h
    scaled_gf_width = gf_width * scale_w
    scaled_gf_height = gf_height * scale_h
    
    # Step 5: Transform back to MCF space with new gaps
    new_left, new_top, new_width, new_height = transform_item_from_gapfree(
        scaled_gf_left, scaled_gf_top, scaled_gf_width, scaled_gf_height,
        new_edge_gap, new_internal_gap, is_spread, is_left_page, has_full_bleed
    )
    
    return new_left, new_top, new_width, new_height
