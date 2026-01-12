
# Widths are spread dimensions (so 2x pages). We list separately the cover and page sizes.
# Note that CEWE calculates a very specific coverWidth which seems to depend on the number of pages
# in the book. This makes some sense if the cover width wraps around the spine - a thicker book will require
# more width to perform that wrapping.  We do not try to replicate that logic here. So when you open and then
# save the book in CEWE Creator, I expect the coverWidth may change slightly.

BOOK_SIZES = {
    'L landscape': {'productname': 'ALB45', 'coverWidth': 3975, 'coverHeight': 1530, 'pageWidth': 3800, 'pageHeight': 1480, 'art_id': 8068},
    'XXL landscape': {'productname': 'ALB42', 'coverWidth': 7870, 'coverHeight': 2960, 'pageWidth': 7640, 'pageHeight': 2900, 'art_id': 9896},
    'XL landscape': {'productname': 'ALB35', 'coverWidth': 5575, 'coverHeight': 2100, 'pageWidth': 5400, 'pageHeight': 2050, 'art_id': 9759},
}


def find_closest_book_size(width: int, height: int) -> str:
    """Find the closest matching book size based on page dimensions.

    Compares the given width and height against the pageWidth and pageHeight
    of each book size, selecting the one with minimum total absolute difference.

    Args:
        width: Page width in MCF units (single page, not spread)
        height: Page height in MCF units

    Returns:
        Book size descriptor (e.g., 'L landscape', 'XXL landscape') with closest matching dimensions.
        Use the 'productname' key in BOOK_SIZES for internal product code.

    Raises:
        ValueError: If BOOK_SIZES is empty

    Example:
        >>> find_closest_book_size(3800, 1480)
        'ALB45'
        >>> find_closest_book_size(7640, 2900)
        'ALB42'
    """
    best_match = None
    min_difference = float('inf')

    for book_key, dimensions in BOOK_SIZES.items():
        page_width = dimensions['pageWidth']
        page_height = dimensions['pageHeight']

        # Calculate total absolute difference
        width_diff = abs(width - page_width/2)
        height_diff = abs(height - page_height)
        total_diff = width_diff + height_diff

        if total_diff < min_difference:
            min_difference = total_diff
            best_match = book_key

    return best_match


