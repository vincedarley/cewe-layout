"""Debug why Page 3 fails to build a tree."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.algorithms.tree_builder import build_tree_from_layout


# Page 3 rectangles from test output
rectangles = [
    LayoutRectangle('0', width=611.2, height=789.4, x=155.6, y=155.6),
    LayoutRectangle('1', width=611.2, height=786.5, x=155.6, y=1056.7),
    LayoutRectangle('2', width=2784.4, height=1689.1, x=880.0, y=155.6),
    LayoutRectangle('3', width=611.2, height=789.4, x=155.6, y=1956.4),
    LayoutRectangle('4', width=611.2, height=789.4, x=880.0, y=1956.4),
    LayoutRectangle('5', width=611.2, height=789.4, x=1604.4, y=1956.4),
    LayoutRectangle('6', width=611.2, height=789.4, x=2328.8, y=1956.4),
    LayoutRectangle('7', width=611.2, height=789.4, x=3053.2, y=1956.4),
]

page_width = 3820
page_height = 2900

print("Page 3 layout:")
for i, r in enumerate(rectangles):
    print(f"  [{i}] x={r.x:.1f}-{r.x+r.width:.1f}, y={r.y:.1f}-{r.y+r.height:.1f}")

print(f"\nPage dimensions: {page_width} x {page_height}")

print("\nAttempting to build tree...")
tree = build_tree_from_layout(rectangles, page_width, page_height, tolerance=5.0)

if tree:
    print("\n✓ Tree built successfully!")
    print(tree)
else:
    print("\n✗ Failed to build tree")

