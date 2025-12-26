"""
Gap Perfecter Algorithm - Eliminates gaps and small overlaps in nearly-perfect layouts.

This algorithm takes a layout that is already very close to perfect (all gaps/overlaps are near zero
in gap-free space) and deterministically adjusts positions and sizes to completely
fill the page with zero gaps.

Algorithm:
1. Sort all rectangles (photos and texts) diagonally by distance from (0,0) top-left corner
2. For each rectangle in order:
   a. Fix small overlaps (<5mm) with previous rects by shifting right/down and shrinking
   b. Expand top-left to meet previous rects above/left (or edges at x=0, y=0)
   c. If within 15mm of right edge, expand to align perfectly with page edge
   d. If within 15mm of bottom edge, expand to align perfectly with page edge

This produces a gap-free layout while preserving the overall structure.
"""

from typing import List, Tuple, Optional
import math

from .base import LayoutAlgorithm, LayoutRectangle


class GapPerfecterAlgorithm(LayoutAlgorithm):
    """
    Deterministically eliminates gaps and small overlaps in nearly-perfect layouts.
    
    Takes an existing layout (from LayoutRectangle.x, LayoutRectangle.y positions)
    and adjusts positions/sizes to completely fill the page with no gaps.
    Works with both photos and text blocks interchangeably.
    
    IMPORTANT: This algorithm REQUIRES that all input rectangles have x,y positions set.
    It will fail if any rectangle has x=None or y=None.
    """
    
    # Tolerance in MCF units (0.1mm)
    OVERLAP_REMOVAL = 70.0  # 5mm
    EDGE_PROXIMITY = 150.0    # 15mm
    MISALIGNMENT_REMOVAL = 35.0  # 5mm - for aligning bottoms/rights with adjacent rects
    
    def generate_layout(
        self,
        page_width: float,
        page_height: float,
        rectangles: List[LayoutRectangle],
        **kwargs
    ) -> Tuple[bool, List[LayoutRectangle], str]:
        """
        Eliminate gaps from an existing layout.
        
        Args:
            page_width: Page width in gap-free coordinates.
            page_height: Page height in gap-free coordinates.
            rectangles: List of LayoutRectangle objects with x,y positions already set.
            **kwargs: Ignored (for compatibility).
        
        Returns:
            Tuple (success, positioned_rectangles, error_message).
        """
        if not rectangles:
            return False, [], "No rectangles to layout"
        
        # Validate that all rectangles have positions
        for rect in rectangles:
            if rect.x is None or rect.y is None:
                return False, [], f"Gap Perfecter requires all rectangles to have x,y positions set. Rectangle {rect.item_id} has x={rect.x}, y={rect.y}"
        
        # Clamp all input rectangles to valid page bounds
        # (They may come in slightly outside due to transformation rounding)
        for rect in rectangles:
            # Clamp position to page bounds
            if rect.x < 0:
                rect.width = max(1.0, rect.width + rect.x)  # Shrink width by amount that was negative
                rect.x = 0.0
            if rect.y < 0:
                rect.height = max(1.0, rect.height + rect.y)  # Shrink height by amount that was negative
                rect.y = 0.0
            
            # Clamp right/bottom edges to page bounds
            if rect.x + rect.width > page_width:
                rect.width = max(1.0, page_width - rect.x)
            if rect.y + rect.height > page_height:
                rect.height = max(1.0, page_height - rect.y)
        
        # Step 1: Sort rectangles diagonally (by distance from 0,0)
        sorted_rects = self._sort_diagonally(rectangles)
        
        debug = True  # Set to True to enable debug logging

        # Step 2: Process each rectangle in order
        perfected_rects = []
        for i, rect in enumerate(sorted_rects):
            # Create a working copy
            new_rect = LayoutRectangle(
                item_id=rect.item_id,
                x=rect.x,
                y=rect.y,
                width=rect.width,
                height=rect.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio
            )
            if debug:
                print(f"Processing rect {i} (ID {new_rect.item_id}): initial pos=({new_rect.x:.1f},{new_rect.y:.1f}) size=({new_rect.width:.1f}x{new_rect.height:.1f})")   

            # Step 3a: Fix small overlaps with previous rects
            self._fix_overlaps(new_rect, perfected_rects, debug)
            
            # Step 3b: Expand top-left to meet previous rects
            self._expand_top_left(new_rect, perfected_rects, debug)
            
            # Step 3c: Expand right if within 15mm of page edge
            self._expand_to_right_edge_if_close(new_rect, page_width, debug)
            
            # Step 3d: Expand bottom if within 15mm of page edge
            self._expand_to_bottom_edge_if_close(new_rect, page_height, debug)
            
            perfected_rects.append(new_rect)
        
        return True, perfected_rects, ""
    
    def _sort_diagonally(self, rectangles: List[LayoutRectangle]) -> List[LayoutRectangle]:
        """
        Sort rectangles by diagonal distance from (0,0).
        
        Distance = sqrt(x^2 + y^2) where (x,y) is the top-left corner.
        
        Args:
            rectangles: List of rectangles with x,y positions.
        
        Returns:
            Sorted list (closest to 0,0 first).
        """
        def distance_from_origin(rect: LayoutRectangle) -> float:
            return math.sqrt(rect.x ** 2 + rect.y ** 2)
        
        return sorted(rectangles, key=distance_from_origin)
    
    def _fix_overlaps(self, rect: LayoutRectangle, previous_rects: List[LayoutRectangle], debug: bool) -> None:
        """
        Fix small overlaps (<5mm) with previous rectangles.
        
        If this rect slightly overlaps with a previous rect, shift this rect right/down
        to remove the overlap and shrink width/height accordingly.
        
        Args:
            rect: Rectangle to fix (modified in place).
            previous_rects: All previously processed rectangles.
        """
        for prev in previous_rects:
            # Check for overlap
            if not self._rectangles_overlap(rect, prev):
                continue
            
            # Calculate overlap amounts
            x_overlap = min(rect.x + rect.width, prev.x + prev.width) - max(rect.x, prev.x)
            y_overlap = min(rect.y + rect.height, prev.y + prev.height) - max(rect.y, prev.y)
            if debug:
                print(f"  Overlap of {x_overlap:.1f}x{y_overlap:.1f} between rect ID {rect.item_id} and prev ID {prev.item_id}")
            
            # Fix the smaller overlap dimension - that will automatically take care of the other.
            if (x_overlap < y_overlap):
                # Fix horizontal overlap if it's small (<5mm) and rect is to the right of prev
                if 0 < x_overlap < self.OVERLAP_REMOVAL and rect.x < prev.x + prev.width:
                    # Shift rect right to align with prev's right edge
                    shift = x_overlap
                    if debug:
                        print(f"  Fixing horizontal overlap of {x_overlap:.1f} between rect ID {rect.item_id} and prev ID {prev.item_id}")
                    rect.x += shift
                    rect.width = max(1.0, rect.width - shift)  # Ensure width stays positive
            else:                    
                # Fix vertical overlap if it's small (<5mm) and rect is below prev
                if 0 < y_overlap < self.OVERLAP_REMOVAL and rect.y < prev.y + prev.height:
                    # Shift rect down to align with prev's bottom edge
                    shift = y_overlap
                    if debug:
                        print(f"  Fixing vertical overlap of {y_overlap:.1f} between rect ID {rect.item_id} and prev ID {prev.item_id}")
                    
                    rect.y += shift
                    rect.height = max(1.0, rect.height - shift)  # Ensure height stays positive
    
    def _expand_top_left(self, rect: LayoutRectangle, previous_rects: List[LayoutRectangle], debug: bool) -> None:
        """
        Expand rectangle's top-left to meet previous rects above/left.
        
        If there's a gap between this rect and previous rects above or to the left,
        expand this rect to fill the gap (move top-left corner, increase width/height).
        Only expands to page edges (0,0) if within 15mm.
        
        Also aligns bottom edge with left or right neighbor and right edge with top or bottom neighbor if within 5mm.
        
        Args:
            rect: Rectangle to expand (modified in place).
            previous_rects: All previously processed rectangles (photos and texts).
        """
        # Find the rightmost edge of any previous rect to our left (with Y overlap)
        target_left = 0.0  # Default: expand to page left edge
        left_neighbors = []  # Track all rects to our left with vertical overlap
        for prev in previous_rects:
            if self._has_vertical_overlap(rect, prev) and prev.x + prev.width <= rect.x:
                # Previous rect is to our left and has vertical overlap
                if prev.x + prev.width > target_left:
                    target_left = prev.x + prev.width
                left_neighbors.append(prev)
        
        # Expand left if there's a gap AND within 15mm of target
        if target_left < rect.x:
            gap = rect.x - target_left
            if gap < self.EDGE_PROXIMITY:
                if debug:
                    print(f".   Expanding left from {rect.x} to {target_left}")
                rect.width += gap  # Increase width
                rect.x = max(0.0, target_left)  # Move left, but not below 0
        
        # Align bottom with any left neighbor if within 5mm
        for left_neighbor in left_neighbors:
            left_bottom = left_neighbor.y + left_neighbor.height
            our_bottom = rect.y + rect.height
            bottom_diff = abs(our_bottom - left_bottom)
            
            if bottom_diff < self.MISALIGNMENT_REMOVAL:
                if debug:
                    print(f".   Aligning bottom edge from {our_bottom} to (left side) {left_bottom}")
                rect.height = left_bottom - rect.y
                break  # Only align to first match
        
        # Find right neighbors (with Y overlap) and align bottom edge if within 5mm
        right_neighbors = []
        for prev in previous_rects:
            if self._has_vertical_overlap(rect, prev) and prev.x >= rect.x + rect.width:
                # Previous rect is to our right and has vertical overlap
                right_neighbors.append(prev)
        
        for right_neighbor in right_neighbors:
            right_bottom = right_neighbor.y + right_neighbor.height
            our_bottom = rect.y + rect.height
            bottom_diff = abs(our_bottom - right_bottom)
            
            if bottom_diff < self.MISALIGNMENT_REMOVAL:
                if debug:
                    print(f".   Aligning bottom edge from {our_bottom} to (right side) {right_bottom}")
                rect.height = right_bottom - rect.y
                break  # Only align to first match
        
        # Find the bottommost edge of any previous rect above us (with X overlap)
        target_top = 0.0  # Default: expand to page top edge
        top_neighbors = []  # Track all rects above us with horizontal overlap
        for prev in previous_rects:
            if self._has_horizontal_overlap(rect, prev) and prev.y + prev.height <= rect.y:
                # Previous rect is above us and has horizontal overlap
                if prev.y + prev.height > target_top:
                    target_top = prev.y + prev.height
                top_neighbors.append(prev)
        
        # Expand top if there's a gap AND within 15mm of target
        if target_top < rect.y:
            gap = rect.y - target_top
            if gap < self.EDGE_PROXIMITY:
                # Within 15mm - expand to fill the gap
                if debug:
                    print(f".   Expanding top from {rect.y} to {target_top}")
                rect.y = max(0.0, target_top)  # Move up, but not below 0
        
        # Align right edge with any top neighbor if within 5mm
        for top_neighbor in top_neighbors:
            top_right = top_neighbor.x + top_neighbor.width
            our_right = rect.x + rect.width
            right_diff = abs(our_right - top_right)
            
            if right_diff < self.MISALIGNMENT_REMOVAL:
                if debug:
                    print(f".   Aligning right edge from {our_right} to (top side) {top_right}")
                # Align our right with this neighbor's right
                rect.width = top_right - rect.x
                break  # Only align to first match
        
        # Find bottom neighbors (with X overlap) and align right edge if within 5mm
        bottom_neighbors = []
        for prev in previous_rects:
            if self._has_horizontal_overlap(rect, prev) and prev.y >= rect.y + rect.height:
                # Previous rect is below us and has horizontal overlap
                bottom_neighbors.append(prev)
        
        for bottom_neighbor in bottom_neighbors:
            bottom_right = bottom_neighbor.x + bottom_neighbor.width
            our_right = rect.x + rect.width
            right_diff = abs(our_right - bottom_right)
            
            if right_diff < self.MISALIGNMENT_REMOVAL:
                if debug:
                    print(f".   Aligning right edge from {our_right} to (bottom side) {bottom_right}")
                rect.width = bottom_right - rect.x
                break  # Only align to first match
    
    def _expand_to_right_edge_if_close(self, rect: LayoutRectangle, page_width: float, debug: bool) -> None:
        """
        If rectangle is within 15mm of right page edge, expand to align perfectly.
        
        Args:
            rect: Rectangle to expand (modified in place).
            page_width: Page width in gap-free coordinates.
        """
        right_edge = rect.x + rect.width
        distance_to_edge = page_width - right_edge
        
        if 0 <= distance_to_edge < self.EDGE_PROXIMITY:
            if debug:
                print(f"Expanding right from {rect.x + rect.width} to {page_width}")
            rect.width = page_width - rect.x  # Set width to exactly reach edge
    
    def _expand_to_bottom_edge_if_close(self, rect: LayoutRectangle, page_height: float, debug: bool) -> None:
        """
        If rectangle is within 15mm of bottom page edge, expand to align perfectly.
        
        Args:
            rect: Rectangle to expand (modified in place).
            page_height: Page height in gap-free coordinates.
        """
        bottom_edge = rect.y + rect.height
        distance_to_edge = page_height - bottom_edge
        
        if 0 <= distance_to_edge < self.EDGE_PROXIMITY:
            if debug:
                print(f"Expanding bottom from {rect.y + rect.height} to {page_height}")
            rect.height = page_height - rect.y  # Set height to exactly reach edge
    
    def _rectangles_overlap(self, rect1: LayoutRectangle, rect2: LayoutRectangle) -> bool:
        """
        Check if two rectangles overlap at all.
        
        Args:
            rect1: First rectangle.
            rect2: Second rectangle.
        
        Returns:
            True if rectangles overlap, False otherwise.
        """
        # Rectangles overlap if they overlap in both X and Y dimensions
        x_overlap = (rect1.x < rect2.x + rect2.width and rect1.x + rect1.width > rect2.x)
        y_overlap = (rect1.y < rect2.y + rect2.height and rect1.y + rect1.height > rect2.y)
        return x_overlap and y_overlap
    
    def _has_vertical_overlap(self, rect1: LayoutRectangle, rect2: LayoutRectangle) -> bool:
        """
        Check if two rectangles have vertical overlap (Y ranges overlap).
        
        Args:
            rect1: First rectangle.
            rect2: Second rectangle.
        
        Returns:
            True if Y ranges overlap, False otherwise.
        """
        # Rectangles overlap vertically if their Y ranges intersect
        # Range 1: [rect1.y, rect1.y + rect1.height]
        # Range 2: [rect2.y, rect2.y + rect2.height]
        # They overlap if: max(top1, top2) < min(bottom1, bottom2)
        top1, bottom1 = rect1.y, rect1.y + rect1.height
        top2, bottom2 = rect2.y, rect2.y + rect2.height
        return max(top1, top2) < min(bottom1, bottom2)
    
    def _has_horizontal_overlap(self, rect1: LayoutRectangle, rect2: LayoutRectangle) -> bool:
        """
        Check if two rectangles have horizontal overlap (X ranges overlap).
        
        Args:
            rect1: First rectangle.
            rect2: Second rectangle.
        
        Returns:
            True if X ranges overlap, False otherwise.
        """
        # Rectangles overlap horizontally if their X ranges intersect
        # Range 1: [rect1.x, rect1.x + rect1.width]
        # Range 2: [rect2.x, rect2.x + rect2.width]
        # They overlap if: max(left1, left2) < min(right1, right2)
        left1, right1 = rect1.x, rect1.x + rect1.width
        left2, right2 = rect2.x, rect2.x + rect2.width
        return max(left1, left2) < min(right1, right2)
