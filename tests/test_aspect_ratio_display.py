"""Test to debug aspect ratio display issue on Page 39 of Album-2022.xmcf"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.mcf_io.mcf_parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.utils.gap_utils import analyze_gaps, make_uniform_edge_gap

# Path to the album
album_path = Path(__file__).parent.parent.parent / "Album-2022.xmcf" / "data.mcf"

if not album_path.exists():
    print(f"ERROR: Album not found at {album_path}")
    sys.exit(1)

# Parse the MCF file
root = parse_mcf_from_path(str(album_path))
pages = extract_pages_info(root)

# Find page 39
page_39_info = None
for pageno, info in pages:
    if pageno == 39:
        page_39_info = info
        break

if not page_39_info:
    print("ERROR: Page 39 not found")
    sys.exit(1)

print(f"\n=== Page 39 Analysis ===")
photos = page_39_info.get('photos', [])
texts = page_39_info.get('texts', [])
page_w = page_39_info.get('page_width', 2100.0)
page_h = page_39_info.get('page_height', 2970.0)
origin_left = page_39_info.get('origin_left', 0.0)

print(f"Page dimensions: {page_w} x {page_h}")
print(f"Origin left: {origin_left}")
print(f"Number of photos: {len(photos)}")
print(f"Number of texts: {len(texts)}")

# Analyze gaps
all_items = photos + texts
# Determine if this is a spread page
is_spread = page_w > page_h * 1.5 or origin_left > 0.0
edge_gap, internal_gap = analyze_gaps(all_items, page_w, page_h, origin_left, is_spread) if all_items else (make_uniform_edge_gap(0.0), 0.0)

print(f"\nGaps:")
print(f"  Edge gaps: top={edge_gap['top']}, bottom={edge_gap['bottom']}, left={edge_gap['left']}, right={edge_gap['right']}")
print(f"  Internal gap: {internal_gap}")

# Display each photo's dimensions and calculated aspect ratio
print(f"\n=== Photo Details ===")
for i, photo in enumerate(photos, 1):
    width = photo.get('area_width', 0)
    height = photo.get('area_height', 0)
    filename = photo.get('filename', '')
    
    # Calculate gap-free dimensions (as done in gui_controls.py lines 1395-1396)
    gf_width = width + internal_gap
    gf_height = height + internal_gap
    aspect_ratio = gf_width / gf_height if gf_height > 0 else 0
    
    print(f"\nP{i}:")
    print(f"  Filename: {filename}")
    print(f"  MCF dimensions: {width:.2f} x {height:.2f}")
    print(f"  Gap-free dimensions: {gf_width:.2f} x {gf_height:.2f}")
    print(f"  Aspect ratio (width/height): {aspect_ratio:.2f}")
    print(f"  Orientation: {'LANDSCAPE' if aspect_ratio >= 1.0 else 'PORTRAIT'}")
