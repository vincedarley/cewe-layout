#!/usr/bin/env python3
"""Test gap change with scaling."""

import sys
sys.path.insert(0, '.')

from cewe_layout.gap_utils import transform_page_to_gapfree, transform_item_to_gapfree, transform_item_from_gapfree

# 2x2 grid setup
page_w = 2100.0
page_h = 2970.0
old_edge = 50.0
old_gap = 112.0
new_edge = 50.0
new_gap = 10.0

# Bottom-right photo in MCF with old gaps
br_left = 1106.0
br_top = 1541.0
br_width = 944.0
br_height = 1379.0

print("=== Original MCF (old gaps) ===")
print(f"Photo: ({br_left}, {br_top}, {br_width}, {br_height})")
print(f"Right edge: {br_left + br_width} (should be {page_w - old_edge})")
print(f"Bottom edge: {br_top + br_height} (should be {page_h - old_edge})")

print("\n=== Transform to gap-free (old gaps) ===")
old_gf_page_w, old_gf_page_h = transform_page_to_gapfree(page_w, page_h, old_edge, old_gap)
print(f"Old gap-free page: {old_gf_page_w} x {old_gf_page_h}")

gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
    br_left, br_top, br_width, br_height, old_edge, old_gap
)
print(f"Gap-free photo: ({gf_left}, {gf_top}, {gf_width}, {gf_height})")
print(f"Right edge: {gf_left + gf_width} (should be {old_gf_page_w})")
print(f"Bottom edge: {gf_top + gf_height} (should be {old_gf_page_h})")

print("\n=== Calculate new gap-free page ===")
new_gf_page_w, new_gf_page_h = transform_page_to_gapfree(page_w, page_h, new_edge, new_gap)
print(f"New gap-free page: {new_gf_page_w} x {new_gf_page_h}")

scale_w = new_gf_page_w / old_gf_page_w
scale_h = new_gf_page_h / old_gf_page_h
print(f"Scale factors: {scale_w:.6f} x {scale_h:.6f}")

print("\n=== Scale gap-free rectangles ===")
scaled_gf_left = gf_left * scale_w
scaled_gf_top = gf_top * scale_h
scaled_gf_width = gf_width * scale_w
scaled_gf_height = gf_height * scale_h
print(f"Scaled gap-free photo: ({scaled_gf_left:.1f}, {scaled_gf_top:.1f}, {scaled_gf_width:.1f}, {scaled_gf_height:.1f})")
print(f"Right edge: {scaled_gf_left + scaled_gf_width:.1f} (should be {new_gf_page_w})")
print(f"Bottom edge: {scaled_gf_top + scaled_gf_height:.1f} (should be {new_gf_page_h})")

print("\n=== Transform back to MCF (new gaps) ===")
new_left, new_top, new_width, new_height = transform_item_from_gapfree(
    scaled_gf_left, scaled_gf_top, scaled_gf_width, scaled_gf_height,
    new_edge, new_gap
)
print(f"New MCF: ({new_left:.1f}, {new_top:.1f}, {new_width:.1f}, {new_height:.1f})")
print(f"Right edge: {new_left + new_width:.1f} (should be {page_w - new_edge})")
print(f"Bottom edge: {new_top + new_height:.1f} (should be {page_h - new_edge})")

overshoot_right = (new_left + new_width) - (page_w - new_edge)
overshoot_bottom = (new_top + new_height) - (page_h - new_edge)
print(f"\nOvershoot right: {overshoot_right:.1f}")
print(f"Overshoot bottom: {overshoot_bottom:.1f}")

if abs(overshoot_right) < 0.1 and abs(overshoot_bottom) < 0.1:
    print("\n✓ SUCCESS: No overshoot with scaling!")
else:
    print("\n✗ FAIL: Still have overshoot")
