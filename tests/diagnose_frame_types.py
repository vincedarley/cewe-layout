"""Diagnostic script to examine frame types in Mimeo database."""
from pathlib import Path
import sys
import sqlite3
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.mimeo_import.mimeo_database import MimeoProject

ppb = Path('../2016-test.photoslibrary/resources/projects/legacy/7D065F9C-2AAF-49A2-A998-238E4C4E5B84.ppb')

# Check KHProjectFrame table schema
db_path = ppb / 'Project.db'
conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

print("KHProjectFrame table columns:")
cursor.execute("PRAGMA table_info(KHProjectFrame)")
frame_columns = cursor.fetchall()
for col in frame_columns:
    print(f"  {col[1]} ({col[2]})")
print()

# Get all frames for page 25 (CEWE page 25 = content page 23 = Mimeo layout index 24)
# Page 1=Front, Page 2=Inside Front, Page 3+=Content (so CEWE page 25 = layout 24)
cursor.execute("""
    SELECT * FROM KHProjectFrame 
    WHERE parentLayoutId = (
        SELECT modelId FROM KHProjectLayout 
        ORDER BY sequence 
        LIMIT 1 OFFSET 24
    )
    ORDER BY modelId
""")

frames = cursor.fetchall()
print(f"Frames on CEWE Page 25 (Mimeo layout index 24):")
print(f"Total frames: {len(frames)}")
print()

for i, frame in enumerate(frames):
    print(f"Frame {i}:")
    for key in frame.keys():
        value = frame[key]
        print(f"  {key}: {value}")
    print()

conn.close()
