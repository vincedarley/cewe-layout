"""Debug why Page 8 fails to build a tree."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.algorithms.tree_builder import build_tree_from_layout, find_split


# Page 8 rectangles from test output
rectangles = [
    LayoutRectangle('0', width=792.3, height=563.0, x=155.6, y=155.6),
    LayoutRectangle('1', width=792.3, height=563.0, x=155.6, y=831.8),
    LayoutRectangle('2', width=1697.8, height=1239.2, x=1061.1, y=155.6),
    LayoutRectangle('3', width=792.3, height=563.0, x=2872.1, y=155.6),
    LayoutRectangle('4', width=792.3, height=563.0, x=2872.1, y=831.8),
    LayoutRectangle('5', width=792.3, height=563.0, x=155.6, y=1506.6),
    LayoutRectangle('6', width=792.3, height=563.0, x=155.6, y=2182.8),
    LayoutRectangle('7', width=794.2, height=1239.2, x=1061.1, y=1506.6),
    LayoutRectangle('8', width=792.3, height=563.0, x=2872.1, y=1506.6),
    LayoutRectangle('9', width=792.3, height=563.0, x=2872.1, y=2182.8),
    LayoutRectangle('10', width=786.5, height=1239.0, x=1972.4, y=1506.8),
]

page_width = 3820
page_height = 2900

print("Page 8 layout visualization:")
print("\nTop section (y < ~1500):")
for i, r in enumerate(rectangles):
    if r.y < 1500:
        print(f"  [{i}] x={r.x:.1f}-{r.x+r.width:.1f}, y={r.y:.1f}-{r.y+r.height:.1f}")

print("\nBottom section (y >= ~1500):")
for i, r in enumerate(rectangles):
    if r.y >= 1500:
        print(f"  [{i}] x={r.x:.1f}-{r.x+r.width:.1f}, y={r.y:.1f}-{r.y+r.height:.1f}")

print("\n\nLooking for initial split:")
indexed = [(i, r) for i, r in enumerate(rectangles)]
split = find_split(indexed, page_width, page_height, tolerance=5.0)

if split:
    direction, position, left, right = split
    print(f"✓ Found {direction} split at {position:.1f}")
    print(f"  Left/Top: {[i for i,r in left]}")
    print(f"  Right/Bottom: {[i for i,r in right]}")
else:
    print("✗ No split found")
    print("\nTrying to understand why...")
    
    # Check for obvious horizontal splits
    y_coords = set()
    for i, r in rectangles:
        y_coords.add(r.y)
        y_coords.add(r.y + r.height)
    
    print(f"\nY coordinates where items start/end: {sorted(y_coords)}")
    
    # Try y=1394.8 (bottom of items 2)
    y = 1394.8
    print(f"\nTrying horizontal split at y={y}:")
    for i, r in enumerate(rectangles):
        if r.y + r.height <= y + 5:
            print(f"  Top: [{i}] ends at y={r.y + r.height:.1f}")
        elif r.y >= y - 5:
            print(f"  Bottom: [{i}] starts at y={r.y:.1f}")
        else:
            print(f"  CROSSES: [{i}] y={r.y:.1f} to {r.y+r.height:.1f}")

print("\n\nAttempting to build full tree...")
tree = build_tree_from_layout(rectangles, page_width, page_height, tolerance=5.0, debug=True)

if tree:
    print("✓ Tree built successfully!")
else:
    print("✗ Failed to build tree")
