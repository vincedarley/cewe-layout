"""
Segment composite images into individual photos.
Uses File_Parser's adaptive thresholding approach for robust photo detection.
"""

import cv2
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from io import BytesIO
from PIL import Image


def segment_composite_image(image_data: bytes, image_format: str, 
                            min_area: int = 50000,
                            kernel_size: int = 5,
                            iterations: int = 2,
                            verbose: bool = False) -> List[Dict[str, Any]]:
    """Segment a composite image into individual photos using adaptive thresholding.
    
    Based on File_Parser's approach for extracting photos from scanned albums.
    
    Args:
        image_data: Image bytes
        image_format: Image format (jpeg, png, etc.)
        min_area: Minimum contour area in pixels (default 50000)
        kernel_size: Size of morphological kernel (default 5)
        iterations: Number of dilation/erosion iterations (default 2)
        verbose: Print debug info
        
    Returns:
        List of dictionaries with keys:
            - 'data': Image bytes for the cropped region
            - 'format': Image format
            - 'left': X position relative to original image
            - 'top': Y position relative to original image
            - 'width': Width of cropped region
            - 'height': Height of cropped region
    """
    # Load image with PIL first to handle various formats
    pil_image = Image.open(BytesIO(image_data))
    
    # Convert to RGB if needed
    if pil_image.mode != 'RGB':
        pil_image = pil_image.convert('RGB')
    
    # Convert to numpy array for OpenCV
    img_array = np.array(pil_image)
    
    # Convert RGB to BGR for OpenCV
    img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    
    if verbose:
        print(f"    Segmenting image: {img_bgr.shape[1]}x{img_bgr.shape[0]}")
    
    # Add white padding to help detect edge photos
    padded_image = add_padding(img_bgr)
    pad_offset = 50  # Padding size
    
    # Convert to grayscale
    gray = cv2.cvtColor(padded_image, cv2.COLOR_BGR2GRAY)
    
    # Apply Gaussian Blur to remove noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Apply adaptive thresholding with larger block size to detect photo boundaries
    # Block size must be odd and larger than 1
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 10
    )
    
    # Invert the thresholded image
    thresh = cv2.bitwise_not(thresh)
    
    # Use dilation and erosion to close gaps in edges
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    thresh = cv2.dilate(thresh, kernel, iterations=iterations)
    thresh = cv2.erode(thresh, kernel, iterations=iterations)
    
    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if verbose:
        print(f"    Found {len(contours)} contours")
    
    # Extract photo regions
    result = []
    photo_count = 0
    
    for contour in contours:
        area = cv2.contourArea(contour)
        
        # Filter out small contours
        if area <= min_area:
            continue
        
        # Approximate contour to polygon
        epsilon = 0.01 * cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, epsilon, True)
        
        # Extract the photo using perspective transform
        if len(approx) == 4:
            # Rectangular photo
            photo = four_point_transform(padded_image, approx.reshape(4, 2))
        else:
            # Non-rectangular (skewed) photo - use minimum area rectangle
            rect = cv2.minAreaRect(contour)
            box = cv2.boxPoints(rect)
            box = np.int32(box)
            photo = four_point_transform(padded_image, box)
        
        # Skip if transformation failed
        if photo is None or photo.size == 0:
            continue
        
        # Remove white margins and crop edges
        photo = crop_white_margins(photo)
        photo = crop_edges(photo, 5)
        
        # Get bounding box in original image coordinates (remove padding offset)
        x, y, w, h = cv2.boundingRect(contour)
        x = max(0, x - pad_offset)
        y = max(0, y - pad_offset)
        
        # Adjust width/height to fit within original image bounds
        w = min(w, img_bgr.shape[1] - x)
        h = min(h, img_bgr.shape[0] - y)
        
        # Convert cropped photo back to RGB
        photo_rgb = cv2.cvtColor(photo, cv2.COLOR_BGR2RGB)
        
        # Convert to PIL Image and save to bytes
        photo_pil = Image.fromarray(photo_rgb)
        buffer = BytesIO()
        photo_pil.save(buffer, format='JPEG', quality=95)
        photo_bytes = buffer.getvalue()
        
        result.append({
            'data': photo_bytes,
            'format': 'jpeg',
            'left': x,
            'top': y,
            'width': w,
            'height': h,
        })
        
        photo_count += 1
        if verbose:
            print(f"    Extracted photo {photo_count}: {w}x{h} at ({x}, {y}), area={area:.0f}")
    
    if not result:
        if verbose:
            print(f"    No photos found, returning original image")
        # Return the whole image if no regions detected
        return [{
            'data': image_data,
            'format': image_format,
            'left': 0,
            'top': 0,
            'width': img_bgr.shape[1],
            'height': img_bgr.shape[0],
        }]
    
    return result


def add_padding(image: np.ndarray, padding: int = 50) -> np.ndarray:
    """Add white padding around the image to help detect photos at edges.
    
    Args:
        image: OpenCV image (BGR)
        padding: Padding size in pixels
        
    Returns:
        Padded image
    """
    return cv2.copyMakeBorder(
        image,
        padding, padding, padding, padding,
        cv2.BORDER_CONSTANT,
        value=[255, 255, 255]
    )


