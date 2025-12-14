"""Generate CEWE MCF format files from extracted PDF content."""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib


def calculate_image_relative_sizes(pdf_content: Dict[str, Any]):
    """Calculate relative sizes for all images across all pages.
    
    Finds the smallest image area and uses it as size 1.0,
    then scales all other images proportionally.
    
    Args:
        pdf_content: Content dictionary from extract_pdf_content
    """
    # Collect all image areas
    all_areas = []
    for page in pdf_content['pages']:
        for img in page['images']:
            area = img['width'] * img['height']
            all_areas.append((img, area))
    
    if not all_areas:
        return
    
    # Find minimum area
    min_area = min(area for _, area in all_areas)
    
    # Calculate relative size for each image
    for img, area in all_areas:
        relative_size = area / min_area if min_area > 0 else 1.0
        img['relative_size'] = relative_size


def write_mcf_project(pdf_content: Dict[str, Any], output_path: str, verbose: bool = False, insidecovers: bool = False):
    """Write extracted PDF content as CEWE MCF project.
    
    Args:
        pdf_content: Content dictionary from extract_pdf_content
        output_path: Path to output .xmcf directory
        verbose: Print detailed info
        insidecovers: Whether PDF includes inside cover pages (affects page mapping)
    """
    output_dir = Path(output_path)
    
    # Create .xmcf directory (and any parent directories)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create data.mcf file
    mcf_path = output_dir / 'data.mcf'
    
    if verbose:
        print(f"Creating MCF file: {mcf_path}")
    
    # Build MCF XML structure
    root = create_mcf_xml(pdf_content, output_dir, verbose, insidecovers)
    
    # Write prettified XML
    xml_str = prettify_xml(root)
    mcf_path.write_text(xml_str, encoding='utf-8')
    
    # Create folderid.xml (required by CEWE)
    create_folderid_xml(output_dir)
    
    if verbose:
        print(f"MCF project created at {output_dir}")


def _create_page_mapping(pdf_page_count: int, insidecovers: bool) -> Dict[str, Optional[int]]:
    """Create mapping from logical page identifiers to PDF page indices.
    
    Args:
        pdf_page_count: Total number of pages in PDF
        insidecovers: Whether PDF includes inside cover pages
        
    Returns:
        Dictionary mapping page identifiers to PDF indices (0-based)
        Page identifiers: "F" (front cover), "B" (back cover), 0 (inside front), 
                         1..N (content pages), N+1 (inside back)
    """
    mapping = {}
    
    if insidecovers:
        # WITH --insidecovers: PDF has [0=front, 1=inside_front, 2..N-2=content, N-1=inside_back, N=back]
        mapping["F"] = 0  # Front cover
        mapping[0] = 1    # Inside front cover
        
        # Content pages: UI pages 1..N-4 map to PDF pages 2..N-2
        content_pages = pdf_page_count - 4  # Exclude front, inside_front, inside_back, back
        for ui_page in range(1, content_pages + 1):
            mapping[ui_page] = ui_page + 1  # UI page 1 → PDF page 2, etc.
        
        mapping[content_pages + 1] = pdf_page_count - 2  # Inside back cover
        mapping["B"] = pdf_page_count - 1  # Back cover
    else:
        # WITHOUT --insidecovers: PDF has [0=front, 1..N-2=content, N-1=back]
        mapping["F"] = 0  # Front cover
        mapping[0] = None  # Inside front cover (empty)
        
        # Content pages: UI pages 1..N-2 map to PDF pages 1..N-2
        content_pages = pdf_page_count - 2  # Exclude front and back
        for ui_page in range(1, content_pages + 1):
            mapping[ui_page] = ui_page  # Direct mapping
        
        mapping[content_pages + 1] = None  # Inside back cover (empty)
        mapping["B"] = pdf_page_count - 1  # Back cover
    
    return mapping


