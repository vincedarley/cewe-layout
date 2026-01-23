"""Minimal parser to extract area/image/cutout info from CEWE .mcf XML."""
from typing import Any

from lxml import etree
import os
import glob
import logging
from cewe_layout.page_utils import determine_page_owner_of_area, page_sort_key
from cewe_layout.book.cewe_photobook import CEWEPhotobook

logger = logging.getLogger(__name__)

# Fixed edge gaps for A5 Calendar format (calculated from Month 1 image area)
# These gaps define the usable image layout area within each calendar page.
# At some point we'll want to generalise the code for other Calendar sizes.
CALENDAR_EDGE_GAPS = {
    'left': 70.0,
    'top': 120.0,
    'right': 70.0,
    'bottom': 250.0
}


def convert_cewe_color(cewe_color: str | None, include_alpha: bool = True) -> str | None:
    """Convert CEWE color format (AARRGGBB) to standard format (RRGGBBAA or RRGGBB).
    
    Args:
        cewe_color: Color string in CEWE format '#AARRGGBB' or None
        include_alpha: If True, return RRGGBBAA format; if False, return RRGGBB format
    
    Returns:
        Color string in standard format '#RRGGBBAA' or '#RRGGBB', or None if input is None
    
    Examples:
        convert_cewe_color('#ffdf1900', True) -> '#df1900ff'
        convert_cewe_color('#ffdf1900', False) -> '#df1900'
        convert_cewe_color('#80ff0000', True) -> '#ff000080'
    """
    if cewe_color is None:
        return None
    
    # Remove '#' prefix if present
    color = cewe_color.lstrip('#')
    
    # Expect 8 hex digits: AARRGGBB
    if len(color) != 8:
        logger.warning(f"Unexpected color format: '{cewe_color}' (expected 8 hex digits)")
        return None
    
    try:
        # Extract components
        aa = color[0:2]  # Alpha
        rr = color[2:4]  # Red
        gg = color[4:6]  # Green
        bb = color[6:8]  # Blue
        
        # Reformat to RRGGBB or RRGGBBAA
        if include_alpha:
            return f'#{rr}{gg}{bb}{aa}'
        else:
            return f'#{rr}{gg}{bb}'
    except (IndexError, ValueError) as e:
        logger.warning(f"Failed to convert color '{cewe_color}': {e}")
        return None


def _parse_decoration(area) -> dict[str, Any]:
    """Parse decoration/border information from an area element.
    
    Args:
        area: The area XML element (can be imagearea or textarea)
    
    Returns:
        Dictionary with border information (color, width, gap, etc.) or empty dict if no decoration
    """
    decoration = area.find('decoration')
    if decoration is None:
        return {}
    
    border = decoration.find('border')
    if border is None:
        return {}
    
    # Parse border attributes
    border_info = {}
    
    # Color (in CEWE format AARRGGBB)
    cewe_color = border.get('color')
    if cewe_color:
        border_info['border_color'] = convert_cewe_color(cewe_color, include_alpha=True)
        border_info['border_color_rgb'] = convert_cewe_color(cewe_color, include_alpha=False)
    
    # Width (in 0.1mm units like other dimensions)
    width_str = border.get('width')
    if width_str:
        try:
            border_info['border_width'] = float(width_str.replace(',', '.'))
        except (ValueError, AttributeError):
            pass
    
    # Gap (space between content and border, in 0.1mm units)
    gap_str = border.get('gap')
    if gap_str:
        try:
            border_info['border_gap'] = float(gap_str.replace(',', '.'))
        except (ValueError, AttributeError):
            pass
    
    # Additional attributes that might be useful
    position = border.get('position')  # e.g., "outside", "inside"
    if position:
        border_info['border_position'] = position
    
    enabled = border.get('enabled')  # e.g., "true", "false"
    if enabled:
        border_info['border_enabled'] = enabled.lower() == 'true'
    
    return border_info


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


