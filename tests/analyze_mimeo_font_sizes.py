"""Analyze Mimeo font style names to decode font and size information."""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict
import re

def analyze_font_sizes(ppb_path: Path):
    """Analyze textStyleName patterns to determine font and size."""
    db_path = ppb_path / 'Project.db'
    
    if not db_path.exists():
        print(f"Error: Project.db not found at {db_path}")
        return
    
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all unique textStyleName values
    cursor.execute(
        "SELECT DISTINCT value FROM KHProjectFrameAttribute WHERE key = 'textStyleName'"
    )
    
    style_names = [row['value'] for row in cursor.fetchall() if row['value']]
    
    print(f"Found {len(style_names)} unique textStyleName values:")
    print(f"{'-' * 60}")
    
    for style_name in sorted(style_names):
        # Try to parse the pattern - likely format: FontName[Weight]Numbers
        # Numbers might be size*100 (e.g., 18.22pt = 1822, 38.46pt = 3846, 9.11pt = 911)
        match = re.match(r'^([A-Za-z]+?)([A-Z][a-z]+)?(\d+)$', style_name)
        
        if match:
            font_family = match.group(1)
            font_weight = match.group(2) or ''
            size_code = match.group(3)
            
            # Try interpreting size_code as size*100
            try:
                size_pt = int(size_code) / 100.0
                print(f"{style_name:30} → Font: {font_family:15} Weight: {font_weight:10} Size: {size_pt:6.2f} pt")
            except:
                print(f"{style_name:30} → Font: {font_family:15} Weight: {font_weight:10} Size code: {size_code}")
        else:
            print(f"{style_name:30} → [Unable to parse pattern]")
    
    print()
    
    # Also check if there's a separate table for font/style definitions
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row['name'] for row in cursor.fetchall()]
    
    print(f"All tables in database:")
    print(f"{'-' * 60}")
    for table in tables:
        if 'text' in table.lower() or 'font' in table.lower() or 'style' in table.lower():
            print(f"  {table} ← (potentially relevant)")
        else:
            print(f"  {table}")
    
    conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python analyze_mimeo_font_sizes.py <path_to_ppb>")
        sys.exit(1)
    
    ppb_path = Path(sys.argv[1])
    analyze_font_sizes(ppb_path)
