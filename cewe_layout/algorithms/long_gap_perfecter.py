"""
Long Gap Perfecter Algorithm - Eliminates gaps by aligning to extended edge lines.

This algorithm finds long lines defined by photo/text edges and aligns all photos
to those lines, creating perfect alignment along major visual axes.

Algorithm:
1. For each edge of each photo/text, extend a line across the page until it
   "cuts through" another photo (>15mm from edge) or reaches page boundary.
   Track which photos are "approximately touching" each line.

2. Group nearby parallel lines (within 10mm) by merging them into single lines
   placed exactly between them. Repeat until no more mergeable pairs exist.

3. Sort lines by length (longest first) and align all touching photos to each line,
   adjusting positions/dimensions fractionally for perfect alignment.

Result: A layout where every major line has photos/texts perfectly aligned to it.
"""

import logging
logger = logging.getLogger(__name__)

from typing import List, Tuple, Optional, Set
from dataclasses import dataclass
from enum import Enum

from .base import LayoutAlgorithm, LayoutRectangle


class LineOrientation(Enum):
    """Orientation of a line."""
    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"


@dataclass
class ExtendedLine:
    """
    A line segment extending across part or all of the page.
    
    For horizontal lines: y is constant, extends from x_start to x_end
    For vertical lines: x is constant, extends from y_start to y_end
    """
    orientation: LineOrientation
    position: float  # y-coordinate for horizontal, x-coordinate for vertical
    start: float  # x for horizontal, y for vertical
    end: float  # x for horizontal, y for vertical
    touching_items: Set[str]  # item_ids of rectangles approximately touching this line
    
    def length(self) -> float:
        """Return the length of this line."""
        return abs(self.end - self.start)
    
    def __repr__(self):
        if self.orientation == LineOrientation.HORIZONTAL:
            return f"H-Line(y={self.position:.1f}, x={self.start:.1f}→{self.end:.1f}, len={self.length():.1f})"
        else:
            return f"V-Line(x={self.position:.1f}, y={self.start:.1f}→{self.end:.1f}, len={self.length():.1f})"