def _calculate_page_dimensions(single_page_mode: bool, right_page: bool, logical_spread_w: float) -> tuple[float, float]:
    """Calculate page_width and origin_left for a given page.
    
    Args:
        single_page_mode: True for Canvas/Calendar (no split), False for photobooks (left/right split)
        right_page: True if this is the right page in a spread (photobook mode)
        logical_spread_w: Full spread width (after rotation adjustment)
    
    Returns:
        Tuple of (page_width, origin_left)
    """
    if single_page_mode:
        # Canvas/Calendar: each page is standalone, full width
        page_width = logical_spread_w
        origin_left = 0.0
    else:
        # Photobook: split spread into left/right pages
        half = logical_spread_w / 2.0
        page_width = half
        # Even pages are on the left (origin_left=0), odd pages are on the right (origin_left=half)
        # Note: pagenr=0 special cases (covers) must be handled separately by caller
        origin_left = half if right_page else 0.0
    
    return page_width, origin_left


def _create_page_info(page_width: float, page_height: float, origin_left: float, 
                      background_id: str | None, canvas_mode: bool, calendar_mode: bool,
                      rotation: float, physical_width: float, physical_height: float,
                      pagenr: int | str, page_type: str | None) -> dict[str, Any]:
    """Create a page info dictionary with consistent structure.
    
    Args:
        page_width: Width of the page in logical coordinates
        page_height: Height of the page in logical coordinates
        origin_left: X offset for this page within the spread
        background_id: Background design element ID
        canvas_mode: True if this is a Canvas product
        calendar_mode: True if this is a Calendar product
        rotation: Page rotation in degrees
        physical_width: Physical spread width (pre-rotation)
        physical_height: Physical spread height (pre-rotation)
        pagenr: Page number (int or string like 'F'/'B' for covers)
        page_type: Page type from XML (e.g., 'normalpage', 'calendarcoverfront')
    
    Returns:
        Dictionary with page information
    """
    return {
        'photos': [],
        'texts': [],
        'page_width': page_width,
        'page_height': page_height,
        'origin_left': origin_left,
        'background_id': background_id,
        'is_canvas': canvas_mode,
        'is_calendar': calendar_mode,
        'rotation': rotation,
        'physical_width': physical_width,
        'physical_height': physical_height,
        'calendar_edge_gaps': CALENDAR_EDGE_GAPS.copy() if calendar_mode else None,
        'cewe_pagenr': pagenr,
        'page_type': page_type
    }


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
    
    # Find cover page (type="fullcover"), or calendarcoverfront for calendars.
    # Note: The fullcover page contains BOTH front and back covers in one spread (for photobooks)
    # Left half = back cover, Right half = front cover (just like normal page spreads)
    cover_page = None
    for page in all_pages:
        if page.get('type') == 'fullcover' or page.get('type') == 'calendarcoverfront':
            template_name = page.get('designStyleTemplateName', '')
            # Find the cover page that has areas (content)
            if page.findall('.//area'):
                cover_page = page
                break
    
    if cover_page is None:
        logger.debug(f"extract_pages_info: No fullcover pages with content found")
    else:
        logger.debug(f"extract_pages_info: Found fullcover page with areas")

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
        
        logger.debug(f"extract_pages_info: pagenr={pagenr_str} extracted background_id={background_id}")
        
        # Calculate page dimensions using helper function
        page_width, origin_left = _calculate_page_dimensions(single_page_mode, (pagenr % 2) == 1, logical_spread_w)
        
        if pagenr not in pages_map:
            logger.debug(f"extract_pages_info: pagenr={pagenr_str} creating page {pagenr} origin_left={origin_left} background_id={background_id}")
            pages_map[pagenr] = _create_page_info(
                page_width, logical_spread_h, origin_left, background_id,
                canvas_mode, calendar_mode, rotation_degrees,
                spread_w, spread_h, pagenr, page_type
            )
    
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
            pages_map[inside_back_page_num] = _create_page_info(
                sample_page['page_width'], sample_page['page_height'],
                sample_page['page_width'],  # origin_left: Right side (inside back is odd page number)
                None,  # background_id
                False, False,  # is_canvas=False, is_calendar=False
                0.0,  # rotation
                sample_page['page_width'] * 2, sample_page['page_height'],  # physical dimensions
                inside_back_page_num,
                'emptypage'  # page_type
            )
            # Add cover-specific metadata
            pages_map[inside_back_page_num]['is_cover'] = False
            pages_map[inside_back_page_num]['is_front_cover'] = False
            pages_map[inside_back_page_num]['has_full_bleed'] = False
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

                owner = determine_page_owner_of_area(area_left, half, left_owner, right_owner)
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
                text_info = _parseTextArea(area, area_width, area_height, area_left, area_top, area_rot, owner)
                pages_map[owner]['texts'].append(text_info)
            else:
                # Image area (photos)
                for imageTag in area.findall('image'):
                    info = _parseImageArea(imageTag, area_width, area_height, area_left, area_top, area_rot, area)

                    pages_map[owner]['photos'].append(info)

    # Process cover page (if it exists)
    # The fullcover page contains BOTH covers - we process it twice:
    # Once for front cover (right half, page "F") and once for back cover (left half, page "B")
    # Calendar covers are single pages - only process front cover
    # NOTE: Using string page identifiers "F" and "B" to distinguish covers from numeric pages
    if cover_page is not None:
        is_calendar_cover = cover_page.get('type') == 'calendarcoverfront'
        
        # Process front cover (right half for photobooks, full page for calendars) as page "F"
        _process_cover_page(pages_map, cover_page, "F", is_front_cover=True)
        
        # Process back cover only for photobooks (calendars don't have back covers)
        if not is_calendar_cover:
            _process_cover_page(pages_map, cover_page, "B", is_front_cover=False)
    
    # Build sorted pages list: page "F" (front cover), page 0 (inside front), pages 1..N, 
    # page N+1 (inside back), page "B" (back cover)
    pages = []
    
    # Sort with "F" first, then numeric pages in order, then "B" last
    for k in sorted(pages_map.keys(), key=page_sort_key):
        entry = pages_map[k]
        pages.append((k, entry))
    
    logger.debug(f"extract_pages_info: Final pages_map keys: {sorted(pages_map.keys(), key=page_sort_key)}")
    logger.debug(f"extract_pages_info: Returning {len(pages)} pages")
    for page_num, page_data in pages:
        is_cover = page_data.get('is_cover', False)
        logger.debug(f"  Page {page_num}: {len(page_data['photos'])} photos, {len(page_data['texts'])} texts (cover={is_cover})")
    
    # Return CEWEPhotobook instance instead of raw list
    return CEWEPhotobook(pages)


