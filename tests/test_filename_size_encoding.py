"""Test preferred size encoding/decoding in filenames."""
import sys
from pathlib import Path

# Add parent directory to path to import the module
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.gui import extract_preferred_size_from_filename, encode_preferred_size_in_filename


def test_extract_simple():
    filename = "photo-sz3.45.jpg"
    base, size = extract_preferred_size_from_filename(filename)
    assert base == "photo.jpg", f"Expected 'photo.jpg', got '{base}'"
    assert size == 3.45, f"Expected 3.45, got {size}"
    print("✓ test_extract_simple")


def test_extract_without_size():
    filename = "photo.jpg"
    base, size = extract_preferred_size_from_filename(filename)
    assert base == "photo.jpg", f"Expected 'photo.jpg', got '{base}'"
    assert size is None, f"Expected None, got {size}"
    print("✓ test_extract_without_size")


def test_extract_safecontainer():
    filename = "safecontainer:/photo-sz1.5.jpeg"
    base, size = extract_preferred_size_from_filename(filename)
    assert base == "safecontainer:/photo.jpeg", f"Expected 'safecontainer:/photo.jpeg', got '{base}'"
    assert size == 1.5, f"Expected 1.5, got {size}"
    print("✓ test_extract_safecontainer")


def test_extract_long_filename():
    filename = "Test-2022-07-17-p002-sz2.35.jpeg"
    base, size = extract_preferred_size_from_filename(filename)
    assert base == "Test-2022-07-17-p002.jpeg", f"Expected 'Test-2022-07-17-p002.jpeg', got '{base}'"
    assert size == 2.35, f"Expected 2.35, got {size}"
    print("✓ test_extract_long_filename")


def test_encode_simple():
    filename = "photo.jpg"
    result = encode_preferred_size_in_filename(filename, 3.45)
    assert result == "photo-sz3.45.jpg", f"Expected 'photo-sz3.45.jpg', got '{result}'"
    print("✓ test_encode_simple")


def test_encode_safecontainer():
    filename = "safecontainer:/photo.jpeg"
    result = encode_preferred_size_in_filename(filename, 1.5)
    assert result == "safecontainer:/photo-sz1.5.jpeg", f"Expected 'safecontainer:/photo-sz1.5.jpeg', got '{result}'"
    print("✓ test_encode_safecontainer")


def test_encode_replace_existing():
    filename = "photo-sz1.0.jpg"
    result = encode_preferred_size_in_filename(filename, 3.45)
    assert result == "photo-sz3.45.jpg", f"Expected 'photo-sz3.45.jpg', got '{result}'"
    print("✓ test_encode_replace_existing")


def test_encode_long_filename():
    filename = "Test-2022-07-17-p002.jpeg"
    result = encode_preferred_size_in_filename(filename, 2.35)
    assert result == "Test-2022-07-17-p002-sz2.35.jpeg", f"Expected 'Test-2022-07-17-p002-sz2.35.jpeg', got '{result}'"
    print("✓ test_encode_long_filename")


def test_encode_long_filename_with_existing():
    filename = "Test-2022-07-17-p002-sz1.0.jpeg"
    result = encode_preferred_size_in_filename(filename, 2.35)
    assert result == "Test-2022-07-17-p002-sz2.35.jpeg", f"Expected 'Test-2022-07-17-p002-sz2.35.jpeg', got '{result}'"
    print("✓ test_encode_long_filename_with_existing")


def test_roundtrip():
    original = "Test-2022-07-17-p002.jpeg"
    size = 2.35
    encoded = encode_preferred_size_in_filename(original, size)
    decoded_name, decoded_size = extract_preferred_size_from_filename(encoded)
    assert decoded_name == original, f"Roundtrip failed: expected '{original}', got '{decoded_name}'"
    assert decoded_size == size, f"Roundtrip size failed: expected {size}, got {decoded_size}"
    print(f"✓ test_roundtrip: {original} -> {encoded} -> {decoded_name}, {decoded_size}")


