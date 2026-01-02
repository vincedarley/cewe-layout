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
from ..book.mcf_writer import write_mcf_project
from ..book.utils import BOOK_SIZES
from ..photos import get_image_dimensions
from ..writer import _calculate_cutout

logger = logging.getLogger(__name__)


class MimeoCoordinateTransformer:
    """Transforms coordinates from Mimeo units to MCF spread units with scaling/padding.
    
    Mimeo coordinate system: Origin at BOTTOM-LEFT (0,0), Y increases upward
    CEWE/MCF coordinate system: Origin at TOP-LEFT (0,0), Y increases downward
    """
    
    def __init__(self, 
                 mimeo_page_width: float, 
                 mimeo_page_height: float,
                 cewe_page_width_mcf: int,
                 cewe_page_height_mcf: int,
                 padding_left: float = 0.0,
                 padding_top: float = 0.0,
                 padding_right: float = 0.0,
                 padding_bottom: float = 0.0,
                 mode: str = 'identity'):
        """Initialize coordinate transformer.
        
        Args:
            mimeo_page_width: Width of Mimeo page in Mimeo units
            mimeo_page_height: Height of Mimeo page in Mimeo units (from bottom to top)
            cewe_page_width_mcf: Width of single CEWE page in MCF units (0.1mm)
            cewe_page_height_mcf: Height of CEWE page in MCF units (0.1mm)
            padding_left/top/right/bottom: Padding in MCF units
            mode: 'fit' (maintain aspect ratio) or 'fill' (stretch)
        """
        self.mimeo_page_width = mimeo_page_width
        self.mimeo_page_height = mimeo_page_height
        self.cewe_page_width_mcf = cewe_page_width_mcf
        self.cewe_page_height_mcf = cewe_page_height_mcf
        self.mode = mode
        
        # Calculate available space after padding
        available_width = cewe_page_width_mcf - padding_left - padding_right
        available_height = cewe_page_height_mcf - padding_top - padding_bottom
        
        if mode == 'fit':
            # Maintain aspect ratio - scale uniformly
            scale_x = available_width / mimeo_page_width
            scale_y = available_height / mimeo_page_height
            self.scale = min(scale_x, scale_y)
            
            # Calculate centering offsets
            scaled_width = mimeo_page_width * self.scale
            scaled_height = mimeo_page_height * self.scale
            self.offset_x = padding_left + (available_width - scaled_width) / 2
            self.offset_y = padding_top + (available_height - scaled_height) / 2
        else:
            # Stretch to fill
            self.scale_x = available_width / mimeo_page_width
            self.scale_y = available_height / mimeo_page_height
            self.offset_x = padding_left
            self.offset_y = padding_top
    
    def transform(self, mimeo_x: float, mimeo_y: float, mimeo_w: float, mimeo_h: float, is_right_page: bool = False) -> Tuple[int, int, int, int]:
        """Transform Mimeo coordinates to MCF spread coordinates.
        
        Mimeo uses bottom-left origin (0,0), CEWE uses top-left origin.
        This method handles coordinate system conversion and scaling.
        
        Args:
            mimeo_x, mimeo_y: CENTER position in Mimeo units (bottom-left origin, Y increases upward)
            mimeo_w, mimeo_h: Size in Mimeo units
            is_right_page: If True, offset by page_width for right side positioning
            
        Returns:
            (x_mcf_spread, y_mcf, w_mcf, h_mcf) in MCF spread coordinates (top-left origin)
        """
        # Convert from center coordinates to top-left coordinates
        # In Mimeo (bottom-left origin): top-left = (center_x - w/2, center_y + h/2)
        # But we need to flip Y to top-left origin: y_topLeft = page_height - y_bottomLeft
        # So: y_mcf_topLeft = page_height - (center_y + h/2)
        #                   = page_height - center_y - h/2
        mimeo_x_topleft = mimeo_x - mimeo_w / 2
        mimeo_y_topleft = self.mimeo_page_height - mimeo_y - mimeo_h / 2
        
        if self.mode == 'identity':
            # No scaling, coordinates are already in MCF units
            mcf_x = int(mimeo_x_topleft)
            mcf_y = int(mimeo_y_topleft)
            mcf_w = int(mimeo_w)
            mcf_h = int(mimeo_h)
        elif self.mode == 'fit':
            mcf_x = int(mimeo_x_topleft * self.scale + self.offset_x)
            mcf_y = int(mimeo_y_topleft * self.scale + self.offset_y)
            mcf_w = int(mimeo_w * self.scale)
            mcf_h = int(mimeo_h * self.scale)
        else:  # 'fill' mode
            mcf_x = int(mimeo_x_topleft * self.scale_x + self.offset_x)
            mcf_y = int(mimeo_y_topleft * self.scale_y + self.offset_y)
            mcf_w = int(mimeo_w * self.scale_x)
            mcf_h = int(mimeo_h * self.scale_y)
        
        # Apply spread positioning: right pages offset by page_width
        if is_right_page:
            mcf_x += self.cewe_page_width_mcf
        
        return mcf_x, mcf_y, mcf_w, mcf_h


