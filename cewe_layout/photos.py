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
from PIL import Image, ImageOps
from PIL.ExifTags import TAGS


def get_iptc_keywords(img_path: Path) -> List[str]:
    """
    Extract IPTC keywords from image metadata.
    
    Args:
        img_path: Path to the image file
    
    Returns:
        List of keyword strings, or empty list if none found
    """
    if not img_path or not img_path.exists():
        return []
    
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        
        img = Image.open(img_path)
        
        # Try to get IPTC data from APP13 segment
        # IPTC keywords are stored in tag 25 (0x19) of the IPTC dataset
        if hasattr(img, 'app'):
            # Check for IPTC in APP13
            app13 = img.app.get('APP13')
            if app13:
                # Parse IPTC data (basic implementation)
                # IPTC keywords field is 2:25
                keywords = []
                # This is a simplified parser - full IPTC parsing is complex
                # For now, try the simpler approach via getexif()
        
        # Try via EXIF data which may contain XMP or IPTC
        exif = img.getexif()
        if exif:
            # IPTC keywords might be in tag 0x9c9e (XPKeywords) or embedded in other tags
            # Try common tags that might contain keywords
            for tag_id, value in exif.items():
                tag_name = TAGS.get(tag_id, tag_id)
                if isinstance(tag_name, str) and 'keyword' in tag_name.lower():
                    if isinstance(value, str):
                        return [kw.strip() for kw in value.split(';') if kw.strip()]
                    elif isinstance(value, bytes):
                        try:
                            decoded = value.decode('utf-16le').rstrip('\x00')
                            return [kw.strip() for kw in decoded.split(';') if kw.strip()]
                        except:
                            pass
        
        # Try using exiftool via subprocess if available (more reliable for IPTC)
        try:
            import subprocess
            result = subprocess.run(
                ['exiftool', '-Keywords', '-s', '-s', '-s', str(img_path)],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                # Keywords are comma-separated in exiftool output
                keywords = [kw.strip() for kw in result.stdout.strip().split(',')]
                return keywords
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            # exiftool not available or failed, continue with other methods
            pass
        
        return []
    
    except Exception as e:
        # Silently fail - keywords are optional
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
    
    Args:
        img_path: Path to the image file
    
    Returns:
        Tuple (width, height) in pixels, or None if load fails
    """
    if not img_path or not img_path.exists():
        return None
    
    try:
        arr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if arr is None:
            return None
        
        # OpenCV returns (height, width, channels)
        img_height, img_width = arr.shape[:2]
        
        if img_height <= 0 or img_width <= 0:
            return None
        
        return (img_width, img_height)
    
    except Exception:
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


def load_thumbnail(path: Path, width: int, height: int, verbose: bool = True) -> Optional[Image.Image]:
    """
    Load an image and create a thumbnail of specified size.
    
    The image is loaded with EXIF orientation applied, converted to RGB,
    and thumbnailed to fit within the specified dimensions. The thumbnail
    is centered on a white background of exactly the requested size.
    
    Args:
        path: Path to the image file
        width: Target thumbnail width in pixels
        height: Target thumbnail height in pixels
        verbose: If True, print diagnostic messages on failures
    
    Returns:
        PIL Image of size (width, height), or None if load fails
    """
    if width <= 0 or height <= 0:
        return None
    
    if not path or not Path(path).exists():
        return None
    
    # Try PIL first
    try:
        im = Image.open(path)
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
        bg = Image.new('RGB', (width, height), 'white')
        x = max(0, (width - im.width) // 2)
        y = max(0, (height - im.height) // 2)
        bg.paste(im, (x, y))
        return bg
    except Exception as e:
        # Detailed diagnostic for failures: print exception and try OpenCV fallback
        if verbose:
            print(f"[thumb] PIL failed to open {path}: {e}")
            traceback.print_exc()
        
        # Try OpenCV fallback
        try:
            arr = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if arr is None:
                if verbose:
                    print(f"[thumb] OpenCV failed to read {path} (imread returned None)")
                return None
            arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
            im2 = Image.fromarray(arr)
            im2.thumbnail((width, height), Image.LANCZOS)
            bg = Image.new('RGB', (width, height), 'white')
            x = max(0, (width - im2.width) // 2)
            y = max(0, (height - im2.height) // 2)
            bg.paste(im2, (x, y))
            return bg
        except Exception as e2:
            if verbose:
                print(f"[thumb] OpenCV fallback also failed for {path}: {e2}")
                traceback.print_exc()
            return None
