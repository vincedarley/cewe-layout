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
        - 'area_left', 'area_top', 'area_width', 'area_height': position/size in native units
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
        - 'area_left', 'area_top', 'area_width', 'area_height': position/size in native units
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
            1..N for normal content pages
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
        
        Note: Image dicts in 'photos' use MCF keys: 'area_left', 'area_top', 'area_width', 'area_height'
        """
        pass


class Photobook(ABC):
    """Abstract representation of a photobook.
    
    A photobook is a collection of pages with metadata. All photobooks
    must have front and back covers. They may optionally have inside covers.
    Content pages are numbered sequentially.  ALL photobooks are integer-indexed as 
    follows, assuming they have N+4 total pages: 0 = front cover, 1 = inside front, 
    2...N+1 = content pages, N+2 = inside back, N+3 = back cover.
    IF the photobook does not have inside covers, then it should return None for those pages.
    From a UI perspective, we use:
    F = front cover, 0 = inside front, 1..N = content pages, N+1 = inside back, B = back cover.

    We refer to the N pages as "Content" pages, and the others as "Inside Covers" and "Covers"
    respectively.  CEWE does not support content on inside covers, but other formats (Mimeo, PDF imports)
    may allow it.  The file format (MCF) does support it, and QLayout can display/edit it.  
    However, for CEWE purchases, any content on inside covers will be ignored.
    (At least this is true of hardcover books).

    
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
    def get_page(self, index: int) -> Optional[PhotobookPage]:
        """Get page at given index (0-based).
        
        Args:
            index: Page index (0 to page_count - 1)
            
        Returns:
            PhotobookPage instance, or None for inside covers when they don't exist
            
        Raises:
            IndexError: If index is out of range
        """
        pass
    
    def get_first_content_page(self) -> Optional[PhotobookPage]:
        """Get first content page."""
        return self.get_page(2) 

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
    
    def get_front_cover_page(self) -> Optional[PhotobookPage]:
        """Get front cover page, or None if not present."""
        if not self.has_covers():
            return None
        return self.get_page(0)

    def get_back_cover_page(self) -> Optional[PhotobookPage]:
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
            if page is not None and page.get_page_type() == PageType.CONTENT:
                pages.append((i, page))
        return pages
    
    def create_empty_page_template(self) -> Dict[str, Any]:
        """Create template for an empty content page.
        
        Uses dimensions and basic properties from the first content page.
        The template will have empty photos and texts lists.
        
        Returns:
            Dict with page_info structure: 'page_width', 'page_height', 'origin_left',
            'photos' (empty list), 'texts' (empty list), and other format-specific fields.
            
        Raises:
            ValueError: If no content pages exist in the photobook
        """
        first_content = self.get_first_content_page()
        if not first_content:
            raise ValueError("Cannot create empty page template - no content pages exist")
        
        # Get page info and create a copy
        template = first_content.get_page_info().copy()
        
        # Clear content
        template['photos'] = []
        template['texts'] = []
        
        return template
    
    @abstractmethod
    def get_native_unit_name(self) -> str:
        """Get name of native coordinate unit (e.g., 'PDF points', 'Mimeo units', 'MCF units')."""
        pass
    
    def __iter__(self) -> Iterator[PhotobookPage]:
        """Allow iteration over pages: for page in photobook:"""
        for i in range(self.get_page_count()):
            page = self.get_page(i)
            if page is not None:
                yield page
    
    def enumerate_pages(self) -> Iterator[Tuple[int, Optional[PhotobookPage]]]:
        """Enumerate pages with indices: for idx, page in photobook.enumerate_pages():
        
        Note: page may be None for inside covers when they don't exist.
        """
        for i in range(self.get_page_count()):
            yield (i, self.get_page(i))
    
    def is_valid_index(self, index: int) -> bool:
        """Check if index is within valid range [0, page_count)."""
        return 0 <= index < self.get_page_count()
    
    def get_page_numbers(self) -> List[Union[str, int]]:
        """Get list of all page numbers for all pages."""
        return [page.get_page_number() for page in self]
    
    def find_page_by_ui_num(self, page_number: Union[str, int]) -> Optional[PhotobookPage]:
        """Find page with specific UI number (e.g., 'F', 'B', 0, 1, 2, etc.).

        By definition 0 should return the inside front cover (which might be None), 1 the first content page, etc
        
        Returns None if not found.
        """
        for page in self:
            if page is not None and page.get_page_number() == page_number:
                return page
        return None

    def get_numeric_pages(self) -> List[PhotobookPage]:
        """Get only content pages (integer page numbers > 0, exclude covers)."""
        result = []
        for page in self:
            if page is not None:
                page_num = page.get_page_number()
                if isinstance(page_num, int) and page_num > 0:
                    result.append(page)
        return result


