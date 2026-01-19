"""Simple CLI for extracting page layout information from CEWE `.mcf` files."""
import argparse
import os
import sys
import re
from pathlib import Path
from collections import defaultdict
from cewe_layout.mcf_io.mcf_parser import parse_mcf_from_path, extract_pages_info
from .photo_utils import get_photo_creation_date, get_photo_star_rating


def natural_sort_key(path):
    """Generate a key for natural (human) sorting of file paths.
    
    Converts numeric parts to integers for proper ordering:
    'file1.jpg' < 'file2.jpg' < 'file10.jpg'
    """
    def convert(text):
        return int(text) if text.isdigit() else text.lower()
    
    return [convert(c) for c in re.split('([0-9]+)', path.name)]


def rename_photos(directory, rename_prefix, pattern='*'):
    """Rename photos in directory with structured naming based on creation date and star rating.
    
    Args:
        directory: Path to directory containing photos
        name_prefix: Prefix to use for renamed files
        pattern: Glob pattern to match files (default: '*' for all files)
    """
    photo_dir = Path(directory)
    if not photo_dir.exists() or not photo_dir.is_dir():
        print(f'Error: {directory} is not a valid directory', file=sys.stderr)
        sys.exit(1)
    
    # Supported image extensions
    image_exts = {'.jpg', '.jpeg', '.JPG', '.JPEG', '.PNG', '.png', '.HEIC', '.heic', '.heif', '.HEIF'}
    
    # Get list of all photos matching the pattern
    photos = [f for f in photo_dir.glob(pattern) if f.is_file() and f.suffix in image_exts]
    
    if not photos:
        print(f'No photos matching "{pattern}" found in {directory}', file=sys.stderr)
        sys.exit(1)
    
    print(f'Found {len(photos)} photos in {directory}')
    
    # Sort photos naturally (by name)
    photos = sorted(photos, key=natural_sort_key)
    
    # Group photos by creation date and process
    date_counters = defaultdict(int)  # Track counter per date
    renamed_count = 0
    
    for photo in photos:
        # Get creation date
        creation_date = get_photo_creation_date(photo)
        if not creation_date:
            print(f'Warning: Could not extract creation date from {photo.name}, skipping', file=sys.stderr)
            continue
        
        # Format date as yyyy-mm-dd
        date_str = creation_date.strftime('%Y-%m-%d')
        
        # Find first available counter for this date (skip existing files)
        counter = date_counters[date_str] + 1
        while True:
            new_name = f"{rename_prefix}-{date_str}-p{counter:03d}"
            
            # Add star rating suffix if present
            star_rating = get_photo_star_rating(photo)
            if star_rating == 5:
                new_name += "-5star"
            elif star_rating == 4:
                new_name += "-4star"
            
            # Add extension (preserve original)
            new_name += photo.suffix.lower()
            
            # Build new path
            new_path = photo.parent / new_name
            
            # Check if this name is available (doesn't exist or is the current photo)
            if not new_path.exists() or new_path == photo:
                # Update counter for this date
                date_counters[date_str] = counter
                break
            
            # Name exists and is not current photo, try next counter
            counter += 1
        
        # Rename
        try:
            photo.rename(new_path)
            print(f'Renamed: {photo.name} -> {new_name}')
            renamed_count += 1
        except Exception as e:
            print(f'Error renaming {photo.name}: {e}', file=sys.stderr)
    
    print(f'\nSuccessfully renamed {renamed_count} of {len(photos)} photos')


def main():
    parser = argparse.ArgumentParser(description='Extract photo slot info from CEWE .mcf or rename photos')
    parser.add_argument('--input', '-i', help='Path to .mcf file or folder containing data.mcf')
    parser.add_argument('--renamephotos', nargs='+', metavar='ARG',
                        help='Rename photos: DIRECTORY RENAMEPREFIX [PATTERN]. Pattern defaults to * (all files).')
    args = parser.parse_args()
    
    # Handle -renamephotos mode
    if args.renamephotos:
        if len(args.renamephotos) < 2:
            parser.error('--renamephotos requires at least DIRECTORY and PREFIX')
        directory = args.renamephotos[0]
        rename_prefix = args.renamephotos[1]
        pattern = args.renamephotos[2] if len(args.renamephotos) > 2 else '*'
        rename_photos(directory, rename_prefix, pattern)
        return
    
    # Original MCF parsing mode
    if not args.input:
        parser.error('--input is required when not using --renamephotos')
    
    args = argparse.Namespace(input=args.input)

    mcf_path = args.input
    if os.path.isdir(mcf_path):
        # look for data.mcf or *.mcf
        candidates = [os.path.join(mcf_path, 'data.mcf')] + [os.path.join(mcf_path, f) for f in os.listdir(mcf_path) if f.endswith('.mcf')]
        found = next((c for c in candidates if os.path.exists(c)), None)
        if found is None:
            print(f'No data.mcf or .mcf_io found in folder: {mcf_path}', file=sys.stderr)
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
