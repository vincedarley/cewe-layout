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
        self.calendar_edge_gaps = None  # Fixed gaps for calendar pages (dict with left/top/right/bottom)
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
        from .gap_utils import analyze_gaps
        
        orig = self.get_original(pageno)
        if not orig or not orig.photos:
            return {}
        
        # Get internal gap for this page (or estimate from layout)
        gap = self.get_internal_gap(pageno)
        if gap == 0.0 and orig.photos and page_width and page_height:
            # Estimate gap from original layout using origin_left for spread pages
            edge_gap, inter_gap = analyze_gaps(orig.photos, page_width, page_height, origin_left, is_spread=False)
            # Use internal gap if available, else average of edge gaps
            gap = inter_gap if inter_gap > 0 else (edge_gap['top'] + edge_gap['bottom'] + edge_gap['left'] + edge_gap['right']) / 4.0
        
        # Compute total area in gap-free space (add gap to each photo dimension)
        total_area = sum(((p.get('area_width', 0) or 0) + gap) * ((p.get('area_height', 0) or 0) + gap) for p in orig.photos)
        if total_area <= 0:
            return {}
        
        # Import helper to extract base filename
        from .gui import extract_metadata_from_filename
        
        result = {}
        for p in orig.photos:
            fn = p.get('filename', '')
            # Extract base filename (without -sz-pg suffix) to use as key
            base_fn, _, _ = extract_metadata_from_filename(fn)
            # Use gap-free area (add gap back to stored dimensions)
            area = ((p.get('area_width', 0) or 0) + gap) * ((p.get('area_height', 0) or 0) + gap)
            result[base_fn] = (area / total_area) * 10.0
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
        """Get edge gap (margin) for a page (default uniform 0.0).
        
        For calendar pages, returns the fixed calendar edge gaps.
        Always returns a dict with keys 'top', 'bottom', 'left', 'right'.
        """
        from .gap_utils import make_uniform_edge_gap
        # If calendar mode is active, return the fixed calendar gaps
        if self.calendar_edge_gaps is not None:
            return self.calendar_edge_gaps
        # Otherwise return the stored value or default to uniform 0.0
        return self.page_edge_gaps.get(pageno, make_uniform_edge_gap(0.0))
    
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
    
    def clear_new_photos(self, pageno):
        """Clear new photo tracking for a page (e.g., when rebuilding tracking after algorithm)."""
        if pageno in self.new_photos:
            self.new_photos[pageno].clear()
    
    def clear_photo_tracking(self, pageno):
        """Clear new/deleted photo tracking for a page (call after successful save)."""
        if pageno in self.new_photos:
            self.new_photos[pageno].clear()
        if pageno in self.deleted_photos:
            self.deleted_photos[pageno].clear()
    
    def replace_photos_with_new(self, pageno, photos_to_remove_indices, new_photos, new_photo_filenames, preferred_sizes=None):
        """Replace specific photos with new photos and update tracking.
        
        This is a high-level API for operations like segmentation that replace existing photos
        with new ones. It handles:
        - Removing old photos from the layout
        - Adding new photos to the layout
        - Marking old photos as deleted
        - Marking new photos as new
        - Setting preferred sizes for new photos
        
        Args:
            pageno: Page number
            photos_to_remove_indices: List of indices of photos to remove, or None/empty to remove all
            new_photos: List of new photo dicts to add
            new_photo_filenames: List of filenames for the new photos (for tracking)
            preferred_sizes: Optional dict of filename -> size for new photos (default 1.0)
            
        Returns:
            True if successful, False if page has no current layout
        """
        # Get current layout
        current = self.get_current(pageno)
        if not current:
            return False
        
        current_photos = list(current.photos)
        current_texts = list(current.texts)
        
        # Mark removed photos as deleted
        if photos_to_remove_indices:
            for idx in photos_to_remove_indices:
                if idx < len(current_photos):
                    old_filename = current_photos[idx].get('filename')
                    if old_filename:
                        self.mark_photo_as_deleted(pageno, old_filename)
        else:
            # Remove all photos
            for photo in current_photos:
                old_filename = photo.get('filename')
                if old_filename:
                    self.mark_photo_as_deleted(pageno, old_filename)
        
        # Build new photos list
        if photos_to_remove_indices:
            # Keep photos not in the removal list
            updated_photos = [p for i, p in enumerate(current_photos) if i not in photos_to_remove_indices]
        else:
            # Remove all photos
            updated_photos = []
        
        # Add new photos
        updated_photos.extend(new_photos)
        
        # Push updated layout
        self.push_layout(pageno, updated_photos, current_texts)
        
        # Mark new photos and set preferred sizes
        for filename in new_photo_filenames:
            self.mark_photo_as_new(pageno, filename)
            if preferred_sizes and filename in preferred_sizes:
                self.set_size(pageno, filename, preferred_sizes[filename])
            else:
                self.set_size(pageno, filename, 1.0)
        
        return True
    
    def replace_photo_by_filename(self, pageno, old_filename, new_filename):
        """Replace a single photo with a new one, updating tracking.
        
        This is used for operations like photo improvement where we're swapping
        one photo for another higher-quality version.
        
        Args:
            pageno: Page number
            old_filename: Filename of photo to replace
            new_filename: Filename of new photo
            
        Returns:
            True if successful, False if photo not found or no current layout
        """
        # Get current layout
        current = self.get_current(pageno)
        if not current:
            return False
        
        # Find and replace the photo
        found = False
        for photo in current.photos:
            if photo.get('filename') == old_filename:
                photo['filename'] = new_filename
                found = True
                break
        
        if not found:
            return False
        
        # Update tracking: mark old as deleted, new as added
        self.mark_photo_as_deleted(pageno, old_filename)
        self.mark_photo_as_new(pageno, new_filename)
        
        # Preserve the preferred size from old photo
        old_size = self.get_size(pageno, old_filename)
        self.set_size(pageno, new_filename, old_size)
        
        # Push updated layout
        self.push_layout(pageno, current.photos, current.texts)
        
        return True    
    def swap_photos(self, pageno1, photo_idx1, pageno2, photo_idx2):
        """Swap two photos in the layout, preserving all metadata.
        
        This swaps the complete photo dictionaries (including position, dimensions,
        rotation, cutout) between two slots. Can swap within same page or across pages.
        
        Args:
            pageno1: Page number for first photo
            photo_idx1: Index of first photo in its page's photo list
            pageno2: Page number for second photo
            photo_idx2: Index of second photo in its page's photo list
            
        Returns:
            True if successful, False if indices invalid or no current layout
        """
        # Get current layouts
        layout1 = self.get_current(pageno1)
        layout2 = self.get_current(pageno2) if pageno2 != pageno1 else layout1
        
        if not layout1 or not layout2:
            return False
        
        # Validate indices
        if photo_idx1 < 0 or photo_idx1 >= len(layout1.photos):
            return False
        if photo_idx2 < 0 or photo_idx2 >= len(layout2.photos):
            return False
        
        if pageno1 == pageno2:
            # Same page - simple swap within one list
            photos = list(layout1.photos)
            photos[photo_idx1], photos[photo_idx2] = photos[photo_idx2], photos[photo_idx1]
            
            # Push updated layout (creates undo point)
            self.push_layout(pageno1, photos, layout1.texts)
        else:
            # Cross-page swap - swap between two separate lists
            photos1 = list(layout1.photos)
            photos2 = list(layout2.photos)
            
            # Swap the photo dictionaries
            photos1[photo_idx1], photos2[photo_idx2] = photos2[photo_idx2], photos1[photo_idx1]
            
            # Push both layouts
            self.push_layout(pageno1, photos1, layout1.texts)
            self.push_layout(pageno2, photos2, layout2.texts)
        
        return True