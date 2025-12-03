#!/usr/bin/env python3
"""Test XML formatting to match CEWE style."""

from lxml import etree

# Create test XML structure
root = etree.Element('page')
root.text = '\n        '

# Create area element
area = etree.SubElement(root, 'area', areatype='imagearea')
area.text = '\n            '

# Create position element
position = etree.SubElement(area, 'position')
position.set('height', '746.927')
position.set('left', '5260.97')
position.set('rotation', '0')
position.set('top', '1053.79')
position.set('width', '981.881')
position.set('zposition', '158')
position.tail = '\n            '

# Create decoration element
decoration = etree.SubElement(area, 'decoration')
decoration.tail = '\n            '

# Create image element
image = etree.SubElement(area, 'image')
image.set('filename', 'safecontainer:/test.jpg')
image.set('useABK', '1')
image.text = '\n                '
image.tail = '\n        '

# Create cutout element
cutout = etree.SubElement(image, 'cutout')
cutout.set('left', '-194.4')
cutout.set('scale', '0.591077')
cutout.set('top', '-103.771')
cutout.tail = '\n                '

# Create quality element
quality = etree.SubElement(image, 'quality')
quality.set('noise', '100')
quality.set('sharpness', '100')
quality.set('texture', '100')
quality.tail = '\n            '

area.tail = '\n    '
root.tail = '\n'

# Write with pretty_print=True
print("=== With pretty_print=True ===")
tree = etree.ElementTree(root)
tree.write('/tmp/test_pretty_true.xml', encoding='utf-8', xml_declaration=True, pretty_print=True)
with open('/tmp/test_pretty_true.xml', 'r') as f:
    print(f.read())

# Write with pretty_print=False
print("\n=== With pretty_print=False ===")
tree.write('/tmp/test_pretty_false.xml', encoding='utf-8', xml_declaration=True, pretty_print=False)
with open('/tmp/test_pretty_false.xml', 'r') as f:
    print(f.read())
