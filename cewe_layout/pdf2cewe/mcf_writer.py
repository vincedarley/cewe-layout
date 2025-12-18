"""Generate CEWE MCF format files from extracted PDF content."""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib
from .pdf_extractor import find_closest_book_size, BOOK_SIZES


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
    
    # Create fotobook element as root (no mcf wrapper)
    fotobook = ET.Element('fotobook')
    
    # Get dimensions from cover and interior pages separately
    # Covers (F and B) may have different dimensions than interior pages
    front_cover_idx = page_mapping.get("F")
    back_cover_idx = page_mapping.get("B")
    
    # Get cover dimensions (use front cover if available, else back cover)
    if front_cover_idx is not None:
        cover_page = pdf_content['pages'][front_cover_idx]
        pdf_cover_width_mcf = round(cover_page['width'])
        pdf_cover_height_mcf = round(cover_page['height'])
    elif back_cover_idx is not None:
        cover_page = pdf_content['pages'][back_cover_idx]
        pdf_cover_width_mcf = round(cover_page['width'])
        pdf_cover_height_mcf = round(cover_page['height'])
    else:
        # Fallback: use first page dimensions
        pdf_cover_width_mcf = round(pdf_content['pages'][0]['width'])
        pdf_cover_height_mcf = round(pdf_content['pages'][0]['height'])
    
    # Get interior page dimensions (use first interior content page)
    # Find first non-cover page for interior dimensions
    interior_page_idx = None
    for ui_page in range(0, len(page_mapping)):
        pdf_idx = page_mapping.get(ui_page)
        if pdf_idx is not None:
            interior_page_idx = pdf_idx
            break
    
    if interior_page_idx is not None:
        interior_page = pdf_content['pages'][interior_page_idx]
        pdf_interior_width_mcf = round(interior_page['width'])
        pdf_interior_height_mcf = round(interior_page['height'])
    else:
        # Fallback: assume same as cover
        pdf_interior_width_mcf = pdf_cover_width_mcf
        pdf_interior_height_mcf = pdf_cover_height_mcf
    
    # Find the closest matching CEWE book size based on interior dimensions
    # (CEWE book sizes are primarily defined by their interior page dimensions)
    book_size_id = find_closest_book_size(pdf_interior_width_mcf, pdf_interior_height_mcf)
    cewe_dimensions = BOOK_SIZES[book_size_id]
    
    # Extract CEWE dimensions for covers and interior pages
    cewe_cover_width_mcf = cewe_dimensions['coverWidth'] / 2  # Single page width
    cewe_cover_height_mcf = cewe_dimensions['coverHeight']
    cewe_interior_width_mcf = cewe_dimensions['pageWidth'] / 2  # Single page width
    cewe_interior_height_mcf = cewe_dimensions['pageHeight']
    
    if verbose:
        print(f"PDF cover dimensions: {pdf_cover_width_mcf} x {pdf_cover_height_mcf} MCF units")
        print(f"PDF interior dimensions: {pdf_interior_width_mcf} x {pdf_interior_height_mcf} MCF units")
        print(f"Matched CEWE book size: {book_size_id}")
        print(f"CEWE cover dimensions: {cewe_cover_width_mcf} x {cewe_cover_height_mcf} MCF units")
        print(f"CEWE interior dimensions: {cewe_interior_width_mcf} x {cewe_interior_height_mcf} MCF units")
        
        # Calculate differences
        cover_width_diff = ((cewe_cover_width_mcf - pdf_cover_width_mcf) / pdf_cover_width_mcf) * 100
        cover_height_diff = ((cewe_cover_height_mcf - pdf_cover_height_mcf) / pdf_cover_height_mcf) * 100
        interior_width_diff = ((cewe_interior_width_mcf - pdf_interior_width_mcf) / pdf_interior_width_mcf) * 100
        interior_height_diff = ((cewe_interior_height_mcf - pdf_interior_height_mcf) / pdf_interior_height_mcf) * 100
        print(f"Cover difference: width {cover_width_diff:+.2f}%, height {cover_height_diff:+.2f}%")
        print(f"Interior difference: width {interior_width_diff:+.2f}%, height {interior_height_diff:+.2f}%")
    
    # CEWE pagecount = number of content pages (not including covers/inside covers)
    # WITHOUT --insidecovers: PDF has [front, content..., back] → content pages = N-2
    # WITH --insidecovers: PDF has [front, inside_front, content..., inside_back, back] → content pages = N-4
    if insidecovers:
        normal_page_count = len(pdf_content['pages']) - 4  # Exclude front, inside_front, inside_back, back
    else:
        normal_page_count = len(pdf_content['pages']) - 2  # Exclude front, back
    
    # Set all required fotobook attributes
    fotobook.set('art_id', str(cewe_dimensions['art_id']))
    fotobook.set('article_name', 'Custom Photobook')
    fotobook.set('externalProjectId', '')
    fotobook.set('folderID', '8418b9a9-25ab-445b-ab58-d6d7901f2105')
    fotobook.set('imagedir', '')
    fotobook.set('isDataMcf', '0')
    fotobook.set('productname', book_size_id)
    fotobook.set('startdatecalendarium', '')
    fotobook.set('useSpineLogo', '1')
    fotobook.set('version', '4.0')
    
    # Add metadata if available
    metadata = pdf_content.get('metadata', {})
    if metadata.get('title'):
        fotobook.set('title', metadata['title'])
    
    # Add CEWE boilerplate elements
    # normalpages = highest numbered page in the book (the last content page with pagenr="N")
    # Inside back cover is pagenr="0", so it doesn't count toward normalpages
    # Calculate this before calling add_cewe_boilerplate_elements
    if insidecovers:
        num_content_pages = len(pdf_content['pages']) - 4
    else:
        num_content_pages = len(pdf_content['pages']) - 2
    normalpages = num_content_pages  # Highest numbered page (1..N)
    add_cewe_boilerplate_elements(fotobook, normalpages)
    
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
            output_dir, cewe_cover_width_mcf, cewe_cover_height_mcf, verbose,
            pdf_cover_width_mcf, pdf_cover_height_mcf
        )
        fotobook.append(cover_page)
    elif front_pdf_idx is not None:
        # Only front cover available
        cover_page = create_cover_spread_element(
            pdf_content['pages'][front_pdf_idx], None,
            output_dir, cewe_cover_width_mcf, cewe_cover_height_mcf, verbose,
            pdf_cover_width_mcf, pdf_cover_height_mcf
        )
        fotobook.append(cover_page)
    
    # Add spine page (required structure) - uses cover dimensions
    spine_page = create_spine_page(cewe_cover_width_mcf, cewe_cover_height_mcf)
    fotobook.append(spine_page)
    
    # Add empty front cover fullcover page (required structure) - uses cover dimensions
    front_cover_empty = create_empty_cover_page(cewe_cover_width_mcf, cewe_cover_height_mcf)
    fotobook.append(front_cover_empty)
    
    # Add inside front cover (4th pagenr=0 emptypage) and page 1
    # Inside front cover is LEFT page of spread (page 0, even = left side)
    # Page 1 is RIGHT page of spread (page 1, odd = right side)
    # Page 1's content is ALWAYS added to page 0's element
    inside_front_pdf_idx = page_mapping[0]
    
    # Create page 0 element - either with content (insidecovers) or empty (no insidecovers)
    # Inside covers use interior page dimensions
    if inside_front_pdf_idx is not None:
        inside_front_data = pdf_content['pages'][inside_front_pdf_idx]
        # Get PDF dimensions from the actual page data
        pdf_page0_width = round(inside_front_data['width'])
        pdf_page0_height = round(inside_front_data['height'])
        inside_front_page = create_page_element(inside_front_data, output_dir, 0, 'emptypage', False, verbose, ui_page=0,
                                               pdf_page_width=pdf_page0_width, pdf_page_height=pdf_page0_height,
                                               cewe_page_width=cewe_interior_width_mcf, cewe_page_height=cewe_interior_height_mcf)
        z_position = 1000 + len(inside_front_data.get('images', [])) + len(inside_front_data.get('text_blocks', []))
    else:
        inside_front_page = create_empty_page(cewe_interior_width_mcf, cewe_interior_height_mcf)
        z_position = 1000
    
    fotobook.append(inside_front_page)
    
    # Add page 1's areas to page 0's element (page 1 is right side of the spread)
    page1_pdf_idx = page_mapping.get(1)
    if page1_pdf_idx is not None:
        page1_data = pdf_content['pages'][page1_pdf_idx]
        # Get PDF dimensions from the actual page data
        pdf_page1_width = round(page1_data['width'])
        pdf_page1_height = round(page1_data['height'])
        for img in page1_data.get('images', []):
            img['ui_page'] = 1  # Page 1 for filename
            area = create_image_area(img, output_dir, z_position, verbose,
                                    pdf_page1_width, pdf_page1_height,
                                    cewe_interior_width_mcf, cewe_interior_height_mcf)
            inside_front_page.append(area)
            z_position += 1
        for text_block in page1_data.get('text_blocks', []):
            area = create_text_area(text_block, z_position, verbose,
                                   pdf_page1_width, pdf_page1_height,
                                   cewe_interior_width_mcf, cewe_interior_height_mcf)
            inside_front_page.append(area)
            z_position += 1
    
    # Create empty page 1 element (placeholder for right side)
    empty_page_1 = create_empty_content_page(cewe_interior_width_mcf, cewe_interior_height_mcf, 1)
    fotobook.append(empty_page_1)
    
    # Add content pages
    # Calculate how many content pages we have from the mapping
    # Content pages are sequential from 1 to N (not including inside covers at 0 and N+1)
    if insidecovers:
        num_content_pages = len(pdf_content['pages']) - 4  # Exclude front, inside_front, inside_back, back
    else:
        num_content_pages = len(pdf_content['pages']) - 2  # Exclude front, back
    
    max_content_ui_page = num_content_pages
    
    # Process content pages starting from page 2
    # Page 0 and 1 are already handled above
    # We only process EVEN pages in the loop, because each even page creates
    # both the left page element (with areas from both pages) and an empty right page element
    if max_content_ui_page >= 2:
        for ui_page in range(2, max_content_ui_page + 1):
            # Skip odd pages (they're created when we process the preceding even page)
            if ui_page % 2 == 1:
                continue
                
            pdf_idx = page_mapping.get(ui_page)
            if pdf_idx is None:
                continue
                
            page_data = pdf_content['pages'][pdf_idx]
            cewe_pagenr = ui_page  # UI page number = CEWE page number
            
            # Even pages (left side of spread) contain areas for both this and next page
            if cewe_pagenr % 2 == 0:
                # Get PDF dimensions from the actual page data
                pdf_even_width = round(page_data['width'])
                pdf_even_height = round(page_data['height'])
                
                # Even page (left page of spread) - create page element with areas
                page_elem = create_page_element(page_data, output_dir, cewe_pagenr, 'normalpage', False, verbose, ui_page=ui_page,
                                               pdf_page_width=pdf_even_width, pdf_page_height=pdf_even_height,
                                               cewe_page_width=cewe_interior_width_mcf, cewe_page_height=cewe_interior_height_mcf)
                fotobook.append(page_elem)
                
                # If there's a next odd page in our mapping, add its areas too
                # This includes both content pages AND the inside back cover (max_content_ui_page + 1)
                next_ui_page = ui_page + 1
                next_pdf_idx = page_mapping.get(next_ui_page)
                # Add next page if it exists in mapping (content page or inside back cover)
                if next_pdf_idx is not None and next_ui_page <= max_content_ui_page + 1:
                    next_page_data = pdf_content['pages'][next_pdf_idx]
                    # Get PDF dimensions from the actual page data
                    pdf_odd_width = round(next_page_data['width'])
                    pdf_odd_height = round(next_page_data['height'])
                    
                    # Add the next page's areas to this page element
                    z_position = 1000 + len(page_data.get('images', [])) + len(page_data.get('text_blocks', []))
                    for img in next_page_data.get('images', []):
                        # Use next_ui_page for the odd (right) page images
                        img['ui_page'] = next_ui_page
                        area = create_image_area(img, output_dir, z_position, verbose,
                                                pdf_odd_width, pdf_odd_height,
                                                cewe_interior_width_mcf, cewe_interior_height_mcf)
                        page_elem.append(area)
                        z_position += 1
                    for text_block in next_page_data.get('text_blocks', []):
                        area = create_text_area(text_block, z_position, verbose,
                                               pdf_odd_width, pdf_odd_height,
                                               cewe_interior_width_mcf, cewe_interior_height_mcf)
                        page_elem.append(area)
                        z_position += 1
                    
                    # Create an empty page element for the odd (right) page
                    # UNLESS it's the inside back cover (which is created separately)
                    if next_ui_page != max_content_ui_page + 1:
                        odd_page_elem = create_empty_content_page(cewe_interior_width_mcf, cewe_interior_height_mcf, cewe_pagenr + 1)
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
    # NOTE: Inside back cover page element is always EMPTY because we already added
    # all its areas to page 60's element in the loop above (when next_ui_page == max_content_ui_page + 1)
    # This empty page element is just the required CEWE structure placeholder
    # Inside back cover uses interior page dimensions
    inside_back_page = create_empty_page(cewe_interior_width_mcf, cewe_interior_height_mcf)
    fotobook.append(inside_back_page)
    
    return fotobook


