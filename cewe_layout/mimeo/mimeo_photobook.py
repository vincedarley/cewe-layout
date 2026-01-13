"""Mimeo photobook implementation of the abstract Photobook interface.

This module provides a Photobook implementation that wraps Mimeo Photos data.
All coordinates are in Mimeo units (~2390×1067 units/page).
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

from ..book.photobook import Photobook, PhotobookPage, PageType

logger = logging.getLogger(__name__)


class MimeoPhotobookPage(PhotobookPage):
    """Mimeo photobook page with coordinates in Mimeo units."""
    
    def __init__(self, page_data: Dict[str, Any], page_type: PageType, page_number, index: int):
        """Initialize Mimeo photobook page.
        
        Args:
            page_data: Page data dict with 'width', 'height', 'images', 'text_blocks'
            page_type: Type of this page
            page_number: Page number (str for covers, int for content)
            index: Page index in book (0-based)
        """
        self._page_data = page_data
        self._page_type = page_type
        self._page_number = page_number
        self._index = index
    
    def get_width(self) -> float:
        """Get page width in Mimeo units."""
        return self._page_data.get('width', 0.0)
    
    def get_height(self) -> float:
        """Get page height in Mimeo units."""
        return self._page_data.get('height', 0.0)
    
    def get_images(self) -> List[Dict[str, Any]]:
        """Get list of image dictionaries.
        
        Returns images with 'area_left', 'area_top', 'area_width', 'area_height' in Mimeo units.
        """
        return self._page_data.get('photos', [])
    
    def get_text_blocks(self) -> List[Dict[str, Any]]:
        """Get list of text block dictionaries.
        
        Returns text blocks with 'area_left', 'area_top', 'area_width', 'area_height' in Mimeo units.
        """
        return self._page_data.get('texts', [])
    
    def get_page_type(self) -> PageType:
        """Get the type of this page."""
        return self._page_type
    
    def get_page_number(self):
        """Get page number/identifier."""
        return self._page_number
    
    def get_page_info(self) -> Dict[str, Any]:
        """Get page info as dictionary for backward compatibility.
        
        Returns dict matching the format expected by gui.py.
        """
        return {
            'photos': self.get_images(),
            'texts': self.get_text_blocks(),
            'page_width': self.get_width(),
            'page_height': self.get_height(),
            'origin_left': 0.0,  # Mimeo uses left page layout
            'background_id': self._page_data.get('background_id'),
            'is_cover': self._page_type in (PageType.FRONT_COVER, PageType.BACK_COVER)
        }
    
    def get_raw_data(self) -> Dict[str, Any]:
        """Get the underlying page data dict (for compatibility)."""
        return self._page_data


class MimeoPhotobook(Photobook):
    """Mimeo photobook with coordinates in Mimeo units.
    
    Mimeo Photos books don't have covers in the traditional sense - just content pages.
    We synthesize front/back covers as empty pages for compatibility.
    """
    
    def __init__(self, pages: List[Dict[str, Any]], metadata: Dict[str, str], insidecovers: bool = True):
        """Initialize Mimeo photobook.
        
        Args:
            pages: List of page data dicts with 'width', 'height', 'images' in Mimeo units
            metadata: Book metadata (title, author, etc.)
            insidecovers: Whether book has inside cover pages (default True)
        """
        super().__init__()
        self._pages = pages
        self._metadata = metadata or {}
        self._page_count = len(pages)
        self._has_inside_covers = insidecovers
        self._pages_cache: Dict[int, MimeoPhotobookPage] = {}
    
    def get_page_count(self) -> int:
        """Get total number of pages (all content pages for Mimeo)."""
        return self._page_count
    
    def get_page(self, index: int) -> Optional[MimeoPhotobookPage]:
        """Get page at given index.
        
        Args:
            index: Page index (0-based)
            
        Returns:
            MimeoPhotobookPage instance, or None if inside covers don't exist
            
        Raises:
            IndexError: If index is out of range
        """
        if index < 0 or index >= self._page_count:
            raise IndexError(f"Page index {index} out of range (0-{self._page_count-1})")
        
        # Return None for inside cover pages if book doesn't have them
        if not self._has_inside_covers:
            if index == 1 or index == self._page_count - 2:
                return None
        
        # Check cache first
        if index in self._pages_cache:
            return self._pages_cache[index]
        
        page_data = self._pages[index]
        
        # Determine page type and page number based on position:
        # Page 1 (index 0) = Front cover ("F")
        # Page 2 (index 1) = Inside front cover (0)
        # Pages 3-88 (index 2-87) = Content pages (1-86)
        # Page 89 (index 88) = Inside back cover (87)
        # Page 90 (index 89) = Back cover ("B")
        if index == 0:
            page_type = PageType.FRONT_COVER
            page_number = "F"
        elif index == 1:
            page_type = PageType.INSIDE_FRONT
            page_number = 0
        elif index == self._page_count - 1:
            page_type = PageType.BACK_COVER
            page_number = "B"
        elif index == self._page_count - 2:
            page_type = PageType.INSIDE_BACK
            page_number = self._page_count - 3  # Content page count + 1
        else:
            page_type = PageType.CONTENT
            page_number = index - 1  # Offset by inside front cover
        
        # Create and cache page
        page = MimeoPhotobookPage(page_data, page_type, page_number, index)
        self._pages_cache[index] = page
        return page
    
    def get_metadata(self) -> Dict[str, str]:
        """Get Mimeo project metadata."""
        return self._metadata
    
    def has_covers(self) -> bool:
        """Mimeo books have front and back covers."""
        return True
    
    def has_inside_covers(self) -> bool:
        """Whether this Mimeo book has inside covers."""
        return self._has_inside_covers
    
    def get_content_page_count(self) -> int:
        """Get number of content pages (excluding 4 cover pages)."""
        return self._page_count - 4
    
    def get_native_unit_name(self) -> str:
        """Get name of native coordinate unit."""
        return "Mimeo units"
