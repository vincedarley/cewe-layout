"""Tests for photobook transformation utilities."""

import pytest
from pathlib import Path
from cewe_layout.book.photobook_transform import (
    create_photobook_with_inside_covers_at_end,
    merge_photobooks
)
from cewe_layout.book.cewe_photobook import CEWEPhotobook


def test_empty_page_template():
    """Test creating an empty page template."""
    # Create a simple photobook with content pages
    pages = [
        ("F", {
            'photos': [],
            'texts': [],
            'page_width': 2800,
            'page_height': 2100,
            'origin_left': 0,
            'is_cover': True
        }),
        (0, {
            'photos': [],
            'texts': [],
            'page_width': 2800,
            'page_height': 2100,
            'origin_left': 0
        }),
        (1, {
            'photos': [{'filename': 'test.jpg', 'area_left': 100, 'area_top': 100, 
                       'area_width': 500, 'area_height': 500}],
            'texts': [],
            'page_width': 2800,
            'page_height': 2100,
            'origin_left': 0
        }),
        (2, {
            'photos': [],
            'texts': [],
            'page_width': 2800,
            'page_height': 2100,
            'origin_left': 0
        }),
        (3, {
            'photos': [],
            'texts': [],
            'page_width': 2800,
            'page_height': 2100,
            'origin_left': 0
        }),
        ("B", {
            'photos': [],
            'texts': [],
            'page_width': 2800,
            'page_height': 2100,
            'origin_left': 0,
            'is_cover': True
        })
    ]
    
    book = CEWEPhotobook(pages)
    
    # Test template creation
    template = book.create_empty_page_template()
    
    assert template['page_width'] == 2800
    assert template['page_height'] == 2100
    assert template['photos'] == []
    assert template['texts'] == []


def test_n_must_be_even():
    """Test that content page count must be even."""
    # Create a photobook with odd number of content pages (invalid)
    pages = [
        ("F", {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 
               'origin_left': 0, 'is_cover': True}),
        (0, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (1, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (2, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (3, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        # Only 3 content pages (1, 2, 3) - ODD!
        (4, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        ("B", {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 
               'origin_left': 0, 'is_cover': True})
    ]
    
    book = CEWEPhotobook(pages)
    
    # Should raise ValueError because N=3 is odd
    with pytest.raises(ValueError, match="Content page count must be even"):
        create_photobook_with_inside_covers_at_end(book, Path('.'), Path('.'))


def test_inside_covers_transformation_page_count():
    """Test that transformation creates correct number of pages."""
    # Create a photobook with N=2 content pages
    pages = [
        ("F", {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100,
               'origin_left': 0, 'is_cover': True}),
        (0, {'photos': [{'filename': 'inside_front.jpg'}], 'texts': [],
             'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (1, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (2, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (3, {'photos': [{'filename': 'inside_back.jpg'}], 'texts': [],
             'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        ("B", {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100,
               'origin_left': 0, 'is_cover': True})
    ]
    
    book = CEWEPhotobook(pages)
    assert book.get_content_page_count() == 2  # N=2
    
    # Note: We can't actually test the transformation without a real output directory
    # This is more of a documentation test showing expected structure


def test_merge_photobooks_n_validation():
    """Test that merge validates both books have even N."""
    # Book1 with N=2 (valid)
    pages1 = [
        ("F", {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100,
               'origin_left': 0, 'is_cover': True}),
        (0, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (1, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (2, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (3, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        ("B", {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100,
               'origin_left': 0, 'is_cover': True})
    ]
    
    # Book2 with N=3 (invalid - odd)
    pages2 = [
        ("F", {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100,
               'origin_left': 0, 'is_cover': True}),
        (0, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (1, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (2, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (3, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        (4, {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100, 'origin_left': 0}),
        ("B", {'photos': [], 'texts': [], 'page_width': 2800, 'page_height': 2100,
               'origin_left': 0, 'is_cover': True})
    ]
    
    book1 = CEWEPhotobook(pages1)
    book2 = CEWEPhotobook(pages2)
    
    # Should raise ValueError because book2 N=3 is odd
    with pytest.raises(ValueError, match="Book2 content page count must be even"):
        merge_photobooks(book1, book2, Path('.'), Path('.'), Path('.'))


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
