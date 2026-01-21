"""
Photo loading utilities for cewe-layout.

Shared functions for loading photos and extracting their dimensions.
Used by both GUI (for thumbnails and aspect ratio checks) and
collage_wrapper (for layout algorithm inputs).

The loading of photos and their metadata is often a bottleneck in the code.
Hence there is a fair amount of caching and parallel processing applied
here to speed things up.  This makes operations like viewing a new page,
dropping a dozen photos onto a page, much faster.
"""

import cv2
import traceback
from pathlib import Path
from typing import Tuple, Optional, List, Dict
from datetime import datetime
from PIL import Image, ImageOps
from PIL.ExifTags import TAGS
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

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

# Persistent thread pool for parallel image operations (avoids shutdown overhead)
_dimension_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="dimension_reader")

# Cache for IPTC keywords to avoid repeated exiftool calls
_iptc_keywords_cache = {}

# Cache for dimensions from EXIF (faster than decoding for HEIF/RAW formats)
_exif_dimensions_cache = {}

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
    except Exception:
        keywords = []
    
    # Cache and return
    _iptc_keywords_cache[cache_key] = keywords
    return keywords


def batch_get_iptc_keywords(img_paths: List[Path]) -> None:
    """
    Pre-populate IPTC keywords cache for multiple images in one exiftool call.
    
    This is much faster than individual calls when processing many images.
    Updates the global _iptc_keywords_cache.
    
    Args:
        img_paths: List of image file paths to process
    """
    if not img_paths:
        return
    
    # Filter to only paths not already in cache
    paths_to_fetch = [p for p in img_paths if p and p.exists() and str(p) not in _iptc_keywords_cache]
    
    if not paths_to_fetch:
        return  # All already cached
    
    try:
        import subprocess
        # Use -csv output format for easier parsing of multiple files
        # Format: SourceFile,Keywords
        result = subprocess.run(
            ['exiftool', '-Keywords', '-csv'] + [str(p) for p in paths_to_fetch],
            capture_output=True,
            text=True,
            timeout=10  # Longer timeout for batch operation
        )
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            # First line is header: SourceFile,Keywords
            # Skip it and process data lines
            for line in lines[1:]:
                parts = line.split(',', 1)  # Split only on first comma
                if len(parts) == 2:
                    source_file, keywords_str = parts
                    if keywords_str and keywords_str != '-':  # '-' means no keywords
                        keywords = [kw.strip() for kw in keywords_str.split(',')]
                    else:
                        keywords = []
                    # Cache using absolute path
                    cache_key = str(Path(source_file).resolve())
                    _iptc_keywords_cache[cache_key] = keywords
        
        # For any paths that weren't in the output, cache empty list
        for path in paths_to_fetch:
            cache_key = str(path)
            if cache_key not in _iptc_keywords_cache:
                _iptc_keywords_cache[cache_key] = []
                
    except Exception as e:
        logger.debug(f"Batch IPTC keywords extraction failed: {e}")
        # Cache empty lists to avoid retry
        for path in paths_to_fetch:
            cache_key = str(path)
            if cache_key not in _iptc_keywords_cache:
                _iptc_keywords_cache[cache_key] = []


