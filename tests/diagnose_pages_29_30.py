"""Diagnostic script to examine coordinate transformation for Mimeo pages."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.mimeo.mimeo_database import MimeoProject
from cewe_layout.mimeo.mimeo_converter import MimeoCoordinateTransformer

ppb = Path('../../2016-test.ppb')

proj = MimeoProject(ppb)
data = proj.extract_all()

layouts = data['layouts']
frames = data['frames']

print(f"Total layouts: {len(layouts)}")
print(f"Total frames: {len(frames)}")

if len(layouts) < 31:
    print("ERROR: Not enough layouts found")
    sys.exit(1)

# Create transformer (no dimensions needed - passed per-transform)
transformer = MimeoCoordinateTransformer()
POINTS_TO_MCF = transformer.POINTS_TO_MCF

print(f"POINTS_TO_MCF conversion factor: {POINTS_TO_MCF}")
print()

# Examine Mimeo pages 1 (front cover) and 29 (content page)
for mimeo_page_num in [1, 29]:
    layout_index = mimeo_page_num - 1  # 0-indexed (page 1 = index 0)
    
    page_layout = layouts[layout_index]
    page_id = page_layout['model_id']
    
    # Get actual page dimensions from layout data
    page_width = page_layout.get('width', 'N/A')
    page_height = page_layout.get('height', 'N/A')
    
    # Calculate MCF page number
    # Mimeo: 0=F, 1=IF, 2-N=content starting at 1
    # MCF: F, 0=IF, 1-N=content
    # So Mimeo page 29 → MCF page 27 (29 - 2 = 27 because we skip F and IF)
    mcf_page = mimeo_page_num - 2  # Subtract 2 to skip Front and Inside Front
    
    # Determine if right page (odd MCF pages are right)
    is_right_page = (mcf_page % 2 == 1)

    print(f"=" * 80)
    print(f"Mimeo Page {mimeo_page_num} → MCF Page {mcf_page} ({'RIGHT' if is_right_page else 'LEFT'})")
    print(f"Layout model_id: {page_id}, sequence: {page_layout['index']}")
    if page_width != 'N/A':
        print(f"Page size: {page_width:.2f} x {page_height:.2f} points (this specific page)")
        mcf_page_width = int(page_width * POINTS_TO_MCF)
        mcf_page_height = int(page_height * POINTS_TO_MCF)
        print(f"MCF size: {mcf_page_width} x {mcf_page_height} MCF = {mcf_page_width/10:.1f} x {mcf_page_height/10:.1f} cm")
    print()

    # Find all frames on this page
    page_frames = [f for f in frames if f['page_id'] == page_id]

    print(f"Number of frames: {len(page_frames)}")
    print()

    for i, frame in enumerate(page_frames):
        # Mimeo coordinates are CENTER-based with BOTTOM-LEFT origin
        # Calculate topleft edges for reference
        mimeo_left = frame['x'] - frame['width'] / 2
        mimeo_right = frame['x'] + frame['width'] / 2
        mimeo_bottom = frame['y'] - frame['height'] / 2  # Y increases upward in Mimeo
        mimeo_top = frame['y'] + frame['height'] / 2
        
        # Transform to MCF coordinates (using THIS PAGE's dimensions)
        mcf_x, mcf_y, mcf_w, mcf_h = transformer.transform(
            frame['x'], frame['y'], frame['width'], frame['height'],
            page_width, page_height,
            is_right_page=is_right_page
        )
        
        print(f"  Frame {i}:")
        print(f"    Mimeo (center-based, bottom-left origin, Y↑):")
        print(f"      center: ({frame['x']:.2f}, {frame['y']:.2f}) points")
        print(f"      size: {frame['width']:.2f} x {frame['height']:.2f} points")
        print(f"      edges: left={mimeo_left:.2f}, right={mimeo_right:.2f}, bottom={mimeo_bottom:.2f}, top={mimeo_top:.2f}")
        print(f"    MCF (topleft-based, top-left origin, Y↓, spread coords):")
        print(f"      left={mcf_x} MCF, top={mcf_y} MCF")
        print(f"      width={mcf_w} MCF, height={mcf_h} MCF")
        print(f"      = ({mcf_x/10:.2f}, {mcf_y/10:.2f}) cm, {mcf_w/10:.2f} x {mcf_h/10:.2f} cm")
        print()

print()
print("=" * 80)
print("SUMMARY:")
print("=" * 80)
print(f"Front cover dimensions: {layouts[0]['width']} x {layouts[0]['height']} points")
print(f"Content page dimensions: {layouts[2]['width']} x {layouts[2]['height']} points")
print(f"Difference: {layouts[0]['width'] - layouts[2]['width']:.2f} x {layouts[0]['height'] - layouts[2]['height']:.2f} points")
print(f"           = {(layouts[0]['width'] - layouts[2]['width']) * POINTS_TO_MCF:.0f} x {(layouts[0]['height'] - layouts[2]['height']) * POINTS_TO_MCF:.0f} MCF")
print()
print("Each page is now transformed using its ACTUAL page dimensions,")
print("so cover pages and content pages will have correct sizes in the MCF.")

