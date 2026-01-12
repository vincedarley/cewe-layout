"""Analyze all text-related attributes in Mimeo database.

This script queries the KHProjectFrameAttribute table to discover what
attributes are available for text frames.
"""

import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

def analyze_text_attributes(ppb_path: Path):
    """Analyze all attributes for text frames."""
    db_path = ppb_path / 'Project.db'
    
    if not db_path.exists():
        print(f"Error: Project.db not found at {db_path}")
        return
    
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # First, find frames that have text (frames with 'rawText' attribute)
    cursor.execute(
        "SELECT DISTINCT frameId FROM KHProjectFrameAttribute WHERE key = 'rawText'"
    )
    text_frame_ids = [row['frameId'] for row in cursor.fetchall()]
    
    print(f"Found {len(text_frame_ids)} text frames")
    print()
    
    # For each text frame, get ALL its attributes
    all_keys = set()
    frame_attrs = defaultdict(dict)
    
    for frame_id in text_frame_ids:
        cursor.execute(
            "SELECT key, value FROM KHProjectFrameAttribute WHERE frameId = ?",
            (frame_id,)
        )
        
        for row in cursor.fetchall():
            key = row['key']
            value = row['value']
            all_keys.add(key)
            frame_attrs[frame_id][key] = value
    
    print(f"All unique attribute keys found across text frames:")
    print(f"{'-' * 60}")
    for key in sorted(all_keys):
        print(f"  {key}")
    print()
    
    # Show detailed info for first few text frames
    print(f"Detailed attributes for first 3 text frames:")
    print(f"{'-' * 60}")
    for idx, frame_id in enumerate(text_frame_ids[:3]):
        print(f"\nFrame {frame_id}:")
        attrs = frame_attrs[frame_id]
        
        # Show text preview
        text = attrs.get('rawText', '')
        text_preview = text[:50] + '...' if len(text) > 50 else text
        print(f"  Text: '{text_preview}'")
        print(f"  Attributes:")
        
        for key in sorted(attrs.keys()):
            if key != 'rawText':  # Already shown above
                value = attrs[key]
                # Truncate long values
                value_str = str(value)
                if len(value_str) > 100:
                    value_str = value_str[:100] + '...'
                print(f"    {key}: {value_str}")
    
    conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python analyze_mimeo_text_attrs.py <path_to_ppb>")
        sys.exit(1)
    
    ppb_path = Path(sys.argv[1])
    analyze_text_attributes(ppb_path)
