"""Generate CEWE MCF format files from extracted PDF content."""

import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib
import logging

from cewe_layout.book.utils import BOOK_SIZES, find_closest_book_size, ResizeTransformer
from cewe_layout.book.photobook import Photobook

logger = logging.getLogger(__name__)


def calculate_image_relative_sizes(photobook: Photobook):
    """Calculate relative sizes for all images across all pages.
    
    Finds the smallest image area and uses it as size 1.0,
    then scales all other images proportionally.
    
    Args:
        photobook: Photobook instance
    """
    # Collect all image areas
    all_areas = []
    for i in range(photobook.get_page_count()):
        page = photobook.get_page(i)
        if page is None:
            # Ok to skip silently - we're just calculating a size heuristic.
            continue  # Skip empty inside cover pages
        for img in page.get_images():
            # All photobook implementations must provide 'area_width' and 'area_height' in get_images()
            if 'area_width' not in img or 'area_height' not in img:
                raise ValueError(f"Image missing required 'area_width' or 'area_height' key on page {i}. "
                               f"Image keys: {list(img.keys())}")
            area = img['area_width'] * img['area_height']
            all_areas.append((img, area))
    
    if not all_areas:
        return
    
    # Find minimum area
    min_area = min(area for _, area in all_areas)
    
    # Calculate relative size for each image
    for img, area in all_areas:
        relative_size = area / min_area if min_area > 0 else 1.0
        img['relative_size'] = relative_size


def write_mcf_project(photobook: Photobook, output_path: str, verbose: bool = False,
                     cover_transformer: Optional[ResizeTransformer] = None,
                     content_transformer: Optional[ResizeTransformer] = None):
    """Write photobook content as CEWE MCF project.

    Note the for the critical photo content, EITHER all of the photo files must
    have already been copied to the output directory (and named appropriately),
    OR the photobook implementation must provide image data in get_images(), and then
    this code path will take care of writing the image files.

    Args:
        photobook: Photobook instance (PDFPhotobook, MimeoPhotobook, etc.)
                  The Photobook abstraction handles inside covers internally - always exposing
                  N+4 page indices and returning None for inside covers when they don't exist.
        output_path: Path to output .xmcf directory
        verbose: Print detailed info
        cover_transformer: Optional ResizeTransformer for cover pages
        content_transformer: Optional ResizeTransformer for content pages
    """
    output_dir = Path(output_path)
    
    # Create .xmcf directory (and any parent directories)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Create data.mcf file
    mcf_path = output_dir / 'data.mcf'
    
    if verbose:
        print(f"Creating MCF file: {mcf_path}")
    
    # Build MCF XML structure
    root = create_mcf_xml_from_photobook(photobook, output_dir, verbose, cover_transformer, content_transformer)
    
    # Write prettified XML
    xml_str = prettify_xml(root)
    mcf_path.write_text(xml_str, encoding='utf-8')
    
    # Create folderid.xml (required by CEWE). The contents of this file seem mostly optional - CEWE
    # will generate it.
    create_folderid_xml(output_dir)
    
    if verbose:
        print(f"MCF project created at {output_dir}")


