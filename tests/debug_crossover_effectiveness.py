#!/usr/bin/env python3
"""Demonstrate that structure-only crossover DOES change photo layouts."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.algorithms.fan_layout import _generate_random_tree, _crossover_trees
from cewe_layout.algorithms.base import LayoutRectangle

def get_layout_positions(tree, page_w, page_h, rectangles):
    """Compute and return the physical positions of photos in the layout."""
    tree.compute_aspect_ratios(rectangles)
    tree.compute_dimensions(page_w, page_h, rectangles)
    tree.compute_layout(0, 0)
    
    leaves = tree.collect_leaves()
    positions = {}
    for leaf in leaves:
        positions[leaf.item_idx] = {
            'x': leaf.x,
            'y': leaf.y,
            'width': leaf.width,
            'height': leaf.height,
            'area': leaf.width * leaf.height
        }
    return positions

def print_layout(positions, label):
    """Print photo positions in a readable format."""
    print(f"\n{label}:")
    for photo_id in sorted(positions.keys()):
        pos = positions[photo_id]
        print(f"  Photo {photo_id}: pos=({pos['x']:.1f}, {pos['y']:.1f}), "
              f"size={pos['width']:.1f}x{pos['height']:.1f}, area={pos['area']:.1f}")

# Create dummy rectangles (4 photos with equal preferred sizes)
rectangles = []
for i in range(4):
    rect = LayoutRectangle(
        item_id=f'photo_{i}',
        width=100.0,
        height=100.0,
        preferred_size=2.5,
        preserve_aspect_ratio=True,
        x=0, y=0
    )
    rectangles.append(rect)

page_w, page_h = 400.0, 300.0

print("="*70)
print("Testing if structure-only crossover changes physical layouts")
print("="*70)

# Generate two random trees
tree1 = _generate_random_tree(4, [0, 1, 2, 3])
tree2 = _generate_random_tree(4, [0, 1, 2, 3])

# Get layouts before crossover
layout1_before = get_layout_positions(tree1, page_w, page_h, rectangles)
layout2_before = get_layout_positions(tree2, page_w, page_h, rectangles)

print_layout(layout1_before, "Parent 1 layout (BEFORE crossover)")
print_layout(layout2_before, "Parent 2 layout (BEFORE crossover)")

# Perform crossover
print("\n" + "="*70)
print("PERFORMING CROSSOVER...")
print("="*70)

# Check what subtrees are available
from cewe_layout.algorithms.tree_builder import TreeNode

def count_subtrees(tree):
    subtrees = [st for st in tree.collect_subtrees(min_leaves=3) if st.parent is not None]
    return len(subtrees)

print(f"Parent 1 has {count_subtrees(tree1)} suitable subtrees for crossover")
print(f"Parent 2 has {count_subtrees(tree2)} suitable subtrees for crossover")

child1, child2 = _crossover_trees(tree1, tree2)

# Get layouts after crossover
layout1_after = get_layout_positions(child1, page_w, page_h, rectangles)
layout2_after = get_layout_positions(child2, page_w, page_h, rectangles)

print_layout(layout1_after, "Child 1 layout (AFTER crossover)")
print_layout(layout2_after, "Child 2 layout (AFTER crossover)")

# Check if physical layouts actually changed
def layouts_equal(layout1, layout2, tolerance=0.1):
    """Check if two layouts are physically the same."""
    for photo_id in layout1.keys():
        pos1 = layout1[photo_id]
        pos2 = layout2[photo_id]
        if (abs(pos1['x'] - pos2['x']) > tolerance or
            abs(pos1['y'] - pos2['y']) > tolerance or
            abs(pos1['width'] - pos2['width']) > tolerance or
            abs(pos1['height'] - pos2['height']) > tolerance):
            return False
    return True

print("\n" + "="*70)
print("ANALYSIS:")
print("="*70)

if layouts_equal(layout1_before, layout1_after):
    print("❌ Child 1 layout is IDENTICAL to Parent 1 - no physical change!")
else:
    print("✓ Child 1 layout is DIFFERENT from Parent 1 - physical positions changed!")
    
    # Show which photos moved significantly
    for photo_id in sorted(layout1_before.keys()):
        before = layout1_before[photo_id]
        after = layout1_after[photo_id]
        dx = abs(after['x'] - before['x'])
        dy = abs(after['y'] - before['y'])
        dw = abs(after['width'] - before['width'])
        dh = abs(after['height'] - before['height'])
        if dx > 1 or dy > 1 or dw > 1 or dh > 1:
            print(f"  Photo {photo_id} moved: dx={dx:.1f}, dy={dy:.1f}, "
                  f"dw={dw:.1f}, dh={dh:.1f}")

if layouts_equal(layout2_before, layout2_after):
    print("\n❌ Child 2 layout is IDENTICAL to Parent 2 - no physical change!")
else:
    print("\n✓ Child 2 layout is DIFFERENT from Parent 2 - physical positions changed!")
    
    for photo_id in sorted(layout2_before.keys()):
        before = layout2_before[photo_id]
        after = layout2_after[photo_id]
        dx = abs(after['x'] - before['x'])
        dy = abs(after['y'] - before['y'])
        dw = abs(after['width'] - before['width'])
        dh = abs(after['height'] - before['h'])
        if dx > 1 or dy > 1 or dw > 1 or dh > 1:
            print(f"  Photo {photo_id} moved: dx={dx:.1f}, dy={dy:.1f}, "
                  f"dw={dw:.1f}, dh={dh:.1f}")
