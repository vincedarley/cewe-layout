"""Debug Page 10 with negative coordinates."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.algorithms.tree_builder import build_tree_from_layout

# Page 10 rectangles
rectangles = [
    LayoutRectangle('0', width=1458.7, height=1485.8, x=-30.0, y=-30.0),
    LayoutRectangle('1', width=2395.1, height=1485.8, x=1424.9, y=-30.0),
    LayoutRectangle('2', width=2429.0, height=1480.0, x=-30.0, y=1450.0),
    LayoutRectangle('3', width=1428.7, height=1480.0, x=2391.3, y=1450.0),
]

page_width = 3820
page_height = 2900

print("Page 10 layout (with bleeds):")
for i, r in enumerate(rectangles):
    print(f"  [{i}] x={r.x:.1f} to {r.x+r.width:.1f}, y={r.y:.1f} to {r.y+r.height:.1f}")

print("\n2x2 grid structure:")
print(f"  Top-left [0]: x={-30} to {1428.7}, y={-30} to {1455.8}")
print(f"  Top-right [1]: x={1424.9} to {3820}, y={-30} to {1455.8}")
print(f"  Bottom-left [2]: x={-30} to {2399}, y={1450} to {2930}")
print(f"  Bottom-right [3]: x={2391.3} to {3820}, y={1450} to {2930}")

print("\nShould split:")
print(f"  Horizontally around y=1450")
print(f"  Vertically around x=1425 (top) or x=2391-2399 (bottom)")

from cewe_layout.algorithms.tree_builder import find_split
indexed = [(i, r) for i, r in enumerate(rectangles)]

print("\nTrying different tolerances:")
for tol in [5.0, 6.0, 10.0, 20.0]:
    split = find_split(indexed, page_width, page_height, tolerance=tol)
    if split:
        direction, position, left, right = split
        print(f"  tol={tol}: {direction} at {position:.1f}, left/top={[i for i,_ in left]}, right/bot={[i for i,_ in right]}")
    else:
        print(f"  tol={tol}: No split")

tree = build_tree_from_layout(rectangles, page_width, page_height, tolerance=10.0, debug=True)

if tree:
    print("\n✓ Tree built!")
else:
    print("\n✗ Failed!")
