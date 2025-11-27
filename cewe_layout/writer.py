"""Utilities to modify and write .mcf files safely with backups.

This module provides a simple test helper that backs up the original .mcf
and writes a patched version where all <area><position> width/height are
scaled by a factor (default 0.9) while keeping each area centered.
"""
from lxml import etree
import os


def _next_backup_name(path: str) -> str:
    base, ext = os.path.splitext(path)
    for i in range(1, 10000):
        cand = f"{base}-{i}{ext}"
        if not os.path.exists(cand):
            return cand
    raise RuntimeError('Unable to find backup name')


def _scale_positions_in_tree(tree: etree._ElementTree, scale: float = 0.9) -> int:
    """Scale area positions by `scale`. Returns number of areas modified."""
    root = tree.getroot()
    modified = 0
    for area in root.findall('.//area'):
        pos = area.find('position')
        if pos is None:
            continue
        try:
            left = float(pos.get('left').replace(',', '.'))
            top = float(pos.get('top').replace(',', '.'))
            width = float(pos.get('width').replace(',', '.'))
            height = float(pos.get('height').replace(',', '.'))
        except Exception:
            continue

        new_w = width * scale
        new_h = height * scale
        new_left = left + (width - new_w) / 2.0
        new_top = top + (height - new_h) / 2.0

        # keep numeric formatting similar to input (2 decimal places)
        pos.set('left', f"{new_left:.2f}")
        pos.set('top', f"{new_top:.2f}")
        pos.set('width', f"{new_w:.2f}")
        pos.set('height', f"{new_h:.2f}")
        modified += 1
    return modified


def patch_mcf_file(path: str, scale: float = 0.9, make_backup: bool = True) -> dict:
    """Parse `path`, backup original file, scale area sizes and overwrite the file.

    Returns a dict with keys: `path`, `backup_path` (or None), `modified_areas`.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    # parse as tree so we can write back preserving xml declaration
    tree = etree.parse(path)

    modified = _scale_positions_in_tree(tree, scale)

    backup_path = None
    if make_backup:
        backup_path = _next_backup_name(path)
        os.rename(path, backup_path)

    # write updated tree to original path
    tree.write(path, encoding='utf-8', xml_declaration=True, pretty_print=True)

    return {'path': path, 'backup_path': backup_path, 'modified_areas': modified}


def restore_mcf_backup(path: str) -> dict:
    """Restore the most recent backup for `path` (e.g. data-1.mcf -> data.mcf).

    Returns a dict with keys: `path`, `restored_from`, `index`.
    """
    if not os.path.exists(path):
        # still allow restoration into the same directory even if current file missing
        base_dir = os.path.dirname(path) or '.'
        base_name = os.path.splitext(os.path.basename(path))[0]
    else:
        base_dir = os.path.dirname(path) or '.'
        base_name = os.path.splitext(os.path.basename(path))[0]

    candidates = []
    for fn in os.listdir(base_dir):
        if not fn.startswith(base_name + '-'):
            continue
        root, ext = os.path.splitext(fn)
        if ext != os.path.splitext(path)[1]:
            continue
        suffix = root[len(base_name) + 1 :]
        try:
            idx = int(suffix)
        except Exception:
            continue
        candidates.append((idx, os.path.join(base_dir, fn)))

    if not candidates:
        raise FileNotFoundError(f'No backups found for {path}')

    candidates.sort(reverse=True)
    idx, backup_path = candidates[0]

    # remove current file if present, then restore
    if os.path.exists(path):
        os.remove(path)
    os.rename(backup_path, path)

    return {'path': path, 'restored_from': backup_path, 'index': idx}
