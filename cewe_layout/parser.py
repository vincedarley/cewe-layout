"""Minimal parser to extract area/image/cutout info from CEWE .mcf XML."""
from lxml import etree
import os
import glob
import logging
from .page_utils import determine_page_owner

logger = logging.getLogger(__name__)

# Fixed edge gaps for A5 Calendar format (calculated from Month 1 image area)
# These gaps define the usable image layout area within each calendar page
CALENDAR_EDGE_GAPS = {
    'left': 70.0,
    'top': 120.0,
    'right': 70.0,
    'bottom': 250.0
}


def is_canvas_format(fotobook_root):
    """Detect if this is a Canvas format (single large page) vs photobook.
    
    Canvas products have normalpages="1" and use a single page with one bundlesize.
    Photobooks have normalpages >= 1 and use two-page spreads.
    
    Returns:
        True if Canvas format, False if photobook format
    """
    article_config = fotobook_root.find('articleConfig')
    if article_config is not None:
        try:
            normal_pages = int(article_config.get('normalpages', '0'))
            total_pages = int(article_config.get('totalpages', '0'))
            # Canvas has exactly 1 normal page and 1 total page
            if normal_pages == 1 and total_pages == 1:
                return True
        except (ValueError, TypeError):
            pass
    return False


def is_calendar_format(fotobook_root):
    """Detect if this is a Calendar format.
    
    Calendars have:
    - Page 0 with type="calendarcoverfront" (title page)
    - Pages 1-N with type="normalpage" (monthly pages)
    - Each page is standalone (not split into left/right like photobooks)
    - normalpages typically equals 12 (for 12 months)
    - totalpages = normalpages + 1 (including title page)
    
    Returns:
        True if Calendar format, False otherwise
    """
    # Check for special calendar cover page at pagenr="0"
    for page in fotobook_root.findall('.//page'):
        if page.get('pagenr') == '0' and page.get('type') == 'calendarcoverfront':
            return True
    return False


def parse_mcf_from_path(path: str):
    # Accept either a path to an .mcf file or a folder containing `data.mcf` (e.g. an unpacked .xmcf).
    # Use resolve_mcf_path to find the file, then parse it.
    real_path = resolve_mcf_path(path)
    with open(real_path, 'rb') as fh:
        tree = etree.parse(fh)
    return tree.getroot()


def resolve_mcf_path(path: str) -> str:
    """Return an actual .mcf file path for `path` which may be a file or directory.

    Preference order for directories: `data.mcf`, non-recursive `*.mcf`, recursive `**/*.mcf`.
    """
    if os.path.isdir(path):
        # Prefer data.mcf
        candidate = os.path.join(path, 'data.mcf')
        if os.path.exists(candidate):
            return candidate
        # first try non-recursive .mcf files
        files = glob.glob(os.path.join(path, '*.mcf'))
        if files:
            return files[0]
        # try recursive search
        files = glob.glob(os.path.join(path, '**', '*.mcf'), recursive=True)
        if files:
            return files[0]
        raise FileNotFoundError(f'No .mcf file found in directory: {path}')
    # otherwise assume it's a file path
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    return path


def _is_normal_page(page_el):
    # Skip pagenr==0 (covers/special pages); treat numeric pagenr >=1 as normal pages
    pagenr = page_el.get('pagenr')
    if pagenr is None:
        return False
    try:
        n = int(pagenr)
        return n >= 1
    except Exception as e:
        logger.warning(f"Failed to parse page number '{pagenr}': {e}")
        return False


