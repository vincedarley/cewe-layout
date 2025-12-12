"""Generate CEWE MCF format files from extracted PDF content."""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Dict, Any
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


def write_mcf_project(pdf_content: Dict[str, Any], output_path: str, verbose: bool = False):
    """Write extracted PDF content as CEWE MCF project.
    
    Args:
        pdf_content: Content dictionary from extract_pdf_content
        output_path: Path to output .xmcf directory
        verbose: Print detailed info
    """
    output_dir = Path(output_path)
    
    # Create .xmcf directory (and any parent directories)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create data.mcf file
    mcf_path = output_dir / 'data.mcf'
    
    if verbose:
        print(f"Creating MCF file: {mcf_path}")
    
    # Build MCF XML structure
    root = create_mcf_xml(pdf_content, output_dir, verbose)
    
    # Write prettified XML
    xml_str = prettify_xml(root)
    mcf_path.write_text(xml_str, encoding='utf-8')
    
    # Create folderid.xml (required by CEWE)
    create_folderid_xml(output_dir)
    
    if verbose:
        print(f"MCF project created at {output_dir}")


def create_mcf_xml(pdf_content: Dict[str, Any], output_dir: Path, verbose: bool = False) -> ET.Element:
    """Create the main MCF XML structure.
    
    Args:
        pdf_content: Extracted PDF content
        output_dir: Output directory for saving images
        verbose: Print detailed info
        
    Returns:
        Root XML element
    """
    # Calculate relative sizes for all images across all pages
    calculate_image_relative_sizes(pdf_content)
    
    # Create root MCF element
    mcf = ET.Element('mcf')
    
    # Create fotobook element with basic attributes
    page_width, page_height = pdf_content['page_size']
    # Convert PDF points to MCF units (0.1mm)
    # PDF points: 72 points = 1 inch = 25.4mm
    # So 1 point = 0.352778 mm = 3.52778 MCF units
    pt_to_mcf = 3.52778
    
    fotobook = ET.SubElement(mcf, 'fotobook')
    fotobook.set('productname', 'Custom Photobook')
    # CEWE pagecount = number of content pages + 3 (front cover, inside front, inside back)
    # PDF pages: 1=front cover, 2..N-1=content, N=back cover (optional)
    # CEWE pages: pagenr 0 (cover+inside) + pagenr 1..(N-2) (content) + pagenr 0 (inside back)
    fotobook.set('pagecount', str(len(pdf_content['pages']) + 2))  # +2 for inside covers
    fotobook.set('type', 'FLATBIND')
    fotobook.set('version', '7.1.5')
    fotobook.set('cover', 'HARDCOVER')
    fotobook.set('covertype', 'FRONT')
    
    # Add metadata if available
    metadata = pdf_content.get('metadata', {})
    if metadata.get('title'):
        fotobook.set('title', metadata['title'])
    
    # Add cover pages (pagenr=0)
    # PDF page 1 = front cover (right side of cover spread)
    if len(pdf_content['pages']) > 0:
        front_cover = create_page_element(pdf_content['pages'][0], output_dir, pt_to_mcf, 0, 'fullcover', True, verbose)
        fotobook.append(front_cover)
    
    # Add inside front cover (empty page, pagenr=0)
    inside_front = create_empty_page(page_width * pt_to_mcf, page_height * pt_to_mcf)
    fotobook.append(inside_front)
    
    # Add content pages (pagenr 1..N-2)
    # PDF pages 2..N-1 map to CEWE pagenr 1..(N-2)
    for i in range(1, len(pdf_content['pages']) - 1):
        page_data = pdf_content['pages'][i]
        cewe_pagenr = i  # PDF page 2 -> CEWE pagenr 1, PDF page 3 -> CEWE pagenr 2, etc.
        
        # Special handling for first content page (pagenr=1)
        # CEWE uses a dummy page 0 with content, followed by empty page 1
        if cewe_pagenr == 1:
            # Create dummy page 0 with the content (positioned on right side of spread)
            dummy_page = create_page_element(page_data, output_dir, pt_to_mcf, 0, 'emptypage', False, verbose, is_first_content_dummy=True)
            fotobook.append(dummy_page)
            
            # Create empty page 1
            empty_page_1 = create_empty_page(page_width * pt_to_mcf, page_height * pt_to_mcf)
            empty_page_1.set('pagenr', '1')
            empty_page_1.set('type', 'normalpage')
            fotobook.append(empty_page_1)
        else:
            page_elem = create_page_element(page_data, output_dir, pt_to_mcf, cewe_pagenr, 'normalpage', False, verbose)
            fotobook.append(page_elem)
    
    # Add inside back cover (empty page, pagenr=0)
    inside_back = create_empty_page(page_width * pt_to_mcf, page_height * pt_to_mcf)
    fotobook.append(inside_back)
    
    return mcf


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


