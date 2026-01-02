"""Convert Mimeo Photos .ppb projects to CEWE .xmcf format.

This module converts legacy Mimeo Photos photobook projects to CEWE format,
copying and renaming photos into the .xmcf directory.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging
import shutil

from .mimeo_database import MimeoProject
from .mimeo_uuid import PhotosLibraryMapper
from .mimeo_photobook import MimeoPhotobook
from ..book.mcf_writer import write_mcf_project
from ..book.utils import BOOK_SIZES
from ..file_utils import encode_metadata_in_filename
from ..photos import get_image_dimensions
from ..writer import _calculate_cutout

logger = logging.getLogger(__name__)


class MimeoCoordinateTransformer:
    """Transforms coordinates from Mimeo units to MCF units with scaling/padding."""
    
    def __init__(self, 
                 mimeo_page_width: float, 
                 mimeo_page_height: float,
                 cewe_page_width_mcf: int,
                 cewe_page_height_mcf: int,
                 padding_left: float = 0.0,
                 padding_top: float = 0.0,
                 padding_right: float = 0.0,
                 padding_bottom: float = 0.0,
                 mode: str = 'fit'):
        """Initialize coordinate transformer."""
        self.mimeo_page_width = mimeo_page_width
        self.mimeo_page_height = mimeo_page_height
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
    
    def transform(self, mimeo_x: float, mimeo_y: float, mimeo_w: float, mimeo_h: float) -> Tuple[int, int, int, int]:
        """Transform Mimeo coordinates to MCF coordinates."""
        if self.mode == 'fit':
            mcf_x = int(mimeo_x * self.scale + self.offset_x)
            mcf_y = int(mimeo_y * self.scale + self.offset_y)
            mcf_w = int(mimeo_w * self.scale)
            mcf_h = int(mimeo_h * self.scale)
        else:
            mcf_x = int(mimeo_x * self.scale_x + self.offset_x)
            mcf_y = int(mimeo_y * self.scale_y + self.offset_y)
            mcf_w = int(mimeo_w * self.scale_x)
            mcf_h = int(mimeo_h * self.scale_y)
        
        return mcf_x, mcf_y, mcf_w, mcf_h


def convert_ppb_to_xmcf(ppb_path: Path,
                       photos_library_path: Path,
                       output_path: Path,
                       book_size_id: Optional[str] = None,
                       padding_mm: Tuple[float, float, float, float] = (0, 0, 0, 0),
                       coordinate_mode: str = 'fit',
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
    
    # Calculate Mimeo page dimensions from actual frame data
    all_frames = mimeo_data['frames']
    if all_frames:
        max_page_width = max(f['x'] + f['width'] for f in all_frames)
        max_page_height = max(f['y'] + f['height'] for f in all_frames)
        mimeo_page_width = max_page_width
        mimeo_page_height = max_page_height
        
        if verbose:
            logger.info(f"Detected Mimeo page: {mimeo_page_width:.2f} x {mimeo_page_height:.2f} units")
    else:
        mimeo_page_width = 2389.57
        mimeo_page_height = 1066.76
        logger.warning("No frames found, using default dimensions")
    
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
        insidecovers=False  # Mimeo books don't have inside covers
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
    
    # Build frame lookup by page_id
    frames_by_page = {}
    for frame in frames:
        page_id = frame['page_id']
        if page_id not in frames_by_page:
            frames_by_page[page_id] = []
        frames_by_page[page_id].append(frame)
    
    # Build photo lookup by index
    photo_by_index = {p['index']: p for p in photos}
    
    # Track global photo index
    global_photo_idx = 0
    photos_copied = 0
    
    # Build list of page data dicts for MimeoPhotobook
    pages = []
    
    # Calculate page dimensions from first layout (all should be same size)
    if layouts:
        first_page_id = layouts[0]['model_id']
        first_page_frames = frames_by_page.get(first_page_id, [])
        if first_page_frames:
            page_width = max(f['x'] + f['width'] for f in first_page_frames)
            page_height = max(f['y'] + f['height'] for f in first_page_frames)
        else:
            page_width = 2389.57
            page_height = 1066.76
    else:
        page_width = 2389.57
        page_height = 1066.76
    
    for layout_idx, layout in enumerate(layouts):
        page_id = layout['model_id']
        page_frames = frames_by_page.get(page_id, [])
        
        page_nr = layout_idx + 1
        
        # Build page data dict
        page_data = {
            'width': page_width,
            'height': page_height,
            'images': [],
            'text_blocks': []
        }
        
        # Debug output for first 5 pages
        if page_nr <= 5 and verbose:
            logger.info(f"PAGE {page_nr} (page_id={page_id}): {len(page_frames)} frames")
        
        for frame_idx, frame in enumerate(page_frames):
            photo = photo_by_index.get(global_photo_idx)
            global_photo_idx += 1
            
            if not photo:
                continue
                
            photo_info = photo_info_map.get(photo['photo_id'])
            if not photo_info:
                if verbose:
                    logger.warning(f"Photo UUID {photo['photo_id']} not found in photo_info_map")
                continue
            
            # Get photo path and dimensions
            photo_path = Path(photo_info['path'])
            if not photo_path.exists():
                logger.warning(f"Photo not found: {photo_path}")
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
            
            # Encode filename with page number and copy to output
            encoded_filename = encode_metadata_in_filename(
                photo_info['original_filename'],
                preferred_size=1.0,
                page_number=page_nr
            )
            
            dest_path = output_path / encoded_filename
            if not dest_path.exists():
                shutil.copy2(photo_path, dest_path)
            
            # Create image data dict in Mimeo units
            image_data = {
                'left': frame['x'],
                'top': frame['y'],
                'width': frame['width'],
                'height': frame['height'],
                'data': None,  # Not needed - file already copied
                'format': photo_path.suffix.lstrip('.').lower(),
                'filename': encoded_filename,
                'index': global_photo_idx - 1,
                'cutout_scale': scale,
                'cutout_left': cutout_left,
                'cutout_top': cutout_top,
                'original_width': image_width,
                'original_height': image_height
            }
            
            page_data['images'].append(image_data)
            photos_copied += 1
        
        pages.append(page_data)
    
    if verbose:
        logger.info(f"Copied {photos_copied} photos to .xmcf directory")
    
    # Create metadata
    metadata = {
        'title': mimeo_data['metadata'].get('name', 'Converted from Mimeo'),
        'author': '',
        'description': 'Converted from Mimeo Photos'
    }
    
    return MimeoPhotobook(pages, metadata)
