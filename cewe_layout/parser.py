"""Minimal parser to extract area/image/cutout info from CEWE .mcf XML."""
from lxml import etree
import os
import glob


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
    except Exception:
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

        # determine spread width/height: look for bundlesize, otherwise assume two A4 pages (4200x2970 in mcf units)
        bundlesize = page.find('./bundlesize')
        try:
            spread_w = float(bundlesize.get('width')) if bundlesize is not None else 4200.0
            spread_h = float(bundlesize.get('height')) if bundlesize is not None else 2970.0
        except Exception:
            spread_w = 4200.0
            spread_h = 2970.0
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
            except Exception:
                area_left = area_top = area_width = area_height = area_rot = None

            # decide which logical page the area belongs to by its horizontal centre
            center_x = (area_left or 0) + (area_width or 0) / 2.0
            # If the page element represents the left side (even pagenr) then left->pagenr, right->pagenr+1
            # otherwise (odd pagenr) left->pagenr-1, right->pagenr
            if (pagenr % 2) == 0:
                left_owner = pagenr
                right_owner = pagenr + 1
            else:
                left_owner = max(1, pagenr - 1)
                right_owner = pagenr

            owner = left_owner if center_x < half else right_owner

            # record page meta for this owner: page width/height and the origin offset
            # origin_left is 0 for left pages, half for right pages
            origin_left = 0.0 if owner == left_owner else half
            if owner not in pages_map:
                pages_map[owner] = {'photos': [], 'page_width': half, 'page_height': spread_h, 'origin_left': origin_left}

            for imageTag in list(area.findall('image')) + list(area.findall('imagebackground')):
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
                    except Exception:
                        info['cutout'] = None
                else:
                    info['cutout'] = None

                pages_map[owner]['photos'].append(info)

    pages = []
    for k in sorted(pages_map.keys()):
        entry = pages_map[k]
        pages.append((k, entry))
    return pages
