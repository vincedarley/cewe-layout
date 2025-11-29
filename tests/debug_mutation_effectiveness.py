#!/usr/bin/env python3
"""Test how effective mutation is at exploring the layout space."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.fan_layout import _generate_random_tree, _mutate_tree, _evaluate_cost
from cewe_layout.algorithms.base import LayoutRectangle
import copy

# Create rectangles matching Page 17 (uneven sizes)
# Page 17: ['2.68', '4.00', '2.68', '0.63'] + 1 text
rectangles = [
    LayoutRectangle(item_id='photo_0', width=180, height=134, preferred_size=2.68, preserve_aspect_ratio=True, x=0, y=0),
    LayoutRectangle(item_id='photo_1', width=180, height=202, preferred_size=4.00, preserve_aspect_ratio=True, x=0, y=0),
    LayoutRectangle(item_id='photo_2', width=180, height=134, preferred_size=2.68, preserve_aspect_ratio=True, x=0, y=0),
    LayoutRectangle(item_id='photo_3', width=78, height=63, preferred_size=0.63, preserve_aspect_ratio=True, x=0, y=0),
    LayoutRectangle(item_id='text_0', width=91, height=59, preferred_size=0.63, preserve_aspect_ratio=False, x=0, y=0),
]

page_w, page_h = 380, 290

print("="*70)
print("Testing Mutation Effectiveness on Page 17-like Layout")
print("="*70)
print(f"Items: {len(rectangles)} (4 photos + 1 text)")
print(f"Preferred sizes: {[r.preferred_size for r in rectangles]}")

# Generate one initial tree
initial_tree = _generate_random_tree(5, [0, 1, 2, 3, 4])
initial_tree.compute_aspect_ratios(rectangles)
initial_tree.compute_dimensions(page_w, page_h, rectangles)
initial_tree.compute_layout(0, 0)
initial_cost = _evaluate_cost(initial_tree, page_w, page_h, rectangles, 
                              size_importance=100.0, undersized_threshold=0.5,
                              undersized_penalty=5.0)

print(f"\nInitial tree cost: {initial_cost:.2f}")

# Apply mutation repeatedly and track results
print("\nApplying 50 mutations and tracking cost distribution...")
costs = [initial_cost]
current_tree = copy.deepcopy(initial_tree)

for i in range(50):
    mutated = _mutate_tree(copy.deepcopy(current_tree))
    mutated.compute_aspect_ratios(rectangles)
    mutated.compute_dimensions(page_w, page_h, rectangles)
    mutated.compute_layout(0, 0)
    cost = _evaluate_cost(mutated, page_w, page_h, rectangles,
                         size_importance=100.0, undersized_threshold=0.5,
                         undersized_penalty=5.0)
    costs.append(cost)
    
    # Keep best mutation (simple hill climbing)
    if cost < costs[-2]:
        current_tree = mutated

costs.sort()
print(f"\nCost distribution after 50 mutations:")
print(f"  Best:    {costs[0]:.2f}")
print(f"  Median:  {costs[len(costs)//2]:.2f}")
print(f"  Worst:   {costs[-1]:.2f}")
print(f"  Improvement from initial: {initial_cost - costs[0]:.2f}")

print(f"\n✓ {sum(1 for c in costs if c < initial_cost)} mutations improved cost")
print(f"✓ {sum(1 for c in costs if c > initial_cost)} mutations worsened cost")
print(f"✓ {sum(1 for c in costs if abs(c - initial_cost) < 0.01)} mutations had no effect")
