#!/usr/bin/env python3
"""
Test different segmentation parameters and algorithms on composite_page1.jpeg.

This test helps find the best segmentation settings for analog scans with
varying black levels and reflections.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.pdf_import.image_segmenter import (
    segment_composite_image,
    MorphologicalSegmenter
)
from cewe_layout.pdf_import.grid_segmenter import GridSegmenter
from cewe_layout.pdf_import.tree_segmenter import TreeSegmenter


def test_different_threshold_c_values():
    """Test various threshold_c values to handle analog scan variations."""
    print("\n" + "=" * 80)
    print("Testing different threshold_c values on composite_page1.jpeg")
    print("=" * 80)
    
    # Load the test image
    test_image_path = Path(__file__).parent / "composite_page1.jpeg"
    
    if not test_image_path.exists():
        print(f"❌ Test image not found: {test_image_path}")
        return
    
    with open(test_image_path, 'rb') as f:
        image_data = f.read()
    
    print(f"✅ Loaded test image: {test_image_path.name} ({len(image_data)} bytes)")
    
    # Test different threshold_c values
    # Lower = more sensitive to brightness changes (may split background)
    # Higher = more tolerant (better for varying black levels)
    threshold_values = [5, 10, 15, 20, 25, 30, 35, 40]
    
    results = []
    
    for threshold_c in threshold_values:
        print(f"\n{'─' * 80}")
        print(f"Testing threshold_c = {threshold_c}")
        print(f"{'─' * 80}")
        
        segments = segment_composite_image(
            image_data,
            'jpeg',
            min_area=50000,
            kernel_size=5,
            iterations=2,
            threshold_c=threshold_c,
            verbose=True
        )
        
        photo_count = len(segments)
        results.append((threshold_c, photo_count))
        
        print(f"  Result: {photo_count} photos detected")
        
        if segments:
            for i, seg in enumerate(segments):
                print(f"    Photo {i+1}: {seg['width']:.0f}x{seg['height']:.0f} at ({seg['left']:.0f}, {seg['top']:.0f})")
    
    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY - threshold_c vs photo count:")
    print(f"{'=' * 80}")
    for threshold_c, count in results:
        print(f"  threshold_c={threshold_c:2d} → {count} photos")
    print()


def test_different_morphological_params():
    """Test various kernel_size and iterations combinations."""
    print("\n" + "=" * 80)
    print("Testing different morphological parameters on composite_page1.jpeg")
    print("=" * 80)
    
    # Load the test image
    test_image_path = Path(__file__).parent / "composite_page1.jpeg"
    
    if not test_image_path.exists():
        print(f"❌ Test image not found: {test_image_path}")
        return
    
    with open(test_image_path, 'rb') as f:
        image_data = f.read()
    
    print(f"✅ Loaded test image: {test_image_path.name}")
    
    # Test different combinations with fixed threshold_c=20
    param_combinations = [
        # (kernel_size, iterations)
        (1, 1),
        (3, 1),
        (3, 2),
        (5, 1),
        (5, 2),
        (5, 3),
        (7, 2),
        (7, 3),
    ]
    
    threshold_c = 20  # Good default for analog scans
    
    results = []
    
    for kernel_size, iterations in param_combinations:
        print(f"\n{'─' * 80}")
        print(f"Testing kernel_size={kernel_size}, iterations={iterations}, threshold_c={threshold_c}")
        print(f"{'─' * 80}")
        
        segments = segment_composite_image(
            image_data,
            'jpeg',
            min_area=50000,
            kernel_size=kernel_size,
            iterations=iterations,
            threshold_c=threshold_c,
            verbose=False
        )
        
        photo_count = len(segments)
        results.append((kernel_size, iterations, photo_count))
        
        print(f"  Result: {photo_count} photos detected")
    
    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY - morphological params vs photo count:")
    print(f"{'=' * 80}")
    for kernel_size, iterations, count in results:
        print(f"  kernel={kernel_size}, iter={iterations} → {count} photos")
    print()


def test_segmenter_for_target_count():
    """Test MorphologicalSegmenter's ability to find parameters for target count."""
    print("\n" + "=" * 80)
    print("Testing MorphologicalSegmenter.segment_for_count() on composite_page1.jpeg")
    print("=" * 80)
    
    # Load the test image
    test_image_path = Path(__file__).parent / "composite_page1.jpeg"
    
    if not test_image_path.exists():
        print(f"❌ Test image not found: {test_image_path}")
        return
    
    with open(test_image_path, 'rb') as f:
        image_data = f.read()
    
    print(f"✅ Loaded test image: {test_image_path.name}")
    
    # Try to segment for different target counts
    target_counts = [1, 3, 5, 7, 9]
    
    for threshold_c in [10, 20, 30]:
        print(f"\n{'═' * 80}")
        print(f"Testing with threshold_c = {threshold_c}")
        print(f"{'═' * 80}")
        
        segmenter = MorphologicalSegmenter(threshold_c=threshold_c)
        
        for target_count in target_counts:
            print(f"\n  Target: {target_count} photos")
            print(f"  {'-' * 76}")
            
            segments = segmenter.segment_for_count(
                image_data,
                'jpeg',
                target_count=target_count,
                verbose=True
            )
            
            if segments:
                print(f"  ✅ Success: Found {len(segments)} photos")
            else:
                print(f"  ❌ Failed: Could not achieve target of {target_count} photos")
    
    print()


if __name__ == '__main__':
    # Run all tests
    test_different_threshold_c_values()
    test_different_morphological_params()
    test_segmenter_for_target_count()
    
    # Also test grid and tree segmenters
    print("\n" + "=" * 80)
    print("Testing GridSegmenter for 7 photos")
    print("=" * 80)
    
    test_image_path = Path(__file__).parent / "composite_page1.jpeg"
    with open(test_image_path, 'rb') as f:
        image_data = f.read()
    
    grid_segmenter = GridSegmenter()
    result = grid_segmenter.segment_for_count(image_data, 'jpeg', target_count=7, verbose=True)
    if result:
        print(f"✅ Grid segmenter found {len(result)} photos")
    else:
        print(f"❌ Grid segmenter could not find 7 photos")
    
    print("\n" + "=" * 80)
    print("Testing TreeSegmenter for 7 photos")
    print("=" * 80)
    
    tree_segmenter = TreeSegmenter()
    result = tree_segmenter.segment_for_count(image_data, 'jpeg', target_count=7, verbose=True)
    if result:
        print(f"✅ Tree segmenter found {len(result)} photos")
    else:
        print(f"❌ Tree segmenter could not find 7 photos")
    
    print("\n" + "=" * 80)
    print("All segmentation parameter tests completed!")
    print("=" * 80)
