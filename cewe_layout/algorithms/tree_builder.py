"""
Build a binary slicing tree from a set of non-overlapping rectangles.

This module implements the algorithm to construct a TreeNode representation
from an existing layout by finding splitting lines.

Coordinate system:
    MCF coordinates use units of 0.1mm (10 units = 1mm).
    This matches the cewe2pdf coordinate system.
"""

from typing import List, Optional, Tuple
from .base import TreeNode, LayoutRectangle


def build_tree_from_layout(rectangles: List[LayoutRectangle], 
                           page_width: float, 
                           page_height: float,
                           tolerance: float = 20.0) -> Optional[TreeNode]:
    """Build a binary slicing tree from a layout.
    
    Algorithm:
    1. Try to find a vertical or horizontal line that splits the page into two
       subsections without cutting through any rectangles
    2. Recursively build trees for each subsection
    3. Combine them with the appropriate split direction
    
    Args:
        rectangles: List of LayoutRectangle objects with x, y, width, height set
        page_width: Width of the page/region
        page_height: Height of the page/region
        tolerance: Tolerance for alignment in MCF units (0.1mm each).
                   Default 20.0 = 2.0mm, allows for small overlaps/bleeds.
        
    Returns:
        Root TreeNode, or None if layout cannot be represented as a slicing tree
    """
    if not rectangles:
        return None
    
    if len(rectangles) == 1:
        # Base case: single rectangle
        return TreeNode(label=0, is_leaf=True, item_idx=0)
    
    # Find all rectangles with their indices
    indexed_rects = [(i, r) for i, r in enumerate(rectangles)]
    
    # Try to find a splitting line
    split = find_split(indexed_rects, page_width, page_height, tolerance)
    
    if split is None:
        return None  # Cannot represent as slicing tree
    
    direction, position, left_rects, right_rects = split
    
    # Build subtrees recursively
    # For left/right splits, we need to compute the bounding box and adjust coordinates
    if direction == 'V':
        # Vertical split at x=position
        # Left side: x from 0 to position
        # Right side: x from position to page_width - need to adjust x coords
        left_width = position
        right_width = page_width - position
        
        # Adjust right side rectangles
        adjusted_right = []
        for idx, rect in right_rects:
            adjusted_rect = LayoutRectangle(
                item_id=rect.item_id,
                width=rect.width,
                height=rect.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio,
                x=rect.x - position,
                y=rect.y
            )
            adjusted_right.append((idx, adjusted_rect))
        
        left_tree = _build_tree_recursive(left_rects, left_width, page_height, tolerance)
        right_tree = _build_tree_recursive(adjusted_right, right_width, page_height, tolerance)
    else:  # 'H'
        # Horizontal split at y=position
        # Top side: y from 0 to position  
        # Bottom side: y from position to page_height - need to adjust y coords
        top_height = position
        bottom_height = page_height - position
        
        # Adjust bottom side rectangles
        adjusted_bottom = []
        for idx, rect in right_rects:
            adjusted_rect = LayoutRectangle(
                item_id=rect.item_id,
                width=rect.width,
                height=rect.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio,
                x=rect.x,
                y=rect.y - position
            )
            adjusted_bottom.append((idx, adjusted_rect))
        
        left_tree = _build_tree_recursive(left_rects, page_width, top_height, tolerance)
        right_tree = _build_tree_recursive(adjusted_bottom, page_width, bottom_height, tolerance)
    
    if left_tree is None or right_tree is None:
        return None
    
    # Combine
    root = TreeNode(label=direction, is_leaf=False)
    root.left = left_tree
    root.right = right_tree
    left_tree.parent = root
    right_tree.parent = root
    
    return root


def _build_tree_recursive(indexed_rects: List[Tuple[int, LayoutRectangle]],
                         width: float, height: float,
                         tolerance: float, depth: int = 0) -> Optional[TreeNode]:
    """Recursive helper for building tree from indexed rectangles."""
    if not indexed_rects:
        return None
    
    if len(indexed_rects) == 1:
        idx, rect = indexed_rects[0]
        return TreeNode(label=idx, is_leaf=True, item_idx=idx)
    
    # Try to find a split
    split = find_split(indexed_rects, width, height, tolerance)
    
    if split is None:
        return None
    
    direction, position, left_rects, right_rects = split
    
    # Adjust rectangle coordinates to be relative to the subregion
    if direction == 'V':
        # Vertical split: adjust x coordinates of right side
        adjusted_right = []
        for idx, rect in right_rects:
            adjusted_rect = LayoutRectangle(
                item_id=rect.item_id,
                width=rect.width,
                height=rect.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio,
                x=rect.x - position,  # Adjust x coordinate
                y=rect.y
            )
            adjusted_right.append((idx, adjusted_rect))
        
        left_width = position
        right_width = width - position
        left_tree = _build_tree_recursive(left_rects, left_width, height, tolerance, depth + 1)
        right_tree = _build_tree_recursive(adjusted_right, right_width, height, tolerance, depth + 1)
    else:  # 'H'
        # Horizontal split: adjust y coordinates of bottom side
        adjusted_bottom = []
        for idx, rect in right_rects:
            adjusted_rect = LayoutRectangle(
                item_id=rect.item_id,
                width=rect.width,
                height=rect.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio,
                x=rect.x,
                y=rect.y - position  # Adjust y coordinate
            )
            adjusted_bottom.append((idx, adjusted_rect))
        
        top_height = position
        bottom_height = height - position
        left_tree = _build_tree_recursive(left_rects, width, top_height, tolerance, depth + 1)
        right_tree = _build_tree_recursive(adjusted_bottom, width, bottom_height, tolerance, depth + 1)
    
    if left_tree is None or right_tree is None:
        return None
    
    root = TreeNode(label=direction, is_leaf=False)
    root.left = left_tree
    root.right = right_tree
    left_tree.parent = root
    right_tree.parent = root
    
    return root