def calculate_resize_impact(old_width: float, old_height: float, 
                           new_width: float, new_height: float,
                           scaling_rule: str, bleed_mm: float = 0) -> dict:
    """Calculate the impact of resizing a page with a given scaling rule.
    
    Args:
        old_width: Current page width in MCF units
        old_height: Current page height in MCF units
        new_width: Target page width in MCF units
        new_height: Target page height in MCF units
        scaling_rule: One of the 5 scaling options
        bleed_mm: Bleed amount in mm (typically 0 or 3)
    
    Returns:
        Dictionary containing:
            - 'crop_left_mm': Amount cropped from left edge (mm)
            - 'crop_right_mm': Amount cropped from right edge (mm)
            - 'crop_top_mm': Amount cropped from top edge (mm)
            - 'crop_bottom_mm': Amount cropped from bottom edge (mm)
            - 'margin_left_mm': Margin added to left edge (mm)
            - 'margin_right_mm': Margin added to right edge (mm)
            - 'margin_top_mm': Margin added to top edge (mm)
            - 'margin_bottom_mm': Margin added to bottom edge (mm)
            - 'aspect_ratio_change_pct': Percentage change in aspect ratio
            - 'photo_crop_pct': Estimated percentage of photo cropping due to aspect ratio change
            - 'scale_x': Horizontal scaling factor
            - 'scale_y': Vertical scaling factor
    """
    MM_TO_MCF = 10.0
    bleed_mcf = bleed_mm * MM_TO_MCF
    
    # Initialize result
    result = {
        'crop_left_mm': 0,
        'crop_right_mm': 0,
        'crop_top_mm': 0,
        'crop_bottom_mm': 0,
        'margin_left_mm': 0,
        'margin_right_mm': 0,
        'margin_top_mm': 0,
        'margin_bottom_mm': 0,
        'aspect_ratio_change_pct': 0,
        'photo_crop_pct': 0,
        'scale_x': 1.0,
        'scale_y': 1.0,
    }
    
    # Calculate old and new aspect ratios
    old_aspect = old_width / old_height
    new_aspect = new_width / new_height
    aspect_change_pct = ((new_aspect - old_aspect) / old_aspect) * 100
    result['aspect_ratio_change_pct'] = aspect_change_pct
    
    # Calculate content area (excluding bleed)
    old_content_width = old_width - 2 * bleed_mcf
    old_content_height = old_height - 2 * bleed_mcf
    new_content_width = new_width - 2 * bleed_mcf
    new_content_height = new_height - 2 * bleed_mcf
    
    if scaling_rule == 'None':
        # No scaling, just place content
        # Content keeps its original size
        result['scale_x'] = 1.0
        result['scale_y'] = 1.0
        
        # Calculate margins/cropping (no centering)
        # Horizontal
        width_diff_mcf = new_content_width - old_content_width
        if width_diff_mcf > 0:
            # New page is wider - add margin on right
            result['margin_right_mm'] = width_diff_mcf / MM_TO_MCF
        else:
            # New page is narrower - crop right
            result['crop_right_mm'] = -width_diff_mcf / MM_TO_MCF
        
        # Vertical
        height_diff_mcf = new_content_height - old_content_height
        if height_diff_mcf > 0:
            # New page is taller - add margin on bottom
            result['margin_bottom_mm'] = height_diff_mcf / MM_TO_MCF
        else:
            # New page is shorter - crop bottom
            result['crop_bottom_mm'] = -height_diff_mcf / MM_TO_MCF
    
    elif scaling_rule == 'None (center on page)':
        # No scaling, but center content
        result['scale_x'] = 1.0
        result['scale_y'] = 1.0
        
        # Horizontal
        width_diff_mcf = new_content_width - old_content_width
        if width_diff_mcf > 0:
            # New page is wider - split margin equally
            margin_each = width_diff_mcf / 2 / MM_TO_MCF
            result['margin_left_mm'] = margin_each
            result['margin_right_mm'] = margin_each
        else:
            # New page is narrower - split crop equally
            crop_each = -width_diff_mcf / 2 / MM_TO_MCF
            result['crop_left_mm'] = crop_each
            result['crop_right_mm'] = crop_each
        
        # Vertical
        height_diff_mcf = new_content_height - old_content_height
        if height_diff_mcf > 0:
            # New page is taller - split margin equally
            margin_each = height_diff_mcf / 2 / MM_TO_MCF
            result['margin_top_mm'] = margin_each
            result['margin_bottom_mm'] = margin_each
        else:
            # New page is shorter - split crop equally
            crop_each = -height_diff_mcf / 2 / MM_TO_MCF
            result['crop_top_mm'] = crop_each
            result['crop_bottom_mm'] = crop_each
    
    elif scaling_rule == 'Fit (may have margins)':
        # Scale uniformly to fit, tightest dimension fits exactly
        scale_x = new_content_width / old_content_width
        scale_y = new_content_height / old_content_height
        scale = min(scale_x, scale_y)  # Use tightest dimension
        
        result['scale_x'] = scale
        result['scale_y'] = scale
        
        # Scaled content dimensions
        scaled_width = old_content_width * scale
        scaled_height = old_content_height * scale
        
        # Calculate margins (centering scaled content)
        width_diff_mcf = new_content_width - scaled_width
        if width_diff_mcf > 0:
            margin_each = width_diff_mcf / 2 / MM_TO_MCF
            result['margin_left_mm'] = margin_each
            result['margin_right_mm'] = margin_each
        
        height_diff_mcf = new_content_height - scaled_height
        if height_diff_mcf > 0:
            margin_each = height_diff_mcf / 2 / MM_TO_MCF
            result['margin_top_mm'] = margin_each
            result['margin_bottom_mm'] = margin_each
        
        # No cropping with this option (it creates margins instead)
    
    elif scaling_rule == 'Fill (crop to avoid margins)':
        # Scale uniformly to fill, loosest dimension fills exactly
        scale_x = new_content_width / old_content_width
        scale_y = new_content_height / old_content_height
        scale = max(scale_x, scale_y)  # Use loosest dimension to fill
        
        result['scale_x'] = scale
        result['scale_y'] = scale
        
        # Scaled content dimensions
        scaled_width = old_content_width * scale
        scaled_height = old_content_height * scale
        
        # Calculate cropping (centering scaled content)
        width_diff_mcf = scaled_width - new_content_width
        if width_diff_mcf > 0:
            crop_each = width_diff_mcf / 2 / MM_TO_MCF
            result['crop_left_mm'] = crop_each
            result['crop_right_mm'] = crop_each
        
        height_diff_mcf = scaled_height - new_content_height
        if height_diff_mcf > 0:
            crop_each = height_diff_mcf / 2 / MM_TO_MCF
            result['crop_top_mm'] = crop_each
            result['crop_bottom_mm'] = crop_each
        
        # Estimate photo cropping due to uniform scaling with different aspect ratio
        if abs(aspect_change_pct) > 0.01:
            # Photos will be cropped to fit their rectangles
            # The tighter dimension determines the crop percentage
            aspect_ratio_factor = abs(1 - old_aspect / new_aspect)
            result['photo_crop_pct'] = aspect_ratio_factor * 100
    
    elif scaling_rule == 'Fill (may change aspect ratio)':
        # Scale each dimension independently to fill exactly
        scale_x = new_content_width / old_content_width
        scale_y = new_content_height / old_content_height
        
        result['scale_x'] = scale_x
        result['scale_y'] = scale_y
        
        # No margins or cropping of the page content - fills exactly
        # However, layout rectangles now have different aspect ratios
        # Photos are cropped to fit their rectangles, so aspect ratio change
        # means photos will be cropped differently
        if abs(aspect_change_pct) > 0.01:
            # Photos will be cropped to fit rectangles with new aspect ratio
            # Estimate the crop percentage based on aspect ratio change
            aspect_ratio_factor = abs(1 - old_aspect / new_aspect)
            result['photo_crop_pct'] = aspect_ratio_factor * 100
    
    return result