def create_mcf_xml(pdf_content: Dict[str, Any], output_dir: Path, verbose: bool = False, insidecovers: bool = False) -> ET.Element:
    """Create the main MCF XML structure.
    
    Args:
        pdf_content: Extracted PDF content
        output_dir: Output directory for saving images
        verbose: Print detailed info
        insidecovers: Whether PDF includes inside cover pages (affects page mapping)
        
    Returns:
        Root XML element
    """
    # Calculate relative sizes for all images across all pages
    calculate_image_relative_sizes(pdf_content)
    
    # Create page mapping
    page_mapping = _create_page_mapping(len(pdf_content['pages']), insidecovers)
    
    # Create root MCF element
    mcf = ET.Element('mcf')
    
    # Create fotobook element with basic attributes
    page_width, page_height = pdf_content['page_size']
    # Convert PDF points to MCF units (0.1mm)
    # PDF points: 72 points = 1 inch = 25.4mm
    # So 1 point = 0.352778 mm = 3.52778 MCF units
    pt_to_mcf = 3.52778
    
    # Calculate page dimensions in MCF units and round to nearest integer
    # This ensures consistent dimensions throughout the photobook and avoids
    # floating-point errors in bundlesize specifications
    #
    # FUTURE: Consider allowing user to override page size here to:
    #   (a) Scale the entire book to a different size (e.g., change aspect ratio)
    #   (b) Snap to one of CEWE's standard printable sizes (e.g., 21x28cm, 28x21cm)
    #       to ensure the resulting MCF can be physically printed
    page_width_mcf = round(page_width * pt_to_mcf)
    page_height_mcf = round(page_height * pt_to_mcf)
    
    fotobook = ET.SubElement(mcf, 'fotobook')
    fotobook.set('productname', 'Custom Photobook')
    # CEWE pagecount = number of content pages (not including covers/inside covers)
    # WITHOUT --insidecovers: PDF has [front, content..., back] → content pages = N-2
    # WITH --insidecovers: PDF has [front, inside_front, content..., inside_back, back] → content pages = N-4
    if insidecovers:
        normal_page_count = len(pdf_content['pages']) - 4  # Exclude front, inside_front, inside_back, back
    else:
        normal_page_count = len(pdf_content['pages']) - 2  # Exclude front, back
    fotobook.set('pagecount', str(normal_page_count))
    fotobook.set('type', 'FLATBIND')
    fotobook.set('version', '7.1.5')
    fotobook.set('cover', 'HARDCOVER')
    fotobook.set('covertype', 'FRONT')
    
    # Add metadata if available
    metadata = pdf_content.get('metadata', {})
    if metadata.get('title'):
        fotobook.set('title', metadata['title'])
    
    # Add cover pages (THREE pagenr=0 pages required before content):
    # 1. Back+Front cover spread (type=fullcover, contains images from both halves)
    # 2. Spine (type=spine, typically empty)
    # 3. Front cover duplicate (type=fullcover, typically empty structure)
    
    front_pdf_idx = page_mapping["F"]
    back_pdf_idx = page_mapping["B"]
    
    if front_pdf_idx is not None and back_pdf_idx is not None:
        # Create combined back+front cover spread
        cover_page = create_cover_spread_element(
            pdf_content['pages'][front_pdf_idx],   # Front cover (right half)
            pdf_content['pages'][back_pdf_idx],    # Back cover (left half)
            output_dir, page_width_mcf, page_height_mcf, verbose
        )
        fotobook.append(cover_page)
    elif front_pdf_idx is not None:
        # Only front cover available
        cover_page = create_cover_spread_element(
            pdf_content['pages'][front_pdf_idx], None,
            output_dir, page_width_mcf, page_height_mcf, verbose
        )
        fotobook.append(cover_page)
    
    # Add spine page (required structure)
    spine_page = create_spine_page(page_width_mcf, page_height_mcf)
    fotobook.append(spine_page)
    
    # Add empty front cover fullcover page (required structure)
    front_cover_empty = create_empty_cover_page(page_width_mcf, page_height_mcf)
    fotobook.append(front_cover_empty)
    
    # Add inside front cover (4th pagenr=0 emptypage)
    # Inside front cover is LEFT page of spread (pagenr=0 is even = left side, x_offset = 0)
    # Page 1 is RIGHT page of spread (pagenr=1 is odd = right side, x_offset = page_width)
    inside_front_pdf_idx = page_mapping[0]
    if inside_front_pdf_idx is not None:
        # Use content from PDF (inside front cover with content)
        inside_front_data = pdf_content['pages'][inside_front_pdf_idx]
        inside_front_page = create_page_element(inside_front_data, output_dir, 0, 'emptypage', False, verbose, ui_page=0)
        fotobook.append(inside_front_page)
        
        # Create empty page 1 (RIGHT side of the same spread)
        empty_page_1 = create_empty_page(page_width_mcf, page_height_mcf)
        empty_page_1.set('pagenr', '1')
        empty_page_1.set('type', 'normalpage')
        fotobook.append(empty_page_1)
    else:
        # Empty inside front cover (no --insidecovers)
        inside_front_page = create_empty_page(page_width_mcf, page_height_mcf)
        fotobook.append(inside_front_page)
    
    # Add content pages
    # Calculate how many content pages we have from the mapping
    # Content pages are sequential from 1 to N (not including inside covers at 0 and N+1)
    if insidecovers:
        num_content_pages = len(pdf_content['pages']) - 4  # Exclude front, inside_front, inside_back, back
    else:
        num_content_pages = len(pdf_content['pages']) - 2  # Exclude front, back
    
    max_content_ui_page = num_content_pages
    
    # Process each content page (1 through max_content_ui_page)
    # We only process EVEN pages in the loop, because each even page creates
    # both the left page element (with areas from both pages) and an empty right page element
    # EXCEPTION: Page 1 must be processed if NOT using insidecovers (it's not created elsewhere)
    if max_content_ui_page > 0:
        for ui_page in range(1, max_content_ui_page + 1):
            # Skip odd pages (they're created when we process the preceding even page)
            # EXCEPT page 1 without insidecovers (no preceding even page creates it)
            if ui_page % 2 == 1:
                if ui_page == 1 and not insidecovers:
                    pass  # Process page 1 without insidecovers
                else:
                    continue  # Skip other odd pages
                
            pdf_idx = page_mapping.get(ui_page)
            if pdf_idx is None:
                continue
            
            page_data = pdf_content['pages'][pdf_idx]
            cewe_pagenr = ui_page  # UI page number = CEWE page number
            
            # Even pages (left side of spread) contain areas for both this and next page
            if cewe_pagenr % 2 == 0:
                # Even page (left page of spread) - create page element with areas
                page_elem = create_page_element(page_data, output_dir, cewe_pagenr, 'normalpage', False, verbose, ui_page=ui_page)
                fotobook.append(page_elem)
                
                # If there's a next odd page in our mapping, add its areas too
                # This includes both content pages AND the inside back cover (max_content_ui_page + 1)
                next_ui_page = ui_page + 1
                next_pdf_idx = page_mapping.get(next_ui_page)
                # Add next page if it exists in mapping (content page or inside back cover)
                if next_pdf_idx is not None and next_ui_page <= max_content_ui_page + 1:
                    next_page_data = pdf_content['pages'][next_pdf_idx]
                    # Add the next page's areas to this page element
                    z_position = 1000 + len(page_data.get('images', [])) + len(page_data.get('text_blocks', []))
                    for img in next_page_data.get('images', []):
                        # Use next_ui_page for the odd (right) page images
                        img['ui_page'] = next_ui_page
                        area = create_image_area(img, output_dir, z_position, verbose)
                        page_elem.append(area)
                        z_position += 1
                    for text_block in next_page_data.get('text_blocks', []):
                        area = create_text_area(text_block, z_position, verbose)
                        page_elem.append(area)
                        z_position += 1
                    
                    # Create an empty page element for the odd (right) page
                    # UNLESS it's the inside back cover (which is created separately)
                    if next_ui_page != max_content_ui_page + 1:
                        odd_page_elem = create_empty_content_page(page_width_mcf, page_height_mcf, cewe_pagenr + 1)
                        fotobook.append(odd_page_elem)
    
    # Add inside back cover (last pagenr=0 emptypage)
    # The inside back cover UI page is determined by looking for the highest integer key
    # in the mapping. This should be max_content_ui_page + 1.
    # CRITICAL: Inside back cover must be at an ODD page number (right side of spread)
    inside_back_ui_page = max_content_ui_page + 1
    
    # Validate: inside back cover must be odd
    if inside_back_ui_page % 2 == 0:
        raise RuntimeError(f"ERROR: Inside back cover calculated as UI page {inside_back_ui_page} (even). "
                          f"It must be odd (right side). max_content_ui_page={max_content_ui_page}, "
                          f"content_pages={len(pdf_content['pages']) - 4 if insidecovers else len(pdf_content['pages']) - 2}")
    
    inside_back_pdf_idx = page_mapping.get(inside_back_ui_page)
    if inside_back_pdf_idx is not None:
        # Use content from PDF (inside back cover with content)
        inside_back_data = pdf_content['pages'][inside_back_pdf_idx]
        inside_back_page = create_page_element(inside_back_data, output_dir, 0, 'emptypage', False, verbose, ui_page=inside_back_ui_page)
        fotobook.append(inside_back_page)
    else:
        # Empty inside back cover
        inside_back_page = create_empty_page(page_width_mcf, page_height_mcf)
        fotobook.append(inside_back_page)
    
    return mcf


