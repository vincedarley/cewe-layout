"""
Shared test infrastructure for page-based layout tests.

This module provides utilities for:
1. Reading page data from tests/samples/Test-album-page-N.txt
2. Writing test results to tests/samples/Test-album-page-N-results.txt
3. Managing result sections so each test can update its own section

All tests use ONLY the .txt files as input and core code routines.
No logic is duplicated in tests.
"""

from pathlib import Path
from typing import NamedTuple, List
from cewe_layout.algorithms.base import LayoutRectangle


class PageData(NamedTuple):
    """Parsed page data from sample file."""
    page_num: int
    page_width: float
    page_height: float
    origin_left: float
    photos: List[dict]  # Each dict has: pos, slot_width, slot_height, img_width, img_height, filename
    texts: List[dict]   # Each dict has: pos, width, height


def read_page_file(page_file: Path) -> PageData:
    """
    Read a page data file and return parsed PageData.
    
    Args:
        page_file: Path to Test-album-page-N.txt
    
    Returns:
        PageData with all parsed information
    """
    # Extract page number from filename
    page_num = int(page_file.stem.split('-')[-1])
    
    with open(page_file, 'r') as f:
        lines = f.readlines()
    
    page_width = page_height = origin_left = 0.0
    photos = []
    texts = []
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if line.startswith('PAGE:'):
            # PAGE: 3820.0 x 2900.0, origin: 0.0
            parts = line.split()
            page_width = float(parts[1])
            page_height = float(parts[3].rstrip(','))
            origin_left = float(parts[5])
        
        elif line.startswith('Photo'):
            # Photo 0: pos: (155.63, 155.61), slot: 1697.78 x 1239.22, img: 4032 x 3024, size: 19.0%
            parts = line.split()
            
            # Parse position - parts[3] is "(155.63,", parts[4] is "155.61),"
            pos_x = float(parts[3].lstrip('(').rstrip(','))
            pos_y = float(parts[4].rstrip('),'))
            
            # Parse slot dimensions - parts[6] and parts[8]
            slot_width = float(parts[6])
            slot_height = float(parts[8].rstrip(','))
            
            # Parse image dimensions - parts[10] and parts[12]
            img_width = int(parts[10])
            img_height = int(parts[12].rstrip(','))
            
            # Get filename from next line
            i += 1
            filename = lines[i].strip() if i < len(lines) else ''
            
            photos.append({
                'pos': (pos_x, pos_y),
                'slot_width': slot_width,
                'slot_height': slot_height,
                'img_width': img_width,
                'img_height': img_height,
                'filename': filename
            })
        
        elif line.startswith('Text'):
            # Text 0: pos: (5789.75, 2177.52), size: 864.901 x 559.642, area: 4.4%
            parts = line.split()
            
            # Parse position - parts[3] is "(5789.75,", parts[4] is "2177.52),"
            pos_x = float(parts[3].lstrip('(').rstrip(','))
            pos_y = float(parts[4].rstrip('),'))
            
            # Parse dimensions - parts[6] and parts[8]
            width = float(parts[6])
            height = float(parts[8].rstrip(','))
            
            texts.append({
                'pos': (pos_x, pos_y),
                'width': width,
                'height': height
            })
        
        i += 1
    
    return PageData(page_num, page_width, page_height, origin_left, photos, texts)


def write_result_section(results_file: Path, section_name: str, content: str):
    """
    Write or update a section in the results file.
    
    Results file format:
      === Section Name ===
      content here
      
      === Another Section ===
      more content
    
    If section exists, it's replaced. Otherwise it's appended.
    
    Args:
        results_file: Path to Test-album-page-N-results.txt
        section_name: Name of the section (e.g., "Gap Analysis", "Original Layout Cost")
        content: Content to write in this section
    """
    section_header = f'=== {section_name} ==='
    section_content = f'{section_header}\n{content}\n'
    
    if not results_file.exists():
        # Create new file with this section
        with open(results_file, 'w') as f:
            f.write(section_content)
        return
    
    # Read existing file
    with open(results_file, 'r') as f:
        lines = f.readlines()
    
    # Find section if it exists
    section_start = None
    section_end = None
    
    for i, line in enumerate(lines):
        if line.strip() == section_header:
            section_start = i
        elif section_start is not None and line.startswith('===') and i > section_start:
            section_end = i
            break
    
    if section_start is not None:
        # Replace existing section
        if section_end is None:
            section_end = len(lines)
        
        new_lines = lines[:section_start] + [section_content + '\n'] + lines[section_end:]
    else:
        # Append new section
        new_lines = lines + ['\n' + section_content]
    
    # Write back
    with open(results_file, 'w') as f:
        f.writelines(new_lines)


def page_data_to_rectangles(page_data: PageData, use_slot_aspect: bool = True) -> List[LayoutRectangle]:
    """
    Convert PageData to LayoutRectangles for use with algorithms.
    
    This uses core code concepts but doesn't depend on MCF parsing.
    
    Args:
        page_data: Parsed page data
        use_slot_aspect: If True, use slot dimensions. If False, use image dimensions.
    
    Returns:
        List of LayoutRectangle objects with positions
    """
    rectangles = []
    
    for idx, photo in enumerate(page_data.photos):
        pos_x, pos_y = photo['pos']
        
        # Adjust for origin_left (right pages)
        x = pos_x - page_data.origin_left
        y = pos_y
        
        # Choose dimensions based on use_slot_aspect
        if use_slot_aspect:
            width = photo['slot_width']
            height = photo['slot_height']
        else:
            # Use image aspect ratio scaled to slot area
            img_aspect = photo['img_width'] / photo['img_height'] if photo['img_height'] > 0 else 1.0
            slot_aspect = photo['slot_width'] / photo['slot_height'] if photo['slot_height'] > 0 else 1.0
            
            # Scale image to fit slot (maintain aspect ratio)
            if img_aspect > slot_aspect:
                # Image is wider - fit to slot width
                width = photo['slot_width']
                height = width / img_aspect
            else:
                # Image is taller - fit to slot height
                height = photo['slot_height']
                width = height * img_aspect
        
        rect = LayoutRectangle(
            item_id=str(idx),
            x=x,
            y=y,
            width=width,
            height=height,
            preferred_size=1.0,
            preserve_aspect_ratio=True
        )
        rectangles.append(rect)
    
    for idx, text in enumerate(page_data.texts):
        pos_x, pos_y = text['pos']
        
        x = pos_x - page_data.origin_left
        y = pos_y
        
        rect = LayoutRectangle(
            item_id=f'TEXT_{idx}',
            x=x,
            y=y,
            width=text['width'],
            height=text['height'],
            preferred_size=1.0,
            preserve_aspect_ratio=False
        )
        rectangles.append(rect)
    
    return rectangles
