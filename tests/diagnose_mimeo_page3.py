"""Diagnostic script to examine frame dimensions for Mimeo pages."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.mimeo_import.mimeo_database import MimeoProject
from cewe_layout.mimeo_import.mimeo_converter import MimeoCoordinateTransformer

ppb = Path('../2016-test.photoslibrary/resources/projects/legacy/7D065F9C-2AAF-49A2-A998-238E4C4E5B84.ppb')

proj = MimeoProject(ppb)
data = proj.extract_all()

layouts = data['layouts']
frames = data['frames']

print(f"Total layouts: {len(layouts)}")
print(f"Total frames: {len(frames)}")

if len(layouts) < 30:
    print("ERROR: Not enough layouts found")
    sys.exit(1)

# Get page dimensions for transformer
first_layout = layouts[0]
mimeo_page_width = first_layout['width']
mimeo_page_height = first_layout['height']

transformer = MimeoCoordinateTransformer(mimeo_page_width, mimeo_page_height)
POINTS_TO_MCF = transformer.POINTS_TO_MCF

print(f"Mimeo page dimensions: {mimeo_page_width} x {mimeo_page_height} points")
print(f"POINTS_TO_MCF conversion factor: {POINTS_TO_MCF}")
print()

# Examine Mimeo pages 29, 30 (which become MCF pages 27, 28)
# Mimeo pages: 0=Front, 1=Inside Front, 2-N=content
# MCF pages: F=Front, 0=Inside Front, 1-N=content
# So Mimeo page 29 = MCF page 27 (since we skip F and IF when counting)

for mimeo_page_num in [29, 30]:
    layout_index = mimeo_page_num  # 0-indexed
    
    page_layout = layouts[layout_index]
    page_id = page_layout['model_id']
    
    # Get actual page dimensions from layout data
    page_width = page_layout.get('width', 'N/A')
    page_height = page_layout.get('height', 'N/A')
    
    # Calculate MCF page number
    # Mimeo: 0=F, 1=IF, 2-N=content starting at 1
    # MCF: F, 0=IF, 1-N=content
    if mimeo_page_num == 0:
        mcf_page = 'F'
    elif mimeo_page_num == 1:
        mcf_page = 0
    else:
        mcf_page = mimeo_page_num - 1  # Subtract 1 to account for Front cover
    
    # Determine if right page (odd MCF pages are right)
    is_right_page = (mcf_page != 'F' and mcf_page != 0 and mcf_page % 2 == 1)

    print(f"=" * 70)
    print(f"Mimeo Page {mimeo_page_num} → MCF Page {mcf_page} ({'RIGHT' if is_right_page else 'LEFT'})")
    print(f"Layout model_id: {page_id}, sequence: {page_layout['index']}")
    if page_width != 'N/A':
        print(f"Actual page size: {page_width:.2f} x {page_height:.2f} (aspect {page_width/page_height:.3f})")
    print()

    # Fi# Transform to MCF coordinates
        mcf_x, mcf_y, mcf_w, mcf_h = transformer.transform(
            frame['x'], frame['y'], frame['width'], frame['height'],
            is_right_page=is_right_page
        )
        
        print(f"Frame {i}:")
        print(f"  Mimeo (center-based, bottom-left origin):")
        print(f"    center: ({frame['x']:.2f}, {frame['y']:.2f}), size: {frame['width']:.2f} x {frame['height']:.2f}")
        print(f"    edges: left={left:.2f}, right={right:.2f}, bottom={top:.2f}, top={bottom:.2f}")
        print(f"  MCF (topleft-based, top-left origin, spread coords):")
        print(f"    left={mcf_x}, top={mcf_y}, width={mcf_w}, height={mcf_h}")
        print(f"    = {mcf_x/10:.1f} x {mcf_y/10:.1f} cm, {mcf_w/10:.1f} x {mcf_h/10:.1f} cm
    print(f"Number of frames: {len(page_frames)}")
    print()

    for i, frame in enumerate(page_frames):
        # Calculate edges if x,y are CENTER coordinates
        left = frame['x'] - frame['width'] / 2
        right = frame['x'] + frame['width'] / 2
        top = frame['y'] - frame['height'] / 2
        bottom = frame['y'] + frame['height'] / 2
        
        print(f"Frame {i}:")
        print(f"  left: {left:.2f}, right: {right:.2f}, top: {top:.2f}, bottom: {bottom:.2f}")
        print(f"  width: {frame['width']:.2f}, height: {frame['height']:.2f}")
        print()
    
    # Check gaps between frames
    if len(page_frames) >= 2:
        for i in range(len(page_frames) - 1):
            frame1_right = page_frames[i]['x'] + page_frames[i]['width'] / 2
            frame2_left = page_frames[i+1]['x'] - page_frames[i+1]['width'] / 2
            horizontal_gap = frame2_left - frame1_right
            
            frame1_bottom = page_frames[i]['y'] + page_frames[i]['height'] / 2
            frame2_top = page_frames[i+1]['y'] - page_frames[i+1]['height'] / 2
            vertical_gap = frame2_top - frame1_bottom
            
            print(f"Gap Frame {i} → Frame {i+1}:")
            print(f"  horizontal (F{i} right to F{i+1} left): {horizontal_gap:.2f}")
            print(f"  vertical (F{i} bottom to F{i+1} top): {vertical_gap:.2f}")
            print()

    # Show page dimensions calculated from frames (for comparison)
    if page_frames:
        max_x = max(f['x'] + f['width'] for f in page_frames)
        max_y = max(f['y'] + f['height'] for f in page_frames)
        print(f"Dimensions from frames: {max_x:.0f} x {max_y:.0f} (aspect {max_x / max_y:.3f})")
        print()