def create_mcf_xml_from_photobook(photobook: Photobook, output_dir: Path, verbose: bool = False,
                                  cover_transformer: Optional[ResizeTransformer] = None,
                                  content_transformer: Optional[ResizeTransformer] = None) -> ET.Element:
    """Create the main MCF XML structure.
    
    CEWE photobooks have inside covers (pages 0 and N+1) which are always empty in CEWE books.
    The MCF file format can store content on these pages, which will be visible/editable in QLayout,
    but CEWE Creator ignores it during printing (at least for hardback books).
    
    The Photobook abstraction handles inside covers transparently:
    - Always exposes N+4 page indices (0=front, 1=inside_front, 2..N+1=content, N+2=inside_back, N+3=back)
    - Returns None for inside cover pages (indices 1 and N+2) when they don't exist in source
    - When inside covers exist and have content, that content is preserved in the MCF

    Args:
        photobook: Photobook instance (PDFPhotobook, MimeoPhotobook, etc.)
        output_dir: Output directory for saving images
        verbose: Print detailed info
        cover_transformer: Optional ResizeTransformer for cover pages
        content_transformer: Optional ResizeTransformer for content pages
        
    Returns:
        Root XML element
    """
    # Calculate relative sizes for all images across all pages
    calculate_image_relative_sizes(photobook)

    # Create fotobook element as root (no mcf wrapper)
    fotobook = ET.Element('fotobook')
    
    # Get dimensions from cover and interior pages separately
    # Covers (F and B) may have different dimensions than interior pages
    front_cover_page = photobook.find_page_by_ui_num("F")
    back_page = photobook.find_page_by_ui_num("B")

    # Get cover dimensions (use front cover if available, else back cover)
    if front_cover_page is not None:
        input_cover_width_mcf = round(front_cover_page.get_width())
        input_cover_height_mcf = round(front_cover_page.get_height())
    elif back_page is not None:
        input_cover_width_mcf = round(back_page.get_width())
        input_cover_height_mcf = round(back_page.get_height())
    else:
        # Fallback: use first page dimensions
        first_page = photobook.find_page_by_ui_num(1)
        input_cover_width_mcf = round(first_page.get_width())
        input_cover_height_mcf = round(first_page.get_height())
    
    # Get interior page dimensions (use first interior content page)
    # Find first non-cover page for interior dimensions
    interior_page = photobook.find_page_by_ui_num(1)
    input_interior_width_mcf = round(interior_page.get_width())
    input_interior_height_mcf = round(interior_page.get_height())
    
    # Find the closest matching CEWE book size based on interior dimensions
    # If resizing, use the TARGET dimensions from the transformer, not the original
    if content_transformer:
        target_width, target_height = content_transformer.transform_page_dimensions()
        book_size_id = find_closest_book_size(target_width, target_height)
    else:
        # No resizing - use original dimensions
        book_size_id = find_closest_book_size(input_interior_width_mcf, input_interior_height_mcf)
    
    cewe_dimensions = BOOK_SIZES[book_size_id]
    
    if verbose:
        print(f"Book cover dimensions: {input_cover_width_mcf} x {input_cover_height_mcf} MCF units")
        print(f"Book interior dimensions: {input_interior_width_mcf} x {input_interior_height_mcf} MCF units")
        print(f"Matched CEWE book size: {book_size_id}")
    
    # CEWE pagecount = number of content pages (not including covers/inside covers)
    # Photobook always has N+4 pages: front, inside_front, N content pages, inside_back, back
    num_content_pages = photobook.get_content_page_count()

    # Set all required fotobook attributes
    fotobook.set('art_id', str(cewe_dimensions['art_id']))
    fotobook.set('article_name', 'Custom Photobook')
    fotobook.set('externalProjectId', '')
    fotobook.set('folderID', '8418b9a9-25ab-445b-ab58-d6d7901f2105')
    fotobook.set('imagedir', '')
    fotobook.set('isDataMcf', '0')
    fotobook.set('productname', str(cewe_dimensions['productname']))
    fotobook.set('startdatecalendarium', '')
    fotobook.set('useSpineLogo', '1')
    fotobook.set('version', '4.0')
    
    # Add metadata if available
    metadata = photobook.get_metadata()
    if metadata.get('title'):
        fotobook.set('title', metadata['title'])
    
    # Add CEWE boilerplate elements
    # num_content_pages = highest numbered page in the book (the last content page with pagenr="N")
    # Inside back cover is pagenr="0", so it doesn't count toward num_content_pages
    # Calculate this before calling add_cewe_boilerplate_elements

    # TODO: CEWE books, by their structure, must have 4xN+2 content pages
    # If our number of pages doesn't match, we should add empty pages.
    add_cewe_boilerplate_elements(fotobook, num_content_pages)
    
    # Add cover pages (THREE pagenr=0 pages required before content):
    # 1. Back+Front cover spread (type=fullcover, contains images from both halves)
    # 2. Spine (type=spine, typically empty)
    # 3. Front cover duplicate (type=fullcover, typically empty structure)

    front_page = photobook.find_page_by_ui_num("F")
    back_page = photobook.find_page_by_ui_num("B")

    if front_page is not None and back_page is not None:
        # Create combined back+front cover spread
        # Get page data dicts for backward compatibility with create_cover_spread_element
        cover_page = create_cover_spread_element(
            front_page.get_page_info(),   # Front cover (right half)
            back_page.get_page_info(),    # Back cover (left half)
            output_dir, input_cover_width_mcf, input_cover_height_mcf, verbose,
            input_cover_width_mcf, input_cover_height_mcf, cover_transformer
        )
        fotobook.append(cover_page)
    elif front_page is not None:
        # Only front cover available
        cover_page = create_cover_spread_element(
            front_page.get_page_info(), None,
            output_dir, input_cover_width_mcf, input_cover_height_mcf, verbose,
            input_cover_width_mcf, input_cover_height_mcf, cover_transformer
        )
        fotobook.append(cover_page)
    
    # Add spine page (required structure) - uses cover dimensions and background from front cover
    spine_page = create_spine_page(input_cover_width_mcf, input_cover_height_mcf, cover_transformer,
                                   front_page.get_page_info() if front_page else None)
    fotobook.append(spine_page)
    
    # Add empty front cover fullcover page (required structure) - uses cover dimensions and background
    front_cover_empty = create_empty_cover_page(input_cover_width_mcf, input_cover_height_mcf, cover_transformer,
                                                front_page.get_page_info() if front_page else None)
    fotobook.append(front_cover_empty)
    
    # Add inside front cover (4th pagenr=0 emptypage) and page 1
    # Inside front cover is LEFT page of spread (page 0, even = left side)
    # Page 1 is RIGHT page of spread (page 1, odd = right side)
    # Page 1's content is ALWAYS added to page 0's element
    inside_front_page_obj = photobook.find_page_by_ui_num(0)

    # Create page 0 element - either with content or empty
    # Inside covers use interior page dimensions
    if inside_front_page_obj is not None:
        inside_front_data = inside_front_page_obj.get_page_info()
        # Get dimensions from the page info
        input_page0_width = round(inside_front_data['page_width'])
        input_page0_height = round(inside_front_data['page_height'])
        inside_front_page = create_page_element(inside_front_data, output_dir, 0, 'emptypage', False, verbose, ui_page=0,
                                               input_page_width=input_page0_width, input_page_height=input_page0_height,
                                               transformer=content_transformer, origin_left=0)
        z_position = 1000 + len(inside_front_data.get('photos', [])) + len(inside_front_data.get('texts', []))
    else:
        inside_front_page = create_empty_page(input_interior_width_mcf, input_interior_height_mcf, content_transformer)
        z_position = 1000
    
    fotobook.append(inside_front_page)
    
    # Add page 1's areas to page 0's element (page 1 is right side of the spread)
    page1_page_obj = photobook.find_page_by_ui_num(1)
    page1_data = page1_page_obj.get_page_info()
    logger.info("Adding areas from UI page 1 to cewe_pagenr=0 (inside front cover)")
    # Get dimensions from the page info
    input_page1_width = round(page1_data['page_width'])
    input_page1_height = round(page1_data['page_height'])
    for img in page1_data.get('photos', []):
        img['ui_page'] = 1  # Page 1 for filename
        area = create_image_area(img, output_dir, z_position, verbose,
                                input_page1_width, input_page1_height,
                                content_transformer, origin_left=input_page1_width,
                                cewe_pagenr=0)
        inside_front_page.append(area)
        z_position += 1
    for text_block in page1_data.get('texts', []):
        area = create_text_area(text_block, z_position, verbose,
                                input_page1_width, input_page1_height,
                                content_transformer, origin_left=input_page1_width)
        inside_front_page.append(area)
        z_position += 1
    
    # Create empty page 1 element (placeholder for right side)
    empty_page_1 = create_empty_content_page(input_interior_width_mcf, input_interior_height_mcf, 1, content_transformer)
    fotobook.append(empty_page_1)
    
    # Add content pages
    max_content_ui_page = photobook.get_content_page_count()

    # Process content pages starting from page 2
    # Page 0 and 1 are already handled above
    # We only process EVEN pages in the loop, because each even page creates
    # both the left page element (with areas from both pages) and an empty right page element
    if max_content_ui_page >= 2:
        for ui_page in range(2, max_content_ui_page + 1):
            # Skip odd pages (they're created when we process the preceding even page)
            if ui_page % 2 == 1:
                continue
                
            page_obj = photobook.find_page_by_ui_num(ui_page)
            if page_obj is None:
                logger.error(f"Unexpected empty UI page for {ui_page} out of {max_content_ui_page}")
                
            page_data = page_obj.get_page_info()
            cewe_pagenr = ui_page  # UI page number = CEWE page number, which we know is even here.
            # Even pages (left side of spread) contain areas for both this and next page
            # Get dimensions from the page info
            input_even_width = round(page_data['page_width'])
            input_even_height = round(page_data['page_height'])
            
            # Even page (left page of spread) - create page element with areas
            page_elem = create_page_element(page_data, output_dir, cewe_pagenr, 'normalpage', False, verbose, ui_page=ui_page,
                                            input_page_width=input_even_width, input_page_height=input_even_height,
                                            transformer=content_transformer, origin_left=0)
            fotobook.append(page_elem)
            
            # If there's a next odd page in our mapping, add its areas too
            # This includes both content pages AND the inside back cover (max_content_ui_page + 1)
            next_ui_page = ui_page + 1
            next_page_obj = photobook.find_page_by_ui_num(next_ui_page)
            # Add next page if it exists in mapping (content page or inside back cover)
            if next_page_obj is not None:
                logger.info("Adding areas from UI page %d to cewe_pagenr=%d (ui_page %d)",
                           next_ui_page, cewe_pagenr, ui_page)
                next_page_data = next_page_obj.get_page_info()
                # Get dimensions from the page info
                input_odd_width = round(next_page_data['page_width'])
                input_odd_height = round(next_page_data['page_height'])
                
                # Add the next page's areas to this page element
                z_position = 1000 + len(page_data.get('photos', [])) + len(page_data.get('texts', []))
                for img in next_page_data.get('photos', []):
                    # Use next_ui_page for the odd (right) page images
                    img['ui_page'] = next_ui_page
                    area = create_image_area(img, output_dir, z_position, verbose,
                                            input_odd_width, input_odd_height,
                                            content_transformer, origin_left=input_odd_width,
                                            cewe_pagenr=cewe_pagenr)
                    page_elem.append(area)
                    z_position += 1
                for text_block in next_page_data.get('texts', []):
                    area = create_text_area(text_block, z_position, verbose,
                                            input_odd_width, input_odd_height,
                                            content_transformer, origin_left=input_odd_width)
                    page_elem.append(area)
                    z_position += 1
                
                # Create an empty page element for the odd (right) page
                # UNLESS it's the inside back cover (which is created separately)
                if next_ui_page != max_content_ui_page + 1:
                    odd_page_elem = create_empty_content_page(input_odd_width, input_odd_height, cewe_pagenr + 1, content_transformer)
                    fotobook.append(odd_page_elem)
            else:
                logger.warning(f"Warning: No mapping found for next UI page {next_ui_page} after processing UI page {ui_page}.")

    if (max_content_ui_page % 4) != 2:
        logger.warning("Adjusting number of content pages to be multiple of 4 plus 2 for CEWE format.")
        pagesToAdd = (4 - (max_content_ui_page % 4) + 2) % 4
        logger.warning(f"Adding {pagesToAdd} blank content pages to reach required count.")
        for _ in range(pagesToAdd):
            blank_page = create_empty_content_page(input_interior_width_mcf, input_interior_height_mcf,
                                                   max_content_ui_page + 1, content_transformer)
            fotobook.append(blank_page)
            max_content_ui_page += 1


    # Add inside back cover (last pagenr=0 emptypage)
    # The inside back cover UI page is determined by looking for the highest integer key
    # in the mapping. This should be max_content_ui_page + 1.
    # CRITICAL: Inside back cover must be at an ODD page number (right side of spread)
    inside_back_ui_page = max_content_ui_page + 1
    
    # Validate: inside back cover must be odd
    if inside_back_ui_page % 2 == 0:
        logger.warning(f"Possible ERROR: inside back cover calculated as UI page {inside_back_ui_page} (even). "
                          f"It must be odd (right side). max_content_ui_page={max_content_ui_page}, "
                          f"content_pages={photobook.get_content_page_count()}")
        logger.warning("Adding a blank content page to fix alignment.")
        
        # Add an extra blank content page at the current (even) position
        blank_page = create_empty_content_page(input_interior_width_mcf, input_interior_height_mcf, 
                                               inside_back_ui_page, content_transformer)
        fotobook.append(blank_page)
        
        # Now the inside back cover moves to the next (odd) page
        inside_back_ui_page += 1
        logger.info(f"Inside back cover moved to UI page {inside_back_ui_page} (odd)")
    
    # NOTE: Inside back cover page element is always EMPTY because we already added
    # all its areas to page 60's element in the loop above (when next_ui_page == max_content_ui_page + 1)
    # This empty page element is just the required CEWE structure placeholder
    # Inside back cover uses interior page dimensions
    inside_back_page = create_empty_page(input_interior_width_mcf, input_interior_height_mcf, content_transformer)
    fotobook.append(inside_back_page)
    
    return fotobook