class ResizeTransformer:
    """Transforms coordinates from original book size to resized book size.
    
    This class handles coordinate transformation when resizing photobooks, applying
    the selected scaling mode to convert rectangles from the original page dimensions
    to the target page dimensions.
    """
    
    def __init__(self, old_width_mcf: int, old_height_mcf: int, 
                 new_width_mcf: int, new_height_mcf: int,
                 scaling_mode: str, bleed_mm: float = 3):
        """Initialize resize transformer.
        
        Args:
            old_width_mcf: Original single page width in MCF units
            old_height_mcf: Original page height in MCF units
            new_width_mcf: Target single page width in MCF units
            new_height_mcf: Target page height in MCF units
            scaling_mode: One of 5 scaling modes from resize_gui
            bleed_mm: Bleed amount in mm (typically 3)
        """
        self.old_width = old_width_mcf
        self.old_height = old_height_mcf
        self.new_width = new_width_mcf
        self.new_height = new_height_mcf
        self.scaling_mode = scaling_mode
        self.bleed_mm = bleed_mm
        
        MM_TO_MCF = 10.0
        bleed_mcf = bleed_mm * MM_TO_MCF
        
        # Calculate content areas (excluding bleed)
        old_content_width = old_width_mcf - 2 * bleed_mcf
        old_content_height = old_height_mcf - 2 * bleed_mcf
        new_content_width = new_width_mcf - 2 * bleed_mcf
        new_content_height = new_height_mcf - 2 * bleed_mcf
        
        # Calculate scaling factors and offsets based on mode
        if scaling_mode == 'None':
            self.scale_x = 1.0
            self.scale_y = 1.0
            self.offset_x = 0
            self.offset_y = 0
            
        elif scaling_mode == 'None (center on page)':
            self.scale_x = 1.0
            self.scale_y = 1.0
            # Center content in new page
            self.offset_x = (new_content_width - old_content_width) / 2
            self.offset_y = (new_content_height - old_content_height) / 2
            
        elif scaling_mode == 'Fit (may have margins)':
            # Scale uniformly, tightest dimension fits exactly
            scale_x_ratio = new_content_width / old_content_width
            scale_y_ratio = new_content_height / old_content_height
            self.scale_x = min(scale_x_ratio, scale_y_ratio)
            self.scale_y = self.scale_x  # Uniform scaling
            
            # Center scaled content
            scaled_width = old_content_width * self.scale_x
            scaled_height = old_content_height * self.scale_y
            self.offset_x = (new_content_width - scaled_width) / 2
            self.offset_y = (new_content_height - scaled_height) / 2
            
        elif scaling_mode == 'Fill (crop to avoid margins)':
            # Scale uniformly, loosest dimension fills exactly
            scale_x_ratio = new_content_width / old_content_width
            scale_y_ratio = new_content_height / old_content_height
            self.scale_x = max(scale_x_ratio, scale_y_ratio)
            self.scale_y = self.scale_x  # Uniform scaling
            
            # Center scaled content (may crop)
            scaled_width = old_content_width * self.scale_x
            scaled_height = old_content_height * self.scale_y
            self.offset_x = (new_content_width - scaled_width) / 2
            self.offset_y = (new_content_height - scaled_height) / 2
            
        elif scaling_mode == 'Fill (may change aspect ratio)':
            # Scale independently to fill exactly
            self.scale_x = new_content_width / old_content_width
            self.scale_y = new_content_height / old_content_height
            self.offset_x = 0
            self.offset_y = 0
        else:
            raise ValueError(f"Unknown scaling mode: {scaling_mode}")
        
        # Store bleed for later use
        self.bleed_mcf = bleed_mcf
    
    def transform_page_dimensions(self):
        """Get transformed page dimensions.
        
        Returns:
            Tuple[int, int]: (new_page_width_mcf, new_page_height_mcf)
        """
        return (self.new_width, self.new_height)
    
    def transform_rect(self, left_mcf: float, top_mcf: float, 
                      width_mcf: float, height_mcf: float,
                      origin_left: float = 0) -> tuple:
        """Transform a rectangle from old to new coordinate system.
        
        Args:
            left_mcf: Left position in original MCF spread coordinates
            top_mcf: Top position in original MCF coordinates
            width_mcf: Width in original MCF units
            height_mcf: Height in original MCF units
            origin_left: ORIGINAL origin offset for right pages (old_width for right, 0 for left)
        
        Returns:
            Tuple[int, int, int, int]: (new_left_mcf, new_top_mcf, new_width_mcf, new_height_mcf)
            Returns coordinates in NEW spread coordinate system (using new_width for right pages)
            Always returns transformed coordinates, even if they end up off-page
        """
        # Convert from OLD spread coordinates to page-relative coordinates
        page_relative_left = left_mcf - origin_left
        
        # Apply transformation relative to content area (accounting for bleed)
        # Content starts at bleed_mcf from the page edge
        content_relative_left = page_relative_left
        content_relative_top = top_mcf
        
        # Apply scaling and offset
        new_content_left = content_relative_left * self.scale_x + self.offset_x
        new_content_top = content_relative_top * self.scale_y + self.offset_y
        new_width = width_mcf * self.scale_x
        new_height = height_mcf * self.scale_y
        
        # Convert back to page coordinates (add bleed back)
        new_page_left = new_content_left
        new_page_top = new_content_top
        
        # Convert back to NEW spread coordinates
        # For right pages: add NEW origin_left (new_width), not old origin_left
        new_origin_left = self.new_width if origin_left > 0 else 0
        new_spread_left = new_page_left + new_origin_left
        
        # Always return transformed coordinates, even if off-page
        # For rendering/display, we want to show everything so the user can see what happened
        # Content that ends up off-page after transformation is still visible to the user
        return (int(new_spread_left), int(new_page_top), int(new_width), int(new_height))
    
    def transform_origin_left(self, origin_left: float) -> int:
        """Transform origin_left for right pages.
        
        For right pages, origin_left equals the old page width (in MCF spread coordinates).
        After resizing, it should equal the new page width.
        
        Args:
            origin_left: Original origin_left value
        
        Returns:
            int: Transformed origin_left value
        """
        if origin_left > 0:
            # This is a right page (origin_left == old page width)
            # Return new page width
            return self.new_width
        else:
            # Left page or no origin adjustment needed
            return 0
