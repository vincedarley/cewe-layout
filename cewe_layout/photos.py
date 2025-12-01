"""
Photo loading utilities for cewe-layout.

Shared functions for loading photos and extracting their dimensions.
Used by both GUI (for thumbnails and aspect ratio checks) and
collage_wrapper (for layout algorithm inputs).
"""

import cv2
from pathlib import Path
from typing import Tuple, Optional


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
