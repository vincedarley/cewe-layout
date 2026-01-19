"""
Tree-based recursive image segmentation using white separator line detection.
Uses priority queue for global optimization - always splits the region with the best separator score.
"""

import cv2
import numpy as np
import heapq
from typing import List, Dict, Any, Tuple, Optional
from io import BytesIO
from PIL import Image
from .segmenter_base import ImageSegmenter, register_segmenter


class TreeSegmenter(ImageSegmenter):
    """Recursive tree-based segmentation using separator line detection.
    
    Automatically detects if photos are on dark or bright background and
    looks for appropriate separator lines.
    """
    
    def get_name(self) -> str:
        return "Tree (recursive separator detection)"
    
    def segment_for_count(self, image_data: bytes, image_format: str,
                         target_count: int, verbose: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Segment image using priority queue optimization to reach target count.
        
        This segmenter uses a priority queue to globally optimize splits - always
        splitting the region with the best separator score. Continues until reaching
        the target count or no more good separators are found.
        
        Automatically detects background type (dark or bright) and looks for
        appropriate separator lines.
        
        Args:
            image_data: Image bytes
            image_format: Image format (jpeg, png, etc.)
            target_count: Target number of regions (algorithm stops when reached)
            verbose: Print debug info
            
        Returns:
            List of segmented photos based on separator lines
        """
        if verbose:
            print(f"  Tree segmentation with target count: {target_count}")
        
        # Auto-detect background type
        pil_image = Image.open(BytesIO(image_data))
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')
        img_array = np.array(pil_image)
        img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        mean_brightness = np.mean(gray)
        
        # Determine if background is dark or bright
        # Dark background (like black photo album) will have low mean brightness
        is_dark_background = mean_brightness < 128
        
        if verbose:
            bg_type = "DARK" if is_dark_background else "BRIGHT"
            print(f"  Auto-detected background: {bg_type} (mean brightness: {mean_brightness:.1f})")
        
        if is_dark_background:
            # For dark backgrounds, look for dark separators (gaps between photos)
            # Use threshold of 50 to find dark lines
            result = segment_tree_priority_queue(
                image_data, image_format,
                target_count=target_count,
                min_separator_width=3,
                separator_threshold=50,
                look_for_dark=True,
                min_region_size=50000,
                verbose=verbose
            )
        else:
            # For bright backgrounds, look for bright white separators
            result = segment_tree_priority_queue(
                image_data, image_format,
                target_count=target_count,
                min_separator_width=3,
                separator_threshold=240,
                look_for_dark=False,
                min_region_size=50000,
                verbose=verbose
            )
        
        if verbose:
            print(f"  Tree segmentation produced {len(result)} regions")
        
        return result if result else None


# Register the tree segmenter
register_segmenter('tree', TreeSegmenter())


class Region:
    """Represents a region that can potentially be split."""
    def __init__(self, img: np.ndarray, offset_x: int, offset_y: int, 
                 best_separator: Optional[Tuple[str, int]] = None, score: float = 0.0):
        self.img = img
        self.offset_x = offset_x
        self.offset_y = offset_y
        self.best_separator = best_separator  # (axis, position) or None
        self.score = score
    
    def __lt__(self, other):
        # For heapq min-heap: higher scores come first (negate for max-heap behavior)
        return self.score > other.score


def segment_tree_priority_queue(image_data: bytes, image_format: str,
                                target_count: int = 1,
                                min_separator_width: int = 5,
                                separator_threshold: int = 240,
                                look_for_dark: bool = False,
                                min_region_size: int = 50000,
                                verbose: bool = False) -> List[Dict[str, Any]]:
    """Segment image using priority queue for global optimization.
    
    Uses a priority queue to always split the region with the best separator score.
    This provides global optimization instead of greedy local decisions.
    
    Args:
        image_data: Image bytes
        image_format: Image format (jpeg, png, etc.)
        target_count: Target number of regions to produce
        min_separator_width: Minimum width of separator in pixels (default 5)
        separator_threshold: Brightness threshold for separators (default 240 for bright, 50 for dark)
        look_for_dark: If True, look for dark separators below threshold; if False, look for bright above threshold
        min_region_size: Minimum area in pixels for a region to be split further (default 50000)
        verbose: Print debug info
        
    Returns:
        List of dictionaries with segment info
    """
    # Load image
    pil_image = Image.open(BytesIO(image_data))
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    
    img_array = np.array(pil_image)
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    
    if verbose:
        h, w = img_bgr.shape[:2]
        sep_mode = "DARK" if look_for_dark else "BRIGHT"
        print(f"    Starting priority queue segmentation on {w}x{h} image (target: {target_count} regions, mode: {sep_mode})")
    
    # Initialize priority queue with the full image
    # Evaluate the initial region
    initial_score, initial_sep = _evaluate_region(img_bgr, min_separator_width, 
                                                   separator_threshold, look_for_dark,
                                                   min_region_size, verbose)
    
    if initial_sep is None:
        # No separator found in entire image - return it as a single segment
        if verbose:
            print(f"    No separator found in full image, returning single region")
        return _convert_regions_to_segments([(img_bgr, 0, 0)], image_format, verbose)
    
    priority_queue = []
    initial_region = Region(img_bgr, 0, 0, initial_sep, initial_score)
    heapq.heappush(priority_queue, initial_region)
    
    # Track final leaf regions (no good separator)
    leaf_regions = []
    
    # PHASE 1: Growth phase - continue splitting until we have enough regions
    iteration = 0
    while priority_queue and (len(leaf_regions) + len(priority_queue)) < target_count:
        iteration += 1
        
        # Pop the region with the best separator score
        region = heapq.heappop(priority_queue)
        
        if verbose:
            axis, pos = region.best_separator
            h, w = region.img.shape[:2]
            print(f"    [Growth] Iteration {iteration}: Splitting {w}x{h} region at {region.offset_x},{region.offset_y} "
                  f"({axis} @ {pos}, score={region.score:.3f})")
        
        # Split this region
        sub_regions = _split_region(region, min_separator_width, separator_threshold, 
                                    look_for_dark, min_region_size, verbose)
        
        # Evaluate each sub-region and add to queue or leaf list
        for sub_img, sub_x, sub_y in sub_regions:
            score, separator = _evaluate_region(sub_img, min_separator_width, 
                                               separator_threshold, look_for_dark, min_region_size, verbose)
            
            if separator is None:
                # No good separator found - check if it's background before adding as leaf
                if is_background_region(sub_img, max_std_dev=10.0, verbose=False):
                    # Background region - discard it
                    if verbose:
                        sh, sw = sub_img.shape[:2]
                        print(f"      Sub-region at {sub_x},{sub_y} ({sw}x{sh}) is background, discarding")
                else:
                    # Not background - this is a real leaf region
                    leaf_regions.append((sub_img, sub_x, sub_y))
                    if verbose:
                        sh, sw = sub_img.shape[:2]
                        print(f"      Sub-region at {sub_x},{sub_y} ({sw}x{sh}) has no good separator, adding to leaves")
            else:
                # Has a good separator - add to priority queue for potential future split
                sub_region = Region(sub_img, sub_x, sub_y, separator, score)
                heapq.heappush(priority_queue, sub_region)
                if verbose:
                    sh, sw = sub_img.shape[:2]
                    sep_axis, sep_pos = separator
                    print(f"      Sub-region at {sub_x},{sub_y} ({sw}x{sh}) has separator "
                          f"({sep_axis} @ {sep_pos}, score={score:.3f}), adding to queue")
    
    # PHASE 2: Refinement phase - trim white borders from remaining regions
    # Continue splitting regions that have white background on one side
    ENABLE_REFINEMENT = False  # DISABLED: Growth phase already produces well-trimmed regions
    
    if ENABLE_REFINEMENT and verbose and priority_queue:
        print(f"    [Refinement] Reached target count ({len(leaf_regions)} leaves, {len(priority_queue)} in queue)")
        print(f"    [Refinement] Trimming white borders from remaining regions...")
        
        # Save pre-refinement regions for debugging
        print(f"    [Refinement] Saving pre-refinement regions to /tmp...")
        for idx, region in enumerate(priority_queue):
            h, w = region.img.shape[:2]
            pre_refine_path = f"/tmp/tree_pre_refine_{idx}_at_{region.offset_x}_{region.offset_y}_{w}x{h}.png"
            cv2.imwrite(pre_refine_path, region.img)
            print(f"      Pre-refinement region {idx}: {w}x{h} at ({region.offset_x},{region.offset_y}) -> {pre_refine_path}")
    
    if verbose and priority_queue and not ENABLE_REFINEMENT:
        print(f"    [Refinement] DISABLED - Reached target count ({len(leaf_regions)} leaves, {len(priority_queue)} in queue)")
        print(f"    [Refinement] Skipping refinement phase - growth phase already trimmed borders")
    
    refinement_iteration = 0
    while ENABLE_REFINEMENT and priority_queue:
        refinement_iteration += 1
        
        # Pop the region with the best separator score
        region = heapq.heappop(priority_queue)
        
        if verbose:
            axis, pos = region.best_separator
            h, w = region.img.shape[:2]
            print(f"    [Refinement] Iteration {refinement_iteration}: Checking {w}x{h} region at {region.offset_x},{region.offset_y} "
                  f"({axis} @ {pos}, score={region.score:.3f})")
        
        # Split this region
        sub_regions = _split_region(region, min_separator_width, separator_threshold, 
                                    min_region_size, verbose)
        
        # Evaluate children and check if any are background
        children_info = []
        has_background_child = False
        
        for sub_img, sub_x, sub_y in sub_regions:
            is_bg = is_background_region(sub_img, max_std_dev=10.0, verbose=False)
            if is_bg:
                has_background_child = True
            
            score, separator = _evaluate_region(sub_img, min_separator_width, 
                                               separator_threshold, min_region_size, verbose)
            
            children_info.append((sub_img, sub_x, sub_y, is_bg, score, separator))
        
        if has_background_child:
            # At least one child is background - this split trims white borders
            # Process non-background children
            if verbose:
                print(f"      Split removes white border - continuing refinement")
            
            for sub_img, sub_x, sub_y, is_bg, score, separator in children_info:
                if is_bg:
                    # Discard background
                    if verbose:
                        sh, sw = sub_img.shape[:2]
                        print(f"      Sub-region at {sub_x},{sub_y} ({sw}x{sh}) is background, discarding")
                elif separator is None:
                    # Not background and no separator - final leaf
                    leaf_regions.append((sub_img, sub_x, sub_y))
                    if verbose:
                        sh, sw = sub_img.shape[:2]
                        print(f"      Sub-region at {sub_x},{sub_y} ({sw}x{sh}) has no separator, adding to leaves")
                else:
                    # Not background and has separator - add back to queue
                    sub_region = Region(sub_img, sub_x, sub_y, separator, score)
                    heapq.heappush(priority_queue, sub_region)
                    if verbose:
                        sh, sw = sub_img.shape[:2]
                        sep_axis, sep_pos = separator
                        print(f"      Sub-region at {sub_x},{sub_y} ({sw}x{sh}) has separator "
                              f"({sep_axis} @ {sep_pos}, score={score:.3f}), adding to queue")
        else:
            # Both children are real photos - splitting would increase photo count
            # Keep this region unsplit as a final leaf
            leaf_regions.append((region.img, region.offset_x, region.offset_y))
            if verbose:
                h, w = region.img.shape[:2]
                print(f"      Both children are photos - keeping {w}x{h} region unsplit")
            # Stop refinement - remaining queue regions are also final
            break
    
    # Collect all final regions: leaf regions + remaining queue regions
    final_regions = list(leaf_regions)
    while priority_queue:
        region = heapq.heappop(priority_queue)
        final_regions.append((region.img, region.offset_x, region.offset_y))
    
    if verbose:
        print(f"    Priority queue segmentation completed: {len(final_regions)} regions "
              f"(target was {target_count})")
        print(f"    Analyzing final regions:")
        for i, (region_img, x, y) in enumerate(final_regions):
            gray = cv2.cvtColor(region_img, cv2.COLOR_BGR2GRAY)
            h, w = region_img.shape[:2]
            mean_val = np.mean(gray)
            std_dev = np.std(gray)
            print(f"      Region {i} at ({x},{y}): {w}x{h}, mean={mean_val:.1f}, std_dev={std_dev:.2f}")
            
            # Save region to /tmp for investigation
            debug_path = f"/tmp/tree_region_{i}_at_{x}_{y}_{w}x{h}.png"
            cv2.imwrite(debug_path, region_img)
            print(f"        Saved to: {debug_path}")
    
    # Convert regions to segment format
    return _convert_regions_to_segments(final_regions, image_format, verbose)


def _evaluate_region(img: np.ndarray, min_separator_width: int, 
                     separator_threshold: int, look_for_dark: bool,
                     min_region_size: int, verbose: bool) -> Tuple[float, Optional[Tuple[str, int]]]:
    """Evaluate a region and find its best separator.
    
    Args:
        look_for_dark: If True, look for dark separators; if False, look for bright ones
    
    Returns:
        Tuple of (score, separator) where separator is (axis, position) or None
    """
    h, w = img.shape[:2]
    area = h * w
    
    # Check if region is too small
    if area < min_region_size:
        return (0.0, None)
    
    # Check if region is uniform background - with diagnostic output
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    std_dev = np.std(gray)
    mean_val = np.mean(gray)
    is_bg = is_background_region(img, max_std_dev=10.0, verbose=False)
    
    if verbose:
        print(f"      Region {w}x{h}: mean={mean_val:.1f}, std_dev={std_dev:.2f}, is_background={is_bg}")
    
    if is_bg:
        return (0.0, None)
    
    # Find best separator (pass through verbose flag to see diagnostics)
    best_sep = find_best_separator(gray, min_separator_width, separator_threshold, 
                                   look_for_dark=look_for_dark, verbose=verbose)
    
    if best_sep is None:
        return (0.0, None)
    
    # Calculate score for this separator
    axis, position = best_sep
    score = _calculate_separator_score(gray, axis, position, min_separator_width)
    
    return (score, best_sep)

def _split_region(region: Region, min_separator_width: int, 
                 separator_threshold: int, look_for_dark: bool,
                 min_region_size: int, verbose: bool) -> List[Tuple[np.ndarray, int, int]]:
    """Split a region along its best separator and crop white margins from sub-regions.
    
    Returns:
        List of (sub_img, offset_x, offset_y) tuples with tight bounding boxes
    """
    from .image_segmenter import crop_white_margins, crop_edges
    
    if region.best_separator is None:
        return [(region.img, region.offset_x, region.offset_y)]
    
    axis, position = region.best_separator
    
    if axis == 'horizontal':
        top_half = region.img[:position, :]
        bottom_half = region.img[position:, :]
        sub_regions = [
            (top_half, region.offset_x, region.offset_y),
            (bottom_half, region.offset_x, region.offset_y + position)
        ]
    else:  # vertical
        left_half = region.img[:, :position]
        right_half = region.img[:, position:]
        sub_regions = [
            (left_half, region.offset_x, region.offset_y),
            (right_half, region.offset_x + position, region.offset_y)
        ]
    
    # Crop white margins from each sub-region and adjust coordinates
    result = []
    for sub_img, offset_x, offset_y in sub_regions:
        # Find bounds of non-white content
        gray = cv2.cvtColor(sub_img, cv2.COLOR_BGR2GRAY)
        non_white = gray < 240
        rows = np.any(non_white, axis=1)
        cols = np.any(non_white, axis=0)
        
        if np.any(rows) and np.any(cols):
            row_indices = np.where(rows)[0]
            col_indices = np.where(cols)[0]
            crop_top = row_indices[0]
            crop_left = col_indices[0]
            crop_bottom = row_indices[-1] + 1
            crop_right = col_indices[-1] + 1
            
            # Crop to content bounds
            cropped = sub_img[crop_top:crop_bottom, crop_left:crop_right]
            
            # Adjust offset coordinates
            adjusted_offset_x = offset_x + crop_left
            adjusted_offset_y = offset_y + crop_top
            
            result.append((cropped, adjusted_offset_x, adjusted_offset_y))
        else:
            # All white - keep original (shouldn't happen in practice)
            result.append((sub_img, offset_x, offset_y))
    
    return result


def _convert_regions_to_segments(regions: List[Tuple[np.ndarray, int, int]], 
                                 image_format: str, 
                                 verbose: bool) -> List[Dict[str, Any]]:
    """Convert region tuples to segment dictionaries.
    
    Args:
        regions: List of (region_img, offset_x, offset_y) tuples with tight bounding boxes
        image_format: Image format for output
        verbose: Print debug info
        
    Returns:
        List of segment dictionaries
    """
    from .image_segmenter import crop_edges
    
    segments = []
    for i, (region_img, left, top) in enumerate(regions):
        # Regions already have tight bounding boxes from splitting process
        # Just apply final edge trimming
        cropped = crop_edges(region_img, pixels=2)
        
        # Convert back to RGB for PIL
        region_rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
        region_pil = Image.fromarray(region_rgb)
        
        # Save to bytes using original format with quality=99 for JPEG
        output = BytesIO()
        save_format = image_format.upper()
        if save_format == 'JPEG' or save_format == 'JPG':
            region_pil.save(output, format='JPEG', quality=99)
        else:
            region_pil.save(output, format=save_format)
        
        region_data = output.getvalue()
        
        segments.append({
            'data': region_data,
            'format': image_format.lower(),
            'left': left,
            'top': top,
            'width': region_pil.width,
            'height': region_pil.height
        })
        
        if verbose:
            print(f"    Region {i}: ({left},{top}) {region_pil.width}x{region_pil.height}")
    
    return segments


def find_best_separator(gray: np.ndarray, min_width: int, threshold: int,
                       look_for_dark: bool = False, verbose: bool = False) -> Optional[Tuple[str, int]]:
    """Find the single best separator line (horizontal or vertical).
    
    Args:
        gray: Grayscale image
        min_width: Minimum width of separator in pixels
        threshold: Brightness threshold (bright separators > threshold, dark separators < threshold)
        look_for_dark: If True, look for dark separators below threshold; if False, look for bright above threshold
        verbose: Print debug info
        
    Returns:
        Tuple of (axis, position) for the best separator, or None if no good separator found
        axis is 'horizontal' or 'vertical'
        position is the center pixel of the separator
    """
    h, w = gray.shape
    
    # Find horizontal separators
    h_seps = find_separator_candidates(gray, 'horizontal', min_width, threshold, look_for_dark)
    
    # Find vertical separators
    v_seps = find_separator_candidates(gray, 'vertical', min_width, threshold, look_for_dark)
    
    if verbose:
        print(f"        Found {len(h_seps)} horizontal candidates, {len(v_seps)} vertical candidates")
    
    # Score each separator by how "clean" it is
    # For bright separators: high average brightness
    # For dark separators: low average brightness (inverted scoring)
    best_score = 0
    best_sep = None
    all_scores = []  # For diagnostics
    
    for position, width, avg_brightness in h_seps:
        # Score based on: brightness (or darkness), width, and how centered it is
        centeredness = 1.0 - abs((position / h) - 0.5)  # 1.0 at center, less toward edges
        
        if look_for_dark:
            # For dark separators: lower brightness is better, invert the score
            brightness_score = 1.0 - (avg_brightness / 255.0)
        else:
            # For bright separators: higher brightness is better
            brightness_score = avg_brightness / 255.0
        
        score = brightness_score * (1 + width / 10.0) * (0.5 + 0.5 * centeredness)
        all_scores.append(('horizontal', position, width, avg_brightness, centeredness, score))
        
        if score > best_score:
            best_score = score
            best_sep = ('horizontal', position)
    
    for position, width, avg_brightness in v_seps:
        centeredness = 1.0 - abs((position / w) - 0.5)
        
        if look_for_dark:
            brightness_score = 1.0 - (avg_brightness / 255.0)
        else:
            brightness_score = avg_brightness / 255.0
        
        score = brightness_score * (1 + width / 10.0) * (0.5 + 0.5 * centeredness)
        all_scores.append(('vertical', position, width, avg_brightness, centeredness, score))
        
        if score > best_score:
            best_score = score
            best_sep = ('vertical', position)
    
    # Diagnostic output when verbose
    if verbose and all_scores:
        # Sort by score descending
        all_scores.sort(key=lambda x: x[5], reverse=True)
        print(f"        Top separator candidates:")
        for axis, pos, width, brightness, cent, score in all_scores[:5]:
            print(f"          {axis:10s} @ {pos:4d}: width={width:3d}, brightness={brightness:5.1f}, centeredness={cent:.3f}, score={score:.3f}")
    
    # Only accept separators with a reasonable score
    if best_score < 0.8:  # Threshold for "good enough" separator
        if verbose and best_score > 0:
            print(f"        Best score {best_score:.3f} is below threshold 0.8 - rejecting")
        return None
    
    if verbose and best_sep:
        axis, pos = best_sep
        print(f"        Accepted separator: {axis} at {pos} (score: {best_score:.3f})")
    
    return best_sep

def _calculate_separator_score(gray: np.ndarray, axis: str, position: int,
                               min_width: int) -> float:
    """Calculate score for a separator.
    
    This is the same scoring logic as find_best_separator, extracted for reuse.
    """
    h, w = gray.shape
    
    if axis == 'horizontal':
        # Check the separator line brightness
        start = max(0, position - min_width // 2)
        end = min(h, position + min_width // 2)
        separator_strip = gray[start:end, :]
        avg_brightness = np.mean(separator_strip)
        width = end - start
        centeredness = 1.0 - abs((position / h) - 0.5)
    else:  # vertical
        start = max(0, position - min_width // 2)
        end = min(w, position + min_width // 2)
        separator_strip = gray[:, start:end]
        avg_brightness = np.mean(separator_strip)
        width = end - start
        centeredness = 1.0 - abs((position / w) - 0.5)
    
    score = (avg_brightness / 255.0) * (1 + width / 10.0) * (0.5 + 0.5 * centeredness)
    return score


def find_separator_candidates(gray: np.ndarray, axis: str, min_width: int,
                              threshold: int, look_for_dark: bool = False) -> List[Tuple[int, int, float]]:
    """Find all potential separator lines along the specified axis.
    
    Args:
        gray: Grayscale image
        axis: 'horizontal' or 'vertical'
        min_width: Minimum width of separator in pixels
        threshold: Brightness threshold (bright separators > threshold, dark separators < threshold)
        look_for_dark: If True, look for dark separators below threshold; if False, look for bright above threshold
        
    Returns:
        List of tuples: (position, width, average_brightness)
    """
    if axis == 'horizontal':
        # Average brightness across each row
        profile = np.mean(gray, axis=1)
    else:
        # Average brightness across each column
        profile = np.mean(gray, axis=0)
    
    # DEBUG: Check profile statistics
    profile_max = np.max(profile)
    profile_min = np.min(profile)
    if look_for_dark:
        num_matching = np.sum(profile < threshold)
        print(f"          DEBUG {axis}: profile range=[{profile_min:.1f}, {profile_max:.1f}], "
           f"{num_matching}/{len(profile)} below threshold {threshold} (DARK mode)")
        is_separator = profile < threshold
    else:
        num_matching = np.sum(profile > threshold)
        print(f"          DEBUG {axis}: profile range=[{profile_min:.1f}, {profile_max:.1f}], "
           f"{num_matching}/{len(profile)} above threshold {threshold} (BRIGHT mode)")
        is_separator = profile > threshold
    candidates = []
    
    in_separator = False
    start = 0
    
    for i, is_sep in enumerate(is_separator):
        if is_sep and not in_separator:
            # Start of separator
            start = i
            in_separator = True
        elif not is_sep and in_separator:
            # End of separator
            width = i - start
            if width >= min_width:
                center = (start + i) // 2
                avg_brightness = np.mean(profile[start:i])
                candidates.append((center, width, avg_brightness))
            in_separator = False
    
    # Handle separator at the end
    if in_separator:
        width = len(is_separator) - start
        if width >= min_width:
            center = (start + len(is_separator)) // 2
            avg_brightness = np.mean(profile[start:])
            candidates.append((center, width, avg_brightness))
    
    return candidates


def is_background_region(img: np.ndarray, max_std_dev: float = 10.0, 
                         verbose: bool = False) -> bool:
    """Check if image region is uniform background (any color).
    
    Uses standard deviation to detect uniformity. A region with very low
    std deviation is likely uniform background, regardless of color.
    
    Args:
        img: Image region in BGR format
        max_std_dev: Maximum std deviation for uniform region (default 10.0)
        verbose: Print debug info
        
    Returns:
        True if region appears to be uniform background
    """
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Calculate standard deviation
    std_dev = np.std(gray)
    
    # Low std deviation = uniform region = likely background
    is_uniform = std_dev < max_std_dev
    
    if verbose and is_uniform:
        mean_val = np.mean(gray)
        print(f"        Uniform region detected: std_dev={std_dev:.2f}, mean={mean_val:.1f}")
    
    return is_uniform
