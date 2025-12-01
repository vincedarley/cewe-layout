#!/usr/bin/env python3
"""Analyze how gaps work in a real layout."""

import sys
sys.path.insert(0, '.')

# Simple 2x2 grid manually constructed
# Page: 2100 x 2970
# edge_gap: 50 (5mm)
# internal_gap: 112 (11.2mm)

# In MCF space, items should be positioned as:
# Top-left: starts at (50, 50), size to fill half minus gaps
# Top-right: starts after top-left + internal_gap
# etc.

page_w = 2100.0
page_h = 2970.0
edge = 50.0
gap = 112.0

# Available space after removing edge gaps
avail_w = page_w - 2*edge  # 2000
avail_h = page_h - 2*edge  # 2870

# For 2x2 grid with internal gap:
# width of each item = (avail_w - 1*gap) / 2
item_w = (avail_w - gap) / 2  # (2000 - 112) / 2 = 944
item_h = (avail_h - gap) / 2  # (2870 - 112) / 2 = 1379

print("=== 2x2 Grid in MCF space ===")
print(f"Page: {page_w} x {page_h}")
print(f"Edge gap: {edge}, Internal gap: {gap}")
print(f"Item dimensions: {item_w} x {item_h}")
print()

# Top-left
tl_left = edge
tl_top = edge
print(f"Top-left: ({tl_left}, {tl_top}, {item_w}, {item_h})")
print(f"  Right edge: {tl_left + item_w}")
print(f"  Bottom edge: {tl_top + item_h}")

# Top-right
tr_left = tl_left + item_w + gap
tr_top = edge
print(f"Top-right: ({tr_left}, {tr_top}, {item_w}, {item_h})")
print(f"  Right edge: {tr_left + item_w} (should be {page_w - edge})")
print(f"  Bottom edge: {tr_top + item_h}")

# Bottom-left
bl_left = edge
bl_top = tl_top + item_h + gap
print(f"Bottom-left: ({bl_left}, {bl_top}, {item_w}, {item_h})")
print(f"  Right edge: {bl_left + item_w}")
print(f"  Bottom edge: {bl_top + item_h}")

# Bottom-right
br_left = bl_left + item_w + gap
br_top = bl_top
print(f"Bottom-right: ({br_left}, {br_top}, {item_w}, {item_h})")
print(f"  Right edge: {br_left + item_w} (should be {page_w - edge})")
print(f"  Bottom edge: {br_top + item_h} (should be {page_h - edge})")

print("\n=== Now transform with current formulas ===")
from cewe_layout.gap_utils import transform_item_to_gapfree, transform_item_from_gapfree, transform_page_to_gapfree

gf_page_w, gf_page_h = transform_page_to_gapfree(page_w, page_h, edge, gap)
print(f"Gap-free page: {gf_page_w} x {gf_page_h}")

# Transform bottom-right to gap-free
gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
    br_left, br_top, item_w, item_h, edge, gap
)
print(f"Bottom-right in gap-free: ({gf_left}, {gf_top}, {gf_width}, {gf_height})")
print(f"  Right edge: {gf_left + gf_width} (should be {gf_page_w})")
print(f"  Bottom edge: {gf_top + gf_height} (should be {gf_page_h})")

# Now change internal_gap to 10
new_gap = 10.0
print(f"\n=== Transform back with new internal_gap={new_gap} ===")
new_left, new_top, new_width, new_height = transform_item_from_gapfree(
    gf_left, gf_top, gf_width, gf_height, edge, new_gap
)
print(f"New MCF: ({new_left}, {new_top}, {new_width}, {new_height})")
print(f"  Right edge: {new_left + new_width} (should be {page_w - edge} = {page_w - edge})")
print(f"  Bottom edge: {new_top + new_height} (should be {page_h - edge} = {page_h - edge})")

overshoot_right = (new_left + new_width) - (page_w - edge)
overshoot_bottom = (new_top + new_height) - (page_h - edge)
print(f"  Overshoot right: {overshoot_right}")
print(f"  Overshoot bottom: {overshoot_bottom}")
