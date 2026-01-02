#!/usr/bin/env python3
"""Explore Mimeo Project.db to understand coordinate system and color formats.

This script analyzes a Mimeo .ppb project to determine:
1. Coordinate system (units, ranges)
2. Color format for backgrounds
3. Border attributes
4. Photo-to-frame mapping strategy

Usage:
    python explore_mimeo.py /path/to/project.ppb
"""

import sys
import sqlite3
from pathlib import Path
from collections import Counter


def explore_coordinates(db_path: Path):
    """Analyze frame coordinates to understand the coordinate system."""
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n=== COORDINATE ANALYSIS ===")
    
    # Get all frames
    cursor.execute("SELECT x, y, width, height FROM KHProjectFrame")
    frames = cursor.fetchall()
    
    if not frames:
        print("No frames found")
        conn.close()
        return
    
    # Calculate ranges
    x_vals = [f['x'] for f in frames]
    y_vals = [f['y'] for f in frames]
    w_vals = [f['width'] for f in frames]
    h_vals = [f['height'] for f in frames]
    
    print(f"\nX range: {min(x_vals):.2f} to {max(x_vals):.2f}")
    print(f"Y range: {min(y_vals):.2f} to {max(y_vals):.2f}")
    print(f"Width range: {min(w_vals):.2f} to {max(w_vals):.2f}")
    print(f"Height range: {min(h_vals):.2f} to {max(h_vals):.2f}")
    
    # Calculate potential page dimensions (assume max x + width, max y + height)
    max_page_width = max(f['x'] + f['width'] for f in frames)
    max_page_height = max(f['y'] + f['height'] for f in frames)
    
    print(f"\nInferred page dimensions:")
    print(f"  Width: {max_page_width:.2f} Mimeo units")
    print(f"  Height: {max_page_height:.2f} Mimeo units")
    
    # Show first few frames as examples
    print(f"\nFirst 5 frames:")
    cursor.execute("SELECT x, y, width, height, parentLayoutId FROM KHProjectFrame LIMIT 5")
    for i, frame in enumerate(cursor.fetchall(), 1):
        print(f"  Frame {i}: x={frame['x']:.2f}, y={frame['y']:.2f}, "
              f"w={frame['width']:.2f}, h={frame['height']:.2f}, page={frame['parentLayoutId']}")
    
    conn.close()


def explore_colors(db_path: Path):
    """Analyze color attributes in the database."""
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n=== COLOR ANALYSIS ===")
    
    # Check KHProjectLayout for background colors
    cursor.execute("PRAGMA table_info(KHProjectLayout)")
    layout_columns = [col['name'] for col in cursor.fetchall()]
    print(f"\nKHProjectLayout columns: {', '.join(layout_columns)}")
    
    # Look for color-related columns
    color_columns = [c for c in layout_columns if 'color' in c.lower()]
    if color_columns:
        print(f"Color-related columns: {', '.join(color_columns)}")
        
        for col in color_columns:
            cursor.execute(f"SELECT DISTINCT {col} FROM KHProjectLayout WHERE {col} IS NOT NULL")
            values = [row[0] for row in cursor.fetchall()]
            if values:
                print(f"\n{col} values: {values[:10]}")  # Show first 10
    
    # Check KHProjectFrame for border colors
    cursor.execute("PRAGMA table_info(KHProjectFrame)")
    frame_columns = [col['name'] for col in cursor.fetchall()]
    print(f"\nKHProjectFrame columns: {', '.join(frame_columns)}")
    
    border_columns = [c for c in frame_columns if 'border' in c.lower() or 'color' in c.lower()]
    if border_columns:
        print(f"Border/color columns: {', '.join(border_columns)}")
        
        for col in border_columns:
            cursor.execute(f"SELECT DISTINCT {col} FROM KHProjectFrame WHERE {col} IS NOT NULL")
            values = [row[0] for row in cursor.fetchall()]
            if values:
                print(f"\n{col} values: {values[:10]}")
    
    conn.close()


def explore_photo_mapping(db_path: Path):
    """Understand how photos map to frames."""
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n=== PHOTO-FRAME MAPPING ===")
    
    # Count photos
    cursor.execute("SELECT COUNT(*) FROM KHProjectPhoto")
    photo_count = cursor.fetchone()[0]
    
    # Count frames
    cursor.execute("SELECT COUNT(*) FROM KHProjectFrame")
    frame_count = cursor.fetchone()[0]
    
    # Count mappings
    cursor.execute("SELECT COUNT(*) FROM KHProjectPhotoFrame")
    mapping_count = cursor.fetchone()[0]
    
    print(f"\nPhotos: {photo_count}")
    print(f"Frames: {frame_count}")
    print(f"Explicit mappings: {mapping_count}")
    
    if mapping_count > 0:
        print("\nUsing explicit KHProjectPhotoFrame mappings")
        cursor.execute("SELECT * FROM KHProjectPhotoFrame LIMIT 5")
        for i, row in enumerate(cursor.fetchall(), 1):
            print(f"  Mapping {i}: {dict(row)}")
    else:
        print("\nNo explicit mappings - likely using index-based mapping")
        print("Assumption: photo[i] → frame[i]")


def explore_pages(db_path: Path):
    """Analyze page layout structure."""
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("\n=== PAGE LAYOUT ANALYSIS ===")
    
    # Count pages
    cursor.execute("SELECT COUNT(*) FROM KHProjectLayout")
    page_count = cursor.fetchone()[0]
    print(f"\nTotal pages: {page_count}")
    
    # Count frames per page
    cursor.execute("""
        SELECT parentLayoutId, COUNT(*) as frame_count
        FROM KHProjectFrame
        GROUP BY parentLayoutId
        ORDER BY parentLayoutId
    """)
    
    frames_per_page = cursor.fetchall()
    counter = Counter(row['frame_count'] for row in frames_per_page)
    
    print(f"\nFrames per page distribution:")
    for count, freq in sorted(counter.items()):
        print(f"  {count} frames: {freq} pages")
    
    conn.close()


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    
    ppb_path = Path(sys.argv[1])
    
    if not ppb_path.exists():
        print(f"Error: Path does not exist: {ppb_path}")
        sys.exit(1)
    
    db_path = ppb_path / 'Project.db'
    
    if not db_path.exists():
        print(f"Error: Project.db not found at: {db_path}")
        sys.exit(1)
    
    print(f"Analyzing Mimeo project: {ppb_path.name}")
    
    explore_coordinates(db_path)
    explore_colors(db_path)
    explore_photo_mapping(db_path)
    explore_pages(db_path)
    
    print("\n=== DONE ===\n")


if __name__ == '__main__':
    main()
