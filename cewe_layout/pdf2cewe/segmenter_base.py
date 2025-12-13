"""
Base class for image segmentation algorithms.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class ImageSegmenter(ABC):
    """Abstract base class for image segmentation algorithms."""
    
    @abstractmethod
    def segment_for_count(self, image_data: bytes, image_format: str,
                         target_count: int, verbose: bool = False) -> Optional[List[Dict[str, Any]]]:
        """Segment image to achieve target photo count.
        
        Args:
            image_data: Image bytes
            image_format: Image format (jpeg, png, etc.)
            target_count: Desired number of photos
            verbose: Print debug info
            
        Returns:
            List of segment dicts with 'data', 'format', 'left', 'top', 'width', 'height'
            or None if target count cannot be achieved
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return human-readable name of this segmenter."""
        pass


# Registry of available segmenters
_SEGMENTERS: Dict[str, ImageSegmenter] = {}


def register_segmenter(name: str, segmenter: ImageSegmenter) -> None:
    """Register a segmenter implementation.
    
    Args:
        name: Name to register (e.g., 'morphological', 'grid')
        segmenter: Segmenter instance
    """
    _SEGMENTERS[name] = segmenter


def get_segmenter(name: str) -> Optional[ImageSegmenter]:
    """Get a registered segmenter by name.
    
    Args:
        name: Segmenter name
        
    Returns:
        Segmenter instance or None if not found
    """
    return _SEGMENTERS.get(name)


def list_segmenters() -> List[str]:
    """List all registered segmenter names."""
    return list(_SEGMENTERS.keys())