def create_spine_page(page_width_mcf: float, page_height_mcf: float) -> ET.Element:
    """Create a spine page element (required structure between back and front cover).
    
    Args:
        page_width_mcf: Single page width in MCF units
        page_height_mcf: Page height in MCF units
        
    Returns:
        Spine page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', '0')
    page.set('type', 'spine')
    page.set('rotation', '0')
    
    # Spread width is double the single page width
    spread_width_mcf = page_width_mcf * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{page_height_mcf:.0f}")
    
    return page


def create_empty_cover_page(page_width_mcf: float, page_height_mcf: float) -> ET.Element:
    """Create an empty front cover page element (required structure).
    
    This is the third pagenr=0 page, typically empty but required by CEWE structure.
    
    Args:
        page_width_mcf: Single page width in MCF units
        page_height_mcf: Page height in MCF units
        
    Returns:
        Empty cover page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', '0')
    page.set('type', 'fullcover')
    page.set('rotation', '0')
    
    # Spread width is double the single page width
    spread_width_mcf = page_width_mcf * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{page_height_mcf:.0f}")
    
    return page


def create_cover_spread_element(front_page_data: Dict[str, Any], back_page_data: Optional[Dict[str, Any]],
                                output_dir: Path, page_width_mcf: float, page_height_mcf: float, 
                                verbose: bool = False) -> ET.Element:
    """Create a cover spread element with both front and back covers.
    
    The cover spread is a single page element with pagenr=0 and type=fullcover.
    - Back cover images: left half of spread (x < page_width_mcf)
    - Front cover images: right half of spread (x >= page_width_mcf)
    
    Args:
        front_page_data: Front cover page content (positioned on right half)
        back_page_data: Back cover page content (positioned on left half), or None if no back cover
        output_dir: Directory to save image files
        page_width_mcf: Single page width in MCF units
        page_height_mcf: Page height in MCF units
        verbose: Print detailed info
        
    Returns:
        Cover page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', '0')
    page.set('type', 'fullcover')
    page.set('rotation', '0')
    
    # Cover spread is double width
    spread_width_mcf = page_width_mcf * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{page_height_mcf:.0f}")
    
    z_position = 1000
    
    # Add back cover images (left half of spread)
    # PDF extractor now correctly positions back cover on left side
    if back_page_data:
        for img in back_page_data.get('images', []):
            img['ui_page'] = 'B'  # Back cover identifier
            area = create_image_area(img, output_dir, z_position, verbose)
            page.append(area)
            z_position += 1
        
        for text_block in back_page_data.get('text_blocks', []):
            area = create_text_area(text_block, z_position, verbose)
            page.append(area)
            z_position += 1
    
    # Add front cover images (right half of spread)
    # Front cover images from PDF already have x in [page_width, 2*page_width) since they're right pages
    for img in front_page_data.get('images', []):
        img['ui_page'] = 'F'  # Front cover identifier
        area = create_image_area(img, output_dir, z_position, verbose)
        page.append(area)
        z_position += 1
    
    for text_block in front_page_data.get('text_blocks', []):
        area = create_text_area(text_block, z_position, verbose)
        page.append(area)
        z_position += 1
    
    return page


def create_empty_page(page_width_mcf: float, page_height_mcf: float) -> ET.Element:
    """Create an empty page element (inside cover).
    
    Args:
        page_width_mcf: Single page width in MCF units
        page_height_mcf: Page height in MCF units
        
    Returns:
        Empty page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', '0')
    page.set('type', 'emptypage')
    page.set('rotation', '0')
    
    # Spread width is double the single page width
    spread_width_mcf = page_width_mcf * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{page_height_mcf:.0f}")
    
    return page