def scale_area_to_cewe(left: float, top: float, width: float, height: float,
                       pdf_width: float, pdf_height: float,
                       cewe_width: float, cewe_height: float) -> tuple[float, float, float, float]:
    """Scale area coordinates from PDF dimensions to CEWE dimensions.
    
    Maps the area from PDF page space to CEWE page space, preserving relative
    position. The bottom-left (0,0) and top-right corners are exactly mapped.
    
    Args:
        left: Left coordinate in PDF space
        top: Top coordinate in PDF space
        width: Width in PDF space
        height: Height in PDF space
        pdf_width: PDF page width (single page)
        pdf_height: PDF page height
        cewe_width: CEWE page width (single page)
        cewe_height: CEWE page height
        
    Returns:
        Tuple of (scaled_left, scaled_top, scaled_width, scaled_height)
    """
    # Calculate scale factors
    # Note: For spread coordinates, width scale applies to full spread width (2*page_width)
    width_scale = cewe_width / pdf_width
    height_scale = cewe_height / pdf_height
    
    # Scale all dimensions
    scaled_left = left * width_scale
    scaled_top = top * height_scale
    scaled_width = width * width_scale
    scaled_height = height * height_scale
    
    return scaled_left, scaled_top, scaled_width, scaled_height


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
                                verbose: bool = False,
                                pdf_page_width: float = None, pdf_page_height: float = None) -> ET.Element:
    """Create a cover spread element with both front and back covers.
    
    The cover spread is a single page element with pagenr=0 and type=fullcover.
    - Back cover images: left half of spread (x < page_width_mcf)
    - Front cover images: right half of spread (x >= page_width_mcf)
    
    Args:
        front_page_data: Front cover page content (positioned on right half)
        back_page_data: Back cover page content (positioned on left half), or None if no back cover
        output_dir: Directory to save image files
        page_width_mcf: Single page width in MCF units (CEWE)
        page_height_mcf: Page height in MCF units (CEWE)
        verbose: Print detailed info
        pdf_page_width: Original PDF page width (for scaling)
        pdf_page_height: Original PDF page height (for scaling)
        
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
            area = create_image_area(img, output_dir, z_position, verbose,
                                    pdf_page_width, pdf_page_height,
                                    page_width_mcf, page_height_mcf)
            page.append(area)
            z_position += 1
        
        for text_block in back_page_data.get('text_blocks', []):
            area = create_text_area(text_block, z_position, verbose,
                                   pdf_page_width, pdf_page_height,
                                   page_width_mcf, page_height_mcf)
            page.append(area)
            z_position += 1
    
    # Add front cover images (right half of spread)
    # Front cover images from PDF already have x in [page_width, 2*page_width) since they're right pages
    for img in front_page_data.get('images', []):
        img['ui_page'] = 'F'  # Front cover identifier
        area = create_image_area(img, output_dir, z_position, verbose,
                                pdf_page_width, pdf_page_height,
                                page_width_mcf, page_height_mcf)
        page.append(area)
        z_position += 1
    
    for text_block in front_page_data.get('text_blocks', []):
        area = create_text_area(text_block, z_position, verbose,
                               pdf_page_width, pdf_page_height,
                               page_width_mcf, page_height_mcf)
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
                       is_first_content_dummy: bool = False, ui_page = None,
                       pdf_page_width: float = None, pdf_page_height: float = None,
                       cewe_page_width: float = None, cewe_page_height: float = None) -> ET.Element:
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
        pdf_page_width: Original PDF page width (for scaling)
        pdf_page_height: Original PDF page height (for scaling)
        cewe_page_width: Target CEWE page width (for scaling)
        cewe_page_height: Target CEWE page height (for scaling)
        
    Returns:
        Page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', str(cewe_pagenr))
    page.set('type', page_type)
    page.set('rotation', '0')
    
    # CEWE photobooks use two-page spreads
    # bundlesize = width of spread (2 pages side-by-side) × height of one page
    # Use CEWE dimensions for bundlesize (not PDF dimensions)
    page_width_mcf = cewe_page_width
    page_height_mcf = cewe_page_height

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
        area = create_image_area(img, output_dir, z_position, verbose,
                                pdf_page_width, pdf_page_height,
                                cewe_page_width, cewe_page_height)
        page.append(area)
        z_position += 1
    
    # Add text areas
    for text_block in page_data['text_blocks']:
        area = create_text_area(text_block, z_position, verbose,
                               pdf_page_width, pdf_page_height,
                               cewe_page_width, cewe_page_height)
        page.append(area)
        z_position += 1
    
    return page


def create_image_area(img: Dict[str, Any], output_dir: Path, z_position: int, verbose: bool = False,
                     pdf_page_width: float = None, pdf_page_height: float = None,
                     cewe_page_width: float = None, cewe_page_height: float = None) -> ET.Element:
    """Create an image area element.
    
    Args:
        img: Image data dictionary with coordinates in MCF spread units
        output_dir: Directory to save image file
        z_position: Z-position for layering
        verbose: Print detailed info
        pdf_page_width: Original PDF page width (for scaling)
        pdf_page_height: Original PDF page height (for scaling)
        cewe_page_width: Target CEWE page width (for scaling)
        cewe_page_height: Target CEWE page height (for scaling)
        
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
    
    # Scale coordinates from PDF to CEWE dimensions if scaling info provided
    # Note: Coordinates are in spread space, so use 2*page_width for spread width
    scaled_left, scaled_top, scaled_width, scaled_height = scale_area_to_cewe(
        img['left'], img['top'], img['width'], img['height'],
        pdf_page_width * 2, pdf_page_height,  # PDF spread dimensions
        cewe_page_width * 2, cewe_page_height  # CEWE spread dimensions
    )
    
    # Create area element
    area = ET.Element('area')
    area.set('areatype', 'imagearea')
    
    # Position element with scaled coordinates
    position = ET.SubElement(area, 'position')
    position.set('left', f"{scaled_left:.2f}")
    position.set('top', f"{scaled_top:.2f}")
    position.set('width', f"{scaled_width:.2f}")
    position.set('height', f"{scaled_height:.2f}")
    position.set('rotation', '0')
    position.set('zposition', str(z_position))
    
    # Image element
    image = ET.SubElement(area, 'image')
    image.set('filename', f"safecontainer:/{image_filename}")
    image.set('backgroundPosition', 'CENTER_MIDDLE')
    
    # Cutout element (default: no crop)
    cutout = ET.SubElement(image, 'cutout')
    cutout.set('left', '0')
    cutout.set('top', '0')
    # We do not set a "scale" because we might have rescaled the page a bit,
    # and CEWE will do its own fitting. Setting scale=1.0 forces no scaling.
    #cutout.set('scale', '1.0')
    
    # Decoration element (no decoration by default)
    ET.SubElement(area, 'decoration')
    
    return area