def scale_area_to_cewe(area_left: float, area_top: float, area_width: float, area_height: float,
                      transformer: Optional[ResizeTransformer] = None,
                      origin_left: float = 0) -> tuple[float, float, float, float]:
    """Scale area coordinates using ResizeTransformer.
    
    Args:
        area_left: Left coordinate in original MCF spread space
        area_top: Top coordinate in original MCF space
        area_width: Width in original MCF units
        area_height: Height in original MCF units
        transformer: ResizeTransformer instance or None
        origin_left: Original origin offset for right pages (old_width for right, 0 for left)
        
    Returns:
        Tuple of (scaled_left, scaled_top, scaled_width, scaled_height)
    """
    if transformer is None:
        # No transformation - return as-is
        return area_left, area_top, area_width, area_height
    
    # Use transformer.transform_rect()
    return transformer.transform_rect(area_left, area_top, area_width, area_height, origin_left)


def create_spine_page(page_width_mcf: float, page_height_mcf: float, 
                     transformer: Optional[ResizeTransformer] = None,
                     page_data: Optional[Dict[str, Any]] = None) -> ET.Element:
    """Create a spine page element (required structure between back and front cover).
    
    Args:
        page_width_mcf: Single page width in MCF units
        page_height_mcf: Page height in MCF units
        transformer: Optional ResizeTransformer for covers
        page_data: Optional page data dict (for background_id from front cover)
        
    Returns:
        Spine page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', '0')
    page.set('type', 'spine')
    page.set('rotation', '0')
    
    # Apply transformation if available
    if transformer:
        page_width_mcf, page_height_mcf = transformer.transform_page_dimensions()
    
    # Spread width is double the single page width
    spread_width_mcf = page_width_mcf * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{page_height_mcf:.0f}")
    
    # Add background if available from page_data (front cover)
    if page_data:
        background_id = page_data.get('background_id')
        if background_id:
            background = ET.SubElement(page, 'background')
            background.set('alignment', '4')
            background.set('designElementId', str(background_id))
            background.set('rotation', '0')
            background.set('type', '1')
    
    return page


def create_empty_cover_page(page_width_mcf: float, page_height_mcf: float, 
                           transformer: Optional[ResizeTransformer] = None,
                           page_data: Optional[Dict[str, Any]] = None) -> ET.Element:
    """Create an empty front cover page element (required structure).
    
    This is the third pagenr=0 page, typically empty but required by CEWE structure.
    
    Args:
        page_width_mcf: Single page width in MCF units
        page_height_mcf: Page height in MCF units
        transformer: Optional ResizeTransformer for covers
        page_data: Optional page data dict (for background_id from front cover)
        
    Returns:
        Empty cover page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', '0')
    page.set('type', 'fullcover')
    page.set('rotation', '0')
    
    # Apply transformation if available
    if transformer:
        page_width_mcf, page_height_mcf = transformer.transform_page_dimensions()
    
    # Spread width is double the single page width
    spread_width_mcf = page_width_mcf * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{page_height_mcf:.0f}")
    
    # Add background if available from page_data (front cover)
    if page_data:
        background_id = page_data.get('background_id')
        if background_id:
            background = ET.SubElement(page, 'background')
            background.set('alignment', '4')
            background.set('designElementId', str(background_id))
            background.set('rotation', '0')
            background.set('type', '1')
    
    return page