def create_empty_content_page(page_width_mcf: float, page_height_mcf: float, pagenr: int) -> ET.Element:
    """Create an empty content page element (for odd pages with no areas).
    
    Odd pages (right pages) in CEWE photobooks have their areas stored in the preceding
    even page's XML. The odd page elements themselves are mostly empty, containing only
    bundlesize and background information.
    
    Args:
        page_width_mcf: Single page width in MCF units
        page_height_mcf: Page height in MCF units
        pagenr: Page number (should be odd)
        
    Returns:
        Empty content page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', str(pagenr))
    page.set('type', 'normalpage')
    page.set('rotation', '0')
    
    # Spread width is double the single page width
    spread_width_mcf = page_width_mcf * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{page_height_mcf:.0f}")
    
    # Add basic background (212 is a common background ID for black/default)
    background = ET.SubElement(page, 'background')
    background.set('alignment', '4')
    background.set('designElementId', '212')
    background.set('rotation', '0')
    background.set('type', '1')
    
    return page


def create_page_element(page_data: Dict[str, Any], output_dir: Path,
                       cewe_pagenr: int, page_type: str, is_cover: bool, verbose: bool = False,
                       is_first_content_dummy: bool = False, ui_page = None) -> ET.Element:
    """Create a page element with images and text.
    
    Args:
        page_data: Page content dictionary with coordinates in MCF spread units
        output_dir: Directory to save image files
        cewe_pagenr: CEWE page number (0 for covers, 1+ for content)
        page_type: CEWE page type ('fullcover', 'normalpage', etc.)
        is_cover: True if this is a cover page
        verbose: Print detailed info
        is_first_content_dummy: True if this is the dummy page 0 for first content page
        ui_page: UI page identifier ("F", "B", 0, 1, 2, ...) for filename generation
        
    Returns:
        Page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', str(cewe_pagenr))
    page.set('type', page_type)
    page.set('rotation', '0')
    
    # CEWE photobooks use two-page spreads
    # bundlesize = width of spread (2 pages side-by-side) × height of one page
    # Each PDF page becomes one side of a spread
    # Coordinates are already in MCF units from PDF extractor
    page_width_mcf = page_data['width']
    page_height_mcf = page_data['height']
    
    # Spread width is double the single page width
    spread_width_mcf = page_width_mcf * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{page_height_mcf:.0f}")
    
    # Coordinates are already in MCF spread units from PDF extractor
    # No x_offset calculation needed - positioning already handled
    
    z_position = 1000  # Starting z-position
    
    # Add image areas
    for img in page_data['images']:
        # Use UI page number if provided, otherwise fall back to PDF page_num
        img['ui_page'] = ui_page if ui_page is not None else page_data.get('page_num', cewe_pagenr)
        area = create_image_area(img, output_dir, z_position, verbose)
        page.append(area)
        z_position += 1
    
    # Add text areas
    for text_block in page_data['text_blocks']:
        area = create_text_area(text_block, z_position, verbose)
        page.append(area)
        z_position += 1
    
    return page


