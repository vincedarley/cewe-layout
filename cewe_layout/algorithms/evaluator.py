"""Layout quality evaluator for page layouts.

Provides functions to compute a cost (badness) for a given layout based on:
  (a) Empty space on the page (typically acceptable: 5-10%)
    (b) How well the layout matches preferred photo sizes

Cost computation:
- Size mismatch: sum of squared differences between preferred sizes (normalized
    to sum to 1.0) and actual area fractions (each photo's area / page area).
- Empty space: penalizes unused page area above acceptable threshold.
- Total cost: weighted sum with weight mismatch as primary consideration.

All functions operate on the abstract `LayoutRectangle` and page dimensions
and do not depend on MCF or file paths.
"""

from typing import List, Dict, Tuple, Optional
from .base import LayoutRectangle


class LayoutCost:
    """Container for layout cost components and overall cost.
    
    Attributes:
        empty_space_cost: Cost due to empty/wasted page area.
        size_mismatch_cost: Cost due to deviation from preferred sizes (sum of squared errors).
        total_cost: Weighted sum of the two cost components.
        empty_space_fraction: Fraction of page that is empty (0.0 to 1.0).
        size_errors: List of (item_id, preferred_norm, actual_norm, squared_error) for each rectangle.
    """
    
    def __init__(self, empty_space_cost: float, size_mismatch_cost: float,
                 total_cost: float, empty_space_fraction: float,
                 size_errors: List[Tuple[str, float, float, float]]):
        self.empty_space_cost = empty_space_cost
        self.size_mismatch_cost = size_mismatch_cost
        self.total_cost = total_cost
        self.empty_space_fraction = empty_space_fraction
        self.size_errors = size_errors
    
    def __repr__(self):
        return (f"LayoutCost(total={self.total_cost:.4f}, "
                f"empty={self.empty_space_cost:.4f}, "
                f"size_mismatch={self.size_mismatch_cost:.4f}, "
                f"empty_frac={self.empty_space_fraction:.2%})")


def evaluate_layout(
    page_width: float,
    page_height: float,
    rectangles: List[LayoutRectangle],
    size_importance: float = 10.0,
    acceptable_empty_fraction: float = 0.05,
) -> LayoutCost:
    """Evaluate the quality/cost of a layout.
    
    Computes two cost components in human-readable units:
    1. Empty space cost: percentage of page unused above `acceptable_empty_fraction`.
    2. Size mismatch cost: λ × (sum of squared percentage errors), where λ is `size_importance`.
    
    Operates in the same coordinate space as the layout algorithm. Callers should
    transform page/rectangles if gaps are used, prior to calling this function.
    
    Args:
        page_width: Page width in algorithm coordinates.
        page_height: Page height in algorithm coordinates.
        rectangles: Positioned `LayoutRectangle` objects with x, y, width, height.
        size_importance: λ factor for size mismatch importance (default 10.0).
        acceptable_empty_fraction: Fraction of page that can be empty without penalty (default 0.05 = 5%).
    
    Returns:
        LayoutCost object with detailed cost breakdown.
    """
    if not rectangles:
        # No rectangles: entire page is empty
        empty_fraction = 1.0
        excess_empty = max(0.0, empty_fraction - acceptable_empty_fraction)
        empty_space_percent = excess_empty * 100.0
        total_cost = empty_space_percent
        return LayoutCost(
            empty_space_cost=empty_space_percent,
            size_mismatch_cost=0.0,
            total_cost=total_cost,
            empty_space_fraction=empty_fraction,
            size_errors=[]
        )
    
    page_area = page_width * page_height
    
    if page_area <= 0:
        return LayoutCost(
            empty_space_cost=float('inf'),
            size_mismatch_cost=float('inf'),
            total_cost=float('inf'),
            empty_space_fraction=1.0,
            size_errors=[]
        )
    
    # (a) Compute empty space cost (percent above acceptable threshold)
    total_rect_area = sum(r.width * r.height for r in rectangles if r.x is not None and r.width and r.height)
    used_fraction = total_rect_area / page_area if page_area > 0 else 0.0
    empty_fraction = 1.0 - used_fraction
    
    # Only penalize empty space above acceptable threshold, convert to percent
    excess_empty = max(0.0, empty_fraction - acceptable_empty_fraction)
    empty_space_percent = excess_empty * 100.0
    
    # (b) Compute weight mismatch cost
    # Normalize desired weights to sum to 1.0
    total_preferred_size = sum(r.preferred_size for r in rectangles)
    if total_preferred_size <= 0:
        total_preferred_size = float(len(rectangles))  # Fallback: uniform sizes
    
    size_errors = []
    size_mismatch_sum = 0.0
    
    for rect in rectangles:
        if rect.x is None or rect.y is None or not rect.width or not rect.height:
            # Skip unpositioned rectangles
            continue
        
        # Desired weight normalized to [0, 1] summing to 1.0 across all rectangles
        preferred_normalized = rect.preferred_size / total_preferred_size
        
        # Actual weight = fraction of page area used by this rectangle
        rect_area = rect.width * rect.height
        actual_normalized = rect_area / page_area if page_area > 0 else 0.0
        
        # Squared error
        error = preferred_normalized - actual_normalized
        squared_error = error * error
        size_mismatch_sum += squared_error
        
        size_errors.append((rect.item_id, preferred_normalized, actual_normalized, squared_error))
    
    # Convert mismatch sum from fractions to percentage-squared, then apply λ
    size_mismatch_pct_sq = size_mismatch_sum * (100.0 * 100.0)
    size_mismatch_cost = size_importance * size_mismatch_pct_sq
    
    # Total cost: Empty% + λ × SizeMismatch%-sq
    total_cost = empty_space_percent + size_mismatch_cost
    
    return LayoutCost(
        empty_space_cost=empty_space_percent,
        size_mismatch_cost=size_mismatch_cost,
        total_cost=total_cost,
        empty_space_fraction=empty_fraction,
        size_errors=size_errors
    )
