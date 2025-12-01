#!/usr/bin/env python3
"""Debug gap transformation with real example."""

import sys
sys.path.insert(0, '.')

from cewe_layout.gap_utils import (
    transform_page_to_gapfree,
    transform_item_to_gapfree,
    transform_item_from_gapfree
)

# Example: Page with 2x2 grid
page_w = 2100.0
page_h = 2970.0

# Original gaps
old_edge_gap = 50.0  # 5mm
old_internal_gap = 112.0  # 11.2mm

# New gaps
new_edge_gap = 50.0  # 5mm (unchanged)
new_internal_gap = 10.0  # 1mm

# Photo in bottom-right corner (should touch right and bottom edges after edge_gap)
# Original position with old gaps:
photo_left = 1100.0
photo_top = 1500.0
photo_width = 950.0
photo_height = 1420.0

print("=== Original MCF (with old gaps) ===")
print(f"Photo: left={photo_left}, top={photo_top}, width={photo_width}, height={photo_height}")
print(f"Photo right edge: {photo_left + photo_width}")
print(f"Photo bottom edge: {photo_top + photo_height}")
print(f"Page right edge: {page_w}")
print(f"Page bottom edge: {page_h}")
print(f"Distance to page right: {page_w - (photo_left + photo_width)} (should be ~edge_gap = {old_edge_gap})")
print(f"Distance to page bottom: {page_h - (photo_top + photo_height)} (should be ~edge_gap = {old_edge_gap})")

print(f"\n=== Transform to gap-free (old gaps) ===")
print(f"Old edge_gap={old_edge_gap}, old internal_gap={old_internal_gap}")

gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
    photo_left, photo_top, photo_width, photo_height,
    old_edge_gap, old_internal_gap
)

print(f"Gap-free: left={gf_left}, top={gf_top}, width={gf_width}, height={gf_height}")

gf_page_w, gf_page_h = transform_page_to_gapfree(page_w, page_h, old_edge_gap, old_internal_gap)
print(f"Gap-free page: {gf_page_w} x {gf_page_h}")
print(f"Photo right in gap-free: {gf_left + gf_width}")
print(f"Photo bottom in gap-free: {gf_top + gf_height}")
print(f"Distance to gf page right: {gf_page_w - (gf_left + gf_width)} (should be 0)")
print(f"Distance to gf page bottom: {gf_page_h - (gf_left + gf_height)} (should be 0)")

print(f"\n=== Transform back to MCF (new gaps) ===")
print(f"New edge_gap={new_edge_gap}, new internal_gap={new_internal_gap}")

new_left, new_top, new_width, new_height = transform_item_from_gapfree(
    gf_left, gf_top, gf_width, gf_height,
    new_edge_gap, new_internal_gap
)

print(f"New MCF: left={new_left}, top={new_top}, width={new_width}, height={new_height}")
print(f"New right edge: {new_left + new_width}")
print(f"New bottom edge: {new_top + new_height}")
print(f"Distance to page right: {page_w - (new_left + new_width)} (should be ~edge_gap = {new_edge_gap})")
print(f"Distance to page bottom: {page_h - (new_top + new_height)} (should be ~edge_gap = {new_edge_gap})")

# Check if overlap occurs
right_overlap = (new_left + new_width) - (page_w - new_edge_gap)
bottom_overlap = (new_top + new_height) - (page_h - new_edge_gap)

if right_overlap > 0:
    print(f"\n⚠️  RIGHT OVERLAP: Photo extends {right_overlap:.1f} units into edge_gap")
if bottom_overlap > 0:
    print(f"⚠️  BOTTOM OVERLAP: Photo extends {bottom_overlap:.1f} units into edge_gap")