# Helper function to extract areas from a cover page
def _process_cover_page(pages_map, page_el, page_number, is_front_cover):
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

    # Detect if this is a calendar cover (single page) vs photobook cover (spread)
    is_calendar_cover = page_el.get('type') == 'calendarcoverfront'

    # Use the same dimension calculation as normal pages for consistency
    # For calendars: single_page_mode=True gives full width
    # For photobooks: single_page_mode=False gives half width, with origin based on front/back
    page_w, origin_left = _calculate_page_dimensions(is_calendar_cover, True, spread_w)

    # Initialize page entry using helper function
    # Note: is_calendar must match the actual format (calendar covers ARE calendar pages)
    pages_map[page_number] = _create_page_info(
        page_w, spread_h, origin_left, background_id,
        False, is_calendar_cover, 0.0,  # is_canvas=False, is_calendar=is_calendar_cover, rotation=0
        spread_w, spread_h, page_number, page_el.get('type')
    )

    # Add cover-specific metadata
    pages_map[page_number]['is_cover'] = True
    pages_map[page_number]['is_front_cover'] = is_front_cover
    pages_map[page_number]['has_full_bleed'] = True  # Covers have bleed on all 4 sides

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

        # Filter based on which half of the spread this area is in (photobooks only)
        if not is_calendar_cover:
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
            text_info = _parseTextArea(area, area_width, area_height, area_left, area_top, area_rot, page_number)
            pages_map[page_number]['texts'].append(text_info)
        elif areatype == 'imagearea':
            for imageTag in area.findall('image'):
                info = _parseImageArea(imageTag, area_width, area_height, area_left, area_top, area_rot, area)
                pages_map[page_number]['photos'].append(info)