def convert_ppb_to_xmcf(ppb_path: Path,
                       photos_library_path: Path,
                       output_path: Path,
                       book_size_id: Optional[str] = None,
                       padding_mm: Tuple[float, float, float, float] = (0, 0, 0, 0),
                       coordinate_mode: str = 'identity',
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
    # These represent the actual page size (e.g., 909 x 702 for typical Mimeo photobook)
    # Note: Frames may extend beyond page bounds ("bleed" system) and may overlap slightly
    layouts = mimeo_data['layouts']
    if not layouts:
        raise ValueError("No layouts found in Mimeo project")
    
    first_layout = layouts[0]
    if 'width' not in first_layout or 'height' not in first_layout:
        raise ValueError("Layout width/height not found in database")
    
    mimeo_page_width = first_layout['width']
    mimeo_page_height = first_layout['height']
    
    if verbose:
        logger.info(f"Detected Mimeo page: {mimeo_page_width:.2f} x {mimeo_page_height:.2f} units")
    
    # Determine CEWE book size
    if book_size_id is None:
        book_size_id = 'ALB42'  # 33x25cm → ALB42 closest
        if verbose:
            logger.info(f"Auto-selected: {book_size_id}")
    
    if book_size_id not in BOOK_SIZES:
        raise ValueError(f"Unknown book size: {book_size_id}")
    
    cewe_dimensions = BOOK_SIZES[book_size_id]
    
    # Convert padding from mm to MCF units
    padding_mcf = tuple(int(p * 10) for p in padding_mm)
    
    # Create coordinate transformer
    transformer = MimeoCoordinateTransformer(
        mimeo_page_width,
        mimeo_page_height,
        cewe_dimensions['pageWidth'] // 2,  # Single page width
        cewe_dimensions['pageHeight'],
        *padding_mcf,
        coordinate_mode
    )
    
    if verbose:
        logger.info(f"Transformer config:")
        logger.info(f"  Mimeo page: {mimeo_page_width} x {mimeo_page_height}")
        logger.info(f"  CEWE single page: {cewe_dimensions['pageWidth'] // 2} x {cewe_dimensions['pageHeight']}")
        logger.info(f"  CEWE spread: {cewe_dimensions['pageWidth']} x {cewe_dimensions['pageHeight']}")
        logger.info(f"  Mode: {coordinate_mode}")
        if coordinate_mode == 'fill':
            logger.info(f"  Scale X: {transformer.scale_x:.4f}, Scale Y: {transformer.scale_y:.4f}")
    
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
    write_mcf_project(
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
    
    # Use page dimensions from database
    # Note: We use the database-stored page dimensions (e.g., 909 x 702) rather than 
    # calculating from frames, because frames may extend beyond page bounds (bleed system)
    # IMPORTANT: Use a CONTENT page's dimensions, not the cover (layout 0 or last)
    # Content pages start at layout index 2 (after front cover and inside front)
    if len(layouts) < 3:
        raise ValueError("Not enough layouts - need at least front, inside front, and one content page")
    
    if 'width' not in layouts[2] or 'height' not in layouts[2]:
        raise ValueError("Layout width/height not found in database")
    
    page_width = layouts[2]['width']  # First content page (layout index 2)
    page_height = layouts[2]['height']
    
    # Calculate MCF dimensions once (all pages same size)
    _, _, mcf_page_width, mcf_page_height = transformer.transform(0, 0, page_width, page_height)
    
    if verbose:
        logger.info(f"Page dimensions:")
        logger.info(f"  Mimeo: {page_width} x {page_height}")
        logger.info(f"  MCF single page (after transform): {mcf_page_width} x {mcf_page_height}")
        logger.info(f"  page_data width (SINGLE page): {mcf_page_width} x {mcf_page_height}")
    
    for layout_idx, layout in enumerate(layouts):
        page_id = layout['model_id']
        page_frames = frames_by_page.get(page_id, [])
        
        page_nr = layout_idx + 1
        
        # Calculate MCF page identifier and positioning
        if layout_idx == 0:
            mcf_page = 'F'
            is_right_page = True  # Front cover on RIGHT
        elif layout_idx == 1:
            mcf_page = 'IF'
            is_right_page = False  # Inside front on LEFT (page 0)
        elif layout_idx == len(layouts) - 1:
            mcf_page = 'B'
            is_right_page = False  # Back cover on LEFT
        else:
            mcf_page = layout_idx - 1  # Content pages start at 1 (after F and IF)
            is_right_page = (mcf_page % 2 == 1)  # Odd pages are RIGHT
        
        # Build page data dict with MCF page dimensions
        # NOTE: page_data['width'] should be SINGLE page width, not spread width
        # mcf_writer multiplies by 2 internally to get spread width
        page_data = {
            'width': mcf_page_width,  # Single page width
            'height': mcf_page_height,
            'images': [],
            'text_blocks': []
        }
        
        # Debug output
        if verbose:
            logger.info(f"PAGE {page_nr} Mimeo (MCF={mcf_page}) (page_id={page_id}): {len(page_frames)} frames")
        
        for frame_idx, frame in enumerate(page_frames):
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
                
                # Transform frame coordinates for text positioning
                mcf_x_spread, mcf_y, mcf_w, mcf_h = transformer.transform(
                    frame['x'], frame['y'], frame['width'], frame['height'],
                    is_right_page=is_right_page
                )
                
                # Parse color (format: "R,G,B,A" where values are 0.0-255.0)
                try:
                    color_parts = color_str.split(',')
                    r, g, b = [float(c) for c in color_parts[:3]]
                    # Convert to integer RGB (0-16777215)
                    color_int = int(r) << 16 | int(g) << 8 | int(b)
                except:
                    color_int = 0  # Black default
                
                # Add text block to page data
                text_block = {
                    'text': text_content,
                    'left': mcf_x_spread,
                    'top': mcf_y,
                    'width': mcf_w,
                    'height': mcf_h,
                    'font': style_name,
                    'size': 12.0,  # Default size, Mimeo doesn't seem to store this
                    'color': color_int,
                    'flags': 0,  # No special flags for now
                }
                
                page_data['text_blocks'].append(text_block)
                
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
            
            image_dims = get_image_dimensions(photo_path)
            if not image_dims:
                logger.warning(f"Could not read dimensions: {photo_path}")
                continue
            
            image_width, image_height = image_dims
            
            # Calculate cutout
            scale, cutout_left, cutout_top = _calculate_cutout(
                frame['width'], frame['height'], image_width, image_height
            )
            
            # Transform Mimeo coordinates to MCF spread coordinates
            # Transformer handles left/right page positioning internally
            mcf_x_spread, mcf_y, mcf_w, mcf_h = transformer.transform(
                frame['x'], frame['y'], frame['width'], frame['height'],
                is_right_page=is_right_page
            )
            
            if verbose and page_nr <= 3 and frame_idx == 0:  # Debug first frame of first 3 pages
                logger.info(f"  Frame 0 transform:")
                logger.info(f"    Mimeo: x={frame['x']:.1f}, y={frame['y']:.1f}, w={frame['width']:.1f}, h={frame['height']:.1f}")
                logger.info(f"    MCF spread: x={mcf_x_spread}, y={mcf_y}, w={mcf_w}, h={mcf_h}")
                logger.info(f"    is_right_page: {is_right_page}")
            
            # Store image data in MCF spread coordinates - mcf_writer will generate filename with proper ui_page
            # We provide the data bytes for it to write
            image_data = {
                'left': mcf_x_spread,
                'top': mcf_y,
                'width': mcf_w,
                'height': mcf_h,
                'data': photo_path.read_bytes(),  # Provide bytes for mcf_writer to save with correct filename
                'format': photo_path.suffix.lstrip('.').lower(),
                'index': global_photo_idx,  # Sequential index for image naming
                'cutout_scale': scale,
                'cutout_left': cutout_left,
                'cutout_top': cutout_top,
                'original_width': image_width,
                'original_height': image_height,
                'camera_filename': photo_info['original_filename'],  # Original camera filename (e.g., IMG_7750.JPG)
                'original_filename': photo_path.name  # Filesystem UUID name for debug
            }
            
            page_data['images'].append(image_data)
            photos_copied += 1
            global_photo_idx += 1  # Increment for next photo
        
        pages.append(page_data)
    
    # Insert empty inside back cover page before the last page (back cover)
    # Mimeo has 89 pages, CEWE needs 90 (front, inside front, content, inside back, back)
    empty_inside_back = {
        'width': mcf_page_width,  # Single page width
        'height': mcf_page_height,
        'images': [],
        'text_blocks': []
    }
    pages.insert(-1, empty_inside_back)  # Insert before last page
    
    if verbose:
        logger.info(f"Processed {photos_copied} photos from Mimeo project")
        logger.info(f"Added empty inside back cover page (total pages: {len(pages)})")
    
    # Create metadata
    metadata = {
        'title': mimeo_data['metadata'].get('name', 'Converted from Mimeo'),
        'author': '',
        'description': 'Converted from Mimeo Photos'
    }
    
    return MimeoPhotobook(pages, metadata)
