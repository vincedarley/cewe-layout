"""Diagnostic script to examine frame dimensions for Mimeo page 3 (Content page 1)."""
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

if len(layouts) < 3:
    print("ERROR: Not enough layouts found")
    sys.exit(1)

# Find page 3 (layout index 2, since 0-indexed)
page_3_layout = layouts[2]
page_id = page_3_layout['model_id']

print(f"Mimeo Page 3 (Content Page 1)")
print(f"Layout model_id: {page_id}, sequence: {page_3_layout['index']}")
print()

# Find all frames on this page
page_3_frames = [f for f in frames if f['page_id'] == page_id]

print(f"Number of frames: {len(page_3_frames)}")
print()

for i, frame in enumerate(page_3_frames):
    print(f"Frame {i}:")
    print(f"  model_id: {frame['model_id']}")
    print(f"  x: {frame['x']}")
    print(f"  y: {frame['y']}")
    print(f"  width: {frame['width']}")
    print(f"  height: {frame['height']}")
    print(f"  aspect ratio (w/h): {frame['width'] / frame['height']:.3f}")
    print()

# Also show page dimensions
all_page_3_frames = page_3_frames
if all_page_3_frames:
    max_x = max(f['x'] + f['width'] for f in all_page_3_frames)
    max_y = max(f['y'] + f['height'] for f in all_page_3_frames)
    print(f"Page dimensions (from frames):")
    print(f"  width: {max_x}")
    print(f"  height: {max_y}")
    print(f"  aspect ratio (w/h): {max_x / max_y:.3f}")
