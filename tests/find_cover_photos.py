"""Find which layouts contain the cover photos."""
import sqlite3
from pathlib import Path
from cewe_layout.mimeo_import.mimeo_database import MimeoProject

ppb = Path('../2016-test.photoslibrary/resources/projects/legacy/7D065F9C-2AAF-49A2-A998-238E4C4E5B84.ppb')

proj = MimeoProject(ppb)
data = proj.extract_all()

# Find page sequence 73 (the special layoutTypeId=4 page)
layout_73 = [l for l in data['layouts'] if l['index'] == 73][0]
print(f"Layout sequence 73 (special type 4):")
print(f"  model_id: {layout_73['model_id']}")

# Find frames on this page
frames_on_73 = [f for f in data['frames'] if f['page_id'] == layout_73['model_id']]
print(f"  Frames: {len(frames_on_73)}")

# Map global photo index to frames
# The current code uses global_photo_idx incrementing through ALL frames
global_photo_idx = 0
for layout_idx, layout in enumerate(data['layouts']):
    page_id = layout['model_id']
    page_frames = [f for f in data['frames'] if f['page_id'] == page_id]
    
    for frame_idx, frame in enumerate(page_frames):
        if layout_idx == 73:
            print(f"  Frame {frame_idx}: photo index {global_photo_idx}")
            if global_photo_idx < len(data['photos']):
                photo = data['photos'][global_photo_idx]
                print(f"    Photo model_id: {photo['model_id']}, UUID: {photo['photo_id'][:20]}...")
        global_photo_idx += 1

print()
print(f"Total photos processed: {global_photo_idx}")
print(f"Total photos in database: {len(data['photos'])}")
