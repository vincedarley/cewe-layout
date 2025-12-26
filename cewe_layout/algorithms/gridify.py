"""
Gridify layout algorithm.

This algorithm takes an existing layout and snaps all photo corners to a regular grid.
The grid spacing is determined by the smallest photo's dimensions.

The algorithm:
1. Find the smallest photo (by area)
2. Calculate grid spacing: how many times the smallest photo's width/height fits across/down the page
3. Create a regular grid with those dimensions
4. Snap each photo's 4 corners to the nearest grid points
5. Update photo positions and dimensions based on snapped corners

This is a cleanup/refinement algorithm that works best on layouts that are already
reasonably well-organized.
"""

from typing import List, Tuple
from .base import LayoutAlgorithm, LayoutRectangle


class GridifyAlgorithm(LayoutAlgorithm):
    """Gridify layout algorithm - snaps existing layout to a regular grid.
    
    This algorithm operates on an existing layout (rectangles must have x, y positions)
    and refines it by aligning all corners to a regular grid determined by the
    smallest photo's dimensions.
    """
    
    def __init__(self, debug=False):
        """Initialize Gridify algorithm.
        
        Args:
            debug: Enable debug output
        """
        self.debug = debug
    
    def forcesUseOfCurrentLayout(self) -> bool:
        """Gridify requires current layout slot dimensions."""
        return True
    
    def generate_layout(
        self,
        page_width: float,
        page_height: float,
        rectangles: List[LayoutRectangle],
        **kwargs
    ) -> Tuple[bool, List[LayoutRectangle], str]:
        """Generate layout by snapping rectangles to a regular grid.
        
        Args:
            page_width: Page width in page coordinates
            page_height: Page height in page coordinates
            rectangles: List of LayoutRectangle objects with x, y, width, height set
            **kwargs: Additional parameters (unused)
        
        Returns:
            Tuple (success: bool, rects: list, error_msg: str)
        """
        try:
            if not rectangles:
                return False, [], "No rectangles to layout"
            
            # Validate that all rectangles have positions
            for i, rect in enumerate(rectangles):
                if rect.x is None or rect.y is None or rect.width is None or rect.height is None:
                    return False, [], f"Rectangle {i} missing position/size (x={rect.x}, y={rect.y}, w={rect.width}, h={rect.height})"
            
            # Find the smallest layout slot by area (ignore text blocks)
            photos = [r for r in rectangles if r.preserve_aspect_ratio]
            if not photos:
                # No photos, just return rectangles as-is
                return True, rectangles, ""
            
            smallest_slot = min(photos, key=lambda r: r.width * r.height)
            
            if self.debug:
                print(f"\n=== Gridify Debug ===")
                print(f"Page: {page_width} x {page_height}")
                print(f"Smallest slot: {smallest_slot.width} x {smallest_slot.height}")
                print(f"\nBEFORE snapping:")
                for i, rect in enumerate(rectangles):
                    print(f"  {i}: x={rect.x:.2f}, y={rect.y:.2f}, w={rect.width:.2f}, h={rect.height:.2f}")
            
            # Calculate grid spacing based on smallest layout slot
            # How many times does smallest slot fit across/down the page?
            # Use int(x + 0.5) for consistent "round half up" behavior (avoids banker's rounding)
            grid_cols = max(1, int(page_width / smallest_slot.width + 0.5))
            grid_rows = max(1, int(page_height / smallest_slot.height + 0.5))
            
            # Actual grid spacing
            grid_spacing_x = page_width / grid_cols
            grid_spacing_y = page_height / grid_rows
            
            # Snap each rectangle's corners to the grid
            for rect in rectangles:
                # Get current corners
                left = rect.x
                top = rect.y
                right = rect.x + rect.width
                bottom = rect.y + rect.height
                
                # Snap each corner to nearest grid point
                snapped_left = self._snap_to_grid(left, grid_spacing_x)
                snapped_top = self._snap_to_grid(top, grid_spacing_y)
                snapped_right = self._snap_to_grid(right, grid_spacing_x)
                snapped_bottom = self._snap_to_grid(bottom, grid_spacing_y)
                
                # Calculate new dimensions
                new_width = snapped_right - snapped_left
                new_height = snapped_bottom - snapped_top
                
                # If corners snapped to same line, expand to at least one grid cell
                # (this should be very rare for already reasonable layouts)
                if new_width <= 0:
                    new_width = grid_spacing_x
                if new_height <= 0:
                    new_height = grid_spacing_y
                
                # Update rectangle with snapped values
                rect.x = snapped_left
                rect.y = snapped_top
                rect.width = new_width
                rect.height = new_height
            
            if self.debug:
                print(f"\nAFTER snapping:")
                for i, rect in enumerate(rectangles):
                    print(f"  {i}: x={rect.x:.2f}, y={rect.y:.2f}, w={rect.width:.2f}, h={rect.height:.2f}")
                print()
            
            return True, rectangles, ""
        
        except Exception as e:
            return False, [], f"Gridify error: {e}"
    
    def _snap_to_grid(self, value: float, grid_spacing: float) -> float:
        """Snap a value to the nearest grid point.
        
        Args:
            value: The value to snap
            grid_spacing: The grid spacing
        
        Returns:
            The snapped value
        """
        return round(value / grid_spacing) * grid_spacing
    
    def get_final_tree(self):
        """Return None - Gridify doesn't use tree structures.
        
        Returns:
            None (no tree representation)
        """
        return None
