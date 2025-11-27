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


# Legacy alias for backward compatibility
LayoutEvaluationResult = LayoutCost


def _page_area(page_width: float, page_height: float) -> float:
    return max(0.0, float(page_width) * float(page_height))


def compute_used_area(rectangles: List[LayoutRectangle]) -> float:
    """Return sum of rectangle areas (width * height).

    Note: This is a simple sum and does not account for overlaps. Algorithms
    should avoid producing overlapping rectangles; if overlaps are possible
    a more sophisticated union-area computation should be used.
    """
    total = 0.0
    for r in rectangles:
        if r.width is None or r.height is None:
            continue
        total += max(0.0, float(r.width) * float(r.height))
    return total


def compute_empty_fraction(rectangles: List[LayoutRectangle], page_width: float, page_height: float) -> float:
    """Compute fraction of the page area that is empty (1 - used_fraction).

    Returns value in [0.0, 1.0].
    """
    page_area = _page_area(page_width, page_height)
    if page_area <= 0.0:
        return 1.0
    used = compute_used_area(rectangles)
    used_frac = min(1.0, used / page_area)
    return max(0.0, 1.0 - used_frac)


def compute_size_mismatch(rectangles: List[LayoutRectangle], page_width: float, page_height: float) -> float:
    """Compute sum of squared differences between preferred size fractions
    and actual area fractions.

    Steps:
    - For each rectangle, obtain preferred_size (default 1.0).
    - Normalize preferred sizes to sum to 1.0 across the rectangles.
    - Compute each rectangle's area fraction (area / page_area).
    - Return sum((preferred_frac - area_frac)**2) over rectangles.
    """
    page_area = _page_area(page_width, page_height)
    if page_area <= 0.0:
        return float('inf')

    preferred_sizes = [max(0.0, float(getattr(r, 'preferred_size', 1.0) or 0.0)) for r in rectangles]
    total_preferred = sum(preferred_sizes)
    if total_preferred <= 0.0:
        # fallback: equal sizes
        preferred_fracs = [1.0 / max(1, len(rectangles)) for _ in rectangles]
    else:
        preferred_fracs = [s / total_preferred for s in preferred_sizes]

    area_fracs = []
    for r in rectangles:
        area = 0.0
        if r.width is not None and r.height is not None:
            area = max(0.0, float(r.width) * float(r.height))
        area_fracs.append(area / page_area)

    # If total area is less than page area, area_fracs will sum <= 1.0; that's expected.
    # We compare desired_fracs with area_fracs directly.
    mismatch = 0.0
    for p, a in zip(preferred_fracs, area_fracs):
        diff = p - a
        mismatch += diff * diff
    return mismatch


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


def evaluate_mcf_page(
    photos: List[dict],
    page_width: float,
    page_height: float,
    preferred_sizes: Optional[dict] = None,
    **eval_kwargs
) -> LayoutCost:
    """Quick helper to evaluate cost of an MCF page layout without running an algorithm.
    
    Converts MCF photo dicts to LayoutRectangle objects and evaluates the layout cost.
    
    Args:
        photos: List of MCF photo dicts with 'area_left', 'area_top', 'area_width', 'area_height', 'filename'.
        page_width: Page width in MCF units.
        page_height: Page height in MCF units.
        preferred_sizes: Optional dict mapping filename -> preferred_size (default 1.0 for all).
        **eval_kwargs: Additional arguments for evaluate_layout (size_importance, etc.).
    
    Returns:
        LayoutCost object.
    """
    rectangles = []
    
    for idx, photo in enumerate(photos):
        filename = photo.get('filename', '')
        preferred_size = 1.0
        if preferred_sizes and filename in preferred_sizes:
            preferred_size = preferred_sizes[filename]
        
        rect = LayoutRectangle(
            item_id=str(idx),
            width=photo.get('area_width', 0),
            height=photo.get('area_height', 0),
            preferred_size=preferred_size,
            x=photo.get('area_left', 0),
            y=photo.get('area_top', 0)
        )
        rectangles.append(rect)
    
    return evaluate_layout(page_width, page_height, rectangles, **eval_kwargs)


# Legacy alias
evaluate_photos_page = evaluate_mcf_page
