"""Diagnose how photos map to frames in Mimeo database."""
import sqlite3
from pathlib import Path
from cewe_layout.mimeo_import.mimeo_database import MimeoProject

ppb = Path('../2016-test.photoslibrary/resources/projects/legacy/7D065F9C-2AAF-49A2-A998-238E4C4E5B84.ppb')

proj = MimeoProject(ppb)
data = proj.extract_all()

print(f"Total photos: {len(data['photos'])}")
print(f"Total frames: {len(data['frames'])}")
print(f"Photo-frame mappings in KHProjectPhotoFrame: {len(data['photo_frame_mappings'])}")
print()

# Check the database schema for other clues
conn = sqlite3.connect(proj.db_path)
cursor = conn.cursor()

# Check if frames have any ordering field
cursor.execute("PRAGMA table_info(KHProjectFrame)")
frame_columns = [row[1] for row in cursor.fetchall()]
print(f"KHProjectFrame columns: {', '.join(frame_columns)}")
print()

# Check if there's a photoIndex or similar in frames
cursor.execute("SELECT modelId, parentLayoutId FROM KHProjectFrame ORDER BY modelId LIMIT 10")
print("First 10 frames (modelId, parentLayoutId):")
for row in cursor.fetchall():
    print(f"  Frame {row[0]}: layout={row[1]}")
print()

# Check photo table schema
cursor.execute("PRAGMA table_info(KHProjectPhoto)")
photo_columns = [row[1] for row in cursor.fetchall()]
print(f"KHProjectPhoto columns: {', '.join(photo_columns)}")
print()

# Check first few photos
cursor.execute("SELECT modelId, photoId FROM KHProjectPhoto ORDER BY modelId LIMIT 10")
print("First 10 photos (modelId, photoId):")
for row in cursor.fetchall():
    print(f"  Photo {row[0]}: UUID={row[1][:20]}...")
print()

# Critical question: Are there exactly as many photos as frames, or not?
# If not, what's the mapping logic?
print(f"Difference: {len(data['photos'])} photos - {len(data['frames'])} frames = {len(data['photos']) - len(data['frames'])} extra photos")

conn.close()
