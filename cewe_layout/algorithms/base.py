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
from typing import List, Tuple, Optional


class TreeNode:
    """Node in a binary slicing tree representing a page layout.
    
    A slicing tree is a binary tree where:
    - Internal nodes represent cuts (horizontal 'H' or vertical 'V')
    - Leaf nodes represent items (photos, text blocks) to be laid out
    
    This is a general-purpose representation used by layout algorithms like
    Fan's GA (2012) and can be used by other tree-based layout methods.
    
    The tree can be evaluated to compute:
    - Aspect ratios (via _compute_aspect_ratios)
    - Dimensions (via _compute_dimensions)
    - Positions (via _compute_layout)
    """
    
    def __init__(self, label=None, is_leaf=False, item_idx=None):
        """Initialize a tree node.
        
        Args:
            label: 'V' or 'H' for internal nodes, item index for leaves
            is_leaf: True if this is a leaf node
            item_idx: Index into rectangles list (for leaf nodes)
        """
        self.label = label  # 'V', 'H' for internal nodes, or item index for leaves
        self.is_leaf = is_leaf
        self.item_idx = item_idx  # Index into rectangles list (for leaf nodes)
        self.left = None
        self.right = None
        self.parent = None
        
        # Computed during layout
        self.aspect_ratio = None  # Width/height ratio
        self.width = None
        self.height = None
        self.x = None
        self.y = None
        
        # LayoutRectangle-compatible attributes (set during evaluation)
        self.item_id = None
        self.preferred_size = None
        self.preserve_aspect_ratio = None
        
        # Cached values (computed once, reused many times)
        self._leaf_count_cache = None
    
    def clone(self, parent=None) -> 'TreeNode':
        """Fast tree cloning optimized for genetic algorithms.
        
        This is ~10x faster than copy.deepcopy() because it:
        - Avoids Python's generic deepcopy machinery
        - Only copies what's needed (structure + labels)
        - Doesn't copy computed attributes (they'll be recomputed)
        
        Args:
            parent: Parent node in the cloned tree
            
        Returns:
            Cloned tree node
        """
        # Create new node with essential attributes only
        new_node = TreeNode(label=self.label, is_leaf=self.is_leaf, item_idx=self.item_idx)
        new_node.parent = parent
        
        # Copy cached leaf count if available (saves millions of recomputations)
        if self._leaf_count_cache is not None:
            new_node._leaf_count_cache = self._leaf_count_cache
        
        # Recursively clone children
        if self.left:
            new_node.left = self.left.clone(parent=new_node)
        if self.right:
            new_node.right = self.right.clone(parent=new_node)
        
        return new_node
    
    def count_leaves(self) -> int:
        """Count leaf nodes in this subtree (cached for performance)."""
        if self._leaf_count_cache is not None:
            return self._leaf_count_cache
        
        if self.is_leaf:
            count = 1
        else:
            left_count = self.left.count_leaves() if self.left else 0
            right_count = self.right.count_leaves() if self.right else 0
            count = left_count + right_count
        
        self._leaf_count_cache = count
        return count
    
    def collect_subtrees(self, min_leaves: int = 3) -> List['TreeNode']:
        """Collect all subtrees with at least min_leaves leaf nodes."""
        subtrees = []
        leaf_count = self.count_leaves()
        if not self.is_leaf and leaf_count >= min_leaves:
            subtrees.append(self)
        if self.left:
            subtrees.extend(self.left.collect_subtrees(min_leaves))
        if self.right:
            subtrees.extend(self.right.collect_subtrees(min_leaves))
        return subtrees
    
    def compute_aspect_ratios(self, rectangles: List['LayoutRectangle']) -> float:
        """Compute aspect ratio recursively for this subtree (Lemma 1 from Fan 2012).
        
        For leaf nodes: uses the rectangle's aspect ratio.
        For vertical cuts: aspect ratios add (a1 + a2).
        For horizontal cuts: uses reciprocal formula (a1*a2)/(a1+a2).
        
        Args:
            rectangles: List of LayoutRectangle objects
            
        Returns:
            Aspect ratio (width/height) of this subtree
        """
        if self.is_leaf:
            rect = rectangles[self.item_idx]
            self.aspect_ratio = rect.width / rect.height if rect.height > 0 else 1.0
            return self.aspect_ratio
        
        # Recursively compute children
        a1 = self.left.compute_aspect_ratios(rectangles)
        a2 = self.right.compute_aspect_ratios(rectangles)
        
        # Apply Lemma 1
        if self.label == 'V':
            # Vertical cut: aspect ratios add
            self.aspect_ratio = a1 + a2
        else:  # 'H'
            # Horizontal cut: reciprocal formula
            self.aspect_ratio = (a1 * a2) / (a1 + a2)
        
        return self.aspect_ratio
    
    def compute_dimensions(self, width: float, height: float, 
                          rectangles: List['LayoutRectangle'],
                          min_fraction: float = 0.01):
        """Compute dimensions recursively for this subtree (Lemma 2 from Fan 2012).
        
        Allocates space to children based on their aspect ratios while
        respecting minimum dimensions to prevent degenerate layouts.
        
        Args:
            width: Available width for this subtree
            height: Available height for this subtree
            rectangles: List of LayoutRectangle objects
            min_fraction: Minimum dimension as fraction of canvas (default 1%)
        """
        if self.is_leaf:
            # Lemma 2: largest image that fits in canvas
            rect = rectangles[self.item_idx]
            aspect = rect.width / rect.height if rect.height > 0 else 1.0
            self.width = min(width, aspect * height)
            self.height = self.width / aspect
            return
        
        # Allocate space to children based on aspect ratios
        a1 = self.left.aspect_ratio
        a2 = self.right.aspect_ratio
        
        # Minimum dimension to prevent degenerate layouts
        min_width = width * min_fraction
        min_height = height * min_fraction
        
        if self.label == 'V':
            # Vertical cut: divide width, both children get full height
            w1_ideal = width * (a1 / (a1 + a2))
            w2_ideal = width * (a2 / (a1 + a2))
            
            # Enforce minimum widths
            w1 = max(min_width, w1_ideal)
            w2 = max(min_width, w2_ideal)
            
            # If both needed adjustment, scale proportionally to fit
            if w1 + w2 > width:
                scale = width / (w1 + w2)
                w1 *= scale
                w2 *= scale
            
            self.left.compute_dimensions(w1, height, rectangles, min_fraction)
            self.right.compute_dimensions(w2, height, rectangles, min_fraction)
            # Set this node's dimensions
            self.width = self.left.width + self.right.width
            self.height = height
        else:  # 'H'
            # Horizontal cut: divide height, both children get full width
            h1_ideal = height * (a2 / (a1 + a2))
            h2_ideal = height * (a1 / (a1 + a2))
            
            # Enforce minimum heights
            h1 = max(min_height, h1_ideal)
            h2 = max(min_height, h2_ideal)
            
            # If both needed adjustment, scale proportionally to fit
            if h1 + h2 > height:
                scale = height / (h1 + h2)
                h1 *= scale
                h2 *= scale
            
            self.left.compute_dimensions(width, h1, rectangles, min_fraction)
            self.right.compute_dimensions(width, h2, rectangles, min_fraction)
            # Set this node's dimensions
            self.width = width
            self.height = self.left.height + self.right.height
    
    def compute_layout(self, x: float, y: float):
        """Compute positions recursively for this subtree.
        
        Places children according to the cut direction:
        - Vertical cuts: left child at (x,y), right child to the right
        - Horizontal cuts: left child at (x,y), right child below
        
        Args:
            x: X position of this subtree's top-left corner
            y: Y position of this subtree's top-left corner
        """
        self.x = x
        self.y = y
        
        if self.is_leaf:
            return
        
        if self.label == 'V':
            # Vertical cut: left child at (x,y), right child to the right
            self.left.compute_layout(x, y)
            self.right.compute_layout(x + self.left.width, y)
        else:  # 'H'
            # Horizontal cut: left child at (x,y), right child below
            self.left.compute_layout(x, y)
            self.right.compute_layout(x, y + self.left.height)
    
    def collect_leaves(self) -> List['TreeNode']:
        """Collect all leaf nodes in this subtree in traversal order."""
        if self.is_leaf:
            return [self]
        leaves = []
        if self.left:
            leaves.extend(self.left.collect_leaves())
        if self.right:
            leaves.extend(self.right.collect_leaves())
        return leaves
    
    def to_compact_string(self) -> str:
        """Generate compact string representation like H[V[1,2],V[3,4]]."""
        if self.is_leaf:
            return str(self.item_idx)
        
        left_str = self.left.to_compact_string() if self.left else "?"
        right_str = self.right.to_compact_string() if self.right else "?"
        return f"{self.label}[{left_str},{right_str}]"


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
    
    def forcesUseOfCurrentLayout(self) -> bool:
        """
        Return True if this algorithm requires using the current layout's slot dimensions.
        
        Algorithms that refine or adjust existing layouts (like Gap Perfecter, Tree Builder)
        need the actual slot dimensions from the current layout, not the image's native dimensions.
        
        Layout generation algorithms (like Collage Generator, Fan Layout) work from scratch
        and use the image's natural dimensions.
        
        Returns:
            True if algorithm requires current layout slot dimensions, False otherwise.
        """
        return False
    
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
