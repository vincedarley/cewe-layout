"""
Abstract base class for page layout algorithms.

Layout algorithms operate on abstract pages and items, knowing nothing about
image files, MCF coordinates, or file paths. They work purely with:
- Page dimensions (width, height).
- Item dimensions (width, height, desired_weight).

The wrapper layer (collage_wrapper) translates between MCF coordinates/photos
and the algorithm's generic item/page space.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple


class LayoutRectangle:
    """Represents an item on a page, serving as both input and output to layout algorithms.
    
    On input to an algorithm:
    - item_id, width, height, desired_weight are set.
    - x, y are optional (may be None); algorithm can use as starting point.
    - achieved_weight is 0.0.
    
    On output from an algorithm:
    - x, y, width, height are set to the computed position/size.
    - achieved_weight reflects the actual weight achieved by the layout.
    
    Attributes:
        item_id: Unique identifier for this item (e.g., index, filename).
        width: Item width in page coordinates (input) or final width (output).
        height: Item height in page coordinates (input) or final height (output).
        desired_weight: Requested relative importance (0.5 to 2.0).
        achieved_weight: Actual weight achieved by layout (output).
        x: Top-left corner x-coordinate (optional input, required output).
        y: Top-left corner y-coordinate (optional input, required output).
    """
    
    def __init__(self, item_id: str, width: float, height: float, 
                 desired_weight: float = 1.0, x: float = None, y: float = None):
        self.item_id = item_id
        self.width = width
        self.height = height
        self.desired_weight = desired_weight
        self.achieved_weight = 0.0
        self.x = x
        self.y = y
    
    def __repr__(self):
        return (f"LayoutRectangle(id={self.item_id}, x={self.x}, y={self.y}, "
                f"w={self.width:.1f}, h={self.height:.1f}, "
                f"desired={self.desired_weight:.1f}, achieved={self.achieved_weight:.1f})")


class LayoutAlgorithm(ABC):
    """Abstract base class for layout generation algorithms.
    
    An algorithm receives:
    - Page dimensions (width, height).
    - A list of LayoutRectangle objects with dimensions, desired_weight, and optional starting positions.
    
    The algorithm modifies the rectangles in-place (or returns modified copies):
    - Sets x, y to computed positions.
    - Updates achieved_weight to reflect actual layout weight.
    
    The algorithm operates in abstract page coordinates. The wrapper layer
    handles all translation between MCF units, file paths, and item dimensions.
    """
    
    @abstractmethod
    def generate_layout(
        self,
        page_width: float,
        page_height: float,
        rectangles: List[LayoutRectangle],
        **kwargs
    ) -> Tuple[bool, List[LayoutRectangle], str]:
        """Generate a layout for rectangles on a page.
        
        Args:
            page_width: Page width in page coordinates.
            page_height: Page height in page coordinates.
            rectangles: List of LayoutRectangle objects with dimensions and desired_weight.
                       May have optional x, y starting hints.
        
        Returns:
            Tuple of (success: bool, rects: list, error_msg: str).
            On success, rects is a list of LayoutRectangle objects with x, y, achieved_weight set.
            On failure, rects is empty and error_msg explains the issue.
        """
        pass
