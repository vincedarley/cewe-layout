"""PDF photobook implementation of the abstract Photobook interface.

This module provides a Photobook implementation that wraps PDF content.
All coordinates are in PDF points (72 points/inch).
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import logging
import fitz  # PyMuPDF

from cewe_layout.book.photobook import Photobook, PhotobookPage, PageType

logger = logging.getLogger(__name__)


class PDFPhotobookPage(PhotobookPage):
    """PDF photobook page with coordinates in PDF points."""
    
    def __init__(self, page_data: Dict[str, Any], page_type: PageType, page_number, index: int):
        """Initialize PDF photobook page.
        
        Args:
            page_data: Page data dict from pdf_extractor with 'width', 'height', 'images', 'text_blocks'
            page_type: Type of this page
            page_number: Page number (str for covers, int for content)
            index: Page index in PDF (0-based)
        """
        self._page_data = page_data
        self._page_type = page_type
        self._page_number = page_number
        self._index = index
    
    def get_width(self) -> float:
        """Get page width in PDF points."""
        return self._page_data.get('width', 0.0)
    
    def get_height(self) -> float:
        """Get page height in PDF points."""
        return self._page_data.get('height', 0.0)
    
    def get_images(self) -> List[Dict[str, Any]]:
        """Get list of image dictionaries.
        
        Returns images with 'area_left', 'area_top', 'area_width', 'area_height' in PDF points.
        """
        return self._page_data.get('photos', [])
    
    def get_text_blocks(self) -> List[Dict[str, Any]]:
        """Get list of text block dictionaries.
        
        Returns text blocks with 'area_left', 'area_top', 'area_width', 'area_height' in PDF points.
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
        # Determine origin_left based on page type/number
        # For PDF, we use standard CEWE layout: left pages have origin_left=0
        is_left_page = False
        if isinstance(self._page_number, int):
            # Even page numbers are on the left in CEWE
            is_left_page = (self._page_number % 2 == 0)
        elif self._page_number == "F":
            # Front cover is considered right page
            is_left_page = False
        elif self._page_number == "B":
            # Back cover is considered left page
            is_left_page = True
        
        return {
            'photos': self.get_images(),
            'texts': self.get_text_blocks(),
            'page_width': self.get_width(),
            'page_height': self.get_height(),
            'origin_left': 0.0 if is_left_page else self.get_width(),
            'background_id': self._page_data.get('background_id'),
            'is_cover': self._page_type in (PageType.FRONT_COVER, PageType.BACK_COVER)
        }
    
    def get_raw_data(self) -> Dict[str, Any]:
        """Get the underlying page data dict (for compatibility with existing code)."""
        return self._page_data