def create_image_area(img: Dict[str, Any], output_dir: Path, z_position: int, verbose: bool = False) -> ET.Element:
    """Create an image area element.
    
    Args:
        img: Image data dictionary with coordinates in MCF spread units
        output_dir: Directory to save image file
        z_position: Z-position for layering
        verbose: Print detailed info
        
    Returns:
        Area XML element
    """
    from ..file_utils import encode_metadata_in_filename
    
    # Get UI page identifier ("F", "B", 0, 1, 2, ...) for filename generation
    ui_page = img.get('ui_page', 0)
    relative_size = img.get('relative_size', 1.0)
    index = img['index']
    
    # Generate base filename and use encode_metadata_in_filename for consistency
    # Format page identifier for filename: F/B as-is, numbers zero-padded
    if isinstance(ui_page, str):
        page_str = ui_page
    else:
        page_str = f"{ui_page:03d}"
    
    base_filename = f"image_p{page_str}_{index:04d}.{img['format']}"
    image_filename = encode_metadata_in_filename(base_filename, relative_size, ui_page)
    
    image_path = output_dir / image_filename
    image_path.write_bytes(img['data'])
    
    if verbose:
        print(f"  Saved image: {image_filename}")
    
    # Create area element
    area = ET.Element('area')
    area.set('areatype', 'imagearea')
    
    # Position element - coordinates are already in MCF spread units from PDF extractor
    # No conversion needed, pt_to_mcf and x_offset are for legacy compatibility only
    position = ET.SubElement(area, 'position')
    position.set('left', f"{img['left']:.2f}")
    position.set('top', f"{img['top']:.2f}")
    position.set('width', f"{img['width']:.2f}")
    position.set('height', f"{img['height']:.2f}")
    position.set('rotation', '0')
    position.set('zposition', str(z_position))
    
    # Image element
    image = ET.SubElement(area, 'image')
    image.set('filename', image_filename)
    image.set('backgroundPosition', 'CENTER_MIDDLE')
    
    # Cutout element (default: no crop)
    cutout = ET.SubElement(image, 'cutout')
    cutout.set('left', '0')
    cutout.set('top', '0')
    cutout.set('scale', '1.0')
    
    # Decoration element (no decoration by default)
    ET.SubElement(area, 'decoration')
    
    return area