if __name__ == '__main__':
    print("Testing filename size encoding/decoding...\n")
    try:
        test_extract_simple()
        test_extract_without_size()
        test_extract_safecontainer()
        test_extract_long_filename()
        test_encode_simple()
        test_encode_safecontainer()
        test_encode_replace_existing()
        test_encode_long_filename()
        test_encode_long_filename_with_existing()
        test_roundtrip()
        print("\n✅ All tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)

    """Test extracting preferred size from filenames."""
    
    def test_simple_filename_with_size(self):
        filename = "photo-sz3.45.jpg"
        base, size = extract_preferred_size_from_filename(filename)
        assert base == "photo.jpg"
        assert size == 3.45
    
    def test_simple_filename_without_size(self):
        filename = "photo.jpg"
        base, size = extract_preferred_size_from_filename(filename)
        assert base == "photo.jpg"
        assert size is None
    
    def test_safecontainer_with_size(self):
        filename = "safecontainer:/photo-sz1.5.jpeg"
        base, size = extract_preferred_size_from_filename(filename)
        assert base == "safecontainer:/photo.jpeg"
        assert size == 1.5
    
    def test_safecontainer_without_size(self):
        filename = "safecontainer:/photo.jpeg"
        base, size = extract_preferred_size_from_filename(filename)
        assert base == "safecontainer:/photo.jpeg"
        assert size is None
    
    def test_integer_size(self):
        filename = "photo-sz6.jpeg"
        base, size = extract_preferred_size_from_filename(filename)
        assert base == "photo.jpeg"
        assert size == 6.0
    
    def test_long_filename_with_size(self):
        filename = "Test-2022-07-17-p002-sz2.35.jpeg"
        base, size = extract_preferred_size_from_filename(filename)
        assert base == "Test-2022-07-17-p002.jpeg"
        assert size == 2.35
    
    def test_none_filename(self):
        base, size = extract_preferred_size_from_filename(None)
        assert base is None
        assert size is None
    
    def test_empty_filename(self):
        base, size = extract_preferred_size_from_filename("")
        assert base == ""
        assert size is None


class TestEncodePreferredSize:
    """Test encoding preferred size into filenames."""
    
    def test_simple_filename(self):
        filename = "photo.jpg"
        result = encode_preferred_size_in_filename(filename, 3.45)
        assert result == "photo-sz3.45.jpg"
    
    def test_safecontainer_filename(self):
        filename = "safecontainer:/photo.jpeg"
        result = encode_preferred_size_in_filename(filename, 1.5)
        assert result == "safecontainer:/photo-sz1.5.jpeg"
    
    def test_replace_existing_size(self):
        filename = "photo-sz1.0.jpg"
        result = encode_preferred_size_in_filename(filename, 3.45)
        assert result == "photo-sz3.45.jpg"
    
    def test_integer_size(self):
        filename = "photo.jpg"
        result = encode_preferred_size_in_filename(filename, 6.0)
        assert result == "photo-sz6.jpg"
    
    def test_trailing_zeros_removed(self):
        filename = "photo.jpg"
        result = encode_preferred_size_in_filename(filename, 1.00)
        assert result == "photo-sz1.jpg"
    
    def test_one_decimal_place(self):
        filename = "photo.jpg"
        result = encode_preferred_size_in_filename(filename, 1.5)
        assert result == "photo-sz1.5.jpg"
    
    def test_long_filename(self):
        filename = "Test-2022-07-17-p002.jpeg"
        result = encode_preferred_size_in_filename(filename, 2.35)
        assert result == "Test-2022-07-17-p002-sz2.35.jpeg"
    
    def test_replace_in_long_filename(self):
        filename = "Test-2022-07-17-p002-sz1.0.jpeg"
        result = encode_preferred_size_in_filename(filename, 2.35)
        assert result == "Test-2022-07-17-p002-sz2.35.jpeg"
    
    def test_none_filename(self):
        result = encode_preferred_size_in_filename(None, 3.45)
        assert result is None
    
    def test_empty_filename(self):
        result = encode_preferred_size_in_filename("", 3.45)
        assert result == ""


class TestRoundTrip:
    """Test that encode/decode are inverses."""
    
    def test_roundtrip_simple(self):
        original = "photo.jpg"
        size = 3.45
        encoded = encode_preferred_size_in_filename(original, size)
        decoded_name, decoded_size = extract_preferred_size_from_filename(encoded)
        assert decoded_name == original
        assert decoded_size == size
    
    def test_roundtrip_safecontainer(self):
        original = "safecontainer:/Test-2022-07-17-p002.jpeg"
        size = 2.35
        encoded = encode_preferred_size_in_filename(original, size)
        decoded_name, decoded_size = extract_preferred_size_from_filename(encoded)
        assert decoded_name == original
        assert decoded_size == size
    
    def test_roundtrip_integer(self):
        original = "photo.jpg"
        size = 6.0
        encoded = encode_preferred_size_in_filename(original, size)
        decoded_name, decoded_size = extract_preferred_size_from_filename(encoded)
        assert decoded_name == original
        assert decoded_size == size
    
    def test_complex_filename_with_underscores_and_uuid(self):
        """Test with real-world complex filename containing underscores, dots, and UUID"""
        original = "gvim81qu_1_xb2487993-1237-48cb-a20f-12ff06f3545d_2fl0_2f001_full.jpg.jpeg"
        size = 1.25
        
        # Encode
        encoded = encode_preferred_size_in_filename(original, size)
        assert encoded == "gvim81qu_1_xb2487993-1237-48cb-a20f-12ff06f3545d_2fl0_2f001_full.jpg-sz1.25.jpeg"
        
        # Decode
        decoded_name, decoded_size = extract_preferred_size_from_filename(encoded)
        assert decoded_name == original
        assert decoded_size == 1.25
        
        # Roundtrip
        re_encoded = encode_preferred_size_in_filename(decoded_name, decoded_size)
        assert re_encoded == encoded
    
    def test_complex_filename_with_dashes_and_rating(self):
        """Test with real-world filename containing dashes and rating suffix"""
        original = "exp1-2022-07-22-p001-4star.jpeg"
        size = 2.5
        
        # Encode
        encoded = encode_preferred_size_in_filename(original, size)
        assert encoded == "exp1-2022-07-22-p001-4star-sz2.5.jpeg"
        
        # Decode
        decoded_name, decoded_size = extract_preferred_size_from_filename(encoded)
        assert decoded_name == original
        assert decoded_size == 2.5
        
        # Roundtrip
        re_encoded = encode_preferred_size_in_filename(decoded_name, decoded_size)
        assert re_encoded == encoded
    
    def test_complex_filename_with_safecontainer(self):
        """Test complex filename with safecontainer prefix"""
        original = "safecontainer:/gvim81qu_1_xb2487993-1237-48cb-a20f-12ff06f3545d_2fl0_2f001_full.jpg.jpeg"
        size = 0.75
        
        # Encode
        encoded = encode_preferred_size_in_filename(original, size)
        assert encoded == "safecontainer:/gvim81qu_1_xb2487993-1237-48cb-a20f-12ff06f3545d_2fl0_2f001_full.jpg-sz0.75.jpeg"
        
        # Decode
        decoded_name, decoded_size = extract_preferred_size_from_filename(encoded)
        assert decoded_name == original
        assert decoded_size == 0.75
        
        # Roundtrip
        re_encoded = encode_preferred_size_in_filename(decoded_name, decoded_size)
        assert re_encoded == encoded


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