class PDFPhotobook(Photobook):
    """PDF photobook with coordinates in PDF points.
    
    Supports both batch (pre-loaded) and on-demand page extraction modes.
    """
    
    def __init__(self, pages: Optional[List[Optional[Dict[str, Any]]]] = None, 
                 metadata: Optional[Dict[str, str]] = None, 
                 pdf_path: Optional[Path] = None,
                 page_to_ui: Optional[Dict[int, Any]] = None,
                 verbose: bool = False,
                 insidecovers: bool = True):
        """Initialize PDF photobook.
        
        Args:
            pages: List of page data dicts for batch mode, None for on-demand mode.
                   MUST contain N+4 items (where N = content page count) with None
                   at indices 1 and N+2 when insidecovers=False.
            metadata: PDF metadata dict (will be lazy-loaded in on-demand mode)
            pdf_path: Path to PDF file (required for on-demand mode)
            page_to_ui: Mapping from actual PDF page index to UI page identifier (required for on-demand mode).
                        When insidecovers=True: PDF has N+4 pages, maps all indices 0..N+3
                        When insidecovers=False: PDF has N+2 pages, maps indices 0..N+1 (no inside covers in PDF)
                        The Photobook will always expose N+4 logical indices, returning None for 1 and N+2 when insidecovers=False.
            verbose: Print detailed extraction info (for on-demand mode)
            insidecovers: Whether book has inside cover pages in the PDF (default True).
                         When False, get_page() returns None for logical indices 1 and N+2.
        """
        super().__init__()
        # Batch mode: pages provided upfront
        if pages is not None:
            self._pages = pages
            self._page_count = len(pages)
            self._on_demand = False
            self._pdf_path = None
            self._page_to_ui = None
            self._doc = None
            # Note: Caller is responsible for ensuring pages[1] and pages[N+2] are None
            # when insidecovers=False. This is enforced by extract_pdf_content().
        # On-demand mode: extract pages as needed
        else:
            if pdf_path is None or page_to_ui is None:
                raise ValueError("pdf_path and page_to_ui are required for on-demand mode")
            
            # Determine page count: Always N+4 (includes logical inside cover slots)
            # When insidecovers=True: PDF has N+4 pages, page_to_ui has N+4 entries
            # When insidecovers=False: PDF has N+2 pages, page_to_ui has N+2 entries,
            #                         but we still need N+4 logical indices
            if insidecovers:
                # PDF has all pages including inside covers
                self._page_count = len(page_to_ui)
            else:
                # PDF missing inside covers - add 2 to page count for logical slots
                self._page_count = len(page_to_ui) + 2
            
            self._pages = [None] * self._page_count  # Placeholder list
            self._on_demand = True
            self._pdf_path = pdf_path
            self._page_to_ui = page_to_ui
            self._doc = None  # Lazy-loaded
            
        self._metadata = metadata or {}
        self._has_inside_covers = insidecovers
        self._pages_cache: Dict[int, PDFPhotobookPage] = {}
        self._verbose = verbose
        
        # Validation: In batch mode with insidecovers=False, verify inside cover slots are None
        if pages is not None and not insidecovers and self._page_count >= 4:
            if self._pages[1] is not None:
                logger.warning(
                    f"In batch mode with insidecovers=False, expected pages[1] to be None "
                    f"but got {type(self._pages[1])}. This may cause inconsistent behavior."
                )
            if self._pages[self._page_count - 2] is not None:
                logger.warning(
                    f"In batch mode with insidecovers=False, expected pages[{self._page_count - 2}] to be None "
                    f"but got {type(self._pages[self._page_count - 2])}. This may cause inconsistent behavior."
                )
    
    def _ensure_doc_open(self):
        """Ensure PDF document is opened (for on-demand mode)."""
        if self._on_demand and self._doc is None:
            self._doc = fitz.open(self._pdf_path)
            # Update metadata from PDF if not already set
            if not self._metadata:
                self._metadata = {
                    'title': self._doc.metadata.get('title', ''),
                    'author': self._doc.metadata.get('author', ''),
                    'subject': self._doc.metadata.get('subject', ''),
                    'producer': self._doc.metadata.get('producer', ''),
                }
    
    def _extract_page_on_demand(self, index: int) -> Dict[str, Any]:
        """Extract a single page on-demand.
        
        Note: This method will not be called for inside cover indices (1, N+2)
        when insidecovers=False, as get_page() returns None early for those.
        
        Args:
            index: PDF page index (0-based)
            
        Returns:
            Page data dict
            
        Raises:
            ValueError: If index not in page_to_ui mapping or page doesn't exist
        """
        from .pdf_extractor import extract_page_content
        
        self._ensure_doc_open()
        
        if index >= len(self._doc):
            raise ValueError(f"Page {index + 1} does not exist")
        
        # Get UI page identifier for coordinate positioning
        if index not in self._page_to_ui:
            raise ValueError(
                f"No UI page mapping found for PDF page {index}. "
                f"On-demand mode requires page_to_ui mapping. "
                f"Available mappings: {list(self._page_to_ui.keys())}"
            )
        
        ui_page = self._page_to_ui[index]
        page = self._doc[index]
        page_data = extract_page_content(page, index, len(self._doc), 
                                        self._verbose, debug=False, ui_page=ui_page)
        
        # Cache the extracted page
        self._pages[index] = page_data
        
        return page_data
    
    def get_page_count(self) -> int:
        """Get total number of pages."""
        return self._page_count
    
    def get_page(self, index: int) -> Optional[PDFPhotobookPage]:
        """Get page at given PDF index.
        
        Args:
            index: PDF page index (0-based)
            
        Returns:
            PDFPhotobookPage instance, or None if inside covers don't exist
            
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
        
        # Get page data (extract on-demand if needed)
        if self._on_demand and self._pages[index] is None:
            page_data = self._extract_page_on_demand(index)
        else:
            page_data = self._pages[index]
            
        if page_data is None:
            raise ValueError(f"Page {index} data not available")
        
        # Determine page type and page number based on index and insidecovers flag
        page_type = self._get_page_type(index)
        page_number = self._get_page_number(index)
        
        # Create and cache page
        page = PDFPhotobookPage(page_data, page_type, page_number, index)
        self._pages_cache[index] = page
        return page
    
    def _get_page_type(self, index: int) -> PageType:
        """Determine page type from index.
        
        Args:
            index: PDF page index (0-based)
            
        Returns:
            PageType enum value
        """
        # WITH inside covers: [0=front, 1=inside_front, 2..N-3=content, N-2=inside_back, N-1=back]
        if index == 0:
            return PageType.FRONT_COVER
        elif index == 1:
            return PageType.INSIDE_FRONT
        elif index == self._page_count - 2:
            return PageType.INSIDE_BACK
        elif index == self._page_count - 1:
            return PageType.BACK_COVER
        else:
            return PageType.CONTENT

    def _get_page_number(self, index: int):
        """Determine page number from index.
        
        Args:
            index: PDF page index (0-based)
            
        Returns:
            Page number (str for covers, int for content/inside covers)
        """
        # WITH inside covers: [0="F", 1=0, 2..N-3=1..(N-4), N-2=(N-3), N-1="B"]
        if index == 0:
            return "F"
        elif index == 1:
            return 0  # Inside front cover
        elif index == self._page_count - 1:
            return "B"
        elif index == self._page_count - 2:
            return self._page_count - 3  # Inside back cover
        else:
            return index - 1  # Content pages start at 1

    def get_metadata(self) -> Dict[str, str]:
        """Get PDF metadata."""
        return self._metadata
    
    def has_covers(self) -> bool:
        """PDF books always have front and back covers."""
        return True
    
    def has_inside_covers(self) -> bool:
        """Whether this PDF book has dedicated inside cover pages."""
        return self._has_inside_covers
    
    def get_content_page_count(self) -> int:
        """Get number of content pages (excluding covers/inside covers)."""
        return self._page_count - 4  # Exclude front, inside_front, inside_back, back

    def get_native_unit_name(self) -> str:
        """Get name of native coordinate unit."""
        return "PDF points"
    
    def close(self):
        """Close the PDF document (for on-demand mode)."""
        if self._doc is not None:
            self._doc.close()
            self._doc = None
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
