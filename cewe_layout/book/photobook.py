"""Abstract photobook representation.

This module defines the core abstraction for photobooks from any source
(PDF, Mimeo, MCF, etc.). Each implementation uses its native coordinate
system - translation to different formats happens separately.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Tuple, Union, Iterator
from enum import Enum


class PageType(Enum):
    """Type of page in a photobook."""
    FRONT_COVER = "front_cover"
    BACK_COVER = "back_cover"
    INSIDE_FRONT = "inside_front"
    INSIDE_BACK = "inside_back"
    CONTENT = "content"


class PhotobookPage(ABC):
    """Abstract representation of a single photobook page.
    
    All dimensions are in the native coordinate system of the source
    (PDF points, Mimeo units, MCF units, etc.).
    """
    
    @abstractmethod
    def get_width(self) -> float:
        """Get page width in native units."""
        pass
    
    @abstractmethod
    def get_height(self) -> float:
        """Get page height in native units."""
        pass
    
    @abstractmethod
    def get_images(self) -> List[Dict[str, Any]]:
        """Get list of image dictionaries for this page.
        
        Each image dict should have at minimum:
        - 'left', 'top', 'width', 'height': position/size in native units
        - 'data': image bytes
        - 'format': file extension ('jpg', 'png', etc.)
        - 'index': unique image index
        
        May also include format-specific fields.
        """
        pass
    
    @abstractmethod
    def get_text_blocks(self) -> List[Dict[str, Any]]:
        """Get list of text block dictionaries for this page.
        
        Each text block dict should have at minimum:
        - 'left', 'top', 'width', 'height': position/size in native units
        - 'text': text content
        - 'font': font name
        - 'size': font size in points
        - 'color': color as integer (0xRRGGBB)
        
        May also include format-specific fields like 'flags'.
        """
        pass
    
    @abstractmethod
    def get_page_type(self) -> PageType:
        """Get the type of this page."""
        pass
    
    @abstractmethod
    def get_page_number(self) -> Union[str, int]:
        """Get page number/identifier.
        
        Returns:
            "F" for front cover, "B" for back cover,
            0 for inside front, N+1 for inside back,
            1..N for content pages
        """
        pass
    
    @abstractmethod
    def get_page_info(self) -> Dict[str, Any]:
        """Get page info as dictionary for backward compatibility.
        
        Returns dict with keys:
            - 'photos': list of photo dicts (same as get_images())
            - 'texts': list of text dicts (same as get_text_blocks())
            - 'page_width': width in native units
            - 'page_height': height in native units
            - 'origin_left': x-offset for spread layout (0.0 for left page)
            - 'background_id': optional background color code
            - 'is_cover': True if this is a cover page
        """
        pass


class Photobook(ABC):
    """Abstract representation of a photobook.
    
    A photobook is a collection of pages with metadata. All photobooks
    must have front and back covers. They may optionally have inside covers.
    Content pages are numbered sequentially.
    
    All dimensions and coordinates are in the native coordinate system of
    the source format.
    """
    
    def __init__(self):
        """Initialize photobook with optional resize transformer."""
        self.resize_transformer = None  # Optional ResizeTransformer for viewing resized
    
    @abstractmethod
    def get_page_count(self) -> int:
        """Get total number of pages (including covers)."""
        pass
    
    @abstractmethod
    def get_page(self, index: int) -> PhotobookPage:
        """Get page at given index (0-based).
        
        Args:
            index: Page index (0 to page_count - 1)
            
        Returns:
            PhotobookPage instance
            
        Raises:
            IndexError: If index is out of range
        """
        pass
    
    def get_first_content_page(self) -> PhotobookPage:
        """Get only content pages (integer page numbers > 0, exclude covers)."""
        return self.get_page(1)   

    @abstractmethod
    def get_metadata(self) -> Dict[str, str]:
        """Get book metadata.
        
        Returns dictionary with optional keys:
        - 'title': Book title
        - 'author': Author name
        - 'description': Book description
        - Other format-specific metadata
        """
        pass

    def allow_spreads(self) -> bool:
        return True

    def page_label(self) -> str:
        return "Page"

    def has_multiple_pages(self) -> bool:
        return self.get_page_count() > 1

    @abstractmethod
    def has_covers(self) -> bool:
        """Whether book has front and back covers.
        
        Books either have both covers or neither - can't have just one.
        Canvas/calendar products may not have covers.
        """
        pass
    
    @abstractmethod
    def has_inside_covers(self) -> bool:
        """Whether book has inside cover pages which can contain content."""
        pass
    
    @abstractmethod
    def get_content_page_count(self) -> int:
        """Get number of content pages (excluding covers/inside covers)."""
        pass
    
    def get_front_cover_page(self) -> PhotobookPage:
        """Get front cover page, or None if not present."""
        if not self.has_covers():
            return None
        return self.get_page(0)

    def get_back_cover_page(self) -> PhotobookPage:
        """Get back cover page, or None if not present."""
        if not self.has_covers():
            return None
        return self.get_page(self.get_page_count()-1)

    def get_inside_front_page(self) -> Optional[PhotobookPage]:
        """Get inside front cover page, or None if not present."""
        if not self.has_inside_covers():
            return None
        return self.get_page(1)

    def get_inside_back_page(self) -> Optional[PhotobookPage]:
        """Get inside back cover page, or None if not present."""
        if not self.has_inside_covers():
            return None
        return self.get_page(self.get_page_count()-2)

    def get_content_pages(self) -> List[Tuple[int, PhotobookPage]]:
        """Get all content pages as (index, page) tuples.
        
        Returns:
            List of (index, page) tuples for content pages only
        """
        pages = []
        for i in range(self.get_page_count()):
            page = self.get_page(i)
            if page.get_page_type() == PageType.CONTENT:
                pages.append((i, page))
        return pages
    
    @abstractmethod
    def get_native_unit_name(self) -> str:
        """Get name of native coordinate unit (e.g., 'PDF points', 'Mimeo units', 'MCF units')."""
        pass
    
    def __iter__(self) -> Iterator[PhotobookPage]:
        """Allow iteration over pages: for page in photobook:"""
        for i in range(self.get_page_count()):
            yield self.get_page(i)
    
    def enumerate_pages(self) -> Iterator[Tuple[int, PhotobookPage]]:
        """Enumerate pages with indices: for idx, page in photobook.enumerate_pages():"""
        for i in range(self.get_page_count()):
            yield (i, self.get_page(i))
    
    def is_valid_index(self, index: int) -> bool:
        """Check if index is within valid range [0, page_count)."""
        return 0 <= index < self.get_page_count()
    
    def get_page_numbers(self) -> List[Union[str, int]]:
        """Get list of all page numbers for all pages."""
        return [page.get_page_number() for page in self]
    
    def find_page_by_number(self, page_number: Union[str, int]) -> Optional[PhotobookPage]:
        """Find page with specific number (e.g., 'F', 'B', 1, 2, etc.).
        
        Returns None if not found.
        """
        for page in self:
            if page.get_page_number() == page_number:
                return page
        return None

    def get_numeric_pages(self) -> List[PhotobookPage]:
        """Get only content pages (integer page numbers > 0, exclude covers)."""
        return [page for page in self 
                if isinstance(page.get_page_number(), int) and page.get_page_number() > 0]
