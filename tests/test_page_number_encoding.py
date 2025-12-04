"""Test page number encoding in filenames."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.gui import (
    extract_page_number_from_filename,
    extract_metadata_from_filename,
    encode_metadata_in_filename
)


def test_extract_page_number_simple():
    """Test extracting page number from simple filename."""
    base, page = extract_page_number_from_filename('photo-pg10.jpg')
    assert base == 'photo.jpg'
    assert page == 10


def test_extract_page_number_safecontainer():
    """Test extracting page number from safecontainer filename."""
    base, page = extract_page_number_from_filename('safecontainer:/photo-pg5.jpg')
    assert base == 'safecontainer:/photo.jpg'
    assert page == 5


def test_extract_page_number_none():
    """Test filename without page number."""
    base, page = extract_page_number_from_filename('photo.jpg')
    assert base == 'photo.jpg'
    assert page is None


def test_extract_metadata_both():
    """Test extracting both size and page number."""
    base, size, page = extract_metadata_from_filename('photo-sz2.5-pg10.jpg')
    assert base == 'photo.jpg'
    assert size == 2.5
    assert page == 10


def test_extract_metadata_alternate_order():
    """Test extracting with alternate order (pg then sz)."""
    base, size, page = extract_metadata_from_filename('photo-pg10-sz2.5.jpg')
    assert base == 'photo.jpg'
    assert size == 2.5
    assert page == 10


def test_extract_metadata_only_size():
    """Test extracting when only size is present."""
    base, size, page = extract_metadata_from_filename('photo-sz3.0.jpg')
    assert base == 'photo.jpg'
    assert size == 3.0
    assert page is None


def test_extract_metadata_only_page():
    """Test extracting when only page is present."""
    base, size, page = extract_metadata_from_filename('photo-pg15.jpg')
    assert base == 'photo.jpg'
    assert size is None
    assert page == 15


def test_extract_metadata_neither():
    """Test extracting when neither is present."""
    base, size, page = extract_metadata_from_filename('photo.jpg')
    assert base == 'photo.jpg'
    assert size is None
    assert page is None


def test_extract_metadata_safecontainer():
    """Test extracting from safecontainer with both."""
    base, size, page = extract_metadata_from_filename('safecontainer:/exp1-photo-sz1.5-pg20.jpg')
    assert base == 'safecontainer:/exp1-photo.jpg'
    assert size == 1.5
    assert page == 20


def test_encode_both():
    """Test encoding both size and page."""
    result = encode_metadata_in_filename('photo.jpg', 2.5, 10)
    assert result == 'photo-sz2.5-pg10.jpg'


def test_encode_only_size():
    """Test encoding only size."""
    result = encode_metadata_in_filename('photo.jpg', 3.0, None)
    assert result == 'photo-sz3.jpg'


def test_encode_only_page():
    """Test encoding only page."""
    result = encode_metadata_in_filename('photo.jpg', None, 10)
    assert result == 'photo-pg10.jpg'


def test_encode_neither():
    """Test encoding when neither provided (returns unchanged)."""
    result = encode_metadata_in_filename('photo.jpg', None, None)
    assert result == 'photo.jpg'


def test_encode_replaces_existing_size():
    """Test that encoding replaces existing size."""
    result = encode_metadata_in_filename('photo-sz1.0.jpg', 2.5, 10)
    assert result == 'photo-sz2.5-pg10.jpg'


def test_encode_replaces_existing_page():
    """Test that encoding replaces existing page."""
    result = encode_metadata_in_filename('photo-pg5.jpg', 2.5, 10)
    assert result == 'photo-sz2.5-pg10.jpg'


def test_encode_replaces_both():
    """Test that encoding replaces both existing values."""
    result = encode_metadata_in_filename('photo-sz1.0-pg5.jpg', 2.5, 10)
    assert result == 'photo-sz2.5-pg10.jpg'


def test_encode_preserves_existing_size():
    """Test that encoding preserves existing size when not provided."""
    result = encode_metadata_in_filename('photo-sz3.0.jpg', None, 10)
    assert result == 'photo-sz3-pg10.jpg'


def test_encode_preserves_existing_page():
    """Test that encoding preserves existing page when not provided."""
    result = encode_metadata_in_filename('photo-pg5.jpg', 2.5, None)
    assert result == 'photo-sz2.5-pg5.jpg'


def test_encode_safecontainer():
    """Test encoding with safecontainer prefix."""
    result = encode_metadata_in_filename('safecontainer:/photo.jpg', 1.5, 20)
    assert result == 'safecontainer:/photo-sz1.5-pg20.jpg'


def test_page_move_scenario():
    """Test photo moving from one page to another (page number changes)."""
    # Photo initially on page 5
    filename = 'photo-sz2.5-pg5.jpg'
    
    # Extract base to verify
    base, size, old_page = extract_metadata_from_filename(filename)
    assert base == 'photo.jpg'
    assert size == 2.5
    assert old_page == 5
    
    # Move to page 10, preserve size
    new_filename = encode_metadata_in_filename(filename, size, 10)
    assert new_filename == 'photo-sz2.5-pg10.jpg'
    
    # Verify extraction
    base, size, new_page = extract_metadata_from_filename(new_filename)
    assert base == 'photo.jpg'
    assert size == 2.5
    assert new_page == 10


def test_size_change_preserves_page():
    """Test changing size while preserving page number."""
    filename = 'photo-sz1.0-pg5.jpg'
    
    # Change size to 3.0, preserve page
    base, _, page = extract_metadata_from_filename(filename)
    new_filename = encode_metadata_in_filename(filename, 3.0, page)
    assert new_filename == 'photo-sz3-pg5.jpg'


def test_roundtrip():
    """Test encode-decode roundtrip preserves values."""
    original_base = 'photo.jpg'
    size = 2.5
    page = 10
    
    encoded = encode_metadata_in_filename(original_base, size, page)
    decoded_base, decoded_size, decoded_page = extract_metadata_from_filename(encoded)
    
    assert decoded_base == original_base
    assert decoded_size == size
    assert decoded_page == page


def test_complex_filename():
    """Test with complex real-world filename."""
    filename = 'safecontainer:/exp1-2022-07-23-p006-sz1.5-pg38.jpeg'
    base, size, page = extract_metadata_from_filename(filename)
    
    assert base == 'safecontainer:/exp1-2022-07-23-p006.jpeg'
    assert size == 1.5
    assert page == 38
    
    # Update to new page
    new_filename = encode_metadata_in_filename(filename, size, 39)
    assert new_filename == 'safecontainer:/exp1-2022-07-23-p006-sz1.5-pg39.jpeg'


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