def create_cover_spread_element(front_page_data: Dict[str, Any], back_page_data: Optional[Dict[str, Any]],
                                output_dir: Path, page_width_mcf: float, page_height_mcf: float, 
                                verbose: bool = False,
                                input_page_width: float = None, input_page_height: float = None,
                                transformer: Optional[ResizeTransformer] = None) -> ET.Element:
    """Create a cover spread element with both front and back covers.
    
    The cover spread is a single page element with pagenr=0 and type=fullcover.
    - Back cover images: left half of spread (x < page_width_mcf)
    - Front cover images: right half of spread (x >= page_width_mcf)
    
    Args:
        front_page_data: Front cover page content (positioned on right half)
        back_page_data: Back cover page content (positioned on left half), or None if no back cover
        output_dir: Directory to save image files
        page_width_mcf: Single page width in MCF units (original, before transformation)
        page_height_mcf: Page height in MCF units (original, before transformation)
        verbose: Print detailed info
        input_page_width: Original PDF page width (for scaling)
        input_page_height: Original PDF page height (for scaling)
        transformer: Optional ResizeTransformer for covers
        
    Returns:
        Cover page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', '0')
    page.set('type', 'fullcover')
    page.set('rotation', '0')
    
    # Get transformed dimensions if transformer available
    transformed_width = page_width_mcf
    transformed_height = page_height_mcf
    if transformer:
        transformed_width, transformed_height = transformer.transform_page_dimensions()
    
    # Cover spread is double width
    spread_width_mcf = transformed_width * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{transformed_height:.0f}")
    
    # Add background if available from front or back cover page_data
    # Prioritize front cover background (more visible), fall back to back cover
    background_id = front_page_data.get('background_id')
    if background_id is None and back_page_data:
        background_id = back_page_data.get('background_id')
    
    if background_id:
        background = ET.SubElement(page, 'background')
        background.set('alignment', '4')
        background.set('designElementId', str(background_id))
        background.set('rotation', '0')
        background.set('type', '1')
    
    z_position = 1000
    
    # Add back cover images (left half of spread)
    # PDF extractor now correctly positions back cover on left side
    if back_page_data:
        for img in back_page_data.get('photos', []):
            img['ui_page'] = 'B'  # Back cover identifier
            area = create_image_area(img, output_dir, z_position, verbose,
                                    input_page_width, input_page_height, transformer, origin_left=0,
                                    cewe_pagenr=None)  # No validation for cover pages
            page.append(area)
            z_position += 1
        
        for text_block in back_page_data.get('texts', []):
            area = create_text_area(text_block, z_position, verbose,
                                   input_page_width, input_page_height, transformer, origin_left=0)
            page.append(area)
            z_position += 1
    
    # Add front cover images (right half of spread)
    # Front cover images from PDF already have x in [page_width, 2*page_width) since they're right pages
    for img in front_page_data.get('photos', []):
        img['ui_page'] = 'F'  # Front cover identifier
        area = create_image_area(img, output_dir, z_position, verbose,
                                input_page_width, input_page_height, transformer, origin_left=page_width_mcf,
                                cewe_pagenr=None)  # No validation for cover pages
        page.append(area)
        z_position += 1
    
    for text_block in front_page_data.get('texts', []):
        area = create_text_area(text_block, z_position, verbose,
                               input_page_width, input_page_height, transformer, origin_left=page_width_mcf) 
        page.append(area)
        z_position += 1
    
    return page


def create_empty_page(page_width_mcf: float, page_height_mcf: float, transformer: Optional[ResizeTransformer] = None) -> ET.Element:
    """Create an empty page element (inside cover).
    
    Args:
        page_width_mcf: Single page width in MCF units
        page_height_mcf: Page height in MCF units
        transformer: Optional ResizeTransformer
        
    Returns:
        Empty page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', '0')
    page.set('type', 'emptypage')
    page.set('rotation', '0')
    
    # Apply transformation if available
    if transformer:
        page_width_mcf, page_height_mcf = transformer.transform_page_dimensions()
    
    # Spread width is double the single page width
    spread_width_mcf = page_width_mcf * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{page_height_mcf:.0f}")
    
    return page


