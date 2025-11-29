"""
Step 2: Measure the cost of original album layouts.

This test evaluates the "real-world excellent" layouts directly from the album,
without building or using trees. The goal is to establish baseline costs that
represent what humans consider good layouts.

Expected result: Costs should be very low (near zero) since these are professionally
designed layouts.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.algorithms.evaluator import evaluate_layout


def extract_layout_rectangles(page_data):
    """Extract LayoutRectangles from page data with their actual positions."""
    area_left = page_data['area_left']
    area_top = page_data['area_top']
    area_width = page_data['area_width']
    area_height = page_data['area_height']
    origin_left = page_data.get('bundleleft', 0)
    
    # Adjust to page-relative coordinates
    page_x = area_left - origin_left
    page_y = area_top
    page_width = area_width
    page_height = area_height
    
    rectangles = []
    
    for item in page_data.get('items', []):
        # Get position and size
        pos_left = item.get('left', 0)
        pos_top = item.get('top', 0)
        pos_width = item.get('width', 0)
        pos_height = item.get('height', 0)
        
        if pos_width <= 0 or pos_height <= 0:
            continue
        
        # Convert to page-relative coordinates
        x = pos_left - origin_left
        y = pos_top
        
        rect = LayoutRectangle(
            item_id=str(len(rectangles)),
            width=pos_width,
            height=pos_height,
            preferred_size=1.0,
            preserve_aspect_ratio=True,
            x=x,
            y=y
        )
        rectangles.append(rect)
    
    return rectangles, page_width, page_height


def main():
    """Evaluate costs of original album layouts."""
    album_path = Path(__file__).parent.parent.parent / 'Test-album.xmcf'
    if not album_path.exists():
        print(f"✗ Album not found: {album_path}")
        return False
    
    print("=" * 70)
    print("Evaluating costs of original Test-album.xmcf layouts")
    print("=" * 70)
    
    fotobook_root = parse_mcf_from_path(str(album_path / 'data.mcf'))
    pages = extract_pages_info(fotobook_root)
    
    costs = []
    
    for page_num, page_data in pages:
        rectangles, page_width, page_height = extract_layout_rectangles(page_data)
        
        if len(rectangles) == 0:
            continue  # Skip empty pages
        
        # Evaluate the original layout
        cost = evaluate_layout(page_width, page_height, rectangles, 
                              size_importance=100.0, detailed=True)
        
        costs.append((page_num, len(rectangles), cost))
        
        print(f"\nPage {page_num}: {len(rectangles)} items, {page_width:.0f}x{page_height:.0f}")
        print(f"  Total cost: {cost.total_cost:.1f}")
        print(f"  Empty space: {cost.empty_space_cost:.1f}% ({cost.empty_space_fraction:.1%})")
        print(f"  Size mismatch: {cost.size_mismatch_cost:.1f}")
    
    # Summary statistics
    print("\n" + "=" * 70)
    print("Summary Statistics")
    print("=" * 70)
    
    if costs:
        total_costs = [c.total_cost for _, _, c in costs]
        empty_costs = [c.empty_space_cost for _, _, c in costs]
        size_costs = [c.size_mismatch_cost for _, _, c in costs]
        
        print(f"Pages analyzed: {len(costs)}")
        print(f"\nTotal cost:")
        print(f"  Mean: {sum(total_costs)/len(total_costs):.1f}")
        print(f"  Min: {min(total_costs):.1f}")
        print(f"  Max: {max(total_costs):.1f}")
        print(f"\nEmpty space cost:")
        print(f"  Mean: {sum(empty_costs)/len(empty_costs):.1f}")
        print(f"  Min: {min(empty_costs):.1f}")
        print(f"  Max: {max(empty_costs):.1f}")
        print(f"\nSize mismatch cost:")
        print(f"  Mean: {sum(size_costs)/len(size_costs):.1f}")
        print(f"  Min: {min(size_costs):.1f}")
        print(f"  Max: {max(size_costs):.1f}")


if __name__ == '__main__':
    main()