def create_text_area(text_block: Dict[str, Any], z_position: int, verbose: bool = False) -> ET.Element:
    """Create a text area element.
    
    Args:
        text_block: Text block data dictionary with coordinates in MCF spread units
        z_position: Z-position for layering
        verbose: Print detailed info
        
    Returns:
        Area XML element
    """
    area = ET.Element('area')
    area.set('areatype', 'textarea')
    
    # Position element - coordinates are already in MCF spread units from PDF extractor
    position = ET.SubElement(area, 'position')
    position.set('left', f"{text_block['left']:.2f}")
    position.set('top', f"{text_block['top']:.2f}")
    position.set('width', f"{text_block['width']:.2f}")
    position.set('height', f"{text_block['height']:.2f}")
    position.set('rotation', '0')
    position.set('zposition', str(z_position))
    
    # Decoration element
    ET.SubElement(area, 'decoration')
    
    # Text element with HTML content
    text = ET.SubElement(area, 'text')
    text.set('applySpotColor', '0')
    
    # Convert color integer to hex
    color_int = text_block.get('color', 0)
    color_hex = f"#{color_int:06x}"
    
    # Determine font weight from flags
    flags = text_block.get('flags', 0)
    is_bold = bool(flags & 2**4)  # Bit 4 is bold
    is_italic = bool(flags & 2**6)  # Bit 6 is italic
    
    font_weight = '700' if is_bold else '400'
    font_style = 'italic' if is_italic else 'normal'
    
    # Create simple HTML content
    html_content = f'''<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">
<html><head><meta name="qrichtext" content="1" /><style type="text/css">
p, li {{ white-space: pre-wrap; }}
</style></head><body style=" font-family:'{text_block['font']}'; font-size:{int(text_block['size'])}pt; font-weight:{font_weight}; font-style:{font_style};">
<p style=" margin-top:0px; margin-bottom:0px; margin-left:0px; margin-right:0px; -qt-block-indent:0; text-indent:0px;"><span style=" color:{color_hex};">{escape_html(text_block['text'])}</span></p>
</body></html>'''
    
    text.text = f'<![CDATA[{html_content}]]>'
    
    # TextFormat element
    textFormat = ET.SubElement(text, 'textFormat')
    textFormat.set('Alignment', 'ALIGNLEADING')
    textFormat.set('font', f"{text_block['font']},{int(text_block['size'])},-1,5,50,0,0,0,0,0")
    textFormat.set('foregroundColor', f"#ff{color_int:06x}")
    textFormat.set('backgroundColor', '#00000000')
    
    return area


def escape_html(text: str) -> str:
    """Escape special HTML characters.
    
    Args:
        text: Text to escape
        
    Returns:
        Escaped text
    """
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&#39;'))


def create_folderid_xml(output_dir: Path):
    """Create folderid.xml file required by CEWE.
    
    Args:
        output_dir: Output directory
    """
    root = ET.Element('fotobook')
    # Generate a unique ID
    unique_id = hashlib.md5(str(output_dir).encode()).hexdigest()[:16]
    root.set('folderid', unique_id)
    
    xml_str = prettify_xml(root)
    folderid_path = output_dir / 'folderid.xml'
    folderid_path.write_text(xml_str, encoding='utf-8')


def prettify_xml(elem: ET.Element) -> str:
    """Return a pretty-printed XML string.
    
    Args:
        elem: Root element
        
    Returns:
        Formatted XML string
    """
    rough_string = ET.tostring(elem, encoding='utf-8')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent='  ', encoding='utf-8').decode('utf-8')
