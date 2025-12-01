"""Layout quality evaluator for page layouts.

Provides functions to compute a cost (badness) for a given layout based on:
  (a) Empty space on the page (typically acceptable: 5-10%)
  (b) How well the layout matches preferred photo sizes

Cost computation:
- Size mismatch: sum of squared differences between preferred sizes (normalized
    to sum to 1.0) and actual area fractions (each photo's area / page area).
- Empty space: penalizes unused page area above acceptable threshold.
- Total cost: weighted sum with size mismatch as primary consideration.

IMPORTANT: All evaluation happens in GAP-FREE coordinate space.
- Gaps (edge_gap, internal_gap) are parameters that define coordinate transformations
- They do NOT affect cost calculations directly
- Caller must transform to gap-free space BEFORE calling evaluate_layout()
- Cost calculation is completely unaware of gaps; it only sees gap-free coordinates

All functions operate on the abstract `LayoutRectangle` and page dimensions
and do not depend on MCF or file paths.
"""

from typing import List, Dict, Tuple, Optional, Union
from .base import LayoutRectangle


class LayoutCost:
    """Container for layout cost components and overall cost.
    
    Attributes:
        empty_space_cost: Cost due to empty/wasted page area.
        size_mismatch_cost: Cost due to deviation from preferred sizes (sum of squared errors).
        size_mismatch_normal_cost: Size mismatch cost for non-undersized rectangles.
        size_mismatch_undersized_cost: Size mismatch cost for undersized rectangles (with penalty).
        total_cost: Weighted sum of all cost components.
        empty_space_fraction: Fraction of page that is empty (0.0 to 1.0).
        size_errors: List of (item_id, preferred_norm, actual_norm, squared_error, is_undersized) for each rectangle.
        undersized_count: Number of rectangles that are undersized.
    """
    
    def __init__(self, empty_space_cost: float, size_mismatch_cost: float,
                 total_cost: float, empty_space_fraction: float,
                 size_errors: List[Tuple[str, float, float, float, bool]],
                 size_mismatch_normal_cost: float = 0.0,
                 size_mismatch_undersized_cost: float = 0.0,
                 undersized_count: int = 0):
        self.empty_space_cost = empty_space_cost
        self.size_mismatch_cost = size_mismatch_cost
        self.size_mismatch_normal_cost = size_mismatch_normal_cost
        self.size_mismatch_undersized_cost = size_mismatch_undersized_cost
        self.total_cost = total_cost
        self.empty_space_fraction = empty_space_fraction
        self.size_errors = size_errors
        self.undersized_count = undersized_count
    
    def __repr__(self):
        return (f"LayoutCost(total={self.total_cost:.4f}, "
                f"empty={self.empty_space_cost:.4f}, "
                f"size_mismatch={self.size_mismatch_cost:.4f} "
                f"(normal={self.size_mismatch_normal_cost:.4f}, "
                f"undersized={self.size_mismatch_undersized_cost:.4f}), "
                f"empty_frac={self.empty_space_fraction:.2%})")


