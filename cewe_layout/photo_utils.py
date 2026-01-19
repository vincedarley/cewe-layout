"""
Photo loading utilities for cewe-layout.

Shared functions for loading photos and extracting their dimensions.
Used by both GUI (for thumbnails and aspect ratio checks) and
collage_wrapper (for layout algorithm inputs).
"""

import cv2
import traceback
from pathlib import Path
from typing import Tuple, Optional, List
from datetime import datetime
from PIL import Image, ImageOps
from PIL.ExifTags import TAGS
import logging

logger = logging.getLogger(__name__)

# Register HEIF/HEIC support if available
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    logger.info("HEIF/HEIC support enabled via pillow-heif")
except ImportError:
    logger.info("pillow-heif not available - HEIC files will not be supported")

# Module-level flags to track first-time failures
_image_load_failures = set()  # Track which files have been logged


# Cache for IPTC keywords to avoid repeated exiftool calls
_iptc_keywords_cache = {}

def get_iptc_keywords(img_path: Path) -> List[str]:
    """
    Extract IPTC keywords from image metadata using exiftool.
    
    Args:
        img_path: Path to the image file
    
    Returns:
        List of keyword strings, or empty list if none found
    """
    if not img_path or not img_path.exists():
        return []
    
    # Check cache first
    cache_key = str(img_path)
    if cache_key in _iptc_keywords_cache:
        return _iptc_keywords_cache[cache_key]
    
    try:
        import subprocess
        result = subprocess.run(
            ['exiftool', '-Keywords', '-s3', str(img_path)],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0 and result.stdout.strip():
            # Keywords are comma-separated in exiftool output
            keywords = [kw.strip() for kw in result.stdout.strip().split(',')]
        else:
            keywords = []
        
        # Cache the result
        _iptc_keywords_cache[cache_key] = keywords
        return keywords
    except Exception as e:
        logger.warning(f"exiftool not available or failed: {e}")
        # Cache empty result to avoid repeated failures
        _iptc_keywords_cache[cache_key] = []
        return []


def get_photo_preferred_size(img_path: Path) -> float:
    """
    Get preferred size multiplier for a photo based on IPTC keywords.
    
    Reads IPTC keywords and maps star ratings to size preferences:
    - "5 star" keyword -> 5.0 (high importance)
    - "4 star" keyword -> 3.0 (medium importance)  
    - Other/no keywords -> 1.0 (normal size)
    
    Args:
        img_path: Path to the image file
    
    Returns:
        Size multiplier: 1.0 (normal), 3.0 (medium importance), or 5.0 (high importance)
    """
    keywords = get_iptc_keywords(img_path)
    
    # Check for star rating keywords (case-insensitive)
    keywords_lower = [kw.lower() for kw in keywords]
    
    if '5 star' in keywords_lower or '5star' in keywords_lower:
        return 5.0
    elif '4 star' in keywords_lower or '4star' in keywords_lower:
        return 3.0
    
    # Default size for all other photos
    return 1.0


def get_photo_star_rating(img_path: Path) -> int:
    """
    Get star rating for a photo based on IPTC keywords.
    
    Args:
        img_path: Path to the image file
    
    Returns:
        Star rating (0-5), or 0 if no rating found
    """
    keywords = get_iptc_keywords(img_path)
    
    # Check for star rating keywords (case-insensitive)
    keywords_lower = [kw.lower() for kw in keywords]
    
    if '5 star' in keywords_lower or '5star' in keywords_lower:
        return 5
    elif '4 star' in keywords_lower or '4star' in keywords_lower:
        return 4
    elif '3 star' in keywords_lower or '3star' in keywords_lower:
        return 3
    elif '2 star' in keywords_lower or '2star' in keywords_lower:
        return 2
    elif '1 star' in keywords_lower or '1star' in keywords_lower:
        return 1
    
    return 0


def get_photo_creation_date(img_path: Path) -> Optional[datetime]:
    """
    Extract creation date from photo EXIF data.
    
    Tries multiple EXIF fields in order:
    1. DateTimeOriginal (when photo was taken)
    2. CreateDate
    3. DateTime (when file was modified)
    
    Args:
        img_path: Path to the image file
    
    Returns:
        datetime object, or None if no date found
    """
    if not img_path or not img_path.exists():
        return None
    
    try:
        import subprocess
        # Try DateTimeOriginal first (most reliable for photos)
        result = subprocess.run(
            ['exiftool', '-DateTimeOriginal', '-s3', str(img_path)],
            capture_output=True,
            text=True,
            timeout=2
        )
        
        date_str = result.stdout.strip()

        # If not found, try CreateDate
        if not date_str:
            result = subprocess.run(
                ['exiftool', '-CreateDate', '-s3', str(img_path)],
                capture_output=True,
                text=True,
                timeout=2
            )
            date_str = result.stdout.strip()
        
        # If still not found, try DateTime
        if not date_str:
            result = subprocess.run(
                ['exiftool', '-DateTime', '-s3', str(img_path)],
                capture_output=True,
                text=True,
                timeout=2
            )
            date_str = result.stdout.strip()
        
        if not date_str:
            return None
        
        # Parse date string (format: "YYYY:MM:DD HH:MM:SS")
        try:
            return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
        except ValueError:
            # Try alternate format without time
            try:
                return datetime.strptime(date_str, '%Y:%m:%d')
            except ValueError:
                return None
    
    except Exception as e:
        logger.warning(f"exiftool not available or failed: {e}")
        return None


def resolve_photo_path(filename: str, mcf_base_folder: Path, image_folder_attr: str = '') -> Optional[Path]:
    """
    Resolve a photo filename to its full path.
    
    Args:
        filename: Photo filename from MCF (may include 'safecontainer:/' prefix)
        mcf_base_folder: Base folder containing the MCF file
        image_folder_attr: Optional imagedir attribute from MCF root
    
    Returns:
        Full path to the image file, or None if not found
    """
    if not filename:
        return None
    
    # Strip safecontainer prefix and leading slashes
    safefn = filename.replace('safecontainer:/', '').lstrip('/')
    
    # Try with imagedir attribute first
    if image_folder_attr:
        candidate = mcf_base_folder / image_folder_attr / safefn
        if candidate.exists():
            return candidate
    
    # Fallback: check relative to mcf_io base
    candidate = mcf_base_folder / safefn
    if candidate.exists():
        return candidate
    
    return None


def get_image_dimensions(img_path: Path) -> Optional[Tuple[int, int]]:
    """
    Load an image and extract its dimensions.
    
    Tries OpenCV first (faster), falls back to PIL for formats like HEIC.
    
    Args:
        img_path: Path to the image file
    
    Returns:
        Tuple (width, height) in pixels, or None if load fails
    """
    if not img_path or not img_path.exists():
        return None
    
    # Try OpenCV first (faster for most formats)
    try:
        arr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if arr is not None:
            # OpenCV returns (height, width, channels)
            img_height, img_width = arr.shape[:2]
            
            if img_height > 0 and img_width > 0:
                return (img_width, img_height)
    except Exception:
        pass  # Fall through to PIL
    
    # Fall back to PIL for formats OpenCV doesn't support (e.g., HEIC)
    try:
        with Image.open(img_path) as im:
            # Auto-orient based on EXIF
            im = ImageOps.exif_transpose(im)
            img_width, img_height = im.size
            
            if img_height > 0 and img_width > 0:
                return (img_width, img_height)
            else:
                if str(img_path) not in _image_load_failures:
                    logger.warning(f"Image has invalid dimensions ({img_width}x{img_height}): {img_path}")
                    _image_load_failures.add(str(img_path))
                return None
    
    except Exception as e:
        # Log first-time failure for this specific file
        if str(img_path) not in _image_load_failures:
            logger.warning(f"Failed to read image dimensions for {img_path}: {e}")
            _image_load_failures.add(str(img_path))
        return None


def get_image_aspect_ratio(img_path: Path) -> Optional[float]:
    """
    Load an image and compute its aspect ratio.
    
    Args:
        img_path: Path to the image file
    
    Returns:
        Aspect ratio (width / height), or None if load fails
    """
    dims = get_image_dimensions(img_path)
    if dims is None:
        return None
    
    width, height = dims
    if height > 0:
        return width / height
    
    return None


# Image load tracking
_image_load_count = 0
_image_load_times = {}

def get_load_stats():
    """Get image loading statistics."""
    total_loads = _image_load_count
    if not _image_load_times:
        return f"No images loaded yet"
    
    all_times = []
    for times in _image_load_times.values():
        all_times.extend(times)
    
    if not all_times:
        return f"Total loads: {total_loads}, but no timing data"
    
    avg_time = sum(all_times) / len(all_times)
    max_time = max(all_times)
    min_time = min(all_times)
    
    return (f"Image loads from disk: {total_loads} | "
            f"Avg: {avg_time:.1f}ms | Min: {min_time:.1f}ms | Max: {max_time:.1f}ms")

def load_thumbnail(path: Path, width: int, height: int, verbose: bool = True) -> Optional[Image.Image]:
    """
    Load an image and create a thumbnail of specified size.
    
    The image is loaded with EXIF orientation applied, converted to RGB,
    and thumbnailed to fit within the specified dimensions. The thumbnail
    is centered on a light gray background of exactly the requested size.
    
    Args:
        path: Path to the image file
        width: Target thumbnail width in pixels
        height: Target thumbnail height in pixels
        verbose: If True, print diagnostic messages on failures
    
    Returns:
        PIL Image of size (width, height), or None if load fails
    """
    global _image_load_count, _image_load_times
    import time
    from pathlib import Path as PathlibPath
    
    if width <= 0 or height <= 0:
        return None
    
    if not path or not Path(path).exists():
        return None
    
    # Track this load
    _image_load_count += 1
    path_str = str(PathlibPath(path).name)  # Just filename for readability
    load_start = time.time()
    
    try:
        im = Image.open(path)
        print(f"  [DISK LOAD #{_image_load_count}] {path_str} ({width}x{height})")
        # Auto-rotate based on EXIF orientation (support older Pillow)
        exif_transpose = getattr(Image, 'exif_transpose', None) or getattr(ImageOps, 'exif_transpose', None)
        if exif_transpose:
            try:
                im = exif_transpose(im)
            except Exception:
                # If transpose fails, continue without raising noisy traceback
                pass
        im = im.convert('RGB')
        im.thumbnail((width, height), Image.LANCZOS)
        # Create a background image exactly the size of slot and paste centered
        bg = Image.new('RGB', (width, height), '#cccccc')  # Light gray background
        x = max(0, (width - im.width) // 2)
        y = max(0, (height - im.height) // 2)
        bg.paste(im, (x, y))
        
        # Track load time
        load_time = (time.time() - load_start) * 1000
        _image_load_times[path_str] = _image_load_times.get(path_str, []) + [load_time]
        if load_time > 50:
            print(f"    [SLOW LOAD] {path_str}: {load_time:.1f}ms")
        
        return bg
    except Exception as e:
        # Log first-time failures for specific paths
        if str(path) not in _image_load_failures:
            logger.warning(f"Failed to load thumbnail for {path}: {e}")
            _image_load_failures.add(str(path))
            if verbose:
                traceback.print_exc()
        return None

