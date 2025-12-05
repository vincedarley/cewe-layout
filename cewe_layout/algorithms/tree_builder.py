"""
Build a binary slicing tree from a set of non-overlapping rectangles.

This module implements the algorithm to construct a TreeNode representation
from an existing layout by finding splitting lines.

Coordinate system:
    MCF coordinates use units of 0.1mm (10 units = 1mm).
    This matches the cewe2pdf coordinate system.
"""

import logging
from typing import List, Optional, Tuple
from .base import TreeNode, LayoutRectangle, LayoutAlgorithm

logger = logging.getLogger(__name__)


def build_tree_from_layout(rectangles: List[LayoutRectangle], 
                           page_width: float, 
                           page_height: float,
                           tolerance: float = 20.0) -> Optional[TreeNode]:
    """Build a binary slicing tree from a layout.
    
    Algorithm:
    1. Try to find a vertical or horizontal line that splits the rectangles into two
       subsections without cutting through any rectangles
    2. Recursively build trees for each subsection
    3. Combine them with the appropriate split direction
    
    Note: This works on the actual bounding box of the rectangles, not the page dimensions.
    Rectangles may extend slightly beyond [0, page_width] x [0, page_height] due to
    coordinate transformations or layout algorithms that don't perfectly center the layout.
    
    Args:
        rectangles: List of LayoutRectangle objects with x, y, width, height set
        page_width: Width of the page/region (informational only)
        page_height: Height of the page/region (informational only)
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
    
    # Compute actual bounding box of all rectangles (may extend beyond page bounds)
    min_x = min(r.x for _, r in indexed_rects)
    max_x = max(r.x + r.width for _, r in indexed_rects)
    min_y = min(r.y for _, r in indexed_rects)
    max_y = max(r.y + r.height for _, r in indexed_rects)
    bbox_width = max_x - min_x
    bbox_height = max_y - min_y
    
    # Try to find a splitting line (using actual bounding box, not page dimensions)
    split = find_split(indexed_rects, bbox_width, bbox_height, tolerance)
    # Try to find a splitting line (using actual bounding box, not page dimensions)
    split = find_split(indexed_rects, bbox_width, bbox_height, tolerance)
    
    if split is None:
        return None  # Cannot represent as slicing tree
    
    direction, position, left_rects, right_rects = split
    
    # Build subtrees recursively
    # For left/right splits, we need to compute the bounding box and adjust coordinates
    if direction == 'V':
        # Vertical split at x=position (relative to min_x)
        # Left side: rectangles left of the split
        # Right side: rectangles right of the split - adjust x coords relative to split position
        left_min_x = min(r.x for _, r in left_rects)
        left_max_x = max(r.x + r.width for _, r in left_rects)
        left_width = left_max_x - left_min_x
        
        right_min_x = min(r.x for _, r in right_rects)
        right_max_x = max(r.x + r.width for _, r in right_rects)
        right_width = right_max_x - right_min_x
        
        # Adjust right side rectangles to be relative to their bounding box
        adjusted_right = []
        for idx, rect in right_rects:
            adjusted_rect = LayoutRectangle(
                item_id=rect.item_id,
                width=rect.width,
                height=rect.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio,
                x=rect.x - right_min_x,
                y=rect.y
            )
            adjusted_right.append((idx, adjusted_rect))
        
        # Adjust left side rectangles to be relative to their bounding box
        adjusted_left = []
        for idx, rect in left_rects:
            adjusted_rect = LayoutRectangle(
                item_id=rect.item_id,
                width=rect.width,
                height=rect.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio,
                x=rect.x - left_min_x,
                y=rect.y
            )
            adjusted_left.append((idx, adjusted_rect))
        
        left_tree = _build_tree_recursive(adjusted_left, left_width, bbox_height, tolerance)
        right_tree = _build_tree_recursive(adjusted_right, right_width, bbox_height, tolerance)
    else:  # 'H'
        # Horizontal split at y=position (relative to min_y)
        # Top side: rectangles above the split
        # Bottom side: rectangles below the split - adjust y coords relative to split position
        top_min_y = min(r.y for _, r in left_rects)
        top_max_y = max(r.y + r.height for _, r in left_rects)
        top_height = top_max_y - top_min_y
        
        bottom_min_y = min(r.y for _, r in right_rects)
        bottom_max_y = max(r.y + r.height for _, r in right_rects)
        bottom_height = bottom_max_y - bottom_min_y
        
        # Adjust bottom side rectangles to be relative to their bounding box
        adjusted_bottom = []
        for idx, rect in right_rects:
            adjusted_rect = LayoutRectangle(
                item_id=rect.item_id,
                width=rect.width,
                height=rect.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio,
                x=rect.x,
                y=rect.y - bottom_min_y
            )
            adjusted_bottom.append((idx, adjusted_rect))
        
        # Adjust top side rectangles to be relative to their bounding box
        adjusted_top = []
        for idx, rect in left_rects:
            adjusted_rect = LayoutRectangle(
                item_id=rect.item_id,
                width=rect.width,
                height=rect.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio,
                x=rect.x,
                y=rect.y - top_min_y
            )
            adjusted_top.append((idx, adjusted_rect))
        
        left_tree = _build_tree_recursive(adjusted_top, bbox_width, top_height, tolerance)
        right_tree = _build_tree_recursive(adjusted_bottom, bbox_width, bottom_height, tolerance)
    
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
    """Recursive helper for building tree from indexed rectangles.
    
    Note: width and height are informational. The actual bounding box
    is computed from rectangles to handle off-center layouts.
    """
    if not indexed_rects:
        return None
    
    if len(indexed_rects) == 1:
        idx, rect = indexed_rects[0]
        return TreeNode(label=idx, is_leaf=True, item_idx=idx)
    
    # Compute bounding box
    min_x = min(r.x for _, r in indexed_rects)
    max_x = max(r.x + r.width for _, r in indexed_rects)
    min_y = min(r.y for _, r in indexed_rects)
    max_y = max(r.y + r.height for _, r in indexed_rects)
    bbox_width = max_x - min_x
    bbox_height = max_y - min_y
    
    # Try to find a split
    split = find_split(indexed_rects, bbox_width, bbox_height, tolerance)
    
    if split is None:
        # Log failure details
        logger.debug(f"Split failed at depth {depth} with {len(indexed_rects)} rects in region {bbox_width:.1f}x{bbox_height:.1f}")
        for idx, rect in indexed_rects:
            logger.debug(f"  Rect[{idx}]: pos=({rect.x:.1f}, {rect.y:.1f}) size=({rect.width:.1f}x{rect.height:.1f})")
        return None
    
    direction, position, left_rects, right_rects = split
    
    # Adjust coordinates relative to subregion bounding boxes
    if direction == 'V':
        # Compute left/right bounding boxes
        left_min_x = min(r.x for _, r in left_rects)
        left_max_x = max(r.x + r.width for _, r in left_rects)
        left_width = left_max_x - left_min_x
        
        right_min_x = min(r.x for _, r in right_rects)
        right_max_x = max(r.x + r.width for _, r in right_rects)
        right_width = right_max_x - right_min_x
        
        # Adjust to bounding boxes
        adjusted_left = [(idx, LayoutRectangle(
            item_id=r.item_id, width=r.width, height=r.height,
            preferred_size=r.preferred_size, preserve_aspect_ratio=r.preserve_aspect_ratio,
            x=r.x - left_min_x, y=r.y - min_y
        )) for idx, r in left_rects]
        
        adjusted_right = [(idx, LayoutRectangle(
            item_id=r.item_id, width=r.width, height=r.height,
            preferred_size=r.preferred_size, preserve_aspect_ratio=r.preserve_aspect_ratio,
            x=r.x - right_min_x, y=r.y - min_y
        )) for idx, r in right_rects]
        
        left_tree = _build_tree_recursive(adjusted_left, left_width, bbox_height, tolerance, depth + 1)
        right_tree = _build_tree_recursive(adjusted_right, right_width, bbox_height, tolerance, depth + 1)
    else:  # 'H'
        # Compute top/bottom bounding boxes
        top_min_y = min(r.y for _, r in left_rects)
        top_max_y = max(r.y + r.height for _, r in left_rects)
        top_height = top_max_y - top_min_y
        
        bottom_min_y = min(r.y for _, r in right_rects)
        bottom_max_y = max(r.y + r.height for _, r in right_rects)
        bottom_height = bottom_max_y - bottom_min_y
        
        # Adjust to bounding boxes
        adjusted_top = [(idx, LayoutRectangle(
            item_id=r.item_id, width=r.width, height=r.height,
            preferred_size=r.preferred_size, preserve_aspect_ratio=r.preserve_aspect_ratio,
            x=r.x - min_x, y=r.y - top_min_y
        )) for idx, r in left_rects]
        
        adjusted_bottom = [(idx, LayoutRectangle(
            item_id=r.item_id, width=r.width, height=r.height,
            preferred_size=r.preferred_size, preserve_aspect_ratio=r.preserve_aspect_ratio,
            x=r.x - min_x, y=r.y - bottom_min_y
        )) for idx, r in right_rects]
        
        left_tree = _build_tree_recursive(adjusted_top, bbox_width, top_height, tolerance, depth + 1)
        right_tree = _build_tree_recursive(adjusted_bottom, bbox_width, bottom_height, tolerance, depth + 1)
    
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
        crossing_rects = []
        
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
                crossing_rects.append((idx, rect))
                valid = False
        
        if valid and len(left) > 0 and len(right) > 0:
            return (x, left, right)
        elif len(left) > 0 and len(right) > 0 and crossing_rects:
            # Log why this split failed (only if it would have been productive)
            logger.debug(f"  Vertical split at x={x:.1f} failed: {len(crossing_rects)} crossing rects")
            for idx, rect in crossing_rects:
                logger.debug(f"    Rect[{idx}] crosses: x=[{rect.x:.1f}, {rect.x + rect.width:.1f}]")
    
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
        crossing_rects = []
        
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
                crossing_rects.append((idx, rect))
                valid = False
        
        if valid and len(top) > 0 and len(bottom) > 0:
            return (y, top, bottom)
        elif len(top) > 0 and len(bottom) > 0 and crossing_rects:
            # Log why this split failed (only if it would have been productive)
            logger.debug(f"  Horizontal split at y={y:.1f} failed: {len(crossing_rects)} crossing rects")
            for idx, rect in crossing_rects:
                logger.debug(f"    Rect[{idx}] crosses: y=[{rect.y:.1f}, {rect.y + rect.height:.1f}]")
    
    return None


class TreeBuilderAlgorithm(LayoutAlgorithm):
    """Layout algorithm that builds a tree from existing layout and recomputes it.
    
    This is useful for:
    1. Validating that a layout can be represented as a slicing tree
    2. Testing tree-based layout computation
    3. Debugging tree builder and compute_dimensions/compute_layout
    
    The algorithm:
    1. Takes the input rectangles with their x, y positions
    2. Builds a binary slicing tree from those positions
    3. Uses the tree to recompute positions (should match original if preserve_aspect_ratio=True)
    """
    
    def __init__(self, tolerance: float = 20.0):
        """Initialize tree builder algorithm.
        
        Args:
            tolerance: Tolerance for alignment in MCF units (0.1mm each).
                      Default 20.0 = 2.0mm.
        """
        self.tolerance = tolerance
        self.final_tree = None
    
    def generate_layout(
        self,
        page_width: float,
        page_height: float,
        rectangles: List[LayoutRectangle],
        **kwargs
    ) -> Tuple[bool, List[LayoutRectangle], str]:
        """Generate layout by building tree from input positions and recomputing.
        
        Args:
            page_width: Page width
            page_height: Page height
            rectangles: Input rectangles with x, y, width, height set
            
        Returns:
            (success, rectangles, error_msg)
        """
        if not rectangles:
            return False, [], "No rectangles to layout"
        
        # Validate that all rectangles have positions (x, y, width, height)
        for rect in rectangles:
            if rect.x is None or rect.y is None or rect.width is None or rect.height is None:
                return False, [], f"TreeBuilder requires all rectangles to have positions. Rectangle {rect.item_id} is missing position data (x={rect.x}, y={rect.y}, w={rect.width}, h={rect.height})"
        
        # Log input for debugging
        logger.info(f"TreeBuilder: Building tree from {len(rectangles)} rectangles")
        logger.info(f"  Page dimensions: {page_width} x {page_height}")
        for i, rect in enumerate(rectangles):
            logger.info(f"  Rect[{i}] id={rect.item_id}: pos=({rect.x:.1f}, {rect.y:.1f}) size=({rect.width:.1f} x {rect.height:.1f}) aspect={rect.preserve_aspect_ratio}")
        
        # Build tree from input positions
        tree = build_tree_from_layout(rectangles, page_width, page_height, self.tolerance)
        
        if tree is None:
            # Log detailed debug information when tree building fails
            logger.error("=" * 80)
            logger.error("TREE BUILDER FAILED: Cannot build slicing tree")
            logger.error(f"Page dimensions: {page_width} x {page_height}")
            logger.error(f"Tolerance: {self.tolerance}")
            logger.error(f"Number of rectangles: {len(rectangles)}")
            logger.error("-" * 80)
            logger.error("Rectangle details:")
            for i, rect in enumerate(rectangles):
                logger.error(f"  [{i}] id={rect.item_id}")
                logger.error(f"      Position: ({rect.x:.2f}, {rect.y:.2f})")
                logger.error(f"      Size: {rect.width:.2f} x {rect.height:.2f}")
                logger.error(f"      Bounds: x=[{rect.x:.2f}, {rect.x + rect.width:.2f}] y=[{rect.y:.2f}, {rect.y + rect.height:.2f}]")
                logger.error(f"      Aspect ratio: {rect.width/rect.height:.4f}")
                logger.error(f"      Preserve aspect: {rect.preserve_aspect_ratio}")
            logger.error("-" * 80)
            
            # Try to diagnose why the split failed
            indexed_rects = [(i, r) for i, r in enumerate(rectangles)]
            
            # Check for vertical split candidates
            logger.error("Checking vertical split candidates:")
            vertical_split = find_vertical_split(indexed_rects, page_width, self.tolerance)
            if vertical_split:
                v_pos, v_left, v_right = vertical_split
                logger.error(f"  Found vertical split at x={v_pos:.2f}: {len(v_left)} left, {len(v_right)} right")
            else:
                logger.error(f"  No valid vertical split found")
                # Log all vertical edges
                x_coords = set()
                for idx, rect in indexed_rects:
                    x_coords.add(rect.x)
                    x_coords.add(rect.x + rect.width)
                logger.error(f"  Tested {len(x_coords)} vertical split positions: {sorted(x_coords)}")
            
            # Check for horizontal split candidates  
            logger.error("Checking horizontal split candidates:")
            horizontal_split = find_horizontal_split(indexed_rects, page_height, self.tolerance)
            if horizontal_split:
                h_pos, h_top, h_bottom = horizontal_split
                logger.error(f"  Found horizontal split at y={h_pos:.2f}: {len(h_top)} top, {len(h_bottom)} bottom")
            else:
                logger.error(f"  No valid horizontal split found")
                # Log all horizontal edges
                y_coords = set()
                for idx, rect in indexed_rects:
                    y_coords.add(rect.y)
                    y_coords.add(rect.y + rect.height)
                logger.error(f"  Tested {len(y_coords)} horizontal split positions: {sorted(y_coords)}")
            
            logger.error("=" * 80)
            
            return False, [], "Cannot build slicing tree from this layout (not tree-representable)"
        
        # Store tree for get_final_tree()
        self.final_tree = tree
        
        # Compute layout from the tree
        tree.compute_aspect_ratios(rectangles)
        tree.compute_dimensions(page_width, page_height, rectangles)
        tree.compute_layout(0, 0)
        
        # Collect results
        leaves = tree.collect_leaves()
        
        # Create output rectangles with computed positions
        output = []
        for leaf in leaves:
            rect = rectangles[leaf.item_idx]
            
            # Create new rectangle with computed position
            output_rect = LayoutRectangle(
                item_id=rect.item_id,
                width=leaf.width,
                height=leaf.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio,
                x=leaf.x,
                y=leaf.y
            )
            output_rect.actual_size = leaf.width * leaf.height  # Set actual size
            output.append(output_rect)
        
        return True, output, ""
    
    def get_final_tree(self):
        """Return the final tree as a TreeNode for visualization/analysis.
        
        Returns:
            TreeNode representing the layout tree, or None if no layout generated yet.
        """
        return self.final_tree
