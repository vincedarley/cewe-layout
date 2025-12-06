"""Minimal parser to extract area/image/cutout info from CEWE .mcf XML."""
from lxml import etree
import os
import glob
import logging

logger = logging.getLogger(__name__)


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
    from collections import defaultdict

    pages_map = defaultdict(list)

    for page in fotobook_root.findall('.//page'):
        if not _is_normal_page(page):
            continue
        pagenr = int(page.get('pagenr'))

        # determine spread width/height from bundlesize (required in MCF)
        bundlesize = page.find('./bundlesize')
        if bundlesize is None:
            raise ValueError(f"Page {pagenr} missing bundlesize element - MCF file format may have changed")
        try:
            spread_w = float(bundlesize.get('width'))
            spread_h = float(bundlesize.get('height'))
        except (TypeError, ValueError, AttributeError) as e:
            raise ValueError(f"Page {pagenr} has invalid bundlesize: {e} - MCF file format may have changed") from e
        half = spread_w / 2.0

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

            # Decide which logical page the area belongs to by its left edge
            # A photo that starts on the left page should be on the left page
            # If the page element represents the left side (even pagenr) then left->pagenr, right->pagenr+1
            # otherwise (odd pagenr) left->pagenr-1, right->pagenr
            if (pagenr % 2) == 0:
                left_owner = pagenr
                right_owner = pagenr + 1
            else:
                left_owner = max(1, pagenr - 1)
                right_owner = pagenr

            owner = left_owner if area_left < half else right_owner

            # record page meta for this owner: page width/height and the origin offset
            # origin_left is 0 for left pages, half for right pages
            origin_left = 0.0 if owner == left_owner else half
            if owner not in pages_map:
                # Extract background designElementId for background color
                background_id = None
                for bg in page.findall('background'):
                    if bg.get('alignment') is not None:  # Primary background has alignment attribute
                        background_id = bg.get('designElementId')
                        break
                
                pages_map[owner] = {'photos': [], 'texts': [], 'page_width': half, 'page_height': spread_h, 'origin_left': origin_left, 'background_id': background_id}

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

    pages = []
    for k in sorted(pages_map.keys()):
        entry = pages_map[k]
        pages.append((k, entry))
    return pages
