"""Examine KHProjectTextStyle table in Mimeo database."""

import sqlite3
import sys
from pathlib import Path

def examine_text_style_table(ppb_path: Path):
    """Examine KHProjectTextStyle table."""
    db_path = ppb_path / 'Project.db'
    
    if not db_path.exists():
        print(f"Error: Project.db not found at {db_path}")
        return
    
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get schema of KHProjectTextStyle table
    cursor.execute("PRAGMA table_info(KHProjectTextStyle)")
    columns = cursor.fetchall()
    
    print("KHProjectTextStyle table schema:")
    print(f"{'-' * 80}")
    for col in columns:
        print(f"  {col['name']:20} {col['type']:15} (NOT NULL: {bool(col['notnull'])})")
    print()
    
    # Get all rows
    cursor.execute("SELECT * FROM KHProjectTextStyle")
    rows = cursor.fetchall()
    
    print(f"Found {len(rows)} text style definitions:")
    print(f"{'-' * 80}")
    
    for row in rows:
        print()
        for col_name in row.keys():
            value = row[col_name]
            # Truncate long values
            value_str = str(value) if value is not None else 'NULL'
            if len(value_str) > 100:
                value_str = value_str[:100] + '...'
            print(f"  {col_name:20}: {value_str}")
    
    conn.close()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python examine_text_style_table.py <path_to_ppb>")
        sys.exit(1)
    
    ppb_path = Path(sys.argv[1])
    examine_text_style_table(ppb_path)
