"""Diagnostic script to understand Mimeo database structure."""
from pathlib import Path
from cewe_layout.mimeo.mimeo_database import MimeoProject
import sqlite3

ppb = Path('../2016-test.photoslibrary/resources/projects/legacy/7D065F9C-2AAF-49A2-A998-238E4C4E5B84.ppb')

proj = MimeoProject(ppb)
data = proj.extract_all()

print(f'Total layouts: {len(data["layouts"])}')
print(f'Total frames: {len(data["frames"])}')
print(f'Total photos: {len(data["photos"])}')
print()

# Check layout types
conn = sqlite3.connect(proj.db_path)
cursor = conn.cursor()

print("Layout type distribution:")
cursor.execute("SELECT layoutTypeId, COUNT(*) FROM KHProjectLayout GROUP BY layoutTypeId")
for row in cursor.fetchall():
    print(f'  Type {row[0]}: {row[1]} pages')
print()

# Find special pages (not type 1)
cursor.execute("SELECT sequence, layoutTypeId, modelId FROM KHProjectLayout WHERE layoutTypeId != 1 ORDER BY sequence")
special_pages = cursor.fetchall()
print(f"Special pages (not type 1):")
for seq, type_id, model_id in special_pages:
    print(f'  Sequence {seq}: layoutTypeId={type_id}, modelId={model_id}')
print()

# Check if there are pages with sequence > 87
cursor.execute("SELECT sequence, layoutTypeId, modelId FROM KHProjectLayout WHERE sequence >= 87 ORDER BY sequence")
print("Pages at sequence >= 87:")
for row in cursor.fetchall():
    print(f'  Sequence {row[0]}: layoutTypeId={row[1]}, modelId={row[2]}')
print()

# Count frames per page for first few and last few pages
print("Frames per page:")
for i in [0, 1, 2, 3, 87, 88]:
    if i < len(data['layouts']):
        layout = data['layouts'][i]
        page_id = layout['model_id']
        frames_on_page = [f for f in data['frames'] if f['page_id'] == page_id]
        print(f'  Page sequence {i}: {len(frames_on_page)} frames')

conn.close()
