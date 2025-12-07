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