def four_point_transform(image: np.ndarray, pts: np.ndarray) -> Optional[np.ndarray]:
    """Apply perspective transform to extract a rectangular region.
    
    Args:
        image: OpenCV image (BGR)
        pts: Four corner points as numpy array of shape (4, 2)
        
    Returns:
        Transformed image, or None if transformation fails
    """
    # Order points: top-left, top-right, bottom-right, bottom-left
    rect = order_points(pts)
    (tl, tr, br, bl) = rect
    
    # Compute width of the new image
    widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
    widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
    maxWidth = max(int(widthA), int(widthB))
    
    # Compute height of the new image
    heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
    heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
    maxHeight = max(int(heightA), int(heightB))
    
    # Check for valid dimensions
    if maxWidth < 1 or maxHeight < 1:
        return None
    
    # Construct destination points
    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]
    ], dtype="float32")
    
    # Compute perspective transform matrix and apply it
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
    
    return warped


def order_points(pts: np.ndarray) -> np.ndarray:
    """Order points in the order: top-left, top-right, bottom-right, bottom-left.
    
    Args:
        pts: Array of 4 points
        
    Returns:
        Ordered points as float32 array
    """
    rect = np.zeros((4, 2), dtype="float32")
    
    # Sum: top-left will have smallest sum, bottom-right will have largest sum
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    
    # Diff: top-right will have smallest diff, bottom-left will have largest diff
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    
    return rect


def crop_white_margins(image: np.ndarray, threshold: int = 250) -> np.ndarray:
    """Remove white margins from an image.
    
    Args:
        image: OpenCV image (BGR)
        threshold: Pixel value threshold for white (default 250)
        
    Returns:
        Cropped image
    """
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    
    # Find non-white pixels
    coords = cv2.findNonZero((gray < threshold).astype(np.uint8))
    
    if coords is None:
        # Image is all white, return as-is
        return image
    
    # Get bounding box of non-white pixels
    x, y, w, h = cv2.boundingRect(coords)
    
    # Crop to bounding box
    return image[y:y+h, x:x+w]


def crop_edges(image: np.ndarray, pixels: int) -> np.ndarray:
    """Crop specified number of pixels from all edges.
    
    Args:
        image: OpenCV image (BGR)
        pixels: Number of pixels to crop from each edge
        
    Returns:
        Cropped image
    """
    h, w = image.shape[:2]
    
    # Don't crop if image is too small
    if h <= 2 * pixels or w <= 2 * pixels:
        return image
    
    return image[pixels:h-pixels, pixels:w-pixels]


def should_segment_image(image_width: int, image_height: int, 
                         page_width: int, page_height: int,
                         threshold: float = 0.8) -> bool:
    """Determine if an image should be segmented.
    
    Large images that cover most of the page are likely composite images
    that should be segmented.
    
    Args:
        image_width: Image width in points
        image_height: Image height in points
        page_width: Page width in points
        page_height: Page height in points
        threshold: Minimum coverage ratio to trigger segmentation (default 80%)
        
    Returns:
        True if image should be segmented
    """
    # Calculate coverage ratio
    image_area = image_width * image_height
    page_area = page_width * page_height
    coverage = image_area / page_area if page_area > 0 else 0
    
    return coverage >= threshold


def find_segmentation_for_count(image_data: bytes, image_format: str,
                                  target_count: int,
                                  min_area: int = 50000,
                                  max_attempts: int = 20,
                                  verbose: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Find segmentation parameters that produce the target number of photos.
    
    Tries different combinations of kernel_size and iterations to find
    a segmentation that produces exactly the target number of photos.
    
    Args:
        image_data: Image bytes
        image_format: Image format (jpeg, png, etc.)
        target_count: Desired number of photos
        min_area: Minimum contour area in pixels
        max_attempts: Maximum number of parameter combinations to try
        verbose: Print debug info
        
    Returns:
        List of segmented photos if successful, None if target count not achieved
    """
    # Define parameter search space
    # Smaller kernel and fewer iterations = more photos (more sensitive)
    # Larger kernel and more iterations = fewer photos (less sensitive)
    # Focus on kernel sizes 1-7 for better sensitivity
    param_combinations = [
        # (kernel_size, iterations)
        # Very sensitive (many photos)
        (1, 0),   # Extremely sensitive
        (1, 1),
        (1, 2),
        (1, 3),
        (3, 0),
        (3, 1),
        (3, 2),
        (3, 3),
        (3, 4),
        (5, 0),
        (5, 1),
        (5, 2),   # Default
        (5, 3),
        (5, 4),
        (5, 5),
        (7, 0),
        (7, 1),
        (7, 2),
        (7, 3),
        (7, 4),
        (7, 5),
    ]
    
    best_result = None
    best_diff = float('inf')
    
    for kernel_size, iterations in param_combinations[:max_attempts]:
        if verbose:
            print(f"  Trying kernel_size={kernel_size}, iterations={iterations}")
        
        result = segment_composite_image(
            image_data, image_format,
            min_area=min_area,
            kernel_size=kernel_size,
            iterations=iterations,
            verbose=False
        )
        
        photo_count = len(result)
        diff = abs(photo_count - target_count)
        
        if verbose:
            print(f"    Got {photo_count} photos (target={target_count}, diff={diff})")
        
        # Update best result
        if diff < best_diff:
            best_diff = diff
            best_result = result
        
        # If we found exact match, return immediately
        if photo_count == target_count:
            if verbose:
                print(f"  ✅ Found exact match with kernel_size={kernel_size}, iterations={iterations}")
            return result
    
    # Return best result if we got reasonably close (within 2 photos)
    if best_diff <= 2 and best_result:
        if verbose:
            print(f"  ⚠️ Returning closest match: {len(best_result)} photos (target={target_count}, diff={best_diff})")
        return best_result
    
    if verbose:
        print(f"  ❌ Could not achieve target count {target_count} (best was {len(best_result) if best_result else 0}, diff={best_diff})")
    
    return None
