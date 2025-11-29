"""
Visualize pages that failed tree construction.

This script shows the layout of rectangles for pages that couldn't be 
represented as binary slicing trees, to help with visual validation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.algorithms.tree_builder import build_tree_from_layout


def extract_layout_rectangles(page_data):
    """Extract LayoutRectangles from page data."""
    photos = page_data['photos']
    texts = page_data['texts']
    page_width = page_data['page_width']
    page_height = page_data['page_height']
    origin_left = page_data.get('origin_left', 0.0)
    
    rectangles = []
    
    # Add photos
    for p in photos:
        area_left = p.get('area_left', 0)
        area_top = p.get('area_top', 0)
        area_width = p.get('area_width', 100)
        area_height = p.get('area_height', 100)
        
        if area_width <= 0 or area_height <= 0:
            continue
        
        x = area_left - origin_left
        y = area_top
        
        if x + area_width < -50 or x > page_width + 50:
            continue
        if y + area_height < -50 or y > page_height + 50:
            continue
        
        rect = LayoutRectangle(
            item_id=p.get('filename', f'photo{len(rectangles)}'),
            width=area_width,
            height=area_height,
            preferred_size=1.0,
            x=x,
            y=y
        )
        rectangles.append(rect)
    
    # Add text blocks
    for i, t in enumerate(texts):
        area_left = t.get('area_left', 0)
        area_top = t.get('area_top', 0)
        area_width = t.get('area_width', 100)
        area_height = t.get('area_height', 100)
        
        if area_width <= 0 or area_height <= 0:
            continue
        
        x = area_left - origin_left
        y = area_top
        
        if x + area_width < -50 or x > page_width + 50:
            continue
        if y + area_height < -50 or y > page_height + 50:
            continue
        
        rect = LayoutRectangle(
            item_id=f'text_{i}',
            width=area_width,
            height=area_height,
            preferred_size=1.0,
            preserve_aspect_ratio=False,
            x=x,
            y=y
        )
        rectangles.append(rect)
    
    return rectangles, page_width, page_height


def draw_ascii_layout(rectangles, page_width, page_height):
    """Draw a simple ASCII representation of the layout."""
    # Create a grid (80x40 characters to represent the page)
    grid_width = 80
    grid_height = 40
    grid = [[' ' for _ in range(grid_width)] for _ in range(grid_height)]
    
    # Map rectangles to grid
    for i, rect in enumerate(rectangles):
        # Convert to grid coordinates
        x1 = int(rect.x / page_width * grid_width)
        y1 = int(rect.y / page_height * grid_height)
        x2 = int((rect.x + rect.width) / page_width * grid_width)
        y2 = int((rect.y + rect.height) / page_height * grid_height)
        
        # Clamp to grid bounds
        x1 = max(0, min(grid_width - 1, x1))
        y1 = max(0, min(grid_height - 1, y1))
        x2 = max(0, min(grid_width, x2))
        y2 = max(0, min(grid_height, y2))
        
        # Use different characters for each rectangle (cycle through 0-9)
        char = str(i % 10)
        
        # Draw rectangle borders and fill
        for y in range(y1, y2):
            for x in range(x1, x2):
                if x < grid_width and y < grid_height:
                    # Draw borders with special chars
                    if y == y1 or y == y2 - 1:
                        if x == x1 or x == x2 - 1:
                            grid[y][x] = '+'  # Corner
                        else:
                            grid[y][x] = '-'  # Top/bottom border
                    elif x == x1 or x == x2 - 1:
                        grid[y][x] = '|'  # Side border
                    else:
                        grid[y][x] = char  # Fill with number
    
    # Print grid
    print('┌' + '─' * grid_width + '┐')
    for row in grid:
        print('│' + ''.join(row) + '│')
    print('└' + '─' * grid_width + '┘')


def visualize_page(page_num, page_data):
    """Visualize a single page."""
    rectangles, page_width, page_height = extract_layout_rectangles(page_data)
    
    if len(rectangles) == 0:
        return None
    
    # Try to build tree
    tree = build_tree_from_layout(rectangles, page_width, page_height, tolerance=5.0)
    
    if tree is not None:
        return None  # Skip pages that successfully build trees
    
    print(f"\n{'='*82}")
    print(f"Page {page_num}: FAILED to build tree")
    print(f"  {len(rectangles)} items, {page_width:.0f}x{page_height:.0f} page")
    print('='*82)
    
    # Show rectangle details
    print(f"\nRectangle positions:")
    for i, r in enumerate(rectangles):
        right = r.x + r.width
        bottom = r.y + r.height
        item_type = "text" if "text_" in r.item_id else "photo"
        print(f"  [{i}] {item_type:5s}: x={r.x:7.1f} to {right:7.1f} (w={r.width:7.1f}), "
              f"y={r.y:7.1f} to {bottom:7.1f} (h={r.height:7.1f})")
    
    print(f"\nASCII Layout (each rectangle numbered 0-9):")
    draw_ascii_layout(rectangles, page_width, page_height)
    
    # Check for potential split lines
    print(f"\nPotential vertical split lines (x-coordinates):")
    x_coords = set()
    for r in rectangles:
        x_coords.add(r.x)
        x_coords.add(r.x + r.width)
    
    for x in sorted(x_coords):
        if x <= 5 or x >= page_width - 5:
            continue
        
        left_count = sum(1 for r in rectangles if r.x + r.width <= x + 5)
        right_count = sum(1 for r in rectangles if r.x >= x - 5)
        crosses = len(rectangles) - left_count - right_count
        
        status = "✓" if crosses == 0 else "✗"
        print(f"  {status} x={x:7.1f}: {left_count} left, {right_count} right, {crosses} crossing")
    
    print(f"\nPotential horizontal split lines (y-coordinates):")
    y_coords = set()
    for r in rectangles:
        y_coords.add(r.y)
        y_coords.add(r.y + r.height)
    
    for y in sorted(y_coords):
        if y <= 5 or y >= page_height - 5:
            continue
        
        top_count = sum(1 for r in rectangles if r.y + r.height <= y + 5)
        bottom_count = sum(1 for r in rectangles if r.y >= y - 5)
        crosses = len(rectangles) - top_count - bottom_count
        
        status = "✓" if crosses == 0 else "✗"
        print(f"  {status} y={y:7.1f}: {top_count} top, {bottom_count} bottom, {crosses} crossing")
    
    print(f"\n→ This layout cannot be represented as a binary slicing tree.")
    print(f"  No vertical or horizontal line cleanly divides all rectangles.")
    
    return True


def main():
    """Visualize all failed pages."""
    album_path = Path(__file__).parent.parent.parent / 'Test-album.xmcf'
    if not album_path.exists():
        print(f"✗ Album not found: {album_path}")
        return False
    
    print("=" * 82)
    print("Visualizing pages that FAILED tree construction")
    print("=" * 82)
    print("\nThese pages have layouts incompatible with binary slicing trees.")
    print("Use this to visually validate that the failures are correct.")
    
    fotobook_root = parse_mcf_from_path(str(album_path / 'data.mcf'))
    pages = extract_pages_info(fotobook_root)
    
    failed_count = 0
    for page_num, page_data in pages:
        result = visualize_page(page_num, page_data)
        if result:
            failed_count += 1
    
    print("\n" + "=" * 82)
    print(f"Total failed pages visualized: {failed_count}")
    print("=" * 82)


if __name__ == '__main__':
    main()
