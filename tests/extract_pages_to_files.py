#!/usr/bin/env python3
"""
Extract page data from Test-album MCF to simple text files.

Each page is saved to tests/samples/Test-album-page-N.txt with human-readable format:
  PAGE: 3820.0 x 2900.0, origin: 0.0
  
  Photo 0: pos: (155.63, 155.61), slot: 1697.78 x 1239.22, img: 4032 x 3024, size: 53.4%
    safecontainer:/8jsasrsy_1_xd3aeee3a-e622-4637-9b16-c4e89bd90052_2fl0_2f001_full.jpg.jpeg
  
  Text 0: pos: (100.0, 200.0), size: 500.0 x 300.0, area: 4.2%

This creates a simple, version-controlled, human-readable format for test data.
"""

from pathlib import Path
import cv2
from cewe_layout.mcf_io.mcf_parser import parse_mcf_from_path, extract_pages_info


def extract_pages(mcf_path, output_dir):
    """
    Extract all pages from MCF file to individual text files.
    
    Args:
        mcf_path: Path to the .mcf file
        output_dir: Directory to write page files to
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    mcf_path = Path(mcf_path)
    mcf_base = mcf_path.parent
    
    root_el = parse_mcf_from_path(str(mcf_path))
    pages = extract_pages_info(root_el)
    
    for page_num, page_data in pages:
        page_width = page_data.get('page_width', 0)
        page_height = page_data.get('page_height', 0)
        origin_left = page_data.get('origin_left', 0.0)
        photos = page_data.get('photos', [])
        texts = page_data.get('texts', [])
        
        # Skip empty pages
        if len(photos) == 0 and len(texts) == 0:
            continue
        
        output_file = output_dir / f'Test-album-page-{page_num}.txt'
        
        with open(output_file, 'w') as f:
            # Write page dimensions
            f.write(f'PAGE: {page_width} x {page_height}, origin: {origin_left}\n\n')
            
            # Calculate total page area for percentages
            page_area = page_width * page_height
            
            # Write photos with both slot and image dimensions
            for idx, photo in enumerate(photos):
                left = photo.get('area_left', 0)
                top = photo.get('area_top', 0)
                slot_width = photo.get('area_width', 0)
                slot_height = photo.get('area_height', 0)
                filename = photo.get('filename', '')
                
                if slot_width <= 0 or slot_height <= 0:
                    continue
                
                if not filename:
                    continue
                
                # Load image to get actual dimensions
                safefn = filename.replace('safecontainer:/', '').lstrip('/')
                img_path = mcf_base / safefn
                
                img_width = 0
                img_height = 0
                if img_path.exists():
                    try:
                        arr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
                        if arr is not None:
                            img_height, img_width = arr.shape[:2]
                    except Exception as e:
                        print(f'  Warning: Could not load {safefn}: {e}')
                
                # Calculate size as percentage of page
                slot_area = slot_width * slot_height
                size_pct = (slot_area / page_area * 100) if page_area > 0 else 0
                
                f.write(f'Photo {idx}: pos: ({left}, {top}), slot: {slot_width} x {slot_height}, img: {img_width} x {img_height}, size: {size_pct:.1f}%\n')
                f.write(f'  {filename}\n\n')
            
            # Write text blocks
            for idx, text in enumerate(texts):
                left = text.get('area_left', 0)
                top = text.get('area_top', 0)
                width = text.get('area_width', 0)
                height = text.get('area_height', 0)
                
                if width <= 0 or height <= 0:
                    continue
                
                # Calculate area as percentage of page
                text_area = width * height
                area_pct = (text_area / page_area * 100) if page_area > 0 else 0
                
                f.write(f'Text {idx}: pos: ({left}, {top}), size: {width} x {height}, area: {area_pct:.1f}%\n\n')
        
        print(f'Wrote {output_file.name}: {len(photos)} photos, {len(texts)} texts')


def main():
    mcf_path = Path('../Test-album.xmcf/data.mcf')
    output_dir = Path('tests/samples')
    
    print(f'Extracting pages from {mcf_path}')
    print(f'Output directory: {output_dir}')
    print()
    
    extract_pages(mcf_path, output_dir)
    
    print()
    print('Done!')


if __name__ == '__main__':
    main()
