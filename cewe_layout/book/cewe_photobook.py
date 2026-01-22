"""CEWE photobook implementation of the abstract Photobook interface.

This module provides a Photobook implementation that wraps CEWE MCF data.
All coordinates are in MCF units (0.1mm per unit).
"""

from typing import Dict, List, Optional, Any, Union
import logging

from .photobook import Photobook, PhotobookPage, PageType

logger = logging.getLogger(__name__)


class CEWEPhotobookPage(PhotobookPage):
    """CEWE photobook page with coordinates in MCF units."""
    
    def __init__(self, page_data: Dict[str, Any], page_number: Union[str, int], index: int):
        """Initialize CEWE photobook page.
        
        Args:
            page_data: Page data dict with 'photos', 'texts', dimensions, etc.
            page_number: Page number (str for covers, int for content)
            index: Page index in book (0-based)
        """
        self._page_data = page_data
        self._page_number = page_number
        self._index = index
    
    def get_width(self) -> float:
        """Get page width in MCF units."""
        return self._page_data.get('page_width', 0.0)
    
    def get_height(self) -> float:
        """Get page height in MCF units."""
        return self._page_data.get('page_height', 0.0)
    
    def get_images(self) -> List[Dict[str, Any]]:
        """Get list of photo dictionaries.
        
        Returns photos with 'area_left', 'area_top', 'area_width', 'area_height' in MCF units.
        """
        return self._page_data.get('photos', [])
    
    def get_text_blocks(self) -> List[Dict[str, Any]]:
        """Get list of text block dictionaries.
        
        Returns text blocks with 'area_left', 'area_top', 'area_width', 'area_height' in MCF units.
        """
        return self._page_data.get('texts', [])
    
    def get_page_type(self) -> PageType:
        """Get the type of this page."""
        # Determine page type from page_number and metadata
        if self._page_number == "F":
            return PageType.FRONT_COVER
        elif self._page_number == "B":
            return PageType.BACK_COVER
        elif self._page_number == 0:
            return PageType.INSIDE_FRONT
        elif isinstance(self._page_number, int):
            # Check if this is the last numeric page (inside back cover)
            # This requires knowledge of total pages, which we don't have here
            # So we check if is_cover is False (content pages are not covers)
            if self._page_data.get('is_cover', False):
                # Could be inside back cover
                # We'll mark this as CONTENT for now and fix if needed
                return PageType.CONTENT
            return PageType.CONTENT
        else:
            return PageType.CONTENT
    
    def get_page_number(self) -> Union[str, int]:
        """Get page number/identifier."""
        return self._page_number
    
    def get_page_info(self) -> Dict[str, Any]:
        """Get page info as dictionary for backward compatibility.
        
        Returns the underlying page_data dict which already has the correct format.
        """
        return self._page_data


class CEWEPhotobook(Photobook):
    """CEWE photobook with coordinates in MCF units.
    
    Wraps the data extracted from CEWE MCF files by extract_pages_info().
    """
    
    def __init__(self, pages: List[tuple[Union[str, int], Dict[str, Any]]], metadata: Optional[Dict[str, str]] = None):
        """Initialize CEWE photobook.
        
        Args:
            pages: List of (page_number, page_data) tuples from extract_pages_info()
            metadata: Optional book metadata
        """
        super().__init__()
        self._pages = pages
        self._metadata = metadata or {}
        self._page_count = len(pages)
        self._pages_cache: Dict[int, CEWEPhotobookPage] = {}
        
        # Determine if book has covers and inside covers by examining page numbers
        self._has_covers = any(pn == "F" for pn, _ in pages) and any(pn == "B" for pn, _ in pages)
        self._has_inside_covers = any(pn == 0 for pn, _ in pages)
        
        # Check format (canvas, calendar, photobook)
        if pages:
            first_page_data = pages[0][1]
            self._is_canvas = first_page_data.get('is_canvas', False)
            self._is_calendar = first_page_data.get('is_calendar', False)
        else:
            self._is_canvas = False
            self._is_calendar = False
            # CEWE photobooks always have inside covers
            assert self._has_inside_covers, "CEWE photobooks must have inside covers"
        

    def get_page_count(self) -> int:
        """Get total number of pages."""
        return self._page_count
    
    def get_page(self, index: int) -> CEWEPhotobookPage:
        """Get page at given index.
        
        Args:
            index: Page index (0-based)
            
        Returns:
            CEWEPhotobookPage instance
            
        Raises:
            IndexError: If index is out of range
        """
        if index < 0 or index >= self._page_count:
            raise IndexError(f"Page index {index} out of range (0-{self._page_count-1})")
        
        # Check cache first
        if index in self._pages_cache:
            return self._pages_cache[index]
        
        page_number, page_data = self._pages[index]
        
        # Create and cache page
        page = CEWEPhotobookPage(page_data, page_number, index)
        self._pages_cache[index] = page
        return page
    
    def get_metadata(self) -> Dict[str, str]:
        """Get CEWE project metadata."""
        return self._metadata

    def allow_spreads(self) -> bool:
        if self._is_canvas: return False
        if self._is_calendar: return False
        return True

    def page_label(self) -> str:
        if self._is_canvas: return "Canvas"
        if self._is_calendar: return "Month"
        return "Page"

    def has_covers(self) -> bool:
        """Whether book has front and back covers."""
        return self._has_covers
    
    def has_inside_covers(self) -> bool:
        """Whether book has inside cover pages."""
        return self._has_inside_covers
    
    def get_content_page_count(self) -> int:
        """Get number of content pages (excluding covers/inside covers)."""
        return self._page_count - 4
    
    def is_calendar(self) -> bool:
        """Whether this is a calendar product (monthly pages)."""
        return self._is_calendar