def create_page_element(page_data: Dict[str, Any], output_dir: Path, pt_to_mcf: float, 
                       cewe_pagenr: int, page_type: str, is_cover: bool, verbose: bool = False,
                       is_first_content_dummy: bool = False) -> ET.Element:
    """Create a page element with images and text.
    
    Args:
        page_data: Page content dictionary
        output_dir: Directory to save image files
        pt_to_mcf: Conversion factor from PDF points to MCF units
        cewe_pagenr: CEWE page number (0 for covers, 1+ for content)
        page_type: CEWE page type ('fullcover', 'normalpage', etc.)
        is_cover: True if this is a cover page
        verbose: Print detailed info
        is_first_content_dummy: True if this is the dummy page 0 for first content page
        
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
    page_width_mcf = page_data['width'] * pt_to_mcf
    page_height_mcf = page_data['height'] * pt_to_mcf
    
    # Spread width is double the single page width
    spread_width_mcf = page_width_mcf * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{page_height_mcf:.0f}")
    
    # Calculate x-offset for positioning content within spread
    # Cover pages: front cover on right side of spread
    # First content page dummy (pagenr=0, emptypage): content on right side
    # Other content pages: odd (1,3,5...) on right, even (2,4,6...) on left
    if is_cover:
        # Front cover on right side of spread
        x_offset = page_width_mcf
    elif is_first_content_dummy:
        # First content page dummy: content on right side of spread
        x_offset = page_width_mcf
    elif cewe_pagenr % 2 == 1:
        # Odd numbered pages on right side of spread
        x_offset = page_width_mcf
    else:
        # Even pages on left side of spread
        x_offset = 0
    
    z_position = 1000  # Starting z-position
    
    # Add image areas
    for img in page_data['images']:
        # Add page number and x_offset to image data
        img['page_num'] = page_data['page_num']
        img['x_offset'] = x_offset
        area = create_image_area(img, output_dir, pt_to_mcf, z_position, verbose)
        page.append(area)
        z_position += 1
    
    # Add text areas
    for text_block in page_data['text_blocks']:
        text_block['x_offset'] = x_offset
        area = create_text_area(text_block, pt_to_mcf, z_position, verbose)
        page.append(area)
        z_position += 1
    
    return page


def create_image_area(img: Dict[str, Any], output_dir: Path, pt_to_mcf: float, z_position: int, verbose: bool = False) -> ET.Element:
    """Create an image area element.
    
    Args:
        img: Image data dictionary
        output_dir: Directory to save image file
        pt_to_mcf: Conversion factor
        z_position: Z-position for layering
        verbose: Print detailed info
        
    Returns:
        Area XML element
    """
    # Save image to file with relative size and page number in filename
    page_num = img.get('page_num', 0)
    relative_size = img.get('relative_size', 1.0)
    index = img['index']
    
    # Format: image_p{page:03d}_{index:04d}-sz{size:.1f}-pg{page}.{ext}
    image_filename = f"image_p{page_num:03d}_{index:04d}-sz{relative_size:.1f}-pg{page_num}.{img['format']}"
    image_path = output_dir / image_filename
    image_path.write_bytes(img['data'])
    
    if verbose:
        print(f"  Saved image: {image_filename}")
    
    # Create area element
    area = ET.Element('area')
    area.set('areatype', 'imagearea')
    
    # Position element (convert PDF coordinates to MCF and add x_offset for spread positioning)
    x_offset = img.get('x_offset', 0)
    position = ET.SubElement(area, 'position')
    position.set('left', f"{img['left'] * pt_to_mcf + x_offset:.2f}")
    position.set('top', f"{img['top'] * pt_to_mcf:.2f}")
    position.set('width', f"{img['width'] * pt_to_mcf:.2f}")
    position.set('height', f"{img['height'] * pt_to_mcf:.2f}")
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


def create_text_area(text_block: Dict[str, Any], pt_to_mcf: float, z_position: int, verbose: bool = False) -> ET.Element:
    """Create a text area element.
    
    Args:
        text_block: Text block data dictionary
        pt_to_mcf: Conversion factor
        z_position: Z-position for layering
        verbose: Print detailed info
        
    Returns:
        Area XML element
    """
    area = ET.Element('area')
    area.set('areatype', 'textarea')
    
    # Position element (add x_offset for spread positioning)
    x_offset = text_block.get('x_offset', 0)
    position = ET.SubElement(area, 'position')
    position.set('left', f"{text_block['left'] * pt_to_mcf + x_offset:.2f}")
    position.set('top', f"{text_block['top'] * pt_to_mcf:.2f}")
    position.set('width', f"{text_block['width'] * pt_to_mcf:.2f}")
    position.set('height', f"{text_block['height'] * pt_to_mcf:.2f}")
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
