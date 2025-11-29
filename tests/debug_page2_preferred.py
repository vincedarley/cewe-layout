#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

from cewe_layout.gap_utils import estimate_gaps, analyze_gaps

photos = [
    {'area_left': 155.63, 'area_top': 155.61, 'area_width': 1697.78, 'area_height': 1239.22},
    {'area_left': 1966.59, 'area_top': 155.61, 'area_width': 1697.78, 'area_height': 1239.22},
    {'area_left': 155.63, 'area_top': 1506.59, 'area_width': 1697.78, 'area_height': 1239.22},
    {'area_left': 1966.59, 'area_top': 1506.59, 'area_width': 1697.78, 'area_height': 1239.22},
]

edge1, inter1 = estimate_gaps(photos, 3820.0, 2900.0, 0.0)
gap_analysis = analyze_gaps(photos, 3820.0, 2900.0, 0.0)

print(f'estimate_gaps: edge={edge1:.2f}, internal={inter1:.2f}')
print(f'analyze_gaps: edge={gap_analysis.edge_gap:.2f}, internal={gap_analysis.internal_gap:.2f}')
print(f'GUI gap (prefer internal): {inter1 if inter1 > 0 else edge1:.2f}')
print()

# Compute preferred sizes as GUI does
gap = inter1 if inter1 > 0 else edge1
total_area = sum((p['area_width'] + gap) * (p['area_height'] + gap) for p in photos)
print(f'Total gap-free area (GUI): {total_area:.2f}')
for i, p in enumerate(photos):
    area = (p['area_width'] + gap) * (p['area_height'] + gap)
    preferred = (area / total_area) * 10.0
    print(f'  Photo {i}: area={(p["area_width"] + gap):.2f} x {(p["area_height"] + gap):.2f} = {area:.2f}, preferred={preferred:.6f}')
print()

# Now compute as my test does
print("My test computation:")
total_gf_area = 0
for p in photos:
    gf_w = p['area_width'] + gap_analysis.internal_gap
    gf_h = p['area_height'] + gap_analysis.internal_gap
    gf_area = gf_w * gf_h
    total_gf_area += gf_area

print(f'Total gap-free area (my test): {total_gf_area:.2f}')
for i, p in enumerate(photos):
    gf_w = p['area_width'] + gap_analysis.internal_gap
    gf_h = p['area_height'] + gap_analysis.internal_gap
    gf_area = gf_w * gf_h
    preferred = (gf_area / total_gf_area * 10.0) if total_gf_area > 0 else 1.0
    print(f'  Photo {i}: area={gf_w:.2f} x {gf_h:.2f} = {gf_area:.2f}, preferred={preferred:.6f}')
