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
    from collections import defaultdict

    canvas_mode = is_canvas_format(fotobook_root)
    calendar_mode = is_calendar_format(fotobook_root)
    # Single-page mode: treat each page as standalone (no left/right split)
    single_page_mode = canvas_mode or calendar_mode
    pages_map = defaultdict(list)

    logger.debug(f"extract_pages_info: canvas_mode={canvas_mode}, calendar_mode={calendar_mode}, single_page_mode={single_page_mode}")
    
    all_pages = fotobook_root.findall('.//page')
    logger.debug(f"extract_pages_info: Found {len(all_pages)} total page elements in XML")

    for page in all_pages:
        pagenr_str = page.get('pagenr')
        page_type = page.get('type')
        is_normal = _is_normal_page(page)
        logger.debug(f"extract_pages_info: Processing page pagenr='{pagenr_str}' type='{page_type}' is_normal={is_normal}")
        
        # Process ALL pages (including page 0) to extract areas, but remember which pages are "normal"
        # Areas from page 0 may belong to page 1 based on their position
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

                # origin_left is 0 for left pages, half for right pages
                origin_left = 0.0 if owner == left_owner else half
                page_width = half  # Half of spread for each page
            
            if owner not in pages_map:
                # Extract background designElementId for background color
                background_id = None
                for bg in page.findall('background'):
                    if bg.get('alignment') is not None:  # Primary background has alignment attribute
                        background_id = bg.get('designElementId')
                        break
                
                # Store both logical dimensions (for UI) and physical dimensions (for saving)
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
                    'physical_width': spread_w,  # Original dimensions before rotation
                    'physical_height': spread_h,
                    'calendar_edge_gaps': CALENDAR_EDGE_GAPS.copy() if calendar_mode else None
                }

            # Check area type
            areatype = area.get('areatype', 'imagearea')
            
            if areatype == 'textarea':
                # Text block - just store position/size, don't need content
                text_info = {
                    'area_left': area_left,
                    'area_top': area_top,
                    'area_width': area_width,
                    'area_height': area_height,
                    'area_rot': area_rot,
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

    # Build final pages list, excluding page 0 (covers/special pages)
    # We process page 0 to extract its areas, but don't include it in results
    pages = []
    for k in sorted(pages_map.keys()):
        if k < 1:  # Skip page 0 and any negative page numbers
            logger.debug(f"extract_pages_info: Skipping page {k} from final results (not a normal page)")
            continue
        entry = pages_map[k]
        pages.append((k, entry))
    
    logger.debug(f"extract_pages_info: Final pages_map keys: {sorted(pages_map.keys())}")
    logger.debug(f"extract_pages_info: Returning {len(pages)} pages")
    for page_num, page_data in pages:
        logger.debug(f"  Page {page_num}: {len(page_data['photos'])} photos, {len(page_data['texts'])} texts")
    
    return pages