def batch_get_exif_data(img_paths: List[Path]) -> None:
    """
    Pre-populate BOTH dimension and keywords caches from EXIF in one exiftool call.
    
    This is faster than calling batch_get_exif_dimensions and batch_get_iptc_keywords
    separately, as it invokes exiftool only once.
    
    Updates both _exif_dimensions_cache and _iptc_keywords_cache.
    
    Args:
        img_paths: List of image file paths to process
    """
    if not img_paths:
        return
    
    # Filter to only paths not already in BOTH caches
    paths_to_fetch = [p for p in img_paths 
                     if p and p.exists() 
                     and (str(p) not in _exif_dimensions_cache 
                          or str(p) not in _iptc_keywords_cache)]
    
    if not paths_to_fetch:
        return  # All already cached
    
    try:
        import subprocess
        # Get dimensions, orientation, AND keywords in one call
        # Orientation is needed to correctly swap width/height for rotated images
        result = subprocess.run(
            ['exiftool', '-ImageWidth', '-ImageHeight', '-Orientation#', '-Keywords', '-csv'] + [str(p) for p in paths_to_fetch],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            # First line is header: SourceFile,ImageWidth,ImageHeight,Orientation,Keywords
            # Skip it and process data lines
            for line in lines[1:]:
                # Split carefully - keywords may contain commas
                parts = line.split(',', 4)  # Split only first 4 commas
                if len(parts) >= 4:
                    source_file = parts[0]
                    width_str = parts[1]
                    height_str = parts[2]
                    orientation_str = parts[3]
                    keywords_str = parts[4] if len(parts) > 4 else '-'
                    
                    cache_key = str(Path(source_file).resolve())
                    
                    # Cache dimensions (with orientation applied)
                    if width_str != '-' and height_str != '-':
                        try:
                            width = int(width_str)
                            height = int(height_str)
                            
                            # Apply EXIF orientation to swap width/height if needed
                            # Orientation values 5, 6, 7, 8 require dimension swap
                            # (these represent 90° or 270° rotations)
                            orientation = 1  # Default: no rotation
                            if orientation_str != '-':
                                try:
                                    orientation = int(orientation_str)
                                except ValueError:
                                    pass
                            
                            # Swap dimensions for rotated images
                            if orientation in (5, 6, 7, 8):
                                width, height = height, width
                            
                            if width > 0 and height > 0:
                                _exif_dimensions_cache[cache_key] = (width, height)
                            else:
                                _exif_dimensions_cache[cache_key] = None
                        except ValueError:
                            _exif_dimensions_cache[cache_key] = None
                    else:
                        _exif_dimensions_cache[cache_key] = None
                    
                    # Cache keywords
                    if keywords_str and keywords_str != '-':
                        keywords = [kw.strip() for kw in keywords_str.split(',')]
                        _iptc_keywords_cache[cache_key] = keywords
                    else:
                        _iptc_keywords_cache[cache_key] = []
        
        # For any paths that weren't in the output, cache None/empty
        for path in paths_to_fetch:
            cache_key = str(path)
            if cache_key not in _exif_dimensions_cache:
                _exif_dimensions_cache[cache_key] = None
            if cache_key not in _iptc_keywords_cache:
                _iptc_keywords_cache[cache_key] = []
                
    except Exception as e:
        logger.debug(f"Batch EXIF data extraction failed: {e}")
        # Cache None/empty to avoid retry
        for path in paths_to_fetch:
            cache_key = str(path)
            if cache_key not in _exif_dimensions_cache:
                _exif_dimensions_cache[cache_key] = None
            if cache_key not in _iptc_keywords_cache:
                _iptc_keywords_cache[cache_key] = []


def batch_get_exif_dimensions(img_paths: List[Path]) -> None:
    """
    Pre-populate dimension cache from EXIF metadata using exiftool.
    
    This is MUCH faster than decoding images, especially for HEIF/HEIC files
    where PIL decoding can take 100ms+ per image. exiftool reads dimensions
    from EXIF in ~1ms per image.
    
    Updates the global _exif_dimensions_cache with (width, height) tuples.
    
    Note: EXIF dimensions may not always match actual image dimensions if the
    file has been edited. Callers should validate dimensions when actually
    loading the image for display.
    
    Args:
        img_paths: List of image file paths to process
    """
    if not img_paths:
        return
    
    # Filter to only paths not already in cache
    paths_to_fetch = [p for p in img_paths if p and p.exists() and str(p) not in _exif_dimensions_cache]
    
    if not paths_to_fetch:
        return  # All already cached
    
    try:
        import subprocess
        # Use -csv output format: SourceFile,ImageWidth,ImageHeight
        result = subprocess.run(
            ['exiftool', '-ImageWidth', '-ImageHeight', '-csv'] + [str(p) for p in paths_to_fetch],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and result.stdout.strip():
            lines = result.stdout.strip().split('\n')
            # First line is header: SourceFile,ImageWidth,ImageHeight
            # Skip it and process data lines
            for line in lines[1:]:
                parts = line.split(',')
                if len(parts) >= 3:
                    source_file = parts[0]
                    width_str = parts[1]
                    height_str = parts[2]
                    
                    # Parse dimensions (skip if '-' which means missing)
                    if width_str != '-' and height_str != '-':
                        try:
                            width = int(width_str)
                            height = int(height_str)
                            if width > 0 and height > 0:
                                cache_key = str(Path(source_file).resolve())
                                _exif_dimensions_cache[cache_key] = (width, height)
                        except ValueError:
                            pass  # Invalid dimension data, skip
        
        # For any paths that weren't in the output, cache None
        for path in paths_to_fetch:
            cache_key = str(path)
            if cache_key not in _exif_dimensions_cache:
                _exif_dimensions_cache[cache_key] = None
                
    except Exception as e:
        logger.debug(f"Batch EXIF dimensions extraction failed: {e}")
        # Cache None to avoid retry
        for path in paths_to_fetch:
            cache_key = str(path)
            if cache_key not in _exif_dimensions_cache:
                _exif_dimensions_cache[cache_key] = None
        
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
    Extract creation date from photo EXIF data or filesystem.
    
    Tries multiple sources in order:
    1. EXIF DateTimeOriginal (when photo was taken)
    2. EXIF CreateDate
    3. EXIF DateTime (when file was modified)
    4. Filesystem creation date (fallback)
    
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
        
        if date_str:
            # Parse date string (format: "YYYY:MM:DD HH:MM:SS")
            try:
                return datetime.strptime(date_str, '%Y:%m:%d %H:%M:%S')
            except ValueError:
                # Try alternate format without time
                try:
                    return datetime.strptime(date_str, '%Y:%m:%d')
                except ValueError:
                    pass  # Fall through to filesystem date
    
    except Exception as e:
        logger.debug(f"exiftool not available or failed for {img_path}: {e}")
    
    # Fallback: use filesystem creation time
    try:
        stat_info = img_path.stat()
        # On macOS, st_birthtime is the creation time
        # On other platforms, may fall back to st_mtime
        creation_time = getattr(stat_info, 'st_birthtime', None) or stat_info.st_mtime
        return datetime.fromtimestamp(creation_time)
    except Exception as e:
        logger.warning(f"Could not get any date for {img_path}: {e}")
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
    
    # Fallback: check relative to mcf base
    candidate = mcf_base_folder / safefn
    if candidate.exists():
        return candidate
    
    return None


def get_image_dimensions(img_path: Path) -> Optional[Tuple[int, int]]:
    """
    Load an image and extract its dimensions.
    
    Checks EXIF cache first (fast), then tries OpenCV (faster), 
    falls back to PIL for formats like HEIC.
    
    Args:
        img_path: Path to the image file
    
    Returns:
        Tuple (width, height) in pixels, or None if load fails
    """
    if not img_path or not img_path.exists():
        return None
    
    # Check EXIF cache first (avoids decoding for HEIF files)
    cache_key = str(Path(img_path).resolve())
    if cache_key in _exif_dimensions_cache:
        cached_dims = _exif_dimensions_cache[cache_key]
        if cached_dims:  # None means EXIF had no dimensions
            return cached_dims
    
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


def batch_get_image_dimensions(img_paths: List[Path], max_workers: int = 8) -> Dict[Path, Optional[Tuple[int, int]]]:
    """
    Read image dimensions for multiple images in parallel.
    
    Uses a persistent ThreadPoolExecutor to avoid thread creation overhead.
    
    Args:
        img_paths: List of Path objects to read
        max_workers: Maximum number of parallel threads (ignored - module executor used)
    
    Returns:
        Dict mapping Path -> (width, height) or None if read failed
    """
    results = {}
    
    # Filter out invalid/non-existent paths first
    valid_paths = [p for p in img_paths if p and p.exists()]
    
    if not valid_paths:
        return {p: None for p in img_paths}
    
    def read_one(img_path: Path) -> Tuple[Path, Optional[Tuple[int, int]]]:
        """Read dimensions for one image and return (path, dimensions)."""
        dims = get_image_dimensions(img_path)
        return (img_path, dims)
    
    # Use persistent module-level executor (no context manager - no shutdown overhead)
    # Submit all tasks
    future_to_path = {_dimension_executor.submit(read_one, path): path for path in valid_paths}
    
    # Collect results as they complete
    for future in as_completed(future_to_path):
        try:
            img_path, dims = future.result()
            results[img_path] = dims
        except Exception as e:
            path = future_to_path[future]
            logger.error(f"Failed to read dimensions for {path}: {e}")
            results[path] = None
    
    # Add None results for invalid paths
    for p in img_paths:
        if p not in results:
            results[p] = None
    
    return results


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