def extract_pages_info(fotobook_root):
    # Collect photos per logical page number. Many .mcf files store a two-page spread
    # in a single <page> element (the "bundle"). To handle that we split areas
    # by the bundle width into left/right halves and assign them to adjacent pages.
    # EXCEPT for Canvas and Calendar formats which have standalone pages with no splitting.
    # ALSO extract cover pages (pagenr="0" type="fullcover") as special pages.
    from collections import defaultdict

    canvas_mode = is_canvas_format(fotobook_root)
    calendar_mode = is_calendar_format(fotobook_root)
    # Single-page mode: treat each page as standalone (no left/right split)
    single_page_mode = canvas_mode or calendar_mode
    pages_map = defaultdict(list)

    logger.debug(f"extract_pages_info: canvas_mode={canvas_mode}, calendar_mode={calendar_mode}, single_page_mode={single_page_mode}")
    
    all_pages = fotobook_root.findall('.//page')
    logger.debug(f"extract_pages_info: Found {len(all_pages)} total page elements in XML")
    
    # Find cover page (type="fullcover")
    # Note: The fullcover page contains BOTH front and back covers in one spread
    # Left half = back cover, Right half = front cover (just like normal page spreads)
    cover_page = None
    for page in all_pages:
        if page.get('type') == 'fullcover':
            template_name = page.get('designStyleTemplateName', '')
            # Find the cover page that has areas (content)
            if page.findall('.//area'):
                cover_page = page
                break
    
    if cover_page is None:
        logger.debug(f"extract_pages_info: No fullcover pages with content found")
    else:
        logger.debug(f"extract_pages_info: Found fullcover page with areas")

    # Helper function to extract areas from a cover page
    def _process_cover_page(page_el, page_number, is_front_cover):
        """Process a cover page and add it to pages_map."""
        bundlesize = page_el.find('./bundlesize')
        if bundlesize is None:
            logger.warning(f"Cover page {page_number} missing bundlesize, skipping")
            return
        
        try:
            spread_w = float(bundlesize.get('width'))
            spread_h = float(bundlesize.get('height'))
        except (TypeError, ValueError, AttributeError) as e:
            logger.warning(f"Cover page {page_number} has invalid bundlesize: {e}, skipping")
            return
        
        # Extract background for cover
        background_id = None
        for bg in page_el.findall('background'):
            if bg.get('alignment') is not None:
                background_id = bg.get('designElementId')
                break
        
        # Cover page width: MCF stores full spread width, but we display half for single page
        # (just like normal pages - only show full width in spread mode)
        page_w = spread_w / 2.0
        
        # origin_left: back cover is left half (0.0), front cover is right half (page_w)
        origin_left = page_w if is_front_cover else 0.0
        
        # Initialize page entry
        pages_map[page_number] = {
            'photos': [],
            'texts': [],
            'page_width': page_w,
            'page_height': spread_h,
            'origin_left': origin_left,
            'background_id': background_id,
            'is_canvas': False,
            'is_calendar': False,
            'is_cover': True,
            'is_front_cover': is_front_cover,
            'has_full_bleed': True,  # Covers have bleed on all 4 sides
            'rotation': 0.0,
            'physical_width': spread_w,  # Store original for potential spread mode
            'physical_height': spread_h,
            'calendar_edge_gaps': None
        }
        
        # Extract areas from cover page
        # Front cover is right half (x >= spread_w/2), back cover is left half (x < spread_w/2)
        for area in page_el.findall('.//area'):
            pos = area.find('position')
            if pos is None:
                continue
            
            try:
                area_left = float(pos.get('left').replace(',', '.'))
                area_top = float(pos.get('top').replace(',', '.'))
                area_width = float(pos.get('width').replace(',', '.'))
                area_height = float(pos.get('height').replace(',', '.'))
                area_rot = float(pos.get('rotation').replace(',', '.'))
            except (TypeError, ValueError, AttributeError) as e:
                logger.warning(f"Cover page {page_number}: Failed to parse area position: {e}")
                continue
            
            areatype = area.get('areatype', 'imagearea')
            
            # Filter based on which half of the spread this area is in
            area_center_x = area_left + area_width / 2.0
            is_on_right_half = area_center_x >= page_w  # page_w is spread_w/2
            
            # Skip this area if it's not on the correct half
            if is_front_cover and not is_on_right_half:
                continue  # Front cover: skip left half
            if not is_front_cover and is_on_right_half:
                continue  # Back cover: skip right half
            
            # Note: origin_left handles the page offset, so coordinates remain in spread units
            # The renderer will subtract origin_left to make them page-relative
            
            areatype = area.get('areatype', 'imagearea')
            
            if areatype == 'textarea':
                raw_html = ""
                text_tag = area.find('text')
                if text_tag is not None and text_tag.text:
                    raw_html = text_tag.text.strip()
                
                # Parse textFormat for font size and alignment
                font_size = 12  # default
                h_align = 'left'  # default horizontal alignment
                v_align = 'top'  # default vertical alignment
                
                text_format = area.find('.//textFormat')
                if text_format is not None:
                    # Parse font attribute (format: "FontName,size,...")
                    font_attr = text_format.get('font', '')
                    if font_attr:
                        parts = font_attr.split(',')
                        if len(parts) > 1:
                            try:
                                font_size = int(parts[1])
                            except (ValueError, IndexError):
                                pass
                    
                    # Parse alignment (format: "ALIGNVCENTER,ALIGNHCENTER" or "ALIGNLEFT", etc.)
                    alignment = text_format.get('Alignment', '')
                    if alignment:
                        # Horizontal alignment
                        if 'ALIGNHCENTER' in alignment:
                            h_align = 'center'
                        elif 'ALIGNTRAILING' in alignment or 'ALIGNRIGHT' in alignment:
                            h_align = 'right'
                        elif 'ALIGNLEADING' in alignment or 'ALIGNLEFT' in alignment:
                            h_align = 'left'
                        
                        # Vertical alignment
                        if 'ALIGNVCENTER' in alignment:
                            v_align = 'center'
                        elif 'ALIGNBOTTOM' in alignment:
                            v_align = 'bottom'
                        elif 'ALIGNTOP' in alignment:
                            v_align = 'top'
                
                # Extract plain text for debug output
                import re, html
                plain_text = raw_html
                plain_text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', plain_text, flags=re.DOTALL)
                plain_text = re.sub(r'<style[^>]*>.*?</style>', '', plain_text, flags=re.DOTALL | re.IGNORECASE)
                plain_text = re.sub(r'<head[^>]*>.*?</head>', '', plain_text, flags=re.DOTALL | re.IGNORECASE)
                plain_text = re.sub(r'<[^>]+>', '', plain_text)
                plain_text = html.unescape(plain_text)
                plain_text = ' '.join(plain_text.split()).strip()
                
                logger.debug(f"  Page {page_number} textarea: text='{plain_text[:50]}{'...' if len(plain_text) > 50 else ''}' font_size={font_size} h_align={h_align} v_align={v_align}")
                
                text_info = {
                    'area_left': area_left,
                    'area_top': area_top,
                    'area_width': area_width,
                    'area_height': area_height,
                    'area_rot': area_rot,
                    'raw_html': raw_html,
                    'font_size': font_size,
                    'h_align': h_align,
                    'v_align': v_align,
                }
                pages_map[page_number]['texts'].append(text_info)
            elif areatype == 'imagearea':
                for imageTag in area.findall('image'):
                    info = {
                        'filename': imageTag.get('filename'),
                        'area_left': area_left,
                        'area_top': area_top,
                        'area_width': area_width,
                        'area_height': area_height,
                        'area_rot': area_rot,
                    }
                    cut = imageTag.find('cutout')
                    if cut is not None:
                        try:
                            cleft = cut.get('left')
                            ctop = cut.get('top')
                            cscale = cut.get('scale')
                            info['cutout'] = {'left': cleft, 'top': ctop, 'scale': cscale}
                        except (TypeError, AttributeError):
                            info['cutout'] = None
                    else:
                        info['cutout'] = None
                    
                    pages_map[page_number]['photos'].append(info)
    
    # For photobooks: identify the two pagenr="0" type="emptypage" elements
    # First one (before pagenr="1") is inside front cover (page 0)
    # Last one (after last numbered page) is inside back cover (page N+1)
    inside_front_cover_page = None
    inside_back_cover_page = None
    max_normal_pagenr = None
    if not single_page_mode:
        # Find all pagenr="0" type="emptypage" elements
        empty_pages = []
        for i, page in enumerate(all_pages):
            if page.get('pagenr') == '0' and page.get('type') == 'emptypage':
                empty_pages.append((i, page))
        
        if len(empty_pages) >= 1:
            # First one is inside front cover
            inside_front_cover_page = empty_pages[0][1]
            logger.debug(f"extract_pages_info: Found inside front cover at index {empty_pages[0][0]}")
        
        if len(empty_pages) >= 2:
            # Last one is inside back cover
            inside_back_cover_page = empty_pages[-1][1]
            logger.debug(f"extract_pages_info: Found inside back cover at index {empty_pages[-1][0]}")
            
            # Find the maximum normal page number to prevent creating page beyond it
            for page in all_pages:
                if _is_normal_page(page):
                    try:
                        pagenr = int(page.get('pagenr'))
                        if max_normal_pagenr is None or pagenr > max_normal_pagenr:
                            max_normal_pagenr = pagenr
                    except (TypeError, ValueError):
                        pass
            logger.debug(f"extract_pages_info: Max normal pagenr={max_normal_pagenr}")

    # Pre-create entries for all normal pages (even if empty)
    # This ensures empty pages don't get lost
    # Also handle inside cover pages (pagenr="0" type="emptypage")
    for page in all_pages:
        pagenr_str = page.get('pagenr')
        page_type = page.get('type')
        is_normal = _is_normal_page(page)
        is_inside_front_cover = (page is inside_front_cover_page)
        is_inside_back_cover = (page is inside_back_cover_page)
        
        if not is_normal and not is_inside_front_cover and not is_inside_back_cover:
            continue
        
        # Handle inside cover pages specially
        if is_inside_front_cover:
            pagenr = 0
        elif is_inside_back_cover:
            # We'll determine the page number later (max + 1), skip for now
            continue
        else:
            try:
                pagenr = int(pagenr_str)
            except (TypeError, ValueError):
                continue
        
        # Get bundlesize for this page
        bundlesize = page.find('./bundlesize')
        if bundlesize is None:
            continue
        try:
            spread_w = float(bundlesize.get('width'))
            spread_h = float(bundlesize.get('height'))
        except (TypeError, ValueError, AttributeError):
            continue
        
        # Check rotation
        page_rotation = page.get('rotation', '0')
        try:
            rotation_degrees = float(page_rotation)
        except (TypeError, ValueError):
            rotation_degrees = 0.0
        
        if rotation_degrees in (90.0, 270.0):
            logical_spread_w = spread_h
            logical_spread_h = spread_w
        else:
            logical_spread_w = spread_w
            logical_spread_h = spread_h
        
        if canvas_mode:
            half = logical_spread_w
        else:
            half = logical_spread_w / 2.0
        
        # Extract background
        background_id = None
        for bg in page.findall('background'):
            if bg.get('alignment') is not None:
                background_id = bg.get('designElementId')
                break
        
        # Pre-create page entries for both left and right pages
        # (or just the single page in canvas mode)
        if single_page_mode:
            owners = [pagenr]
            origin_lefts = [0.0]
            page_widths = [logical_spread_w]
        else:
            if (pagenr % 2) == 0:
                # Even pagenr -> left page is pagenr, right is pagenr+1
                # BUT: if this is the last normal page and there's an inside back cover,
                # don't create pagenr+1 (it will be the inside back cover)
                if inside_back_cover_page is not None and pagenr == max_normal_pagenr:
                    owners = [pagenr]
                    origin_lefts = [0.0]
                    page_widths = [half]
                else:
                    owners = [pagenr, pagenr + 1]
                    origin_lefts = [0.0, half]
                    page_widths = [half, half]
            else:
                # Odd pagenr -> left page is pagenr-1 (or skip if would be < 1), right is pagenr
                owners = [max(1, pagenr - 1), pagenr]
                origin_lefts = [0.0, half]
                page_widths = [half, half]
        
        for owner, origin_left, page_width in zip(owners, origin_lefts, page_widths):            
            if owner not in pages_map:
                pages_map[owner] = {
                    'photos': [], 
                    'texts': [], 
                    'page_width': page_width, 
                    'page_height': logical_spread_h, 
                    'origin_left': origin_left, 
                    'background_id': background_id, 
                    'is_canvas': canvas_mode,
                    'is_calendar': calendar_mode,
                    'rotation': rotation_degrees,
                    'physical_width': spread_w,
                    'physical_height': spread_h,
                    'calendar_edge_gaps': CALENDAR_EDGE_GAPS.copy() if calendar_mode else None,
                    'cewe_pagenr': pagenr,
                    'page_type': page_type
                }
    
    # Now create inside back cover page (after we know max page number)
    if inside_back_cover_page is not None and not single_page_mode:
        numeric_pages = [k for k in pages_map.keys() if isinstance(k, int) and k > 0]
        if numeric_pages:
            inside_back_page_num = max(numeric_pages) + 1
            
            # DEBUG: Verify inside back cover number
            logger.debug(f"extract_pages_info: Inside back cover calculated as page {inside_back_page_num}, numeric_pages max={max(numeric_pages)}")
            if inside_back_page_num % 2 == 0:
                raise RuntimeError(f"ERROR: Inside back cover page {inside_back_page_num} is even (left side). It should be odd (right side).")
            
            # Get dimensions from a normal page
            sample_page = pages_map[min(numeric_pages)]
            pages_map[inside_back_page_num] = {
                'photos': [],
                'texts': [],
                'page_width': sample_page['page_width'],
                'page_height': sample_page['page_height'],
                'origin_left': 0.0,  # Left side
                'background_id': None,
                'is_canvas': False,
                'is_calendar': False,
                'is_cover': False,
                'is_front_cover': False,
                'has_full_bleed': False,
                'rotation': 0.0,
                'physical_width': sample_page['page_width'] * 2,
                'physical_height': sample_page['page_height'],
                'calendar_edge_gaps': None
            }
            logger.debug(f"extract_pages_info: Created inside back cover as page {inside_back_page_num}")
    
    # Now process areas and add them to the pre-created pages
    for page in all_pages:
        pagenr_str = page.get('pagenr')
        page_type = page.get('type')
        is_normal = _is_normal_page(page)
        is_inside_front_cover = (page is inside_front_cover_page)
        is_inside_back_cover = (page is inside_back_cover_page)
        
        logger.debug(f"extract_pages_info: Processing page pagenr='{pagenr_str}' type='{page_type}' is_normal={is_normal}")
        
        # Skip pages that are not normal or inside covers
        if not is_normal and not is_inside_front_cover and not is_inside_back_cover:
            logger.debug(f"  Skipping page pagenr='{pagenr_str}' (not normal or inside cover)")
            continue
        
        # Process this page to extract areas
        try:
            pagenr = int(pagenr_str)
        except (TypeError, ValueError):
            logger.warning(f"Skipping page with invalid pagenr: '{pagenr_str}'")
            continue

        # determine spread width/height from bundlesize (required in MCF)
        bundlesize = page.find('./bundlesize')
        if bundlesize is None:
            raise ValueError(f"Page {pagenr} missing bundlesize element - MCF file format may have changed")
        try:
            spread_w = float(bundlesize.get('width'))
            spread_h = float(bundlesize.get('height'))
        except (TypeError, ValueError, AttributeError) as e:
            raise ValueError(f"Page {pagenr} has invalid bundlesize: {e} - MCF file format may have changed") from e
        
        # Check for page rotation (used in portrait Canvases)
        page_rotation = page.get('rotation', '0')
        try:
            rotation_degrees = float(page_rotation)
        except (TypeError, ValueError):
            rotation_degrees = 0.0
        
        # For 90° or 270° rotation, swap width and height for logical dimensions
        # This way the UI works in portrait mode naturally
        if rotation_degrees in (90.0, 270.0):
            # Swap dimensions - stored as landscape, display as portrait
            logical_spread_w = spread_h
            logical_spread_h = spread_w
        else:
            logical_spread_w = spread_w
            logical_spread_h = spread_h
        
        # Canvas mode: treat entire bundlesize as single page (no left/right split)
        if canvas_mode:
            half = logical_spread_w  # No splitting
        else:
            half = logical_spread_w / 2.0

        for area in page.findall('.//area'):
            pos = area.find('position')
            if pos is None:
                continue
            try:
                area_left = float(pos.get('left').replace(',', '.'))
                area_top = float(pos.get('top').replace(',', '.'))
                area_width = float(pos.get('width').replace(',', '.'))
                area_height = float(pos.get('height').replace(',', '.'))
                area_rot = float(pos.get('rotation').replace(',', '.'))
            except (TypeError, ValueError, AttributeError) as e:
                logger.error(f"Page {pagenr}: Failed to parse area position coordinates: {e} - MCF file format may have changed")
                raise ValueError(f"Page {pagenr}: Invalid area position data") from e
            
            # Apply page rotation transformation if needed
            # For 90° rotation: portrait displayed as landscape in MCF
            # Transform: physical (x, y, w, h) → logical rotated 90° clockwise
            if rotation_degrees == 90.0:
                # Rotate coordinates 90° clockwise: (x,y) → (y, W-x-w)
                rotated_left = area_top
                rotated_top = spread_w - area_left - area_width
                rotated_width = area_width  # Keep as-is (swapped below)
                rotated_height = area_height  # Keep as-is (swapped below)
                area_left = rotated_left
                area_top = rotated_top
                # Swap width and height after rotation
                area_width = rotated_height
                area_height = rotated_width
                # Also rotate the area's own rotation
                area_rot = (area_rot + 90.0) % 360.0
            elif rotation_degrees == 270.0:
                # Rotate coordinates 270° clockwise (90° counter-clockwise): (x,y) → (H-y-h, x)
                rotated_left = spread_h - area_top - area_height
                rotated_top = area_left
                rotated_width = area_height
                rotated_height = area_width
                area_left = rotated_left
                area_top = rotated_top
                area_width = rotated_width
                area_height = rotated_height
                # Also rotate the area's own rotation
                area_rot = (area_rot + 270.0) % 360.0

            # Decide which logical page the area belongs to by its left edge
            # Single-page mode (Canvas/Calendar): all areas belong to the single page
            # Photobook mode: split areas between left/right pages by position
            if single_page_mode:
                owner = pagenr
                origin_left = 0.0
                page_width = logical_spread_w  # Full page width (logical, post-rotation)
                logger.debug(f"  Page {pagenr}: single_page_mode, area at ({area_left}, {area_top}) assigned to owner={owner}")
            else:
                # A photo that starts on the left page should be on the left page
                # If the page element represents the left side (even pagenr) then left->pagenr, right->pagenr+1
                # otherwise (odd pagenr) left->pagenr-1, right->pagenr
                if (pagenr % 2) == 0:
                    left_owner = pagenr
                    right_owner = pagenr + 1
                else:
                    left_owner = max(1, pagenr - 1)
                    right_owner = pagenr
                
                logger.debug(f"  Page {pagenr}: pagenr%2={pagenr%2}, left_owner={left_owner}, right_owner={right_owner}, half={half}")

                owner = determine_page_owner(area_left, half, left_owner, right_owner)
                logger.debug(f"  Page {pagenr}: area at left={area_left} assigned to owner={owner}")

            # Page should already exist in pages_map (pre-created above)
            # If it doesn't, something is wrong but continue anyway
            if owner not in pages_map:
                logger.warning(f"Page {pagenr}: owner {owner} not found in pages_map - this shouldn't happen")
                continue

            # VALIDATION: Check if area is in the wrong page's XML
            # In photobook mode, ALL areas for a spread should be in the LEFT page's XML (even pagenr)
            # The left page XML contains areas for both the left page (pagenr) and right page (pagenr+1)
            # If we're processing an odd-numbered page (right page) and find ANY areas, that's wrong
            if not single_page_mode and not canvas_mode:
                if (pagenr % 2) == 1:
                    # We're processing an odd (right) page, but areas should NEVER be in odd page XML
                    # They should all be in the even (left) page XML of this spread
                    logger.error(f"Page {pagenr}: Found area in WRONG page XML! Area at left={area_left:.1f} "
                               f"belongs to page {owner}, but is in odd page {pagenr}'s XML. "
                               f"All areas for this spread should be in page {pagenr-1}'s XML (the left page). "
                               f"SKIPPING this area.")
                    continue
            
            # Check area type
            areatype = area.get('areatype', 'imagearea')
            
            if areatype == 'textarea':
                # Text block - store position/size and raw HTML content
                # Extract the text content
                raw_html = ""
                text_tag = area.find('text')
                if text_tag is not None and text_tag.text:
                    raw_html = text_tag.text.strip()
                
                # Parse textFormat for font size and alignment
                font_size = 12  # default
                h_align = 'left'  # default horizontal alignment
                v_align = 'top'  # default vertical alignment
                
                text_format = area.find('.//textFormat')
                if text_format is not None:
                    # Parse font attribute (format: "FontName,size,...")
                    font_attr = text_format.get('font', '')
                    if font_attr:
                        parts = font_attr.split(',')
                        if len(parts) > 1:
                            try:
                                font_size = int(parts[1])
                            except (ValueError, IndexError):
                                pass
                    
                    # Parse alignment (format: "ALIGNVCENTER,ALIGNHCENTER" or "ALIGNLEFT", etc.)
                    alignment = text_format.get('Alignment', '')
                    if alignment:
                        # Horizontal alignment
                        if 'ALIGNHCENTER' in alignment:
                            h_align = 'center'
                        elif 'ALIGNTRAILING' in alignment or 'ALIGNRIGHT' in alignment:
                            h_align = 'right'
                        elif 'ALIGNLEADING' in alignment or 'ALIGNLEFT' in alignment:
                            h_align = 'left'
                        
                        # Vertical alignment
                        if 'ALIGNVCENTER' in alignment:
                            v_align = 'center'
                        elif 'ALIGNBOTTOM' in alignment:
                            v_align = 'bottom'
                        elif 'ALIGNTOP' in alignment:
                            v_align = 'top'
                
                # Extract plain text for debug output
                import re, html
                plain_text = raw_html
                plain_text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', plain_text, flags=re.DOTALL)
                plain_text = re.sub(r'<style[^>]*>.*?</style>', '', plain_text, flags=re.DOTALL | re.IGNORECASE)
                plain_text = re.sub(r'<head[^>]*>.*?</head>', '', plain_text, flags=re.DOTALL | re.IGNORECASE)
                plain_text = re.sub(r'<[^>]+>', '', plain_text)
                plain_text = html.unescape(plain_text)
                plain_text = ' '.join(plain_text.split()).strip()
                
                logger.debug(f"  Page {owner} textarea: text='{plain_text[:50]}{'...' if len(plain_text) > 50 else ''}' font_size={font_size} h_align={h_align} v_align={v_align}")
                
                text_info = {
                    'area_left': area_left,
                    'area_top': area_top,
                    'area_width': area_width,
                    'area_height': area_height,
                    'area_rot': area_rot,
                    'raw_html': raw_html,
                    'font_size': font_size,
                    'h_align': h_align,
                    'v_align': v_align,
                }
                pages_map[owner]['texts'].append(text_info)
            else:
                # Image area (photos)
                for imageTag in area.findall('image'):
                    info = {
                        'filename': imageTag.get('filename'),
                        'area_left': area_left,
                        'area_top': area_top,
                        'area_width': area_width,
                        'area_height': area_height,
                        'area_rot': area_rot,
                    }
                    cut = imageTag.find('cutout')
                    if cut is not None:
                        try:
                            cleft = cut.get('left')
                            ctop = cut.get('top')
                            cscale = cut.get('scale')
                            info['cutout'] = {'left': cleft, 'top': ctop, 'scale': cscale}
                        except (TypeError, AttributeError) as e:
                            logger.warning(f"Page {pagenr}: Failed to parse cutout data: {e}")
                            info['cutout'] = None
                    else:
                        info['cutout'] = None

                    pages_map[owner]['photos'].append(info)

    # Process cover page (if it exists)
    # The fullcover page contains BOTH covers - we process it twice:
    # Once for front cover (right half, page "F") and once for back cover (left half, page "B")
    # NOTE: Using string page identifiers "F" and "B" to distinguish covers from numeric pages
    if cover_page is not None:
        # Process front cover (right half) as page "F"
        _process_cover_page(cover_page, "F", is_front_cover=True)
    
    # Process back cover (left half of cover spread shown as the final page)
    if cover_page is not None:
        _process_cover_page(cover_page, "B", is_front_cover=False)
    
    # Build sorted pages list: page "F" (front cover), page 0 (inside front), pages 1..N, 
    # page N+1 (inside back), page "B" (back cover)
    pages = []
    
    # Sort with "F" first, then numeric pages in order, then "B" last
    def page_sort_key(page_num):
        if page_num == "F":
            return (0, 0)  # Front cover comes first
        elif page_num == "B":
            return (2, 0)  # Back cover comes last
        else:
            return (1, page_num)  # Numeric pages in between
    
    for k in sorted(pages_map.keys(), key=page_sort_key):
        entry = pages_map[k]
        pages.append((k, entry))
    
    logger.debug(f"extract_pages_info: Final pages_map keys: {sorted(pages_map.keys(), key=page_sort_key)}")
    logger.debug(f"extract_pages_info: Returning {len(pages)} pages")
    for page_num, page_data in pages:
        is_cover = page_data.get('is_cover', False)
        logger.debug(f"  Page {page_num}: {len(page_data['photos'])} photos, {len(page_data['texts'])} texts (cover={is_cover})")
    
    return pages
