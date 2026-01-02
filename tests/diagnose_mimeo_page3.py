"""Diagnostic script to examine frame dimensions for Mimeo pages."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.mimeo.mimeo_database import MimeoProject

ppb = Path('../2016-test.photoslibrary/resources/projects/legacy/7D065F9C-2AAF-49A2-A998-238E4C4E5B84.ppb')

proj = MimeoProject(ppb)
data = proj.extract_all()

layouts = data['layouts']
frames = data['frames']

print(f"Total layouts: {len(layouts)}")
print(f"Total frames: {len(frames)}")

if len(layouts) < 13:
    print("ERROR: Not enough layouts found")
    sys.exit(1)

# Examine content pages 10, 11 (Mimeo pages 12, 13)
# Page 1 = Front cover, Page 2 = Inside Front, Pages 3+ = Content

for content_page_num in [10, 11]:
    mimeo_page_num = content_page_num + 2  # +2 because of front and inside front covers
    layout_index = mimeo_page_num - 1  # 0-indexed
    
    page_layout = layouts[layout_index]
    page_id = page_layout['model_id']
    
    # Get actual page dimensions from layout data
    page_width = page_layout.get('width', 'N/A')
    page_height = page_layout.get('height', 'N/A')

    print(f"=" * 70)
    print(f"Mimeo Page {mimeo_page_num} (Content Page {content_page_num})")
    print(f"Layout model_id: {page_id}, sequence: {page_layout['index']}")
    if page_width != 'N/A':
        print(f"Actual page size: {page_width:.2f} x {page_height:.2f} (aspect {page_width/page_height:.3f})")
    print()

    # Find all frames on this page
    page_frames = [f for f in frames if f['page_id'] == page_id]

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