def create_empty_content_page(page_width_mcf: float, page_height_mcf: float, pagenr: int, transformer: Optional[ResizeTransformer] = None) -> ET.Element:
    """Create an empty content page element (for odd pages with no areas).
    
    Odd pages (right pages) in CEWE photobooks have their areas stored in the preceding
    even page's XML. The odd page elements themselves are mostly empty, containing only
    bundlesize and background information.
    
    Args:
        page_width_mcf: Single page width in MCF units
        page_height_mcf: Page height in MCF units
        pagenr: Page number (should be odd)
        transformer: Optional ResizeTransformer
        
    Returns:
        Empty content page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', str(pagenr))
    page.set('type', 'normalpage')
    page.set('rotation', '0')
    
    # Apply transformation if available
    if transformer:
        page_width_mcf, page_height_mcf = transformer.transform_page_dimensions()
    
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
                       input_page_width: float = None, input_page_height: float = None,
                       transformer: Optional[ResizeTransformer] = None, origin_left: float = 0) -> ET.Element:
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
        input_page_width: Original PDF page width (for scaling)
        input_page_height: Original PDF page height (for scaling)
        transformer: Optional ResizeTransformer
        origin_left: Original origin offset for this page (0 for left, page_width for right)
        
    Returns:
        Page XML element
    """
    page = ET.Element('page')
    page.set('pagenr', str(cewe_pagenr))
    page.set('type', page_type)
    page.set('rotation', '0')
    
    # CEWE photobooks use two-page spreads
    # bundlesize = width of spread (2 pages side-by-side) × height of one page
    page_width_mcf = input_page_width
    page_height_mcf = input_page_height
    
    # Apply transformation if available
    if transformer:
        page_width_mcf, page_height_mcf = transformer.transform_page_dimensions()

    # Spread width is double the single page width
    spread_width_mcf = page_width_mcf * 2
    
    bundlesize = ET.SubElement(page, 'bundlesize')
    bundlesize.set('width', f"{spread_width_mcf:.0f}")
    bundlesize.set('height', f"{page_height_mcf:.0f}")
    
    # Add background if available from page_data
    background_id = page_data.get('background_id')
    if background_id:
        background = ET.SubElement(page, 'background')
        background.set('alignment', '4')
        background.set('designElementId', str(background_id))
        background.set('rotation', '0')
        background.set('type', '1')
    
    # Coordinates are already in MCF spread units from PDF extractor
    # No x_offset calculation needed - positioning already handled
    
    z_position = 1000  # Starting z-position
    
    # Add image areas
    for img in page_data['photos']:
        # Use UI page number if provided, otherwise fall back to PDF page_num
        img['ui_page'] = ui_page if ui_page is not None else page_data.get('page_num', cewe_pagenr)
        area = create_image_area(img, output_dir, z_position, verbose,
                                input_page_width, input_page_height, transformer, origin_left,
                                cewe_pagenr=cewe_pagenr)
        page.append(area)
        z_position += 1
    
    # Add text areas
    for text_block in page_data['texts']:
        area = create_text_area(text_block, z_position, verbose,
                               input_page_width, input_page_height, transformer, origin_left)
        page.append(area)
        z_position += 1
    
    return page