def evaluate_layout(
    page_width: float,
    page_height: float,
    rectangles: List[LayoutRectangle],
    size_importance: float = 10.0,
    acceptable_empty_fraction: float = 0.05,
    undersized_threshold: float = 0.5,
    undersized_penalty: float = 5.0,
    detailed: bool = True,
) -> Union[float, 'LayoutCost']:
    """Evaluate the quality/cost of a layout.
    
    Computes cost components in human-readable units:
    1. Empty space cost: percentage of page unused above `acceptable_empty_fraction`.
    2. Size mismatch cost: λ × (sum of squared percentage errors), split into:
       - Normal: photos not severely undersized
       - Undersized: photos < threshold × preferred, with additional k × penalty
    
    Inspired by Fan (2012): apply extra penalty when important photos end up too small.
    
    Operates in the same coordinate space as the layout algorithm. Callers should
    transform page/rectangles if gaps are used, prior to calling this function.
    
    Args:
        page_width: Page width in algorithm coordinates.
        page_height: Page height in algorithm coordinates.
        rectangles: Positioned `LayoutRectangle` objects with x, y, width, height.
        size_importance: λ factor for size mismatch importance (default 10.0).
        acceptable_empty_fraction: Fraction of page that can be empty without penalty (default 0.05 = 5%).
        undersized_threshold: Ratio threshold for undersizing (default 0.5 = 50%).
        undersized_penalty: Additional multiplier k for undersized photos (default 5.0).
        detailed: If True, return LayoutCost with full breakdown. If False, return just float cost (default True).
    
    Returns:
        LayoutCost object with detailed breakdown if detailed=True, otherwise float cost.
    """
    # Handle empty rectangles
    if not rectangles:
        empty_fraction = 1.0
        excess_empty = max(0.0, empty_fraction - acceptable_empty_fraction)
        empty_space_percent = excess_empty * 100.0
        total_cost = empty_space_percent
        
        if not detailed:
            return total_cost
        
        return LayoutCost(
            empty_space_cost=empty_space_percent,
            size_mismatch_cost=0.0,
            total_cost=total_cost,
            empty_space_fraction=empty_fraction,
            size_errors=[],
            size_mismatch_normal_cost=0.0,
            size_mismatch_undersized_cost=0.0,
            undersized_count=0
        )
    
    page_area = page_width * page_height
    
    if page_area <= 0:
        if not detailed:
            return float('inf')
        
        return LayoutCost(
            empty_space_cost=float('inf'),
            size_mismatch_cost=float('inf'),
            total_cost=float('inf'),
            empty_space_fraction=1.0,
            size_errors=[],
            size_mismatch_normal_cost=float('inf'),
            size_mismatch_undersized_cost=float('inf'),
            undersized_count=0
        )
    
    # (a) Compute empty space cost (percent above acceptable threshold)
    total_rect_area = sum(r.width * r.height for r in rectangles if r.x is not None and r.width and r.height)
    used_fraction = total_rect_area / page_area if page_area > 0 else 0.0
    empty_fraction = 1.0 - used_fraction
    
    # Only penalize empty space above acceptable threshold, convert to percent
    excess_empty = max(0.0, empty_fraction - acceptable_empty_fraction)
    empty_space_percent = excess_empty * 100.0
    
    # (b) Compute size mismatch cost (split into normal and undersized)
    # Normalize desired sizes to sum to 1.0
    total_preferred_size = sum(r.preferred_size for r in rectangles)
    if total_preferred_size <= 0:
        total_preferred_size = float(len(rectangles))  # Fallback: uniform sizes
    
    size_errors = [] if detailed else None  # Only track if detailed output requested
    size_mismatch_normal_sum = 0.0
    size_mismatch_undersized_sum = 0.0
    
    for rect in rectangles:
        if rect.x is None or rect.y is None or not rect.width or not rect.height:
            # Skip unpositioned rectangles
            continue
        
        # Desired weight normalized to [0, 1] summing to 1.0 across all rectangles
        preferred_normalized = rect.preferred_size / total_preferred_size
        
        # Actual weight = fraction of page area used by this rectangle
        rect_area = rect.width * rect.height
        actual_normalized = rect_area / page_area if page_area > 0 else 0.0
        
        # Check if undersized: actual < threshold × preferred
        is_undersized = (actual_normalized < undersized_threshold * preferred_normalized)
        
        # Squared error
        error = preferred_normalized - actual_normalized
        squared_error = error * error
        
        if is_undersized:
            size_mismatch_undersized_sum += squared_error
        else:
            size_mismatch_normal_sum += squared_error
        
        if detailed:
            size_errors.append((rect.item_id, preferred_normalized, actual_normalized, squared_error, is_undersized))
    
    # Convert mismatch sums from fractions to percentage-squared, then apply λ
    size_mismatch_normal_pct_sq = size_mismatch_normal_sum * (100.0 * 100.0)
    size_mismatch_normal_cost = size_importance * size_mismatch_normal_pct_sq
    
    # Undersized: apply λ and additional penalty k
    size_mismatch_undersized_pct_sq = size_mismatch_undersized_sum * (100.0 * 100.0)
    size_mismatch_undersized_cost = size_importance * undersized_penalty * size_mismatch_undersized_pct_sq
    
    # Total size mismatch cost
    size_mismatch_cost = size_mismatch_normal_cost + size_mismatch_undersized_cost
    
    # Total cost: Empty% + λ × SizeMismatch%-sq (normal) + λ × k × SizeMismatch%-sq (undersized)
    total_cost = empty_space_percent + size_mismatch_cost
    
    # Return appropriate format
    if not detailed:
        return total_cost
    
    # Count undersized rectangles (only if detailed)
    undersized_count = sum(1 for _, _, _, _, is_undersized in size_errors if is_undersized) if size_errors else 0
    
    return LayoutCost(
        empty_space_cost=empty_space_percent,
        size_mismatch_cost=size_mismatch_cost,
        total_cost=total_cost,
        empty_space_fraction=empty_fraction,
        size_errors=size_errors,
        size_mismatch_normal_cost=size_mismatch_normal_cost,
        size_mismatch_undersized_cost=size_mismatch_undersized_cost,
        undersized_count=undersized_count
    )
