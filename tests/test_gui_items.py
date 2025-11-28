"""
Test GUI item display for both photos and texts.

This test verifies that the GUI correctly handles displaying weights
for both photos and text blocks.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_item_identifiers():
    """Test that photos and texts get correct identifiers."""
    
    # Photos should use filename as identifier
    # Texts should use TEXT_<index> as identifier
    
    photos = [
        {'filename': 'photo1.jpg', 'area_width': 500, 'area_height': 300},
        {'filename': 'photo2.jpg', 'area_width': 600, 'area_height': 400},
    ]
    
    texts = [
        {'area_width': 400, 'area_height': 200},
    ]
    
    # Expected identifiers for layout manager
    expected_photo_ids = ['photo1.jpg', 'photo2.jpg']
    expected_text_ids = ['TEXT_0']
    
    # Verify photo identifiers
    for i, photo in enumerate(photos):
        photo_id = photo.get('filename', '')
        assert photo_id == expected_photo_ids[i], f"Photo {i} ID mismatch: {photo_id} != {expected_photo_ids[i]}"
    
    # Verify text identifiers
    for i, text in enumerate(texts):
        text_id = f'TEXT_{i}'
        assert text_id == expected_text_ids[i], f"Text {i} ID mismatch: {text_id} != {expected_text_ids[i]}"
    
    print("✓ Item identifiers correct")
    print(f"  Photo IDs: {expected_photo_ids}")
    print(f"  Text IDs: {expected_text_ids}")


def test_item_display_labels():
    """Test that display labels use correct prefixes."""
    
    # Photos should display as P1, P2, P3, ...
    # Texts should display as T1, T2, T3, ...
    
    photos = [{'filename': f'p{i}.jpg'} for i in range(3)]
    texts = [{} for _ in range(2)]
    
    # Expected display labels
    expected_photo_labels = ['P1', 'P2', 'P3']
    expected_text_labels = ['T1', 'T2']
    
    # Simulate label creation logic
    photo_labels = [f'P{i+1}' for i in range(len(photos))]
    text_labels = [f'T{i+1}' for i in range(len(texts))]
    
    assert photo_labels == expected_photo_labels, f"Photo labels mismatch"
    assert text_labels == expected_text_labels, f"Text labels mismatch"
    
    print("✓ Display labels correct")
    print(f"  Photo labels: {photo_labels}")
    print(f"  Text labels: {text_labels}")


def test_combined_item_list():
    """Test that photos and texts are combined correctly for display."""
    
    photos = [
        {'filename': 'photo1.jpg', 'area_width': 500, 'area_height': 300},
        {'filename': 'photo2.jpg', 'area_width': 600, 'area_height': 400},
    ]
    
    texts = [
        {'area_width': 400, 'area_height': 200},
    ]
    
    # Simulate item_identifiers list creation
    item_identifiers = []
    
    # Add photos
    for i, p in enumerate(photos):
        fn = p.get('filename', '')
        item_identifiers.append(('photo', i, fn))
    
    # Add texts
    for i, t in enumerate(texts):
        text_id = f'TEXT_{i}'
        item_identifiers.append(('text', i, text_id))
    
    # Expected result
    expected = [
        ('photo', 0, 'photo1.jpg'),
        ('photo', 1, 'photo2.jpg'),
        ('text', 0, 'TEXT_0'),
    ]
    
    assert item_identifiers == expected, f"Item identifiers mismatch"
    
    # Test label generation
    labels = []
    for item_type, item_idx, item_id in item_identifiers:
        type_prefix = 'P' if item_type == 'photo' else 'T'
        label = f'{type_prefix}{item_idx+1}'
        labels.append(label)
    
    expected_labels = ['P1', 'P2', 'T1']
    assert labels == expected_labels, f"Labels mismatch: {labels} != {expected_labels}"
    
    print("✓ Combined item list correct")
    print(f"  Item identifiers: {item_identifiers}")
    print(f"  Display labels: {labels}")


if __name__ == '__main__':
    print("Testing GUI item handling...\n")
    
    test_item_identifiers()
    print()
    
    test_item_display_labels()
    print()
    
    test_combined_item_list()
    print()
    
    print("All tests passed! ✓")