def create_image_area(img: Dict[str, Any], output_dir: Path, z_position: int, verbose: bool = False,
                     input_page_width: float = None, input_page_height: float = None,
                     transformer: Optional[ResizeTransformer] = None, origin_left: float = 0,
                     cewe_pagenr: int = None) -> ET.Element:
    """Create an image area element.
    
    Args:
        img: Image data dictionary with coordinates in MCF spread units
        output_dir: Directory to save image file
        z_position: Z-position for layering
        verbose: Print detailed info
        input_page_width: Original PDF page width (for scaling)
        input_page_height: Original PDF page height (for scaling)
        transformer: Optional ResizeTransformer
        origin_left: Original origin offset for this page (0 for left, page_width for right)
        cewe_pagenr: CEWE page number where this image will be saved (for validation)
        
    Returns:
        Area XML element
    """
    from ..file_utils import encode_metadata_in_filename
    
    # Get UI page identifier ("F", "B", 0, 1, 2, ...) for filename generation
    ui_page = img.get('ui_page', 0)
    relative_size = img.get('relative_size', 1.0)
    
    # If image already has a filename (e.g., from CEWE MCF, Mimeo converter), use it
    # Otherwise generate a new filename
    if 'filename' in img and img['filename']:
        image_filename = img['filename']
        # Strip CEWE's "safecontainer:/" prefix if present
        if image_filename.startswith('safecontainer:/'):
            image_filename = image_filename[len('safecontainer:/'):]
    else:
        # Generate new filename - requires 'index' field
        index = img.get('index', 0)  # Default to 0 if not provided
        
        # Format page identifier for filename: F/B as-is, numbers zero-padded
        if isinstance(ui_page, str):
            page_str = ui_page
        else:
            page_str = f"{ui_page:03d}"
        
        base_filename = f"image_p{page_str}_{index:04d}.{img['format']}"
        image_filename = encode_metadata_in_filename(base_filename, relative_size, ui_page)
    
    image_path = output_dir / image_filename
    
    # VALIDATION: Check that photos with "-pgN" suffix are being saved in the correct <page> element
    # This catches bugs where photos from odd (right) pages are placed in wrong page elements
    if cewe_pagenr is not None:
        # Extract page number from filename if it has "-pgN" suffix
        import re
        match = re.search(r'-pg(\d+)', image_filename)
        if match:
            filename_page = int(match.group(1))
            # The filename page should be either cewe_pagenr or cewe_pagenr+1
            # (because a spread can contain photos from both the left and right pages)
            if filename_page not in [cewe_pagenr, cewe_pagenr + 1]:
                raise ValueError(
                    f"ERROR: Photo filename mismatch detected!\n"
                    f"  Filename: {image_filename} (indicates page {filename_page})\n"
                    f"  Being saved in: <page pagenr=\"{cewe_pagenr}\">\n"
                    f"  Expected: Photo from page {filename_page} should be in pagenr={filename_page} or pagenr={filename_page-1}\n"
                    f"  This indicates a bug in page number assignment (ui_page) during MCF generation."
                )
    
    # Only write image data if it's provided (PDF extracts bytes, Mimeo already copied files)
    if img.get('data') is not None:
        image_path.write_bytes(img['data'])
        
        if verbose:
            camera_name = img.get('camera_filename', 'unknown')
            uuid_name = img.get('original_filename', 'unknown')
            #print(f"  Saved image: {image_filename} (camera: {camera_name}, uuid: {uuid_name})")
    else:
        # File should already exist (pre-copied by converter)
        if not image_path.exists():
            raise FileNotFoundError(
                f"Image file not found: {image_path}\n"
                f"Image data is None but file was not pre-copied by converter."
            )
        if verbose:
            print(f"  Using existing image: {image_filename}")
    
    # Scale coordinates from PDF to CEWE dimensions if scaling info provided
    # Note: Coordinates are in spread space, so use 2*page_width for spread width
    scaled_left, scaled_top, scaled_width, scaled_height = scale_area_to_cewe(
        img['area_left'], img['area_top'], img['area_width'], img['area_height'], transformer, origin_left
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
                    input_page_width: float = None, input_page_height: float = None,
                    transformer: Optional[ResizeTransformer] = None, origin_left: float = 0) -> ET.Element:
    """Create a text area element.
    
    Args:
        text_block: Text block data dictionary with coordinates in MCF spread units
        z_position: Z-position for layering
        verbose: Print detailed info
        input_page_width: Original PDF page width (for scaling)
        input_page_height: Original PDF page height (for scaling)
        transformer: Optional ResizeTransformer
        origin_left: Original origin offset for this page (0 for left, page_width for right)
        
    Returns:
        Area XML element
    """
    # Scale coordinates from PDF to CEWE dimensions if scaling info provided
    # Note: Coordinates are in spread space, so use 2*page_width for spread width
    scaled_left, scaled_top, scaled_width, scaled_height = scale_area_to_cewe(
        text_block['area_left'], text_block['area_top'], text_block['area_width'], text_block['area_height'], transformer, origin_left)
    
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
    
    # Check format: CEWE (has 'raw_html') vs Mimeo/PDF (has 'text', 'font', 'size')
    if 'raw_html' in text_block:
        # CEWE format: use raw HTML directly
        html_content = text_block['raw_html']
        font_size = text_block.get('font_size', 12)
        
        # Set areaTextType attribute
        text.set('areaTextType', 'content')
        text.text = html_content
        
        # Add outline element
        outline = ET.SubElement(text, 'outline')
        outline.set('width', '0')
        
        # TextFormat element - minimal attributes for CEWE format
        textFormat = ET.SubElement(text, 'textFormat')
        
        # Build alignment string from h_align and v_align
        h_align = text_block.get('h_align', 'left')
        v_align = text_block.get('v_align', 'top')
        
        align_parts = []
        if v_align == 'center':
            align_parts.append('ALIGNVCENTER')
        elif v_align == 'bottom':
            align_parts.append('ALIGNBOTTOM')
        else:  # top or default
            align_parts.append('ALIGNTOP')
        
        if h_align == 'center':
            align_parts.append('ALIGNHCENTER')
        elif h_align == 'right':
            align_parts.append('ALIGNRIGHT')
        else:  # left or default
            align_parts.append('ALIGNLEFT')
        
        textFormat.set('Alignment', ','.join(align_parts))
        textFormat.set('IndentMargin', '4')
        textFormat.set('VerticalIndentMargin', '50')
        textFormat.set('backgroundColor', '#00000000')
        # Note: We don't have full font info from CEWE format, so use minimal font string
        textFormat.set('font', f"Arial,{font_size},-1,5,400,0,0,0,0,0,0,1,0,0,0,1")
        textFormat.set('foregroundColor', '#ff000000')
        textFormat.set('hasOutline', '0')
        textFormat.set('hyphenation', '0')
        textFormat.set('letterSpacing', '0')
        textFormat.set('lineHeight', '100')
    else:
        # Mimeo/PDF format: generate HTML from text, font, size, color, flags
        color_int = text_block.get('color', 0)
        color_hex = f"#{color_int:06x}"
        
        # Determine font weight from flags
        flags = text_block.get('flags', 0)
        is_bold = bool(flags & 2**4)  # Bit 4 is bold
        is_italic = bool(flags & 2**6)  # Bit 6 is italic
        
        font_weight = '700' if is_bold else '400'
        font_style = 'italic' if is_italic else 'normal'
        
        font_name = text_block['font']
        font_size = int(text_block['size'])
        text_content = text_block['text']
        
        # Create minimal HTML content - just font, size, and text
        html_content = f'<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd"><html><head><meta name="qrichtext" content="1" /></head><body style="font-family:\'{font_name}\'; font-size:{font_size}pt;"><p><span style="color:{color_hex};">{escape_html(text_content)}</span></p></body></html>'
        
        # Set areaTextType attribute
        text.set('areaTextType', 'content')
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
        textFormat.set('font', f"{font_name},{font_size},-1,5,{font_weight},0,0,0,0,0,0,1,0,0,0,1")
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


def add_cewe_boilerplate_elements(fotobook: ET.Element, num_normal_pages: int) -> None:
    """Add required CEWE boilerplate XML elements to fotobook.
    
    These elements (project, savingVersion, creationHistory, articleConfig) are required
    by CEWE's photobook format and appear immediately after the opening
    fotobook tag.
    
    Args:
        fotobook: The fotobook element to add boilerplate to
        num_normal_pages: Highest page number in the book (for articleConfig)
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
    article_config.set('normalpages', str(num_normal_pages))
    article_config.set('pagenaming', '1')
    article_config.set('spotColor', 'digital_embossing')
    article_config.set('totalpages', str(num_normal_pages + 5))


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
