"""Convert Mimeo Photos .ppb projects to CEWE .xmcf format.

This module converts legacy Mimeo Photos photobook projects to CEWE format,
copying and renaming photos into the .xmcf directory.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging

from .mimeo_database import MimeoProject
from .mimeo_uuid import PhotosLibraryMapper
from .mimeo_photobook import MimeoPhotobook
from ..book.mcf_writer import photobook_write_to_mcf
from ..book.utils import BOOK_SIZES
from ..photos import get_image_dimensions
from ..mcf_layout_change import _calculate_cutout
from ..colour_utils import find_closest_color_code
import re

logger = logging.getLogger(__name__)


def parse_mimeo_text_style(style_name: str) -> Tuple[str, float]:
    """Parse Mimeo textStyleName into font family and size.
    
    Mimeo encodes font information as: FontFamily[Weight]SizeCode
    where SizeCode = size_in_points * 100
    
    Examples:
        'HelveticaNeue1822' → ('Helvetica Neue', 18.22)
        'HelveticaNeueBold3846' → ('Helvetica Neue-Bold', 38.46)
        'HelveticaNeue911' → ('Helvetica Neue', 9.11)
    
    Args:
        style_name: Mimeo textStyleName (e.g., 'HelveticaNeueBold3846')
        
    Returns:
        Tuple of (font_name, size_in_points)
    """
    if not style_name:
        return ('Helvetica Neue', 12.0)  # Default
    
    # Parse pattern: FontFamily[Weight]Numbers
    match = re.match(r'^([A-Za-z]+?)([A-Z][a-z]+)?(\d+)$', style_name)
    
    if not match:
        logger.warning(f"Could not parse text style name: {style_name}")
        return ('Helvetica Neue', 12.0)
    
    font_family = match.group(1)
    font_weight = match.group(2) or ''
    size_code = match.group(3)
    
    # Convert font family (e.g., 'Helvetica' → 'Helvetica', 'HelveticaNeue' → 'Helvetica Neue')
    # Insert spaces before capital letters (but not at start)
    font_family_spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', font_family)
    
    # Build full font name
    if font_weight and font_weight not in ['Neue']:  # 'Neue' is part of family name
        font_name = f"{font_family_spaced}-{font_weight}"
    else:
        font_name = font_family_spaced
    
    # Parse size (encoded as size * 100)
    try:
        size_pt = int(size_code) / 100.0
    except ValueError:
        logger.warning(f"Could not parse size from: {size_code}")
        size_pt = 12.0
    
    return (font_name, size_pt)


class MimeoCoordinateTransformer:
    """Transforms coordinates from Mimeo units to MCF spread units.
    
    Mimeo coordinate system: 
    - Origin at BOTTOM-LEFT (0,0), Y increases upward
    - Coordinates are in Points.
    - Coordinates are center-based
    - Coordinates are per-single-page
    - Bleed allowed on ALL 4 edges
    
    CEWE/MCF coordinate system: 
    - Origin at TOP-LEFT (0,0), Y increases downward
    - Coordinates are in MCF units (0.1 mm)
    - Coordinates are top-left-based
    - Coordinates are per-spread (left + right pages) - so things on right hand pages all have very high X values.
    - Bleed allowed on 3 edges only (NOT on spine/binding edge)
    
    This transformer performs coordinate system conversion and adjusts bleed to match CEWE constraints.
    
    Bleed adjustment rules:
    - Left pages: Can bleed left (outer edge), NOT right (spine)
    - Right pages: Can bleed right (outer edge), NOT left (spine)
    - Spine bleed is clipped (small overhang) or indicates spread-spanning photo (large overhang, preserved)
    - Excessive outer-edge bleed (>2cm) triggers warning but is preserved
    """
    
    # Conversion factor from points to MCF units
    # 1 point = 1/72 inch = 25.4mm/72 = 0.352778mm = 3.527778 MCF units
    POINTS_TO_MCF = 25.4 / 72 / 0.1  # 3.527778
    
    # Maximum allowed bleed on outer edges (in MCF units)
    # Frames extending beyond this are considered spread-spanning, not bleed
    MAX_BLEED_MCF = 200  # 2cm = 200 MCF
    
    def __init__(self):
        """Initialize coordinate transformer.
        
        Note: Page dimensions are now passed per-transform to support different sizes
        for covers vs content pages.
        """
        pass
        
    
    def transform(self, mimeo_x: float, mimeo_y: float, mimeo_w: float, mimeo_h: float, 
                  mimeo_page_width: float, mimeo_page_height: float,
                  is_right_page: bool = False) -> Tuple[int, int, int, int]:
        """Transform Mimeo coordinates to MCF spread coordinates with bleed adjustment.
        
        Args:
            mimeo_x, mimeo_y: CENTER position in points (bottom-left origin, Y increases upward)
            mimeo_w, mimeo_h: Size in points
            mimeo_page_width: Width of this specific page in points (covers may differ from content)
            mimeo_page_height: Height of this specific page in points
            is_right_page: If True, this is a right-hand page (offset x by page_width for spread positioning)
            
        Returns:
            (x_mcf_spread, y_mcf, w_mcf, h_mcf) in CEWE spread coordinates (top-left origin, MCF units)
            with bleed adjusted to CEWE constraints (no spine bleed)
        """
        # Step 1: Convert from center-based to top-left-based coordinates
        # In Mimeo (center-based): left_edge = center_x - w/2
        mimeo_x_topleft = mimeo_x - mimeo_w / 2
        
        # Step 2: Flip Y axis from bottom-left origin to top-left origin
        # In bottom-left origin: bottom_edge = center_y - h/2
        # In top-left origin: top_edge = page_height - (bottom_edge + h)
        #                              = page_height - (center_y - h/2 + h)
        #                              = page_height - center_y - h/2
        mimeo_y_topleft = mimeo_page_height - mimeo_y - mimeo_h / 2
        
        # Step 3: Convert from per-page to per-spread coordinates
        # Right pages are offset by page_width to position them on the right side of the spread
        if is_right_page:
            mimeo_x_topleft += mimeo_page_width
        
        # Step 4: Convert from points to MCF units
        mcf_x = mimeo_x_topleft * self.POINTS_TO_MCF
        mcf_y = mimeo_y_topleft * self.POINTS_TO_MCF
        mcf_w = mimeo_w * self.POINTS_TO_MCF
        mcf_h = mimeo_h * self.POINTS_TO_MCF
        
        # Calculate MCF page width for bleed adjustment (using this page's dimensions)
        mcf_page_width = int(mimeo_page_width * self.POINTS_TO_MCF)
        
        # Step 5: Adjust bleed to match CEWE constraints (no spine bleed)
        mcf_x, mcf_w = self._adjust_spine_bleed(mcf_x, mcf_w, mcf_page_width, is_right_page)
        
        return int(mcf_x), int(mcf_y), int(mcf_w), int(mcf_h)
    
    def _adjust_spine_bleed(self, mcf_x: float, mcf_w: float, mcf_page_width: int, is_right_page: bool) -> Tuple[float, float]:
        """Adjust frame position/width to remove bleed on spine edge.
        
        CEWE doesn't allow bleed on the spine (binding) edge:
        - Left pages: Spine is on RIGHT (x + w should not exceed page_width)
        - Right pages: Spine is on LEFT (x should not be < page_width)
        
        Outer edge bleed IS allowed and preserved.
        
        Args:
            mcf_x: Left coordinate in MCF spread units
            mcf_w: Width in MCF units
            mcf_page_width: Width of this specific page in MCF units
            is_right_page: True if right page
            
        Returns:
            (adjusted_x, adjusted_w) tuple
        """
        if is_right_page:
            # Right page: spine is on LEFT at x=page_width
            # Remove any bleed into spine (x < page_width)
            if mcf_x < mcf_page_width:
                # Frame bleeds into spine - clip it
                bleed_amount = mcf_page_width - mcf_x
                mcf_x = mcf_page_width
                mcf_w -= bleed_amount
            
            # Outer edge (right edge) bleed is ALLOWED
            # But warn if excessive (>2cm beyond page edge) - likely an error
            right_edge = mcf_x + mcf_w
            page_right_edge = 2 * mcf_page_width
            if right_edge > page_right_edge + self.MAX_BLEED_MCF:
                overhang = right_edge - page_right_edge
                logger.warning(f"Right page frame extends {overhang:.0f} MCF ({overhang/10:.1f}cm) beyond outer edge - possible error")
            
        else:
            # Left page: spine is on RIGHT at x=page_width
            # Remove any bleed into spine (x + w > page_width)
            right_edge = mcf_x + mcf_w
            if right_edge > mcf_page_width:
                overhang = right_edge - mcf_page_width
                # Only clip small bleed; large overhang means spread-spanning photo (preserve it)
                if overhang < self.MAX_BLEED_MCF:
                    mcf_w -= overhang
            
            # Outer edge (left edge) bleed is ALLOWED
            # But warn if excessive (>2cm beyond page edge) - likely an error
            if mcf_x < -self.MAX_BLEED_MCF:
                logger.warning(f"Left page frame extends {abs(mcf_x):.0f} MCF ({abs(mcf_x)/10:.1f}cm) beyond outer edge - possible error")
        
        return mcf_x, mcf_w


def convert_ppb_to_xmcf(ppb_path: Path,
                       photos_library_path: Path,
                       output_path: Path,
                       verbose: bool = False) -> None:
    """Convert Mimeo Photos .ppb project to CEWE .xmcf format."""
    # Read Mimeo project
    logger.info(f"Reading Mimeo project from {ppb_path}")
    mimeo_project = MimeoProject(ppb_path)
    mimeo_data = mimeo_project.extract_all()
    
    if verbose:
        logger.info(f"Project: {mimeo_data['metadata'].get('name', 'Untitled')}")
        logger.info(f"Photos: {len(mimeo_data['photos'])}, Frames: {len(mimeo_data['frames'])}, Pages: {len(mimeo_data['layouts'])}")
    
    # Map photo UUIDs to actual files
    logger.info("Mapping photo UUIDs to Photos library...")
    mapper = PhotosLibraryMapper(photos_library_path)
    
    photo_uuids = [p['photo_id'] for p in mimeo_data['photos']]
    uuid_mappings = mapper.map_mimeo_uuids_batch(photo_uuids)
    
    missing = mapper.get_missing_photos(uuid_mappings)
    if missing and verbose:
        logger.warning(f"{len(missing)} photos not found")
    
    # Get Mimeo page dimensions from database
    # Page dimensions are stored in KHProjectLayout table (width, height columns)
    layouts = mimeo_data['layouts']
    if not layouts:
        raise ValueError("No layouts found in Mimeo project")
    
    if len(layouts) < 3:
        raise ValueError("Need at least 3 layouts (front, inside front, first content)")
    
    if verbose:
        # Show dimension info for first few pages
        for idx in range(min(3, len(layouts))):
            layout = layouts[idx]
            layout_type = ['Front Cover', 'Inside Front', 'First Content'][idx] if idx < 3 else f'Page {idx+1}'
            logger.info(f"{layout_type}: {layout.get('width', '?')} x {layout.get('height', '?')} points")
        
    # Create coordinate transformer (doesn't need dimensions at init - passed per-transform)
    transformer = MimeoCoordinateTransformer()
    
    # Create output directory
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    
    if verbose:
        logger.info(f"Output directory: {output_path}")
    
    # Build photo info map (UUID -> original photo info)
    photo_info_map = {}
    for mimeo_uuid, photo_info in uuid_mappings.items():
        if photo_info and Path(photo_info['path']).exists():
            photo_info_map[mimeo_uuid] = photo_info
    
    if verbose:
        logger.info(f"Found {len(photo_info_map)} photos to convert")
    
    # Build Mimeo photobook from extracted data
    mimeo_photobook = _build_mimeo_photobook(
        mimeo_data,
        photo_info_map,
        transformer,
        output_path,
        verbose
    )
    
    # Use generalized write_mcf_project to create the CEWE project
    photobook_write_to_mcf(
        mimeo_photobook,
        str(output_path),
        verbose=verbose,
        insidecovers=True  # Mimeo books have inside covers
    )
    
    logger.info(f"Created CEWE project at {output_path}")


def _build_mimeo_photobook(mimeo_data: Dict[str, Any],
                          photo_info_map: Dict[str, Dict[str, str]],
                          transformer: MimeoCoordinateTransformer,
                          output_path: Path,
                          verbose: bool) -> MimeoPhotobook:
    """Build MimeoPhotobook from Mimeo database data.
    
    Args:
        mimeo_data: Extracted Mimeo project data
        photo_info_map: Mapping from Mimeo UUID to photo file info
        transformer: Coordinate transformer from Mimeo to MCF units
        output_path: Output directory for copying photos
        verbose: Print detailed info
        
    Returns:
        MimeoPhotobook instance ready for write_mcf_project
    """
    # Process pages
    layouts = mimeo_data['layouts']
    frames = mimeo_data['frames']
    photos = mimeo_data['photos']
    frame_to_photo = mimeo_data['frame_to_photo']  # Dict mapping frame modelId -> photo modelId
    frame_text = mimeo_data['frame_text']  # Dict mapping frame modelId -> text data
    
    if verbose:
        logger.info(f"Total photos: {len(photos)}, Total frames: {len(frames)}")
        logger.info(f"Frame-to-photo mappings: {len(frame_to_photo)}")
        logger.info(f"Frame text content: {len(frame_text)}")
    
    # Build frame lookup by page_id
    # Note: Mimeo stores (x, y) as CENTER of frame with BOTTOM-LEFT origin (Y increases upward)
    # We DON'T convert here - the transformer handles both center→topleft and Y-flip
    # Frames may extend beyond page bounds (bleed system) and may overlap slightly
    frames_by_page = {}
    for frame in frames:
        page_id = frame['page_id']
        if page_id not in frames_by_page:
            frames_by_page[page_id] = []
        
        # Keep original center coordinates - transformer will handle conversion
        frames_by_page[page_id].append(frame)
    
    # Build photo lookup by model_id (not index!)
    photo_by_model_id = {p['model_id']: p for p in photos}
    
    # Track global photo index
    global_photo_idx = 0
    photos_copied = 0
    
    # Build list of page data dicts for MimeoPhotobook
    pages = []
    
    # Track MCF page counter (starts at 1 for first content page, increments by 2 for spreads)
    mcf_page_counter = 1
    
    # Validate we have enough layouts
    if len(layouts) < 3:
        raise ValueError("Not enough layouts - need at least front, inside front, and one content page")
    
    # Get "normal" content page dimensions from layouts[2]
    # This will be used as a fallback when a page has unusual dimensions
    normal_content_layout = layouts[2]
    normal_page_width = normal_content_layout['width']
    normal_page_height = normal_content_layout['height']
    normal_page_area = normal_page_width * normal_page_height
    
    if verbose:
        logger.info(f"Normal content page dimensions: {normal_page_width} x {normal_page_height} points")
        logger.info(f"Normal page area: {normal_page_area:.0f} sq points")
    
    for layout_idx, layout in enumerate(layouts):
        page_id = layout['model_id']
        page_frames = frames_by_page.get(page_id, [])
        
        page_nr = layout_idx + 1
        
        # Check if this is a spread page (layoutTypeId=4)
        layout_type_id = layout.get('layout_type_id', 1)
        is_spread = (layout_type_id == 4)
        
        # Get page dimensions from this specific layout
        if 'width' not in layout or 'height' not in layout:
            raise ValueError(f"Layout {layout_idx} width/height not found in database")
        
        layout_width = layout['width']
        layout_height = layout['height']
        layout_area = layout_width * layout_height
        
        # For spreads, the actual single page width is half the layout width
        if is_spread:
            page_width = layout_width / 2
            page_height = layout_height
            if verbose:
                logger.info(f"Page {page_nr}: SPREAD detected (layoutTypeId={layout_type_id}, width={layout_width:.0f})")
                logger.info(f"  Will create two MCF pages from this spread")
        else:
            page_width = layout_width
            page_height = layout_height        
            # Check if this page's area differs significantly from normal content pages
            # If area differs by >30%, use normal page dimensions instead
            # (Skip this check for spreads as they're intentionally 2x width)
            area_ratio = layout_area / normal_page_area
            if area_ratio < 0.7 or area_ratio > 1.3:
                # Area differs by >30% - force use of normal page dimensions
                page_width = normal_page_width
                page_height = normal_page_height
                if verbose and layout_idx <= 5:
                    logger.info(f"Page {page_nr}: Using normal dimensions (area differs by {abs(1-area_ratio)*100:.0f}%)")
        
        # Calculate MCF dimensions for this specific page (simple unit conversion)
        mcf_page_width = int(page_width * transformer.POINTS_TO_MCF)
        mcf_page_height = int(page_height * transformer.POINTS_TO_MCF)
        
        if verbose and layout_idx <= 2:
            logger.info(f"Page {page_nr} dimensions:")
            logger.info(f"  Mimeo: {page_width} x {page_height}")
            logger.info(f"  MCF: {mcf_page_width} x {mcf_page_height}")
        
        # Determine base MCF page for logging (will be incremented inside loop for spreads)
        if layout_idx == 0:
            base_mcf_page = 'F'
        elif layout_idx == 1:
            base_mcf_page = 'IF'
        elif layout_idx == len(layouts) - 1:
            base_mcf_page = 'B'
        else:
            base_mcf_page = mcf_page_counter
        
        # Build page data dict with MCF page dimensions
        # NOTE: page_data['width'] should be SINGLE page width, not spread width
        # mcf_writer multiplies by 2 internally to get spread width
        page_data = {
            'width': mcf_page_width,  # Single page width
            'height': mcf_page_height,
            'photos': [],
            'texts': []
        }
        
        # Add background color if available
        # Convert Mimeo RGBA color to CEWE color code
        bg_rgba = None
        bg_code = None
        if 'background_color' in layout:
            bg_rgba = layout['background_color']
            bg_code = find_closest_color_code(bg_rgba)
            
            if verbose and page_nr <= 5:
                logger.info(f"  Background: {bg_rgba} -> CEWE code {bg_code}")
        
        # For spread pages, split frames into left and right halves
        if is_spread:
            # The fold is at the center of the spread width
            fold_x = layout_width / 2
            left_frames = [f for f in page_frames if f['x'] < fold_x]
            right_frames = [f for f in page_frames if f['x'] >= fold_x]
            
            if verbose:
                logger.info(f"PAGE {page_nr} Mimeo SPREAD (MCF={base_mcf_page},{base_mcf_page+1}) (page_id={page_id}): {len(page_frames)} frames total")
                logger.info(f"  Left side: {len(left_frames)} frames, Right side: {len(right_frames)} frames")
            
            # We'll create two pages from this spread
            # Store frame lists for each page to process
            pages_to_create = [
                ('left', left_frames),   # (side_name, frames)
                ('right', right_frames)
            ]
        else:
            # Regular single page - process all frames together
            # Debug output
            if verbose:
                logger.info(f"PAGE {page_nr} Mimeo (MCF={base_mcf_page}) (page_id={page_id}): {len(page_frames)} frames")
            
            pages_to_create = [
                (None, page_frames)  
            ]
        
        # Process each page (one for regular pages, two for spreads)
        for side_info in pages_to_create:
            side_name, frames_for_this_page = side_info
            
            # Calculate MCF page identifier for THIS specific page
            if layout_idx == 0:
                mcf_page = 'F'
            elif layout_idx == 1:
                mcf_page = 'IF'
            elif layout_idx == len(layouts) - 1:
                mcf_page = 'B'
            else:
                # For content pages, use current counter value
                mcf_page = mcf_page_counter
            
            # Determine if this is a right page (for coordinate transformation)
            if isinstance(mcf_page, str):
                # Special pages: F=right, IF=left, B=left
                is_right_for_transform = (mcf_page == 'F')
            else:
                # Content pages: odd=right, even=left
                is_right_for_transform = (mcf_page % 2 == 1)
            
            # Build page data dict with MCF page dimensions
            # NOTE: page_data['width'] should be SINGLE page width, not spread width
            # mcf_writer multiplies by 2 internally to get spread width
            page_data = {
                'width': mcf_page_width,  # Single page width
                'height': mcf_page_height,
                'photos': [],
                'texts': []
            }
            
            # Add background color if available
            if bg_code is not None:
                page_data['background_id'] = bg_code
            
            for frame_idx, frame in enumerate(frames_for_this_page):
                frame_id = frame['model_id']
                
                # Check if this frame has a photo
                photo_model_id = frame_to_photo.get(frame_id)
                
                # Check if this frame has text
                text_data = frame_text.get(frame_id)
                
                if photo_model_id is None and text_data is None:
                    # Frame has neither photo nor text (empty or other content type)
                    if verbose and page_nr <= 5:
                        logger.info(f"  Frame {frame_idx} (id={frame_id}): empty (no photo or text)")
                    continue
                
                # Handle text frames
                if text_data and photo_model_id is None:
                    text_content = text_data.get('text', '')
                    text_type = text_data.get('text_type', 0)
                    style_name = text_data.get('style_name', '')
                    color_str = text_data.get('color', '0.00,0.00,0.00,1.00')
                    
                    if verbose and page_nr <= 5:
                        text_preview = text_content[:50] + '...' if len(text_content) > 50 else text_content
                        logger.info(f"  Frame {frame_idx} (id={frame_id}): TEXT type={text_type}, text='{text_preview}'")
                    
                    # Skip page numbers (textType=2) for now
                    if text_type == 2:
                        if verbose and page_nr <= 5:
                            logger.info(f"    Skipping page number frame")
                        continue
                    
                    # Adjust frame coordinates for spreads
                    # For right side of spread, convert from spread coords to right-page coords
                    if is_spread and is_right_for_transform:
                        frame_x = frame['x'] - fold_x
                    else:
                        frame_x = frame['x']
                    
                    # Transform frame coordinates for text positioning
                    mcf_x_spread, mcf_y, mcf_w, mcf_h = transformer.transform(
                        frame_x, frame['y'], frame['width'], frame['height'],
                        page_width, page_height,
                        is_right_page=is_right_for_transform
                    )
                    
                    # Parse color (format: "R,G,B,A" where values are 0.0-255.0)
                    try:
                        color_parts = color_str.split(',')
                        r, g, b = [float(c) for c in color_parts[:3]]
                        # Convert to integer RGB (0-16777215)
                        color_int = int(r) << 16 | int(g) << 8 | int(b)
                    except:
                        color_int = 0  # Black default
                    
                    # Parse font family and size from Mimeo textStyleName
                    font_name, font_size = parse_mimeo_text_style(style_name)
                    
                    if verbose and page_nr <= 5:
                        logger.info(f"    Font: '{font_name}' {font_size}pt (from style '{style_name}')")
                    
                    # Add text block to page data
                    text_block = {
                        'text': text_content,
                        'area_left': mcf_x_spread,
                        'area_top': mcf_y,
                        'area_width': mcf_w,
                        'area_height': mcf_h,
                        'font': font_name,
                        'size': font_size,
                        'color': color_int,
                        'flags': 0,  # No special flags for now
                    }
                    
                    page_data['texts'].append(text_block)
                    
                    if verbose and page_nr <= 5:
                        logger.info(f"    Added text block at ({mcf_x_spread}, {mcf_y}) size {mcf_w}x{mcf_h}")
                    continue
                
                # Handle photo frames
                if photo_model_id is None:
                    # Frame has text but we already handled it above
                    continue
                
                photo = photo_by_model_id.get(photo_model_id)
                
                if verbose and page_nr <= 5:  # Detailed debug for first 5 pages
                    if photo:
                        photo_info = photo_info_map.get(photo['photo_id'])
                        if photo_info:
                            filename = Path(photo_info['path']).name
                            logger.info(f"  Frame {frame_idx} (id={frame_id}): photo_id={photo_model_id}, photo='{filename}'")
                        else:
                            logger.info(f"  Frame {frame_idx} (id={frame_id}): photo_id={photo_model_id}, UUID not in map")
                    else:
                        logger.info(f"  Frame {frame_idx} (id={frame_id}): photo_id={photo_model_id}, NOT FOUND in photos table")
                
                if not photo:
                    if verbose and page_nr <= 5:
                        logger.warning(f"    Photo model_id {photo_model_id} not found in photos table")
                    continue
                    
                photo_info = photo_info_map.get(photo['photo_id'])
                if not photo_info:
                    if verbose and page_nr <= 5:
                        logger.warning(f"    Photo UUID {photo['photo_id'][:20]}... not in photo_info_map")
                    continue
                
                # Get photo path and dimensions
                photo_path = Path(photo_info['path'])
                if not photo_path.exists():
                    if verbose and page_nr <= 5:
                        logger.warning(f"    Photo file not found: {photo_path}")
                    continue
                
                # Load image to get dimensions
                from PIL import Image
                
                img = Image.open(photo_path)
                image_width, image_height = img.size
                
                # Calculate cutout
                scale, cutout_left, cutout_top = _calculate_cutout(
                    frame['width'], frame['height'], image_width, image_height
                )
                
                # Adjust frame coordinates for spreads
                # For right side of spread, convert from spread coords to right-page coords
                if is_spread and is_right_for_transform:
                    frame_x = frame['x'] - fold_x
                else:
                    frame_x = frame['x']
                
                # Transform Mimeo coordinates to MCF spread coordinates
                # Transformer handles left/right page positioning internally
                mcf_x_spread, mcf_y, mcf_w, mcf_h = transformer.transform(
                    frame_x, frame['y'], frame['width'], frame['height'],
                    page_width, page_height,
                    is_right_page=is_right_for_transform
                )
                
                if verbose and page_nr <= 3 and frame_idx == 0:  # Debug first frame of first 3 pages
                    logger.info(f"  Frame 0 transform:")
                    logger.info(f"    Mimeo original: x={frame['x']:.1f}, y={frame['y']:.1f}, w={frame['width']:.1f}, h={frame['height']:.1f}")
                    if is_spread and is_right_for_transform:
                        logger.info(f"    Adjusted for right side: x={frame_x:.1f} (subtracted fold_x={fold_x:.1f})")
                    logger.info(f"    MCF spread: x={mcf_x_spread}, y={mcf_y}, w={mcf_w}, h={mcf_h}")
                    logger.info(f"    MCF page: {mcf_page}, is_right: {is_right_for_transform}")
                
                # Store image data in MCF spread coordinates - mcf_writer will generate filename with proper ui_page
                # We provide the data bytes for it to write
                image_data = {
                    'area_left': mcf_x_spread,
                    'area_top': mcf_y,
                    'area_width': mcf_w,
                    'area_height': mcf_h,
                    'data': photo_path.read_bytes(),
                    'format': photo_path.suffix.lstrip('.').lower(),
                    'index': global_photo_idx,  # Sequential index for image naming
                    'cutout_scale': scale,
                    'cutout_left': cutout_left,
                    'cutout_top': cutout_top,
                    'original_width': image_width,
                    'original_height': image_height,
                    'camera_filename': photo_info['original_filename'],  # Original camera filename (e.g., IMG_7750.JPG)
                    'original_filename': photo_path.name,  # Filesystem UUID name for debug
                    'orientation': photo_info.get('orientation', 1)  # EXIF orientation from Photos database
                }
                
                page_data['photos'].append(image_data)
                photos_copied += 1
                global_photo_idx += 1  # Increment for next photo
            
            # Add this page_data to the pages list
            pages.append(page_data)
            
            # Increment MCF page counter for content pages
            # (Don't increment for front, inside front, or back covers)
            if layout_idx not in [0, 1, len(layouts) - 1]:
                mcf_page_counter += 1
    
    # Insert empty inside back cover page if needed
    # CEWE needs: front, inside front, even number of content pages, inside back, back
    # Count content pages (excluding F, IF, B)
    content_page_count = len(pages) - 3  # Subtract F, IF, B
    
    # Only insert inside back if we have an even number of content pages
    # (so that inside back ends up on the right/odd page)
    if content_page_count % 2 == 0:
        # Even number of content pages - need to add inside back
        content_layout = layouts[2]
        content_width = content_layout['width']
        content_height = content_layout['height']
        content_mcf_width = int(content_width * transformer.POINTS_TO_MCF)
        content_mcf_height = int(content_height * transformer.POINTS_TO_MCF)
        
        empty_inside_back = {
            'width': content_mcf_width,  # Single page width (from content page)
            'height': content_mcf_height,
            'photos': [],
            'texts': []
        }
        pages.insert(-1, empty_inside_back)  # Insert before last page
        
        if verbose:
            logger.info(f"Processed {photos_copied} photos from Mimeo project")
            logger.info(f"Added empty inside back cover page (content_pages={content_page_count}, total pages: {len(pages)})")
    else:
        # Odd number of content pages - inside back would fall on wrong side, skip it
        if verbose:
            logger.info(f"Processed {photos_copied} photos from Mimeo project")
            logger.info(f"Skipping inside back cover (content_pages={content_page_count} is odd, total pages: {len(pages)})")
    
    # Create metadata
    metadata = {
        'title': mimeo_data['metadata'].get('name', 'Converted from Mimeo'),
        'author': '',
        'description': 'Converted from Mimeo Photos'
    }
    
    return MimeoPhotobook(pages, metadata)
