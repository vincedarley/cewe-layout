#!/usr/bin/env python3
"""Diagnose how photos are mapped to frames in Mimeo database."""

import sqlite3
from pathlib import Path

# Path to the Mimeo project
ppb_path = Path('../2016-test.photoslibrary/resources/projects/legacy/7D065F9C-2AAF-49A2-A998-238E4C4E5B84.ppb')

if not ppb_path.exists():
    print(f"ERROR: Project not found at {ppb_path}")
    exit(1)

print(f"Found project at: {ppb_path.resolve()}")

# Connect to database
db_path = ppb_path / "database.sqlite"
if not db_path.exists():
    print(f"ERROR: Database not found at {db_path}")
    exit(1)

print(f"Found database at: {db_path.resolve()}")

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# First, let's see all tables in the database
print("\n" + "=" * 80)
print("All tables in database:")
print("=" * 80)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
all_tables = [row['name'] for row in cursor.fetchall()]

if not all_tables:
    print("  No tables found!")
    conn.close()
    exit(1)

for table_name in all_tables:
    cursor.execute(f"SELECT COUNT(*) as count FROM {table_name}")
    count = cursor.fetchone()['count']
 
if not ppb_path.exists():
    print(f"ERROR: Project not found at {ppb_path}")
    exit(1)

print(f"Found projrojectPhoto table:")
print("=" * 80)
if 'KHProjectPhoto' in all_tables:
    cursor.execute("PRAGMA table_info(KHProjectPhoto)")
    columns = [row['name'] for row in cursor.fetchall()]
    print(f"Columns: {', '.join(columns)}")
    
    # Show first 3 photos
    cursor.execute("SELE
print(f"FKHProjectPhoto LIMIT 3")
    print("\nFirst 3 photos:")
    for row in cursor.fetchall():
        print(f"  {dict(row)}")
else:
    print("  Table not found!")

# Look at KHProjectFrame structure
print("\n" + "=" * 80)
print("KHProjectFrame table:")
print("=" * 8all_tables = [row['name'] for row in curso# Check if childLayoutId might link to photos
    cursor.execute("SELECT modelId, parentLayoutId, childLayoutId, contentEntityClass FROM KHProjectFrame WHERE childLayoutId > 0 LIMIT 5")
    frames_with_child = cursor.fetchall()
    print(f"Frames with childLayoutId > 0: {len(frames_with_child)}")
    if frames_with_child:
        for row in frames_with_child:
            print(f"  {dict(row)}")
else:
   print("=" * 80)
if 'Kound!")

# Look for any content-related tables
print("\n" + "=" * 80)
print("Content-related tables:")
print("=" * 80)
for table_name in all_tables:
    if 'content' in table_name.lower() or 'photo' in table_name.lower() or 'frame' in table_name.lower():
        print(f"\n{table_name}:")
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [row['name'] for row in cursor.fetchall()]
        print(f"  Columns: {', '.join(columns)}")
        
        # Show sample row
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 1")
        sample = cursor.fetchone()
        if sample:
            print(f"  Sample: {dict(sample)}")

conn.close()
print("\nDone.")