def find_split(indexed_rects: List[Tuple[int, LayoutRectangle]],
              width: float, height: float,
              tolerance: float) -> Optional[Tuple[str, float, List, List]]:
    """Find a vertical or horizontal line that splits rectangles cleanly.
    
    Returns:
        Tuple of (direction, position, left_rects, right_rects) or None
        direction: 'V' for vertical split, 'H' for horizontal split
        position: coordinate of the split line
        left_rects: rectangles on left/top side
        right_rects: rectangles on right/bottom side
    """
    # Try vertical splits (split along x-axis)
    vertical_split = find_vertical_split(indexed_rects, width, tolerance)
    
    # Try horizontal splits (split along y-axis)
    horizontal_split = find_horizontal_split(indexed_rects, height, tolerance)
    
    # Prefer the split that is more balanced (closer to 50/50)
    if vertical_split and horizontal_split:
        v_pos, v_left, v_right = vertical_split
        h_pos, h_left, h_right = horizontal_split
        
        v_balance = abs(len(v_left) - len(v_right))
        h_balance = abs(len(h_left) - len(h_right))
        
        if v_balance <= h_balance:
            return ('V', v_pos, v_left, v_right)
        else:
            return ('H', h_pos, h_left, h_right)
    elif vertical_split:
        v_pos, v_left, v_right = vertical_split
        return ('V', v_pos, v_left, v_right)
    elif horizontal_split:
        h_pos, h_left, h_right = horizontal_split
        return ('H', h_pos, h_left, h_right)
    else:
        return None


def find_vertical_split(indexed_rects: List[Tuple[int, LayoutRectangle]],
                       width: float, tolerance: float) -> Optional[Tuple[float, List, List]]:
    """Find a vertical line that splits rectangles cleanly.
    
    A vertical split is a line at x=position where no rectangle crosses the line.
    All rectangles are either entirely to the left (x+width <= position+tol)
    or entirely to the right (x >= position-tol).
    
    Returns:
        Tuple of (position, left_rects, right_rects) or None
    """
    # Collect all x-coordinates where rectangles start or end
    x_coords = set()
    for idx, rect in indexed_rects:
        x_coords.add(rect.x)
        x_coords.add(rect.x + rect.width)
    
    # Try each x-coordinate as a potential split
    for x in sorted(x_coords):
        left = []
        right = []
        valid = True
        
        for idx, rect in indexed_rects:
            rect_left = rect.x
            rect_right = rect.x + rect.width
            
            if rect_right <= x + tolerance:
                # Rectangle is fully on the left
                left.append((idx, rect))
            elif rect_left >= x - tolerance:
                # Rectangle is fully on the right
                right.append((idx, rect))
            else:
                # Rectangle crosses the split line
                valid = False
                break
        
        if valid and len(left) > 0 and len(right) > 0:
            return (x, left, right)
    
    return None


def find_horizontal_split(indexed_rects: List[Tuple[int, LayoutRectangle]],
                         height: float, tolerance: float) -> Optional[Tuple[float, List, List]]:
    """Find a horizontal line that splits rectangles cleanly.
    
    A horizontal split is a line at y=position where no rectangle crosses the line.
    All rectangles are either entirely above (y+height <= position+tol)
    or entirely below (y >= position-tol).
    
    Returns:
        Tuple of (position, top_rects, bottom_rects) or None
    """
    # Collect all y-coordinates where rectangles start or end
    y_coords = set()
    for idx, rect in indexed_rects:
        y_coords.add(rect.y)
        y_coords.add(rect.y + rect.height)
    
    # Try each y-coordinate as a potential split
    for y in sorted(y_coords):
        top = []
        bottom = []
        valid = True
        
        for idx, rect in indexed_rects:
            rect_top = rect.y
            rect_bottom = rect.y + rect.height
            
            if rect_bottom <= y + tolerance:
                # Rectangle is fully on top
                top.append((idx, rect))
            elif rect_top >= y - tolerance:
                # Rectangle is fully on bottom
                bottom.append((idx, rect))
            else:
                # Rectangle crosses the split line
                valid = False
                break
        
        if valid and len(top) > 0 and len(bottom) > 0:
            return (y, top, bottom)
    
    return None
