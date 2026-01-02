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
    
    def __init__(self, page_data: Dict[str, Any], page_type: PageType):
        """Initialize Mimeo photobook page.
        
        Args:
            page_data: Page data dict with 'width', 'height', 'images', 'text_blocks'
            page_type: Type of this page
        """
        self._page_data = page_data
        self._page_type = page_type
    
    def get_width(self) -> float:
        """Get page width in Mimeo units."""
        return self._page_data.get('width', 0.0)
    
    def get_height(self) -> float:
        """Get page height in Mimeo units."""
        return self._page_data.get('height', 0.0)
    
    def get_images(self) -> List[Dict[str, Any]]:
        """Get list of image dictionaries.
        
        Returns images with 'left', 'top', 'width', 'height' in Mimeo units.
        """
        return self._page_data.get('images', [])
    
    def get_text_blocks(self) -> List[Dict[str, Any]]:
        """Get list of text block dictionaries.
        
        Returns text blocks with 'left', 'top', 'width', 'height' in Mimeo units.
        """
        return self._page_data.get('text_blocks', [])
    
    def get_page_type(self) -> PageType:
        """Get the type of this page."""
        return self._page_type
    
    def get_raw_data(self) -> Dict[str, Any]:
        """Get the underlying page data dict (for compatibility)."""
        return self._page_data


class MimeoPhotobook(Photobook):
    """Mimeo photobook with coordinates in Mimeo units.
    
    Mimeo Photos books don't have covers in the traditional sense - just content pages.
    We synthesize front/back covers as empty pages for compatibility.
    """
    
    def __init__(self, pages: List[Dict[str, Any]], metadata: Dict[str, str]):
        """Initialize Mimeo photobook.
        
        Args:
            pages: List of page data dicts with 'width', 'height', 'images' in Mimeo units
            metadata: Book metadata (title, author, etc.)
        """
        self._pages = pages
        self._metadata = metadata or {}
        self._page_count = len(pages)
        self._pages_cache: Dict[int, MimeoPhotobookPage] = {}
    
    def get_page_count(self) -> int:
        """Get total number of pages (all content pages for Mimeo)."""
        return self._page_count
    
    def get_page(self, index: int) -> MimeoPhotobookPage:
        """Get page at given index.
        
        Args:
            index: Page index (0-based)
            
        Returns:
            MimeoPhotobookPage instance
            
        Raises:
            IndexError: If index is out of range
        """
        if index < 0 or index >= self._page_count:
            raise IndexError(f"Page index {index} out of range (0-{self._page_count-1})")
        
        # Check cache first
        if index in self._pages_cache:
            return self._pages_cache[index]
        
        page_data = self._pages[index]
        
        # Determine page type based on position:
        # Page 1 (index 0) = Front cover
        # Page 2 (index 1) = Inside front cover
        # Pages 3-88 (index 2-87) = Content pages (86 pages)
        # Page 89 (index 88) = Inside back cover (empty)
        # Page 90 (index 89) = Back cover
        if index == 0:
            page_type = PageType.FRONT_COVER
        elif index == 1:
            page_type = PageType.INSIDE_FRONT
        elif index == self._page_count - 1:
            page_type = PageType.BACK_COVER
        elif index == self._page_count - 2:
            page_type = PageType.INSIDE_BACK
        else:
            page_type = PageType.CONTENT
        
        # Create and cache page
        page = MimeoPhotobookPage(page_data, page_type)
        self._pages_cache[index] = page
        return page
    
    def get_metadata(self) -> Dict[str, str]:
        """Get Mimeo project metadata."""
        return self._metadata
    
    def has_inside_covers(self) -> bool:
        """Mimeo books have inside covers."""
        return True
    
    def get_content_page_count(self) -> int:
        """Get number of content pages (excluding 4 cover pages)."""
        return self._page_count - 4
    
    def get_native_unit_name(self) -> str:
        """Get name of native coordinate unit."""
        return "Mimeo units"
    
    def get_front_cover_page(self) -> PhotobookPage:
        """Get the front cover page (first page)."""
        return self.get_page(0)
    
    def get_back_cover_page(self) -> PhotobookPage:
        """Get the back cover page (last page)."""
        return self.get_page(self._page_count - 1)
