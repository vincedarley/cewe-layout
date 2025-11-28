"""
Abstract base class for page layout algorithms.

Layout algorithms operate on abstract pages and items, knowing nothing about
image files, MCF coordinates, or file paths. They work purely with:
- Page dimensions (width, height).
- Item dimensions (width, height, preferred_size).

The wrapper layer (collage_wrapper) translates between MCF coordinates/photos
and the algorithm's generic item/page space.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple


class LayoutRectangle:
    """Represents an item on a page, serving as both input and output to layout algorithms.
    
    On input to an algorithm:
    - item_id, width, height, preferred_size are set.
    - x, y are optional (may be None); algorithm can use as starting point.
    - actual_size is 0.0.
    
    On output from an algorithm:
    - x, y, width, height are set to the computed position/size.
    - actual_size reflects the actual size achieved by the layout.
    
    Attributes:
        item_id: Unique identifier for this item (e.g., index, filename).
        width: Item width in page coordinates (input) or final width (output).
        height: Item height in page coordinates (input) or final height (output).
        preferred_size: Requested relative importance (0.5 to 2.0).
        actual_size: Actual size achieved by layout (output).
        preserve_aspect_ratio: True for photos, False for text blocks that can stretch.
        x: Top-left corner x-coordinate (optional input, required output).
        y: Top-left corner y-coordinate (optional input, required output).
    """
    
    def __init__(self, item_id: str, width: float, height: float, 
                 preferred_size: float = 1.0, preserve_aspect_ratio: bool = True,
                 x: float = None, y: float = None):
        self.item_id = item_id
        self.width = width
        self.height = height
        self.preferred_size = preferred_size
        self.preserve_aspect_ratio = preserve_aspect_ratio
        self.actual_size = 0.0
        self.x = x
        self.y = y
    
    def __repr__(self):
        aspect_str = "photo" if self.preserve_aspect_ratio else "text"
        return (f"LayoutRectangle(id={self.item_id}, x={self.x}, y={self.y}, "
                f"w={self.width:.1f}, h={self.height:.1f}, "
                f"preferred={self.preferred_size:.1f}, actual={self.actual_size:.1f}, type={aspect_str})")


class LayoutAlgorithm(ABC):
    """Abstract base class for layout generation algorithms.
    
    An algorithm receives:
    - Page dimensions (width, height).
    - A list of LayoutRectangle objects with dimensions, preferred_size, and optional starting positions.
    
    The algorithm modifies the rectangles in-place (or returns modified copies):
    - Sets x, y to computed positions.
    - Updates actual_size to reflect actual layout size.
    
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
            rectangles: List of LayoutRectangle objects with dimensions and preferred_size.
                       May have optional x, y starting hints.
        
        Returns:
            Tuple of (success: bool, rects: list, error_msg: str).
            On success, rects is a list of LayoutRectangle objects with x, y, actual_size set.
            On failure, rects is empty and error_msg explains the issue.
        """
        pass
