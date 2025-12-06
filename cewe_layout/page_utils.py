"""
Page-related utility functions.

Shared utilities for determining page ownership and handling two-page spreads.
"""


def determine_page_owner(area_left: float, half_width: float, left_owner: int, right_owner: int) -> int:
    """Determine which logical page owns an area based on its left edge position.
    
    Photos/text areas are assigned to the page where their left edge starts,
    not based on their center. This ensures consistent behavior across the codebase.
    
    Args:
        area_left: Left edge x-coordinate of the area (in MCF units)
        half_width: Half the width of the spread (boundary between pages)
        left_owner: Page number for the left page
        right_owner: Page number for the right page
    
    Returns:
        Page number that owns this area (either left_owner or right_owner)
    
    Example:
        Photo at x=-30 with width=7700 on a spread with half_width=3820:
        - Left edge (-30) < half_width (3820) → belongs to left page
        - Even though center (3820) >= half_width, it still belongs to left page
    """
    return left_owner if area_left < half_width else right_owner


def belongs_to_page(area_left: float, area_width: float, x_min: float, x_max: float) -> bool:
    """Check if an area belongs to a specific page based on its left edge.
    
    Used by the writer to filter areas that belong to a specific logical page
    within a two-page spread.
    
    Args:
        area_left: Left edge x-coordinate of the area (in MCF units)
        area_width: Width of the area (unused, kept for API compatibility)
        x_min: Minimum x-coordinate for this page (inclusive)
        x_max: Maximum x-coordinate for this page (exclusive)
    
    Returns:
        True if the area's left edge is within [x_min, x_max)
    
    Note:
        The area_width parameter is included for backward compatibility but not used.
        Assignment is based solely on the left edge position.
    """
    return x_min <= area_left < x_max
