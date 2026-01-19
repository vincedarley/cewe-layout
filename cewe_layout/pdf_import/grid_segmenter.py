"""
Grid-based image segmentation using white separator line detection.
Suitable for photobook pages with regular grid layouts separated by white borders.
"""

import cv2
import numpy as np
import math
from typing import List, Dict, Any, Tuple, Optional
from io import BytesIO
from PIL import Image
from .segmenter_base import ImageSegmenter, register_segmenter


class GridSegmenter(ImageSegmenter):
    """Grid-based segmentation using white separator line detection."""
    
    def get_name(self) -> str:
        return "Grid (white separator detection)"
    
    def segment_for_count(self, image_data: bytes, image_format: str,
                         target_count: int, verbose: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Find grid layout that produces the target number of photos.
        
        Args:
            image_data: Image bytes
            image_format: Image format (jpeg, png, etc.)
            target_count: Desired number of photos
            verbose: Print debug info
            
        Returns:
            List of segmented photos if successful, None if target count not achieved
        """
        # Try to infer grid dimensions from target count
        # Try common layouts: 1x2, 2x2, 2x3, 2x4, 3x3, 3x4, etc.
        possible_grids = []
        for rows in range(1, 6):
            for cols in range(1, 6):
                if rows * cols == target_count:
                    possible_grids.append((rows, cols))
        
        # Try most common layouts first
        if not possible_grids:
            # Fallback: use reasonable defaults based on count
            if target_count <= 2:
                possible_grids = [(1, target_count)]
            elif target_count <= 4:
                possible_grids = [(2, 2)]
            elif target_count <= 8:
                possible_grids = [(2, 4)]
            else:
                # Try to make roughly square
                rows = int(math.sqrt(target_count))
                cols = (target_count + rows - 1) // rows
                possible_grids = [(rows, cols)]
        
        if verbose:
            print(f"  Trying grid algorithm with possible layouts: {possible_grids}")
        
        for rows, cols in possible_grids:
            result = segment_grid_by_separators(
                image_data, image_format,
                target_rows=rows,
                target_cols=cols,
                verbose=verbose
            )
            if len(result) == target_count:
                if verbose:
                    print(f"  ✅ Grid segmentation succeeded with {rows}x{cols} layout")
                return result
        
        # Could not achieve target count
        if verbose:
            print(f"  Grid segmentation did not achieve target count {target_count}")
        return None


# Register the grid segmenter
register_segmenter('grid', GridSegmenter())


def segment_grid_by_separators(image_data: bytes, image_format: str,
                                target_rows: int = 2,
                                target_cols: int = 4,
                                min_separator_width: int = 5,
                                separator_threshold: int = 240,
                                verbose: bool = False) -> List[Dict[str, Any]]:
    """Segment image by detecting white separator lines in a regular grid.
    
    This works well for photobook pages where photos are arranged in a regular
    grid with thin white borders between them.
    
    Args:
        image_data: Image bytes
        image_format: Image format (jpeg, png, etc.)
        target_rows: Expected number of rows (default 2)
        target_cols: Expected number of columns (default 4)
        min_separator_width: Minimum width of separator in pixels (default 5)
        separator_threshold: Brightness threshold for white separators (default 240)
        verbose: Print debug info
        
    Returns:
        List of dictionaries with segment info (same format as segment_composite_image)
    """
    # Load image
    pil_image = Image.open(BytesIO(image_data))
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    
    img_array = np.array(pil_image)
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    h, w = img_bgr.shape[:2]
    
    if verbose:
        print(f"    Grid segmentation: {w}x{h} image, looking for {target_rows}x{target_cols} grid")
    
    # Convert to grayscale
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    
    # Find horizontal separator lines
    horizontal_seps = find_separator_lines(gray, axis='horizontal', 
                                          min_width=min_separator_width,
                                          threshold=separator_threshold,
                                          verbose=verbose)
    
    # Find vertical separator lines
    vertical_seps = find_separator_lines(gray, axis='vertical',
                                        min_width=min_separator_width,
                                        threshold=separator_threshold,
                                        verbose=verbose)
    
    if verbose:
        print(f"    Found {len(horizontal_seps)} horizontal separators: {horizontal_seps}")
        print(f"    Found {len(vertical_seps)} vertical separators: {vertical_seps}")
    
    # If we don't have enough separators, try to infer grid from image size
    if len(horizontal_seps) < target_rows - 1 or len(vertical_seps) < target_cols - 1:
        if verbose:
            print(f"    Not enough separators found, using uniform grid")
        return create_uniform_grid(img_bgr, image_format, target_rows, target_cols, verbose)
    
    # Create grid cells from separators
    row_boundaries = [0] + horizontal_seps + [h]
    col_boundaries = [0] + vertical_seps + [w]
    
    segments = []
    for row_idx in range(len(row_boundaries) - 1):
        for col_idx in range(len(col_boundaries) - 1):
            top = row_boundaries[row_idx]
            bottom = row_boundaries[row_idx + 1]
            left = col_boundaries[col_idx]
            right = col_boundaries[col_idx + 1]
            
            # Extract the cell
            cell = img_bgr[top:bottom, left:right]
            
            # Crop white borders from the cell
            from .image_segmenter import crop_white_margins, crop_edges
            cell = crop_white_margins(cell, threshold=240)
            cell = crop_edges(cell, pixels=2)
            
            # Convert back to RGB for PIL
            cell_rgb = cv2.cvtColor(cell, cv2.COLOR_BGR2RGB)
            cell_pil = Image.fromarray(cell_rgb)
            
            # Save to bytes
            output = BytesIO()
            cell_pil.save(output, format=image_format.upper())
            cell_data = output.getvalue()
            
            segments.append({
                'data': cell_data,
                'format': image_format,
                'left': left,
                'top': top,
                'width': cell_pil.width,
                'height': cell_pil.height
            })
            
            if verbose:
                print(f"    Cell [{row_idx},{col_idx}]: ({left},{top}) {cell_pil.width}x{cell_pil.height}")
    
    return segments


def find_separator_lines(gray: np.ndarray, axis: str, min_width: int,
                         threshold: int, verbose: bool = False) -> List[int]:
    """Find white separator lines along the specified axis.
    
    Args:
        gray: Grayscale image
        axis: 'horizontal' or 'vertical'
        min_width: Minimum width of separator in pixels
        threshold: Brightness threshold for white
        verbose: Print debug info
        
    Returns:
        List of separator positions (center of each separator)
    """
    if axis == 'horizontal':
        # Average brightness across each row
        profile = np.mean(gray, axis=1)
    else:
        # Average brightness across each column
        profile = np.mean(gray, axis=0)
    
    # Find runs of bright pixels
    is_bright = profile > threshold
    separators = []
    
    in_separator = False
    start = 0
    
    for i, bright in enumerate(is_bright):
        if bright and not in_separator:
            # Start of separator
            start = i
            in_separator = True
        elif not bright and in_separator:
            # End of separator
            width = i - start
            if width >= min_width:
                # Use the center of the separator
                center = (start + i) // 2
                separators.append(center)
            in_separator = False
    
    # Handle separator at the end
    if in_separator:
        width = len(is_bright) - start
        if width >= min_width:
            center = (start + len(is_bright)) // 2
            separators.append(center)
    
    return separators


def create_uniform_grid(img_bgr: np.ndarray, image_format: str,
                       rows: int, cols: int, verbose: bool = False) -> List[Dict[str, Any]]:
    """Create a uniform grid when separator detection fails.
    
    Args:
        img_bgr: Image in BGR format
        image_format: Image format
        rows: Number of rows
        cols: Number of columns
        verbose: Print debug info
        
    Returns:
        List of segment dictionaries
    """
    h, w = img_bgr.shape[:2]
    cell_h = h // rows
    cell_w = w // cols
    
    segments = []
    for row in range(rows):
        for col in range(cols):
            top = row * cell_h
            bottom = (row + 1) * cell_h if row < rows - 1 else h
            left = col * cell_w
            right = (col + 1) * cell_w if col < cols - 1 else w
            
            cell = img_bgr[top:bottom, left:right]
            
            # Crop white borders from the cell
            from .image_segmenter import crop_white_margins, crop_edges
            cell = crop_white_margins(cell, threshold=240)
            cell = crop_edges(cell, pixels=2)
            
            cell_rgb = cv2.cvtColor(cell, cv2.COLOR_BGR2RGB)
            cell_pil = Image.fromarray(cell_rgb)
            
            output = BytesIO()
            cell_pil.save(output, format=image_format.upper())
            cell_data = output.getvalue()
            
            # Use actual cropped dimensions
            segments.append({
                'data': cell_data,
                'format': image_format,
                'left': left,
                'top': top,
                'width': cell_pil.width,
                'height': cell_pil.height
            })
            
            if verbose:
                print(f"    Uniform cell [{row},{col}]: ({left},{top}) {cell_pil.width}x{cell_pil.height}")
    
    return segments
