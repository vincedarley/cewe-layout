"""Layout generation and management for pages.

Provides collage-generator integration, in-memory layout storage with undo,
and per-photo preferred size management.
"""
from collections import defaultdict
import copy


class PageLayout:
    """In-memory representation of a page layout."""
    def __init__(self, pageno, photos_with_areas, texts_with_areas=None, internal_gap=0.0):
        self.pageno = pageno
        # photos_with_areas: list of photo dicts with area info
        self.photos = copy.deepcopy(photos_with_areas)
        # texts_with_areas: list of text block dicts with area info
        self.texts = copy.deepcopy(texts_with_areas) if texts_with_areas else []
        self.internal_gap = internal_gap  # Uniform spacing in MCF units (0.1mm)

    def clone(self):
        return PageLayout(self.pageno, self.photos, self.texts, self.internal_gap)


class LayoutManager:
    """Manages in-memory layout history per page, sizes, and original state."""
    def __init__(self):
        self.page_layouts = defaultdict(list)  # pageno -> [PageLayout, ...]
        self.page_sizes = defaultdict(lambda: defaultdict(lambda: 1.0))  # pageno -> filename -> preferred_size
        self.page_internal_gaps = {}  # pageno -> internal_gap (MCF units, 0.1mm)
        self.page_edge_gaps = {}  # pageno -> edge_gap (MCF units, 0.1mm)
        self.page_original = {}  # pageno -> PageLayout (read from file)
        self.new_photos = defaultdict(set)  # pageno -> set of filenames added after original
        self.deleted_photos = defaultdict(set)  # pageno -> set of filenames deleted from original

    def set_original(self, pageno, photos, texts=None):
        """Store the original layout read from the file."""
        self.page_original[pageno] = PageLayout(pageno, photos, texts)

    def get_original(self, pageno):
        """Return the original layout for a page."""
        if pageno in self.page_original:
            return self.page_original[pageno].clone()
        return None

    def get_current(self, pageno):
        """Return the current layout (most recent in history, or original)."""
        if pageno in self.page_layouts and len(self.page_layouts[pageno]) > 0:
            return self.page_layouts[pageno][-1].clone()
        return self.get_original(pageno)

    def push_layout(self, pageno, photos, texts=None):
        """Store a new layout variant for a page."""
        self.page_layouts[pageno].append(PageLayout(pageno, photos, texts))

    def undo_layout(self, pageno):
        """Remove the most recent layout, reverting to previous."""
        if pageno in self.page_layouts and len(self.page_layouts[pageno]) > 0:
            self.page_layouts[pageno].pop()
            return True
        return False

    def clear_layouts(self, pageno):
        """Clear all stored layouts for a page."""
        if pageno in self.page_layouts:
            del self.page_layouts[pageno]

    def set_size(self, pageno, filename, preferred_size):
        """Set preferred size for a photo by filename."""
        self.page_sizes[pageno][filename] = preferred_size

    def get_size(self, pageno, filename):
        """Get preferred size for a photo (default 1.0)."""
        return self.page_sizes[pageno][filename]

    def get_sizes_for_page(self, pageno):
        """Return dict of filename -> preferred_size for a page."""
        return dict(self.page_sizes[pageno])
    
    def get_stored_sizes_for_page(self, pageno, page_width=None, page_height=None, origin_left=0.0):
        """Get dict of filename -> area-based size from original layout.
        
        Returns sizes scaled by 10× for human readability (e.g., 1.2, 3.5).
        Uses gap-free areas to match evaluation coordinate space.
        
        Args:
            pageno: Page number.
            page_width: Page width in MCF units (for gap estimation).
            page_height: Page height in MCF units (for gap estimation).
            origin_left: For right-hand pages, the absolute X offset (default 0.0).
        """
        from .gap_utils import estimate_gaps
        
        orig = self.get_original(pageno)
        if not orig or not orig.photos:
            return {}
        
        # Get internal gap for this page (or estimate from layout)
        gap = self.get_internal_gap(pageno)
        if gap == 0.0 and orig.photos and page_width and page_height:
            # Estimate gap from original layout using origin_left for spread pages
            edge_gap, inter_gap = estimate_gaps(orig.photos, page_width, page_height, origin_left)
            gap = inter_gap if inter_gap > 0 else edge_gap
        
        # Compute total area in gap-free space (add gap to each photo dimension)
        total_area = sum(((p.get('area_width', 0) or 0) + gap) * ((p.get('area_height', 0) or 0) + gap) for p in orig.photos)
        if total_area <= 0:
            return {}
        result = {}
        for p in orig.photos:
            fn = p.get('filename', '')
            # Use gap-free area (add gap back to stored dimensions)
            area = ((p.get('area_width', 0) or 0) + gap) * ((p.get('area_height', 0) or 0) + gap)
            result[fn] = (area / total_area) * 10.0
        return result

    def set_internal_gap(self, pageno, internal_gap):
        """Set internal gap spacing for a page (MCF units, 0.1mm)."""
        self.page_internal_gaps[pageno] = internal_gap

    def get_internal_gap(self, pageno):
        """Get internal gap spacing for a page (default 0.0)."""
        return self.page_internal_gaps.get(pageno, 0.0)

    def set_edge_gap(self, pageno, edge_gap):
        """Set edge gap (margin) for a page (MCF units, 0.1mm). Can be negative for bleed."""
        self.page_edge_gaps[pageno] = edge_gap

    def get_edge_gap(self, pageno):
        """Get edge gap (margin) for a page (default 0.0)."""
        return self.page_edge_gaps.get(pageno, 0.0)
    
    def has_edge_gap(self, pageno):
        """Check if edge gap has been set for a page."""
        return pageno in self.page_edge_gaps
    
    def has_internal_gap(self, pageno):
        """Check if internal gap has been set for a page."""
        return pageno in self.page_internal_gaps
    
    def clear_gaps(self, pageno):
        """Clear stored gap values for a page, forcing re-initialization from original layout."""
        if pageno in self.page_internal_gaps:
            del self.page_internal_gaps[pageno]
        if pageno in self.page_edge_gaps:
            del self.page_edge_gaps[pageno]
    
    def mark_photo_as_new(self, pageno, filename):
        """Mark a photo as newly added to the page (not in original layout)."""
        self.new_photos[pageno].add(filename)
        # If photo was previously deleted, remove from deleted set
        if filename in self.deleted_photos[pageno]:
            self.deleted_photos[pageno].remove(filename)
    
    def mark_photo_as_deleted(self, pageno, filename):
        """Mark a photo as deleted from the page."""
        # If photo was newly added (not in original), just remove from new set
        if filename in self.new_photos[pageno]:
            self.new_photos[pageno].remove(filename)
        else:
            # Photo was in original layout, mark as deleted
            self.deleted_photos[pageno].add(filename)
    
    def get_new_photos(self, pageno):
        """Get set of filenames for photos newly added to this page."""
        return self.new_photos[pageno]
    
    def get_deleted_photos(self, pageno):
        """Get set of filenames for photos deleted from this page."""
        return self.deleted_photos[pageno]
    
    def clear_photo_tracking(self, pageno):
        """Clear new/deleted photo tracking for a page (call after successful save)."""
        if pageno in self.new_photos:
            self.new_photos[pageno].clear()
        if pageno in self.deleted_photos:
            self.deleted_photos[pageno].clear()
