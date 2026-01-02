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
    
    def __init__(self, page_data: Dict[str, Any], page_type: PageType):
        """Initialize PDF photobook page.
        
        Args:
            page_data: Page data dict from pdf_extractor with 'width', 'height', 'images', 'text_blocks'
            page_type: Type of this page
        """
        self._page_data = page_data
        self._page_type = page_type
    
    def get_width(self) -> float:
        """Get page width in PDF points."""
        return self._page_data.get('width', 0.0)
    
    def get_height(self) -> float:
        """Get page height in PDF points."""
        return self._page_data.get('height', 0.0)
    
    def get_images(self) -> List[Dict[str, Any]]:
        """Get list of image dictionaries.
        
        Returns images with 'left', 'top', 'width', 'height' in PDF points.
        """
        return self._page_data.get('images', [])
    
    def get_text_blocks(self) -> List[Dict[str, Any]]:
        """Get list of text block dictionaries.
        
        Returns text blocks with 'left', 'top', 'width', 'height' in PDF points.
        """
        return self._page_data.get('text_blocks', [])
    
    def get_page_type(self) -> PageType:
        """Get the type of this page."""
        return self._page_type
    
    def get_raw_data(self) -> Dict[str, Any]:
        """Get the underlying page data dict (for compatibility with existing code)."""
        return self._page_data


class PDFPhotobook(Photobook):
    """PDF photobook with coordinates in PDF points.
    
    Supports both batch (pre-loaded) and on-demand page extraction modes.
    """
    
    def __init__(self, pages: Optional[List[Dict[str, Any]]] = None, 
                 metadata: Optional[Dict[str, str]] = None, 
                 insidecovers: bool = False,
                 pdf_path: Optional[Path] = None,
                 page_to_ui: Optional[Dict[int, Any]] = None,
                 verbose: bool = False):
        """Initialize PDF photobook.
        
        Args:
            pages: List of page data dicts (for batch mode) or None (for on-demand mode)
            metadata: PDF metadata dict (required)
            insidecovers: Whether PDF includes inside cover pages
            pdf_path: Path to PDF file (required for on-demand mode)
            page_to_ui: Mapping from PDF index to UI page (required for on-demand mode)
            verbose: Print detailed extraction info (for on-demand mode)
        """
        # Batch mode: pages provided upfront
        if pages is not None:
            self._pages = pages
            self._page_count = len(pages)
            self._on_demand = False
            self._pdf_path = None
            self._page_to_ui = None
            self._doc = None
        # On-demand mode: extract pages as needed
        else:
            if pdf_path is None or page_to_ui is None:
                raise ValueError("pdf_path and page_to_ui are required for on-demand mode")
            self._pages = [None] * len(page_to_ui)  # Placeholder list
            self._page_count = len(page_to_ui)
            self._on_demand = True
            self._pdf_path = pdf_path
            self._page_to_ui = page_to_ui
            self._doc = None  # Lazy-loaded
            
        self._metadata = metadata or {}
        self._has_inside_covers = insidecovers
        self._pages_cache: Dict[int, PDFPhotobookPage] = {}
        self._verbose = verbose
    
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
        
        Args:
            index: PDF page index (0-based)
            
        Returns:
            Page data dict
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
    
    def get_page(self, index: int) -> PDFPhotobookPage:
        """Get page at given PDF index.
        
        Args:
            index: PDF page index (0-based)
            
        Returns:
            PDFPhotobookPage instance
            
        Raises:
            IndexError: If index is out of range
        """
        if index < 0 or index >= self._page_count:
            raise IndexError(f"Page index {index} out of range (0-{self._page_count-1})")
        
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
        
        # Determine page type based on index and insidecovers flag
        page_type = self._get_page_type(index)
        
        # Create and cache page
        page = PDFPhotobookPage(page_data, page_type)
        self._pages_cache[index] = page
        return page
    
    def _get_page_type(self, index: int) -> PageType:
        """Determine page type from index.
        
        Args:
            index: PDF page index (0-based)
            
        Returns:
            PageType enum value
        """
        if self._has_inside_covers:
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
        else:
            # WITHOUT inside covers: [0=front, 1..N-2=content, N-1=back]
            if index == 0:
                return PageType.FRONT_COVER
            elif index == self._page_count - 1:
                return PageType.BACK_COVER
            else:
                return PageType.CONTENT
    
    def get_metadata(self) -> Dict[str, str]:
        """Get PDF metadata."""
        return self._metadata
    
    def has_inside_covers(self) -> bool:
        """Whether book has dedicated inside cover pages."""
        return self._has_inside_covers
    
    def get_content_page_count(self) -> int:
        """Get number of content pages (excluding covers/inside covers)."""
        if self._has_inside_covers:
            return self._page_count - 4  # Exclude front, inside_front, inside_back, back
        else:
            return self._page_count - 2  # Exclude front, back
    
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