def create_text_area(text_block: Dict[str, Any], z_position: int, verbose: bool = False,
                    pdf_page_width: float = None, pdf_page_height: float = None,
                    cewe_page_width: float = None, cewe_page_height: float = None) -> ET.Element:
    """Create a text area element.
    
    Args:
        text_block: Text block data dictionary with coordinates in MCF spread units
        z_position: Z-position for layering
        verbose: Print detailed info
        pdf_page_width: Original PDF page width (for scaling)
        pdf_page_height: Original PDF page height (for scaling)
        cewe_page_width: Target CEWE page width (for scaling)
        cewe_page_height: Target CEWE page height (for scaling)
        
    Returns:
        Area XML element
    """
    # Scale coordinates from PDF to CEWE dimensions if scaling info provided
    # Note: Coordinates are in spread space, so use 2*page_width for spread width
    scaled_left, scaled_top, scaled_width, scaled_height = scale_area_to_cewe(
        text_block['left'], text_block['top'], text_block['width'], text_block['height'],
        pdf_page_width * 2, pdf_page_height,  # PDF spread dimensions
        cewe_page_width * 2, cewe_page_height  # CEWE spread dimensions
    )
    
    area = ET.Element('area')
    area.set('areatype', 'textarea')
    
    # Position element with scaled coordinates
    position = ET.SubElement(area, 'position')
    position.set('left', f"{scaled_left:.2f}")
    position.set('top', f"{scaled_top:.2f}")
    position.set('width', f"{scaled_width:.2f}")
    position.set('height', f"{scaled_height:.2f}")
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
    
    # Create minimal HTML content - just font, size, and text
    html_content = f'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd"><html><head><meta name="qrichtext" content="1" /></head><body style="font-family:\'{text_block["font"]}\'; font-size:{int(text_block["size"])}pt;"><p><span style="color:{color_hex};">{escape_html(text_block["text"])}</span></p></body></html>'
    
    # Set areaTextType attribute
    text.set('areaTextType', 'content')
    # Store HTML directly - we'll wrap in CDATA during XML serialization
    text.text = html_content
    
    # Add outline element
    outline = ET.SubElement(text, 'outline')
    outline.set('width', '0')
    
    # TextFormat element with full CEWE attributes
    textFormat = ET.SubElement(text, 'textFormat')
    textFormat.set('Alignment', 'ALIGNLEFT')
    textFormat.set('IndentMargin', '4')
    textFormat.set('VerticalIndentMargin', '50')
    textFormat.set('backgroundColor', '#00000000')
    textFormat.set('font', f"{text_block['font']},{int(text_block['size'])},-1,5,{font_weight},0,0,0,0,0,0,1,0,0,0,1")
    textFormat.set('foregroundColor', f"#ff{color_int:06x}")
    textFormat.set('hasOutline', '0')
    textFormat.set('hyphenation', '0')
    textFormat.set('letterSpacing', '0')
    textFormat.set('lineHeight', '100')
    
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


