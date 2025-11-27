"""Simple CLI for extracting page layout information from CEWE `.mcf` files."""
import argparse
import os
import sys
from .parser import parse_mcf_from_path, extract_pages_info


def main():
    parser = argparse.ArgumentParser(description='Extract photo slot info from CEWE .mcf')
    parser.add_argument('--input', '-i', required=True, help='Path to .mcf file or folder containing data.mcf')
    args = parser.parse_args()

    mcf_path = args.input
    if os.path.isdir(mcf_path):
        # look for data.mcf or *.mcf
        candidates = [os.path.join(mcf_path, 'data.mcf')] + [os.path.join(mcf_path, f) for f in os.listdir(mcf_path) if f.endswith('.mcf')]
        found = next((c for c in candidates if os.path.exists(c)), None)
        if found is None:
            print(f'No data.mcf or .mcf found in folder: {mcf_path}', file=sys.stderr)
            sys.exit(2)
        mcf_path = found

    try:
        root = parse_mcf_from_path(mcf_path)
    except Exception as e:
        print(f'Error parsing {mcf_path}: {e}', file=sys.stderr)
        sys.exit(1)

    pages = extract_pages_info(root)
    for pageNo, info in pages:
        photos = info['photos']
        print(f"Page {pageNo}: {len(photos)} photos")
        for idx, p in enumerate(photos, start=1):
            print(f"  {idx}. filename={p.get('filename')}")
            print(f"     area left={p.get('area_left')} top={p.get('area_top')} width={p.get('area_width')} height={p.get('area_height')} rot={p.get('area_rot')}")
            cut = p.get('cutout')
            if cut:
                print(f"     cutout left={cut.get('left')} top={cut.get('top')} scale={cut.get('scale')}")
        print('')