def _parseImageArea(imageTag, area_width: float, area_height: float, area_left: float, area_top: float,
                    area_rot: float, area=None) -> dict[str, float | Any]:
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
            # Only parse attributes that are actually present (no defaults)
            left_str = cut.get('left')
            top_str = cut.get('top')
            scale_str = cut.get('scale')
            
            info['cutout_left'] = float(left_str.replace(',', '.')) if left_str is not None else None
            info['cutout_top'] = float(top_str.replace(',', '.')) if top_str is not None else None
            info['cutout_scale'] = float(scale_str.replace(',', '.')) if scale_str is not None else None
        except (TypeError, AttributeError, ValueError):
            info['cutout_left'] = None
            info['cutout_top'] = None
            info['cutout_scale'] = None
    else:
        info['cutout_left'] = None
        info['cutout_top'] = None
        info['cutout_scale'] = None
    
    # Parse decoration/border information if area element is provided
    if area is not None:
        border_info = _parse_decoration(area)
        info.update(border_info)
    
    return info


def _parseTextArea(area, area_width: float, area_height: float, area_left: float, area_top: float, area_rot: float,
                   owner: int | Any) -> dict[str, float | str | int | Any]:
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

    # Parse colors and alignment from textFormat
    background_color = None
    background_color_rgb = None
    foreground_color = None
    foreground_color_rgb = None
    
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
        
        # Parse background and foreground colors (CEWE format: AARRGGBB)
        bg_color = text_format.get('backgroundColor')
        if bg_color:
            background_color = convert_cewe_color(bg_color, include_alpha=True)
            background_color_rgb = convert_cewe_color(bg_color, include_alpha=False)
        
        fg_color = text_format.get('foregroundColor')
        if fg_color:
            foreground_color = convert_cewe_color(fg_color, include_alpha=True)
            foreground_color_rgb = convert_cewe_color(fg_color, include_alpha=False)
    
    # Check for inline color styling in the HTML content (overrides textFormat color)
    # Common pattern: <span style="...color:#rrggbb...">
    import re, html
    color_match = re.search(r'color:\s*#([0-9a-fA-F]{6})', raw_html)
    if color_match:
        # Found inline color - override foreground colors
        inline_color_rgb = '#' + color_match.group(1).lower()
        foreground_color_rgb = inline_color_rgb
        foreground_color = inline_color_rgb + 'ff'  # Add fully opaque alpha channel
        logger.debug(f"  Found inline color style: {inline_color_rgb} (overriding textFormat color)")

    # Extract plain text for debug output
    plain_text = raw_html
    plain_text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', plain_text, flags=re.DOTALL)
    plain_text = re.sub(r'<style[^>]*>.*?</style>', '', plain_text, flags=re.DOTALL | re.IGNORECASE)
    plain_text = re.sub(r'<head[^>]*>.*?</head>', '', plain_text, flags=re.DOTALL | re.IGNORECASE)
    plain_text = re.sub(r'<[^>]+>', '', plain_text)
    plain_text = html.unescape(plain_text)
    plain_text = ' '.join(plain_text.split()).strip()

    logger.debug(
        f"  Page {owner} textarea: text='{plain_text[:50]}{'...' if len(plain_text) > 50 else ''}' font_size={font_size} h_align={h_align} v_align={v_align}")

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
    
    # Add color information if present
    if background_color is not None:
        text_info['background_color'] = background_color
        text_info['background_color_rgb'] = background_color_rgb
    if foreground_color is not None:
        text_info['foreground_color'] = foreground_color
        text_info['foreground_color_rgb'] = foreground_color_rgb
    
    # Add decoration/border information if present
    border_info = _parse_decoration(area)
    text_info.update(border_info)
    
    return text_info