def add_cewe_boilerplate_elements(fotobook: ET.Element, normalpages: int) -> None:
    """Add required CEWE boilerplate XML elements to fotobook.
    
    These elements (project, savingVersion, creationHistory, articleConfig) are required
    by CEWE's photobook format and appear immediately after the opening
    fotobook tag.
    
    Args:
        fotobook: The fotobook element to add boilerplate to
        normalpages: Highest page number in the book (for articleConfig)
    """
    import uuid
    import time
    from datetime import datetime
    
    # Generate unique project ID
    project_id = str(uuid.uuid4())
    epoch_time = int(time.time())
    current_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    
    # <project> element
    project = ET.SubElement(fotobook, 'project')
    project.set('createdWithHPSVersion', '8.0.5')
    project.set('createdWithHPSVersionBuild', '20251014')
    project.set('multiPurposeText', '')
    project.set('projectID', project_id)
    project.set('projectIDCreatedEpoch', str(epoch_time))
    
    # <savingVersion> element
    saving_version = ET.SubElement(fotobook, 'savingVersion')
    saving_version.set('compatibilityVersion', '6.4.2')
    saving_version.set('programversion', '8.0.5')
    saving_version.set('programversionBuild', '20251014')
    saving_version.set('savetime', current_date)
    
    # <creationHistory> element
    creation_history = ET.SubElement(fotobook, 'creationHistory')
    creation_history.set('clientId', '37')
    creation_history.set('clientVersion', '7.4.3-20240328-default')
    creation_history.set('creationDate', current_date)
    
    # <articleConfig> element
    article_config = ET.SubElement(fotobook, 'articleConfig')
    article_config.set('normalpages', str(normalpages))
    article_config.set('pagenaming', '1')
    article_config.set('spotColor', 'digital_embossing')
    article_config.set('totalpages', str(normalpages + 5))


