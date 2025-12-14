"""
Page-related utility functions.

Shared utilities for determining page ownership and handling two-page spreads.
"""
from typing import Any


def page_sort_key(page_num):
    """Sort key for mixed page identifiers (strings and integers).
    
    Provides consistent ordering for page numbers that may include:
    - "F": Front cover
    - "B": Back cover  
    - Integers: Content pages (0, 1, 2, ...)
    
    Args:
        page_num: Page identifier (str "F"/"B" or int)
        
    Returns:
        Tuple (priority, secondary_key) for sorting
        
    Example:
        >>> sorted(["B", 3, "F", 1, 0], key=page_sort_key)
        ["F", 0, 1, 3, "B"]
    """
    if page_num == "F":
        return (0, 0)  # Front cover comes first
    elif page_num == "B":
        return (2, 0)  # Back cover comes last
    else:
        return (1, page_num)  # Numeric pages in between


def determine_page_owner_of_area(area_left: float, half_width: float, left_owner: Any, right_owner: Any) -> Any:
    """Determine which logical page owns an area based on its left edge position.
    
    Photos/text areas are assigned to the page where their left edge starts,
    not based on their center. This ensures consistent behavior across the codebase.
    
    Args:
        area_left: Left edge x-coordinate of the area (in MCF units)
        half_width: Half the width of the spread (boundary between pages)
        left_owner: UI page identifier for the left page (str 'F'/'B' or int)
        right_owner: UI page identifier for the right page (str 'F'/'B' or int)
    
    Returns:
        UI page identifier that owns this area (either left_owner or right_owner)
    
    Example:
        Photo at x=-30 with width=7700 on a spread with half_width=3820:
        - Left edge (-30) < half_width (3820) → belongs to left page
        - Even though center (3820) >= half_width, it still belongs to left page
    """
    return left_owner if area_left < half_width else right_owner
