
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
                           transformer: 'ResizeTransformer') -> dict:
    """Calculate the impact of resizing a page by analyzing transformer output.
    
    Instead of duplicating transformation logic, this function uses the actual
    transformer to transform a test rectangle (the full page) and analyzes the
    result to determine the impact.
    
    Args:
        old_width: Current page width in MCF units
        old_height: Current page height in MCF units
        transformer: ResizeTransformer to analyze
    
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
    
    # Get new dimensions from transformer
    new_width, new_height = transformer.transform_page_dimensions()
    
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
        'scale_x': transformer.scale_x,
        'scale_y': transformer.scale_y,
    }
    
    # Calculate old and new aspect ratios
    old_aspect = old_width / old_height
    new_aspect = new_width / new_height
    aspect_change_pct = ((new_aspect - old_aspect) / old_aspect) * 100
    result['aspect_ratio_change_pct'] = aspect_change_pct
    
    # Transform a test rectangle that represents the entire page content area
    # (excluding bleed). This will tell us how content is mapped.
    bleed_mcf = transformer.bleed_mcf
    old_content_width = old_width - 2 * bleed_mcf
    old_content_height = old_height - 2 * bleed_mcf
    new_content_width = new_width - 2 * bleed_mcf
    new_content_height = new_height - 2 * bleed_mcf
    
    # Transform the content rectangle (left page, so origin_left = 0)
    # Start at (0, 0) with size (old_content_width, old_content_height)
    new_left, new_top, transformed_width, transformed_height = transformer.transform_rect(
        0, 0, old_content_width, old_content_height, origin_left=0
    )
    
    # Analyze the transformation result
    # If content starts at negative position, it's cropped from that edge
    # If content ends before the page edge, there's a margin on that edge
    
    # Left edge
    if new_left < 0:
        result['crop_left_mm'] = -new_left / MM_TO_MCF
    elif new_left > 0:
        result['margin_left_mm'] = new_left / MM_TO_MCF
    
    # Top edge
    if new_top < 0:
        result['crop_top_mm'] = -new_top / MM_TO_MCF
    elif new_top > 0:
        result['margin_top_mm'] = new_top / MM_TO_MCF
    
    # Right edge
    new_right = new_left + transformed_width
    if new_right > new_content_width:
        result['crop_right_mm'] = (new_right - new_content_width) / MM_TO_MCF
    elif new_right < new_content_width:
        result['margin_right_mm'] = (new_content_width - new_right) / MM_TO_MCF
    
    # Bottom edge
    new_bottom = new_top + transformed_height
    if new_bottom > new_content_height:
        result['crop_bottom_mm'] = (new_bottom - new_content_height) / MM_TO_MCF
    elif new_bottom < new_content_height:
        result['margin_bottom_mm'] = (new_content_height - new_bottom) / MM_TO_MCF
    
    # Estimate photo cropping for non-uniform scaling or aspect ratio changes
    if abs(result['scale_x'] - result['scale_y']) > 0.001:
        # Non-uniform scaling - aspect ratio of rectangles changed
        # Photos will be cropped to fit their rectangles
        aspect_ratio_factor = abs(1 - old_aspect / new_aspect)
        result['photo_crop_pct'] = aspect_ratio_factor * 100
    elif abs(aspect_change_pct) > 0.01 and transformer.scale_x == transformer.scale_y:
        # Uniform scaling but different page aspect ratios
        # Photos in repositioned rectangles may experience different cropping
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