def prettify_xml(elem: ET.Element) -> str:
    """Return a pretty-printed XML string.
    
    Args:
        elem: Root element
        
    Returns:
        Formatted XML string
    """
    rough_string = ET.tostring(elem, encoding='utf-8')
    reparsed = minidom.parseString(rough_string)
    pretty_xml = reparsed.toprettyxml(indent='  ', encoding='utf-8').decode('utf-8')
    
    # Remove blank lines that minidom adds around text content
    lines = pretty_xml.split('\n')
    non_blank_lines = [line for line in lines if line.strip()]
    result = '\n'.join(non_blank_lines)
    
    # Unescape CDATA markers first (ElementTree escapes them)
    result = result.replace('&lt;![CDATA[', '<![CDATA[')
    result = result.replace(']]&gt;', ']]>')
    
    # Wrap text element HTML content in CDATA sections
    # The HTML content in <text> elements needs to be in CDATA to prevent XML parsing
    import re
    
    # Pattern: <text ...>whitespace_and_escaped_html_content<outline.../>
    # Match everything between <text> opening tag and <outline/> tag, including whitespace and newlines
    # This will capture the HTML content that needs CDATA wrapping
    def wrap_text_in_cdata(match):
        opening_tag = match.group(1)
        content = match.group(2)
        outline_tag = match.group(3)
        
        # Strip all leading/trailing whitespace (including newlines)
        content = content.strip()
        
        # Skip if content is already wrapped in CDATA (from a previous match)
        if content.startswith('<![CDATA[') and content.endswith(']]>'):
            return match.group(0)  # Return unchanged
        
        # Unescape the HTML content (ElementTree escapes < > etc)
        content = content.replace('&lt;', '<').replace('&gt;','>').replace('&quot;', '"').replace('&amp;', '&')
        
        # Wrap in CDATA and keep everything on one line with outline
        return f'{opening_tag}<![CDATA[{content}]]>{outline_tag}'
    
    # Match: <text ...>content<outline.../> where content is everything until we hit <outline
    # Use non-greedy match to stop at first <outline tag
    # IMPORTANT: Must match <text> but NOT <textFormat> - use word boundary or space after 'text'
    result = re.sub(
        r'(<text\s[^>]*>)((?:(?!<outline).)*?)(<outline[^>]*/?>)',
        wrap_text_in_cdata,
        result,
        flags=re.DOTALL
    )
    
    return result