class LongGapPerfecterAlgorithm(LayoutAlgorithm):
    """
    Eliminates gaps by finding and aligning to extended edge lines.
    
    Works by finding long lines defined by photo edges, grouping nearby parallel
    lines, and then aligning all photos to those lines for perfect alignment.
    
    IMPORTANT: This algorithm REQUIRES that all input rectangles have x,y positions set.
    """
    
    # Tolerance in MCF units (10 units = 1mm)
    CUT_THRESHOLD = 150.0  # 15mm - line must cut through photo by at least this much
    PROXIMITY_THRESHOLD = 100.0  # 10mm - parallel lines within this distance are merged
    ALIGNMENT_TOLERANCE = 50.0  # 5mm - photos within this distance are considered "touching"
    
    def getName(self) -> str:
        return "Long Gap Perfecter"
    
    def forcesUseOfCurrentLayout(self) -> bool:
        """Long Gap Perfecter requires current layout slot dimensions."""
        return True
    
    def generate_layout(
        self,
        page_width: float,
        page_height: float,
        rectangles: List[LayoutRectangle],
        **kwargs
    ) -> Tuple[bool, List[LayoutRectangle], str]:
        """
        Eliminate gaps by aligning to extended edge lines.
        
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
                return False, [], f"Long Gap Perfecter requires all rectangles to have x,y positions set. Rectangle {rect.item_id} has x={rect.x}, y={rect.y}"
        
        debug = True
        
        if debug:
            print(f"\n=== Long Gap Perfecter: Processing {len(rectangles)} rectangles ===")
            print(f"Page size: {page_width:.1f} x {page_height:.1f}")
        
        # Step 1: Create extended lines from all edges
        lines = self._create_extended_lines(rectangles, page_width, page_height, debug)
        
        if debug:
            print(f"\nStep 1 complete: Created {len(lines)} extended lines")
        
        # Step 2: Merge nearby parallel lines
        merged_lines = self._merge_parallel_lines(lines, debug)
        
        if debug:
            print(f"\nStep 2 complete: Merged to {len(merged_lines)} lines")
            print("\nFinal lines (sorted by length):")
            for i, line in enumerate(sorted(merged_lines, key=lambda l: l.length(), reverse=True)[:10]):
                print(f"  {i+1}. {line}, touching {len(line.touching_items)} items")
        
        # Step 3: Align rectangles to lines (longest first)
        aligned_rects = self._align_to_lines(rectangles, merged_lines, page_width, page_height, debug)
        
        if debug:
            print(f"\nStep 3 complete: Aligned {len(aligned_rects)} rectangles")
        
        return True, aligned_rects, ""
    
    def _create_extended_lines(
        self,
        rectangles: List[LayoutRectangle],
        page_width: float,
        page_height: float,
        debug: bool
    ) -> List[ExtendedLine]:
        """
        Step 1: Create extended lines from all rectangle edges.
        
        For each edge of each rectangle, extend a line until it cuts through
        another rectangle or reaches the page boundary.
        
        Args:
            rectangles: List of positioned rectangles.
            page_width: Page width.
            page_height: Page height.
            debug: Enable debug logging.
        
        Returns:
            List of extended lines with touching items tracked.
        """
        lines = []
        
        if debug:
            print(f"\nCreating extended lines from {len(rectangles)} rectangles:")
            for i, rect in enumerate(rectangles):
                print(f"  Rect {i} (ID {rect.item_id}): pos=({rect.x:.1f},{rect.y:.1f}) size=({rect.width:.1f}x{rect.height:.1f})")
                print(f"    Top edge: y={rect.y:.1f}, Bottom edge: y={rect.y + rect.height:.1f}")
        
        for rect in rectangles:
            # Four edges per rectangle
            # Top edge: horizontal line at y=rect.y
            # Bottom edge: horizontal line at y=rect.y + rect.height
            # Left edge: vertical line at x=rect.x
            # Right edge: vertical line at x=rect.x + rect.width
            
            # Top edge (horizontal)
            line = self._extend_horizontal_line(
                rect.y, rect.x, rect.x + rect.width, rect.item_id,
                rectangles, page_width, page_height, debug
            )
            if line:
                lines.append(line)
            
            # Bottom edge (horizontal)
            line = self._extend_horizontal_line(
                rect.y + rect.height, rect.x, rect.x + rect.width, rect.item_id,
                rectangles, page_width, page_height, debug
            )
            if line:
                lines.append(line)
            
            # Left edge (vertical)
            line = self._extend_vertical_line(
                rect.x, rect.y, rect.y + rect.height, rect.item_id,
                rectangles, page_width, page_height, debug
            )
            if line:
                lines.append(line)
            
            # Right edge (vertical)
            line = self._extend_vertical_line(
                rect.x + rect.width, rect.y, rect.y + rect.height, rect.item_id,
                rectangles, page_width, page_height, debug
            )
            if line:
                lines.append(line)
        
        if debug:
            print("\nAll initial horizontal lines created in Step 1:")
            h_lines = [line for line in lines if line.orientation == LineOrientation.HORIZONTAL]
            for line in sorted(h_lines, key=lambda l: l.position):
                print(f"  {line}")
        
        return lines
    
    def _extend_horizontal_line(
        self,
        y_pos: float,
        x_start: float,
        x_end: float,
        source_id: str,
        rectangles: List[LayoutRectangle],
        page_width: float,
        page_height: float,
        debug: bool
    ) -> Optional[ExtendedLine]:
        """
        Extend a horizontal line left and right until it cuts through a rectangle.
        
        Args:
            y_pos: Y-coordinate of the line.
            x_start: Initial starting x-coordinate.
            x_end: Initial ending x-coordinate.
            source_id: ID of rectangle that created this line.
            rectangles: All rectangles.
            page_width: Page width.
            debug: Enable debug logging.
        
        Returns:
            ExtendedLine or None if line has zero length.
        """
        touching_items = {source_id}
        
        if debug and abs(y_pos - 913.9) < 1.0:
            print(f"\n  Creating H-line at y={y_pos:.1f} from Rect {source_id}, initial range x={x_start:.1f} to {x_end:.1f}")
        
        # Extend left from x_start
        final_x_start = 0.0  # Default to page edge
        for rect in rectangles:
            if rect.item_id == source_id:
                continue
            
            # Check if this rectangle could be in the path of the extension
            # (i.e., it has some part to the left of or at x_start)
            rect_left = rect.x
            rect_right = rect.x + rect.width
            
            if rect_left < x_start:  # Rectangle could be in the leftward path
                # Does the line cut through this rectangle?
                if self._line_cuts_through_horizontal(y_pos, rect):
                    # Yes - this terminates the line
                    final_x_start = max(final_x_start, rect_right)
                elif self._is_touching_horizontal(y_pos, rect):
                    # No - it's approximately touching
                    touching_items.add(rect.item_id)
        
        # Extend right from x_end
        final_x_end = page_width  # Default to page edge
        for rect in rectangles:
            if rect.item_id == source_id:
                continue
            
            # Check if this rectangle could be in the path of the extension
            # (i.e., it has some part to the right of or at x_end)
            rect_left = rect.x
            rect_right = rect.x + rect.width
            
            if rect_right > x_end:  # Rectangle could be in the rightward path
                # Does the line cut through this rectangle?
                cuts_through = self._line_cuts_through_horizontal(y_pos, rect)
                if cuts_through:
                    # Yes - this terminates the line
                    final_x_end = min(final_x_end, rect_left)
                elif self._is_touching_horizontal(y_pos, rect):
                    # No - it's approximately touching
                    touching_items.add(rect.item_id)
        
        # Create line if it has non-zero length
        if final_x_end > final_x_start:
            line = ExtendedLine(
                orientation=LineOrientation.HORIZONTAL,
                position=y_pos,
                start=final_x_start,
                end=final_x_end,
                touching_items=touching_items
            )
            # Validate line is within page bounds, with tiny rounding allowed
            if not (0.0 <= y_pos <= page_height):
                logger.warning(f"Error on input: Created horizontal line at y={y_pos:.1f} outside page bounds (page_height={page_height:.1f})! Source: {source_id}")
            
            return line
        
        return None
    
    def _extend_vertical_line(
        self,
        x_pos: float,
        y_start: float,
        y_end: float,
        source_id: str,
        rectangles: List[LayoutRectangle],
        page_width: float,
        page_height: float,
        debug: bool
    ) -> Optional[ExtendedLine]:
        """
        Extend a vertical line up and down until it cuts through a rectangle.
        
        Args:
            x_pos: X-coordinate of the line.
            y_start: Initial starting y-coordinate.
            y_end: Initial ending y-coordinate.
            source_id: ID of rectangle that created this line.
            rectangles: All rectangles.
            page_width: Page width.
            page_height: Page height.
            debug: Enable debug logging.
        
        Returns:
            ExtendedLine or None if line has zero length.
        """
        touching_items = {source_id}
        
        # Extend up from y_start
        final_y_start = 0.0  # Default to page edge
        for rect in rectangles:
            if rect.item_id == source_id:
                continue
            
            # Check if this rectangle could be in the path of the extension
            # (i.e., it has some part above or at y_start)
            rect_top = rect.y
            rect_bottom = rect.y + rect.height
            
            if rect_top < y_start:  # Rectangle could be in the upward path
                # Does the line cut through this rectangle?
                if self._line_cuts_through_vertical(x_pos, rect):
                    # Yes - this terminates the line
                    final_y_start = max(final_y_start, rect_bottom)
                elif self._is_touching_vertical(x_pos, rect):
                    # No - it's approximately touching
                    touching_items.add(rect.item_id)
        
        # Extend down from y_end
        final_y_end = page_height  # Default to page edge
        for rect in rectangles:
            if rect.item_id == source_id:
                continue
            
            # Check if this rectangle could be in the path of the extension
            # (i.e., it has some part below or at y_end)
            rect_top = rect.y
            rect_bottom = rect.y + rect.height
            
            if rect_bottom > y_end:  # Rectangle could be in the downward path
                # Does the line cut through this rectangle?
                if self._line_cuts_through_vertical(x_pos, rect):
                    # Yes - this terminates the line
                    final_y_end = min(final_y_end, rect_top)
                elif self._is_touching_vertical(x_pos, rect):
                    # No - it's approximately touching
                    touching_items.add(rect.item_id)
        
        # Create line if it has non-zero length
        if final_y_end > final_y_start:
            line = ExtendedLine(
                orientation=LineOrientation.VERTICAL,
                position=x_pos,
                start=final_y_start,
                end=final_y_end,
                touching_items=touching_items
            )
            # Validate line is within page bounds
            if not (0.0 <= x_pos <= page_width):
                logger.warning(f"Error on input: Created vertical line at x={x_pos:.1f} outside page bounds (page_width={page_width:.1f})! Source: {source_id}")
            return line
        
        return None
    
    def _line_cuts_through_horizontal(self, y_pos: float, rect: LayoutRectangle) -> bool:
        """
        Check if a horizontal line cuts through a rectangle (>15mm from edges).
        
        Args:
            y_pos: Y-coordinate of the horizontal line.
            rect: Rectangle to check.
        
        Returns:
            True if line cuts through rectangle significantly.
        """
        rect_top = rect.y
        rect_bottom = rect.y + rect.height
        
        # Line must be within rectangle's y-range
        if y_pos <= rect_top or y_pos >= rect_bottom:
            return False
        
        # Line must be at least CUT_THRESHOLD away from both edges
        distance_from_top = y_pos - rect_top
        distance_from_bottom = rect_bottom - y_pos
        
        return (distance_from_top > self.CUT_THRESHOLD and 
                distance_from_bottom > self.CUT_THRESHOLD)
    
    def _line_cuts_through_vertical(self, x_pos: float, rect: LayoutRectangle) -> bool:
        """
        Check if a vertical line cuts through a rectangle (>15mm from edges).
        
        Args:
            x_pos: X-coordinate of the vertical line.
            rect: Rectangle to check.
        
        Returns:
            True if line cuts through rectangle significantly.
        """
        rect_left = rect.x
        rect_right = rect.x + rect.width
        
        # Line must be within rectangle's x-range
        if x_pos <= rect_left or x_pos >= rect_right:
            return False
        
        # Line must be at least CUT_THRESHOLD away from both edges
        distance_from_left = x_pos - rect_left
        distance_from_right = rect_right - x_pos
        
        return (distance_from_left > self.CUT_THRESHOLD and 
                distance_from_right > self.CUT_THRESHOLD)
    
    def _is_touching_horizontal(self, y_pos: float, rect: LayoutRectangle) -> bool:
        """
        Check if a horizontal line is approximately touching a rectangle's edge.
        
        Args:
            y_pos: Y-coordinate of the horizontal line.
            rect: Rectangle to check.
        
        Returns:
            True if line is within ALIGNMENT_TOLERANCE of top or bottom edge.
        """
        rect_top = rect.y
        rect_bottom = rect.y + rect.height
        
        return (abs(y_pos - rect_top) < self.ALIGNMENT_TOLERANCE or
                abs(y_pos - rect_bottom) < self.ALIGNMENT_TOLERANCE)
    
    def _is_touching_vertical(self, x_pos: float, rect: LayoutRectangle) -> bool:
        """
        Check if a vertical line is approximately touching a rectangle's edge.
        
        Args:
            x_pos: X-coordinate of the vertical line.
            rect: Rectangle to check.
        
        Returns:
            True if line is within ALIGNMENT_TOLERANCE of left or right edge.
        """
        rect_left = rect.x
        rect_right = rect.x + rect.width
        
        return (abs(x_pos - rect_left) < self.ALIGNMENT_TOLERANCE or
                abs(x_pos - rect_right) < self.ALIGNMENT_TOLERANCE)
    
    def _merge_parallel_lines(self, lines: List[ExtendedLine], debug: bool) -> List[ExtendedLine]:
        """
        Step 2: Merge nearby parallel lines into single lines.
        
        Repeatedly find pairs of parallel lines within PROXIMITY_THRESHOLD and
        replace them with a single line exactly between them.
        
        Args:
            lines: List of extended lines.
            debug: Enable debug logging.
        
        Returns:
            List of merged lines.
        """
        merged = list(lines)  # Start with all lines
        
        iteration = 0
        while True:
            iteration += 1
            # Try to find a mergeable pair
            merge_found = False
            
            for i in range(len(merged)):
                for j in range(i + 1, len(merged)):
                    line1 = merged[i]
                    line2 = merged[j]
                    
                    # Check if these lines can be merged
                    new_line = self._try_merge_lines(line1, line2, debug)
                    if new_line:
                        # Merge found - replace both lines with new merged line
                        if debug:
                            print(f"\nIteration {iteration}: Merging lines")
                            print(f"  Line 1: {line1}")
                            print(f"  Line 2: {line2}")
                            print(f"  Result: {new_line}")
                        
                        # Remove both old lines and add new merged line
                        merged = [line for k, line in enumerate(merged) if k != i and k != j]
                        merged.append(new_line)
                        merge_found = True
                        break
                
                if merge_found:
                    break
            
            if not merge_found:
                # No more mergeable pairs found
                break
        
        if debug:
            print(f"\nMerging complete after {iteration} iterations")
        
        return merged
    
    def _try_merge_lines(
        self,
        line1: ExtendedLine,
        line2: ExtendedLine,
        debug: bool
    ) -> Optional[ExtendedLine]:
        """
        Try to merge two lines if they are parallel and close enough.
        
        Args:
            line1: First line.
            line2: Second line.
            debug: Enable debug logging.
        
        Returns:
            Merged line if mergeable, None otherwise.
        """
        # Lines must have same orientation
        if line1.orientation != line2.orientation:
            return None
        
        # Lines must be within PROXIMITY_THRESHOLD of each other
        distance = abs(line1.position - line2.position)
        if distance > self.PROXIMITY_THRESHOLD:
            return None
        
        # Lines must overlap significantly in their length
        # At least 50% of the shorter line's length must overlap
        overlap_start = max(line1.start, line2.start)
        overlap_end = min(line1.end, line2.end)
        overlap_length = overlap_end - overlap_start
        
        if overlap_length <= 0:
            return None
        
        min_length = min(line1.length(), line2.length())
        if overlap_length < 0.5 * min_length:
            return None
        
        # Create merged line
        # Position: exactly between the two lines
        # Start/End: take the union (longer extent)
        merged_position = (line1.position + line2.position) / 2.0
        merged_start = min(line1.start, line2.start)
        merged_end = max(line1.end, line2.end)
        merged_touching = line1.touching_items | line2.touching_items
        
        return ExtendedLine(
            orientation=line1.orientation,
            position=merged_position,
            start=merged_start,
            end=merged_end,
            touching_items=merged_touching
        )
    
    def _align_to_lines(
        self,
        rectangles: List[LayoutRectangle],
        lines: List[ExtendedLine],
        page_width: float,
        page_height: float,
        debug: bool
    ) -> List[LayoutRectangle]:
        """
        Step 3: Align rectangles to lines (longest first).
        
        For each line, adjust all touching rectangles to perfectly align with it.
        
        Args:
            rectangles: List of rectangles to align.
            lines: List of merged lines.
            debug: Enable debug logging.
        
        Returns:
            List of aligned rectangles.
        """
        # Create working copies of rectangles
        aligned = []
        rect_map = {}
        for rect in rectangles:
            new_rect = LayoutRectangle(
                item_id=rect.item_id,
                x=rect.x,
                y=rect.y,
                width=rect.width,
                height=rect.height,
                preferred_size=rect.preferred_size,
                preserve_aspect_ratio=rect.preserve_aspect_ratio
            )
            aligned.append(new_rect)
            rect_map[rect.item_id] = new_rect
        
        # Sort lines by length (longest first)
        sorted_lines = sorted(lines, key=lambda l: l.length(), reverse=True)
        
        if debug:
            print(f"\nAligning rectangles to {len(sorted_lines)} lines...")
        
        for i, line in enumerate(sorted_lines):
            if debug and i < 10:  # Only show first 10
                print(f"\nProcessing line {i+1}: {line}")
            
            # Align all touching items to this line
            for item_id in line.touching_items:
                rect = rect_map.get(item_id)
                if rect is None:
                    continue
                
                if line.orientation == LineOrientation.HORIZONTAL:
                    self._align_rect_to_horizontal_line(rect, line, debug and i < 10)
                else:
                    self._align_rect_to_vertical_line(rect, line, debug and i < 10)
        
        # Validate and clamp rectangles to page bounds
        if debug:
            print("\nValidating aligned rectangles are within page bounds:")
        for rect in aligned:
            right_edge = rect.x + rect.width
            bottom_edge = rect.y + rect.height
            if rect.x < 0 or rect.y < 0 or right_edge > page_width or bottom_edge > page_height:
                if debug:
                    print(f"  WARNING: Rect {rect.item_id} out of bounds!")
                    print(f"    x={rect.x:.1f} (should be >= 0)")
                    print(f"    y={rect.y:.1f} (should be >= 0)")
                    print(f"    right={right_edge:.1f} (should be <= {page_width:.1f})")
                    print(f"    bottom={bottom_edge:.1f} (should be <= {page_height:.1f})")
        
        # Clamp all rectangles to page bounds to prevent accumulating errors
        for rect in aligned:
            if rect.x < 0:
                rect.width = max(1.0, rect.width + rect.x)  # Preserve right edge
                rect.x = 0
            if rect.y < 0:
                rect.height = max(1.0, rect.height + rect.y)  # Preserve bottom edge
                rect.y = 0
            if rect.x + rect.width > page_width:
                rect.width = max(1.0, page_width - rect.x)
            if rect.y + rect.height > page_height:
                rect.height = max(1.0, page_height - rect.y)
        
        return aligned
    
    def _align_rect_to_horizontal_line(
        self,
        rect: LayoutRectangle,
        line: ExtendedLine,
        debug: bool
    ) -> None:
        """
        Align a rectangle to a horizontal line.
        
        If the line is close to the rectangle's top, align top to line.
        If the line is close to the rectangle's bottom, align bottom to line.
        
        Args:
            rect: Rectangle to align (modified in place).
            line: Horizontal line.
            debug: Enable debug logging.
        """
        rect_top = rect.y
        rect_bottom = rect.y + rect.height
        
        dist_to_top = abs(line.position - rect_top)
        dist_to_bottom = abs(line.position - rect_bottom)
        
        if dist_to_top < self.ALIGNMENT_TOLERANCE:
            # Align top to line (keep bottom edge fixed by adjusting height)
            old_bottom = rect.y + rect.height
            if debug:
                print(f"  Aligning {rect.item_id} top from {rect_top:.1f} to {line.position:.1f} (dist={dist_to_top:.1f})")
            rect.y = line.position
            rect.height = old_bottom - rect.y
        
        elif dist_to_bottom < self.ALIGNMENT_TOLERANCE:
            # Align bottom to line
            if debug:
                print(f"  Aligning {rect.item_id} bottom from {rect_bottom:.1f} to {line.position:.1f} (dist={dist_to_bottom:.1f})")
            rect.height = line.position - rect.y
    
    def _align_rect_to_vertical_line(
        self,
        rect: LayoutRectangle,
        line: ExtendedLine,
        debug: bool
    ) -> None:
        """
        Align a rectangle to a vertical line.
        
        If the line is close to the rectangle's left, align left to line.
        If the line is close to the rectangle's right, align right to line.
        
        Args:
            rect: Rectangle to align (modified in place).
            line: Vertical line.
            debug: Enable debug logging.
        """
        rect_left = rect.x
        rect_right = rect.x + rect.width
        
        dist_to_left = abs(line.position - rect_left)
        dist_to_right = abs(line.position - rect_right)
        
        if dist_to_left < self.ALIGNMENT_TOLERANCE:
            # Align left to line (keep right edge fixed by adjusting width)
            old_right = rect.x + rect.width
            if debug:
                print(f"  Aligning {rect.item_id} left from {rect_left:.1f} to {line.position:.1f} (dist={dist_to_left:.1f})")
                print(f"    Before: x={rect.x:.4f}, width={rect.width:.4f}, right={old_right:.4f}")
            rect.x = line.position
            rect.width = old_right - rect.x
            if debug:
                new_right = rect.x + rect.width
                print(f"    After:  x={rect.x:.4f}, width={rect.width:.4f}, right={new_right:.4f}")
        
        elif dist_to_right < self.ALIGNMENT_TOLERANCE:
            # Align right to line
            if debug:
                print(f"  Aligning {rect.item_id} right from {rect_right:.1f} to {line.position:.1f} (dist={dist_to_right:.1f})")
            rect.width = line.position - rect.x
