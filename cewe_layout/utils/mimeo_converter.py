"""Convert Mimeo Photos .ppb projects to CEWE .xmcf format.

This module converts legacy Mimeo Photos photobook projects to CEWE format,
reusing existing infrastructure from cewe-layout.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import logging
import shutil

from .mimeo_database import MimeoProject
from .mimeo_uuid import PhotosLibraryMapper

logger = logging.getLogger(__name__)


# CEWE book sizes (duplicated from pdf2cewe to avoid heavy dependencies)
BOOK_SIZES = {
    'ALB42': {'art_id': 42, 'pageWidth': 7640, 'pageHeight': 2900},
    'ALB82': {'art_id': 82, 'pageWidth': 5200, 'pageHeight': 3500},
}


def add_cewe_boilerplate_elements(fotobook: ET.Element, normalpages: int) -> None:
    """Add required CEWE boilerplate elements to fotobook XML."""
    project = ET.SubElement(fotobook, 'project')
    project.set('id', 'cewe-converted')
    
    saving = ET.SubElement(fotobook, 'savingVersion')
    saving.text = '1'
    
    creation = ET.SubElement(fotobook, 'creationHistory')
    creation.set('version', '1')
    
    article = ET.SubElement(fotobook, 'articleConfig')
    article.set('normalpages', str(normalpages))


def encode_metadata_in_filename(original_filename: str, preferred_size: float, page_number: int) -> str:
    """Encode metadata into photo filename."""
    stem = Path(original_filename).stem
    suffix = Path(original_filename).suffix
    return f"{stem}-sz{preferred_size:.2f}-pg{page_number}{suffix}"


def get_image_dimensions(image_path: Path) -> Optional[Tuple[int, int]]:
    """Get image dimensions using PIL."""
    try:
        from PIL import Image
        with Image.open(image_path) as img:
            return img.size
    except Exception as e:
        logger.error(f"Failed to read {image_path}: {e}")
        return None


def _calculate_cutout(area_width: int, area_height: int, image_width: int, image_height: int) -> Tuple[float, float, float]:
    """Calculate cutout scale and offsets."""
    area_aspect = area_width / area_height
    image_aspect = image_width / image_height
    
    if image_aspect > area_aspect:
        # Image wider than area - fit height, crop width
        scale = area_height / image_height
        scaled_image_width = image_width * scale
        cutout_left = (scaled_image_width - area_width) / 2
        cutout_top = 0.0
    else:
        # Image taller than area - fit width, crop height
        scale = area_width / image_width
        scaled_image_height = image_height * scale
        cutout_left = 0.0
        cutout_top = (scaled_image_height - area_height) / 2
    
    return scale, cutout_left, cutout_top


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
    
    # Create output directory and staging for photos
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    
    staging_dir = output_path.parent / f"{output_path.stem}-photos"
    staging_dir.mkdir(parents=True, exist_ok=True)
    if verbose:
        logger.info(f"Staging photos in: {staging_dir}")
    
    # Copy photos to staging
    logger.info("Copying photos to staging...")
    photo_staging_map = {}
    for mimeo_uuid, photo_info in uuid_mappings.items():
        if photo_info and Path(photo_info['path']).exists():
            source_path = Path(photo_info['path'])
            staged_path = staging_dir / photo_info['original_filename']
            
            if not staged_path.exists():
                shutil.copy2(source_path, staged_path)
            
            photo_staging_map[mimeo_uuid] = staged_path
    
    if verbose:
        logger.info(f"Copied {len(photo_staging_map)} photos")
    
    # Create folderid.xml
    import uuid as uuid_module
    folder_id = str(uuid_module.uuid4())
    folderid_xml = ET.Element('folderID')
    folderid_xml.text = folder_id
    tree = ET.ElementTree(folderid_xml)
    tree.write(output_path / 'folderid.xml', encoding='utf-8', xml_declaration=True)
    
    # Build MCF XML
    mcf_xml = create_mcf_from_mimeo(
        mimeo_data,
        uuid_mappings,
        transformer,
        cewe_dimensions,
        book_size_id,
        verbose
    )
    
    # Write data.mcf
    mcf_path = output_path / 'data.mcf'
    tree = ET.ElementTree(mcf_xml)
    ET.indent(tree, space='  ')
    tree.write(mcf_path, encoding='utf-8', xml_declaration=True)
    
    logger.info(f"Created CEWE project at {output_path}")


def create_mcf_from_mimeo(mimeo_data: Dict[str, Any],
                         uuid_mappings: Dict[str, Optional[Dict[str, str]]],
                         transformer: MimeoCoordinateTransformer,
                         cewe_dimensions: Dict[str, int],
                         book_size_id: str,
                         verbose: bool) -> ET.Element:
    """Create MCF XML structure from Mimeo data."""
    # Create root fotobook element
    fotobook = ET.Element('fotobook')
    fotobook.set('version', '4.0')
    fotobook.set('productname', book_size_id)
    fotobook.set('art_id', str(cewe_dimensions['art_id']))
    fotobook.set('imagedir', '')
    fotobook.set('isDataMcf', '0')
    fotobook.set('useSpineLogo', '1')
    fotobook.set('title', mimeo_data['metadata'].get('name', 'Converted from Mimeo'))
    
    # Add CEWE boilerplate
    num_interior_pages = len(mimeo_data['layouts'])
    add_cewe_boilerplate_elements(fotobook, num_interior_pages)
    
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
    
    for layout_idx, layout in enumerate(layouts):
        page_id = layout['model_id']
        page_frames = frames_by_page.get(page_id, [])
        
        page_nr = layout_idx + 1
        page_elem = ET.SubElement(fotobook, 'page')
        page_elem.set('pagenr', str(page_nr))
        page_elem.set('type', 'EMPTY' if page_nr % 2 == 0 else 'emptypage')
        
        bundlesize = ET.SubElement(page_elem, 'bundlesize')
        bundlesize.set('width', str(cewe_dimensions['pageWidth']))
        bundlesize.set('height', str(cewe_dimensions['pageHeight']))
        
        for frame_idx, frame in enumerate(page_frames):
            mcf_left, mcf_top, mcf_width, mcf_height = transformer.transform(
                frame['x'], frame['y'], frame['width'], frame['height']
            )
            
            photo = photo_by_index.get(global_photo_idx)
            global_photo_idx += 1
            
            if photo:
                photo_info = uuid_mappings.get(photo['photo_id'])
                
                if photo_info:
                    add_image_area(page_elem, photo_info, mcf_left, mcf_top,
                                 mcf_width, mcf_height, frame_idx, page_nr)
    
    return fotobook


def add_image_area(page_elem: ET.Element,
                  photo_info: Dict[str, str],
                  left: int,
                  top: int,
                  width: int,
                  height: int,
                  z_position: int,
                  page_nr: int) -> None:
    """Add an image area to a page element."""
    photo_path = Path(photo_info['path'])
    
    if not photo_path.exists():
        logger.warning(f"Photo not found: {photo_path}")
        return
    
    image_dims = get_image_dimensions(photo_path)
    if not image_dims:
        logger.warning(f"Could not read dimensions: {photo_path}")
        return
    
    image_width, image_height = image_dims
    
    # Calculate cutout using existing function
    scale, cutout_left, cutout_top = _calculate_cutout(width, height, image_width, image_height)
    
    # Create area element
    area = ET.SubElement(page_elem, 'area')
    area.set('areatype', 'imagearea')
    
    position = ET.SubElement(area, 'position')
    position.set('left', str(left))
    position.set('top', str(top))
    position.set('width', str(width))
    position.set('height', str(height))
    position.set('rotation', '0')
    position.set('zposition', str(1000 + z_position))
    
    # Encode filename with page number
    encoded_filename = encode_metadata_in_filename(
        photo_info['original_filename'],
        preferred_size=1.0,
        page_number=page_nr
    )
    
    image = ET.SubElement(area, 'image')
    image.set('filename', f'safecontainer:/{encoded_filename}')
    
    cutout = ET.SubElement(image, 'cutout')
    cutout.set('scale', f'{scale:.6f}')
    cutout.set('left', f'{cutout_left:.2f}')
    cutout.set('top', f'{cutout_top:.2f}')
    
    quality = ET.SubElement(image, 'quality')
    quality.set('noise', '100')
    quality.set('sharpness', '100')
    quality.set('texture', '100')
