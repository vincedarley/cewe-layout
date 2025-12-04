"""Test that saving photos with preferred sizes works correctly."""
import sys
from pathlib import Path
import tempfile
import shutil
import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.writer import update_page_layout
from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.gui import extract_metadata_from_filename


def test_save_photos_with_sz_suffix():
    """Test that photos with -sz suffix in filename are matched correctly during save."""
    
    # Create a minimal MCF file for testing
    mcf_content = """<?xml version="1.0" encoding="utf-8"?>
<fotobook>
  <page pagenr="2" type="normalpage">
    <bundlesize width="4200" height="2970"/>
    <area areatype="imagearea">
      <position left="100" top="100" width="1000" height="1000"/>
      <image filename="safecontainer:/test-photo.jpg" backgroundposition="1">
        <cutout left="0.0" top="0.0" scale="1.0"/>
      </image>
    </area>
  </page>
</fotobook>
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mcf_path = tmpdir / "test.mcf"
        mcf_path.write_text(mcf_content)
        
        # Photos list has -sz suffix in filename (as it would after loading and setting size)
        photos = [
            {
                'filename': 'safecontainer:/test-photo-sz2.5.jpg',
                'area_left': 100.0,
                'area_top': 100.0,
                'area_width': 1000.0,
                'area_height': 1000.0,
                'image_width': 2000,
                'image_height': 1500,
            }
        ]
        
        # Rename map: XML base name -> photo filename with -sz
        rename_map = {
            'safecontainer:/test-photo.jpg': 'safecontainer:/test-photo-sz2.5.jpg'
        }
        
        # Update the page
        result = update_page_layout(
            str(mcf_path),
            pageno=2,  # Right page of spread
            photos=photos,
            texts=[],
            make_backup=False,
            new_photos=[],
            deleted_photos=[],
            rename_map=rename_map,
            validate_files=False  # Don't check file existence in test
        )
        
        # Should have modified the photo
        assert result['modified_photos'] == 1, f"Expected 1 modified photo, got {result['modified_photos']}"
        assert result['added_photos'] == 0, f"Expected 0 added photos, got {result['added_photos']}"
        assert len(result['warnings']) == 0, f"Got unexpected warnings: {result['warnings']}"
        
        # Verify XML was updated with new filename
        tree = etree.parse(str(mcf_path))
        image = tree.find('.//image')
        assert image is not None, "Image element not found"
        assert image.get('filename') == 'safecontainer:/test-photo-sz2.5.jpg', \
            f"Expected filename to be updated to test-photo-sz2.5.jpg, got {image.get('filename')}"
        
        print("✓ Photo with -sz suffix matched and saved correctly")
        print(f"  Modified: {result['modified_photos']}, Added: {result['added_photos']}")
        print(f"  Warnings: {result['warnings']}")


def test_save_multiple_photos_with_different_sizes():
    """Test saving multiple photos, each with different preferred sizes."""
    
    # Page 2 is right side, so areas must have center_x >= 2100 (half of 4200)
    mcf_content = """<?xml version="1.0" encoding="utf-8"?>
<fotobook>
  <page pagenr="2" type="normalpage">
    <bundlesize width="4200" height="2970"/>
    <area areatype="imagearea">
      <position left="2200" top="100" width="800" height="600"/>
      <image filename="safecontainer:/photo1.jpg" backgroundposition="1">
        <cutout left="0.0" top="0.0" scale="1.0"/>
      </image>
    </area>
    <area areatype="imagearea">
      <position left="3000" top="100" width="800" height="600"/>
      <image filename="safecontainer:/photo2.jpg" backgroundposition="1">
        <cutout left="0.0" top="0.0" scale="1.0"/>
      </image>
    </area>
    <area areatype="imagearea">
      <position left="2200" top="800" width="600" height="800"/>
      <image filename="safecontainer:/photo3.jpg" backgroundposition="1">
        <cutout left="0.0" top="0.0" scale="1.0"/>
      </image>
    </area>
  </page>
</fotobook>
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mcf_path = tmpdir / "test.mcf"
        mcf_path.write_text(mcf_content)
        
        # Photos with different preferred sizes (all on right page)
        photos = [
            {
                'filename': 'safecontainer:/photo1-sz0.5.jpg',
                'area_left': 2200.0,
                'area_top': 100.0,
                'area_width': 800.0,
                'area_height': 600.0,
                'image_width': 3000,
                'image_height': 2000,
            },
            {
                'filename': 'safecontainer:/photo2-sz3.0.jpg',
                'area_left': 3000.0,
                'area_top': 100.0,
                'area_width': 800.0,
                'area_height': 600.0,
                'image_width': 4000,
                'image_height': 3000,
            },
            {
                'filename': 'safecontainer:/photo3-sz1.2.jpg',
                'area_left': 2200.0,
                'area_top': 800.0,
                'area_width': 600.0,
                'area_height': 800.0,
                'image_width': 2000,
                'image_height': 3000,
            },
        ]
        
        rename_map = {
            'safecontainer:/photo1.jpg': 'safecontainer:/photo1-sz0.5.jpg',
            'safecontainer:/photo2.jpg': 'safecontainer:/photo2-sz3.0.jpg',
            'safecontainer:/photo3.jpg': 'safecontainer:/photo3-sz1.2.jpg',
        }
        
        result = update_page_layout(
            str(mcf_path),
            pageno=3,  # Page 3 is the right side of the spread with pagenr=2
            photos=photos,
            texts=[],
            make_backup=False,
            rename_map=rename_map,
            validate_files=False  # Don't check file existence in test
        )
        
        assert result['modified_photos'] == 3, f"Expected 3 modified photos, got {result['modified_photos']}"
        assert len(result['warnings']) == 0, f"Got unexpected warnings: {result['warnings']}"
        
        # Verify all filenames were updated
        tree = etree.parse(str(mcf_path))
        images = tree.findall('.//image')
        assert len(images) == 3, f"Expected 3 images, found {len(images)}"
        
        filenames = {img.get('filename') for img in images}
        expected = {
            'safecontainer:/photo1-sz0.5.jpg',
            'safecontainer:/photo2-sz3.0.jpg',
            'safecontainer:/photo3-sz1.2.jpg',
        }
        assert filenames == expected, f"Filenames mismatch. Expected {expected}, got {filenames}"
        
        print("✓ Multiple photos with different sizes saved correctly")
        print(f"  Modified: {result['modified_photos']}")
        print(f"  Filenames: {filenames}")


def test_validation_detects_count_mismatch():
    """Test that an exception is raised when trying to add photo not in new_photos list."""
    
    # MCF with 2 photos
    mcf_content = """<?xml version="1.0" encoding="utf-8"?>
<fotobook>
  <page pagenr="2" type="normalpage">
    <bundlesize width="4200" height="2970"/>
    <area areatype="imagearea">
      <position left="2200" top="100" width="800" height="600"/>
      <image filename="safecontainer:/photo1.jpg" backgroundposition="1">
        <cutout left="0.0" top="0.0" scale="1.0"/>
      </image>
    </area>
    <area areatype="imagearea">
      <position left="3000" top="100" width="800" height="600"/>
      <image filename="safecontainer:/photo2.jpg" backgroundposition="1">
        <cutout left="0.0" top="0.0" scale="1.0"/>
      </image>
    </area>
  </page>
</fotobook>
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mcf_path = tmpdir / "test.mcf"
        mcf_path.write_text(mcf_content)
        
        # Try to save 3 photos but XML only has 2
        photos = [
            {
                'filename': 'safecontainer:/photo1-sz1.0.jpg',
                'area_left': 2200.0,
                'area_top': 100.0,
                'area_width': 800.0,
                'area_height': 600.0,
                'image_width': 3000,
                'image_height': 2000,
            },
            {
                'filename': 'safecontainer:/photo2-sz1.0.jpg',
                'area_left': 3000.0,
                'area_top': 100.0,
                'area_width': 800.0,
                'area_height': 600.0,
                'image_width': 4000,
                'image_height': 3000,
            },
            {
                'filename': 'safecontainer:/photo3-sz1.0.jpg',
                'area_left': 2200.0,
                'area_top': 800.0,
                'area_width': 600.0,
                'area_height': 800.0,
                'image_width': 2000,
                'image_height': 3000,
            },
        ]
        
        rename_map = {
            'safecontainer:/photo1.jpg': 'safecontainer:/photo1-sz1.0.jpg',
            'safecontainer:/photo2.jpg': 'safecontainer:/photo2-sz1.0.jpg',
        }
        
        # Should raise exception immediately - photo3 not in XML and not in new_photos
        with pytest.raises(ValueError, match=r"not in new_photos list"):
            update_page_layout(
                str(mcf_path),
                pageno=3,
                photos=photos,
                texts=[],
                make_backup=False,
                rename_map=rename_map,
                validate_files=False
            )
        
        print("✓ Exception raised when trying to add unlisted photo")


def test_validation_detects_missing_files():
    """Test that validation detects when photo files don't exist on disk."""
    
    mcf_content = """<?xml version="1.0" encoding="utf-8"?>
<fotobook>
  <page pagenr="2" type="normalpage">
    <bundlesize width="4200" height="2970"/>
    <area areatype="imagearea">
      <position left="2200" top="100" width="800" height="600"/>
      <image filename="safecontainer:/photo1.jpg" backgroundposition="1">
        <cutout left="0.0" top="0.0" scale="1.0"/>
      </image>
    </area>
  </page>
</fotobook>
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mcf_path = tmpdir / "test.mcf"
        mcf_path.write_text(mcf_content)
        
        photos = [
            {
                'filename': 'safecontainer:/photo1-sz1.0.jpg',
                'area_left': 2200.0,
                'area_top': 100.0,
                'area_width': 800.0,
                'area_height': 600.0,
                'image_width': 3000,
                'image_height': 2000,
            },
        ]
        
        rename_map = {
            'safecontainer:/photo1.jpg': 'safecontainer:/photo1-sz1.0.jpg',
        }
        
        # Enable file validation but file doesn't exist
        result = update_page_layout(
            str(mcf_path),
            pageno=3,
            photos=photos,
            texts=[],
            make_backup=False,
            rename_map=rename_map,
            validate_files=True  # Enable file existence checking
        )
        
        # Should detect missing file
        assert len(result['warnings']) > 0, "Expected validation warnings"
        assert any('Photo file not found' in w for w in result['warnings']), \
            f"Expected missing file warning, got: {result['warnings']}"
        assert any('photo1-sz1.0.jpg' in w for w in result['warnings']), \
            f"Expected filename in warning, got: {result['warnings']}"
        
        print("✓ Validation correctly detected missing photo file")
        print(f"  Warnings: {result['warnings']}")


def test_save_encodes_page_numbers():
    """Test that saving encodes page numbers into filenames."""
    
    mcf_content = """<?xml version="1.0" encoding="utf-8"?>
<fotobook>
  <page pagenr="2" type="normalpage">
    <bundlesize width="4200" height="2970"/>
    <area areatype="imagearea">
      <position left="2200" top="100" width="800" height="600"/>
      <image filename="safecontainer:/photo1.jpg" backgroundposition="1">
        <cutout left="0.0" top="0.0" scale="1.0"/>
      </image>
    </area>
  </page>
</fotobook>
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mcf_path = tmpdir / "test.mcf"
        mcf_path.write_text(mcf_content)
        
        # Photo with size and page will be encoded
        photos = [
            {
                'filename': 'safecontainer:/photo1-sz2.5-pg3.jpg',
                'area_left': 2200.0,
                'area_top': 100.0,
                'area_width': 800.0,
                'area_height': 600.0,
                'image_width': 3000,
                'image_height': 2000,
            },
        ]
        
        rename_map = {
            'safecontainer:/photo1.jpg': 'safecontainer:/photo1-sz2.5-pg3.jpg',
        }
        
        result = update_page_layout(
            str(mcf_path),
            pageno=3,
            photos=photos,
            texts=[],
            make_backup=False,
            rename_map=rename_map,
            validate_files=False
        )
        
        assert result['modified_photos'] == 1, f"Expected 1 modified photo, got {result['modified_photos']}"
        
        # Verify XML has the new filename with both -sz and -pg
        tree = etree.parse(str(mcf_path))
        image = tree.find('.//image')
        assert image is not None, "Image element not found"
        saved_filename = image.get('filename')
        
        # Extract metadata to verify
        base, size, page = extract_metadata_from_filename(saved_filename)
        assert base == 'safecontainer:/photo1.jpg', f"Expected base 'safecontainer:/photo1.jpg', got '{base}'"
        assert size == 2.5, f"Expected size 2.5, got {size}"
        assert page == 3, f"Expected page 3, got {page}"
        
        print("✓ Page number encoded correctly in saved filename")
        print(f"  Saved filename: {saved_filename}")
        print(f"  Extracted: base={base}, size={size}, page={page}")


def test_photo_moved_between_pages():
    """Test photo moving from one page to another updates page number."""
    
    mcf_content = """<?xml version="1.0" encoding="utf-8"?>
<fotobook>
  <page pagenr="2" type="normalpage">
    <bundlesize width="4200" height="2970"/>
    <area areatype="imagearea">
      <position left="2200" top="100" width="800" height="600"/>
      <image filename="safecontainer:/photo1.jpg" backgroundposition="1">
        <cutout left="0.0" top="0.0" scale="1.0"/>
      </image>
    </area>
  </page>
</fotobook>
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mcf_path = tmpdir / "test.mcf"
        mcf_path.write_text(mcf_content)
        
        # Photo was previously on page 5, now being saved to page 3
        # Size should be preserved, page number should update
        photos = [
            {
                'filename': 'safecontainer:/photo1-sz2.5-pg3.jpg',  # Updated page number
                'area_left': 2200.0,
                'area_top': 100.0,
                'area_width': 800.0,
                'area_height': 600.0,
                'image_width': 3000,
                'image_height': 2000,
            },
        ]
        
        rename_map = {
            'safecontainer:/photo1.jpg': 'safecontainer:/photo1-sz2.5-pg3.jpg',
        }
        
        result = update_page_layout(
            str(mcf_path),
            pageno=3,
            photos=photos,
            texts=[],
            make_backup=False,
            rename_map=rename_map,
            validate_files=False
        )
        
        # Verify the filename in XML has page 3
        tree = etree.parse(str(mcf_path))
        image = tree.find('.//image')
        saved_filename = image.get('filename')
        
        base, size, page = extract_metadata_from_filename(saved_filename)
        assert page == 3, f"Expected page 3 after move, got {page}"
        assert size == 2.5, f"Expected size preserved as 2.5, got {size}"
        
        print("✓ Photo page number updated correctly when moved")
        print(f"  New filename: {saved_filename}")
        print(f"  Page: {page}, Size: {size}")


def test_xml_has_sz_already():
    """Test that we can update photos when XML already has -sz suffix from previous save."""
    
    # This simulates the real scenario: XML was previously saved with -sz
    mcf_content = """<?xml version="1.0" encoding="utf-8"?>
<fotobook>
  <page pagenr="2" type="normalpage">
    <bundlesize width="4200" height="2970"/>
    <area areatype="imagearea">
      <position left="2200" top="100" width="800" height="600"/>
      <image filename="safecontainer:/photo1-sz2.5.jpg" backgroundposition="1">
        <cutout left="0.0" top="0.0" scale="1.0"/>
      </image>
    </area>
  </page>
</fotobook>
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mcf_path = tmpdir / "test.mcf"
        mcf_path.write_text(mcf_content)
        
        # Photo list has current filename (with -sz, about to add -pg)
        photos = [
            {
                'filename': 'safecontainer:/photo1-sz2.5-pg3.jpg',
                'area_left': 2200.0,
                'area_top': 100.0,
                'area_width': 800.0,
                'area_height': 600.0,
                'image_width': 3000,
                'image_height': 2000,
            },
        ]
        
        # rename_map needs to handle: XML has -sz, we're adding -pg
        rename_map = {
            'safecontainer:/photo1.jpg': 'safecontainer:/photo1-sz2.5-pg3.jpg',  # base -> new
            'safecontainer:/photo1-sz2.5.jpg': 'safecontainer:/photo1-sz2.5-pg3.jpg',  # -sz -> -sz-pg
        }
        
        result = update_page_layout(
            str(mcf_path),
            pageno=3,
            photos=photos,
            texts=[],
            make_backup=False,
            rename_map=rename_map,
            validate_files=False
        )
        
        # Should successfully match and update
        assert result['modified_photos'] == 1, f"Expected 1 modified, got {result['modified_photos']}"
        assert len(result['warnings']) == 0, f"Got warnings: {result['warnings']}"
        
        # Verify XML was updated
        tree = etree.parse(str(mcf_path))
        image = tree.find('.//image')
        saved_filename = image.get('filename')
        assert saved_filename == 'safecontainer:/photo1-sz2.5-pg3.jpg', \
            f"Expected 'safecontainer:/photo1-sz2.5-pg3.jpg', got '{saved_filename}'"
        
        print("✓ Successfully updated photo when XML had -sz suffix")
        print(f"  XML before: safecontainer:/photo1-sz2.5.jpg")
        print(f"  XML after: {saved_filename}")


def test_new_photos_with_metadata():
    """Test that newly added photos are saved with both size and page number."""
    
    # Empty page initially
    mcf_content = """<?xml version="1.0" encoding="utf-8"?>
<fotobook>
  <page pagenr="2" type="normalpage">
    <bundlesize width="4200" height="2970"/>
  </page>
</fotobook>
"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        mcf_path = tmpdir / "test.mcf"
        mcf_path.write_text(mcf_content)
        
        # New photo being added to page 3
        photos = [
            {
                'filename': 'safecontainer:/newphoto-sz2.5-pg3.jpg',  # Updated with metadata
                'area_left': 2200.0,
                'area_top': 100.0,
                'area_width': 800.0,
                'area_height': 600.0,
                'image_width': 3000,
                'image_height': 2000,
            },
        ]
        
        # Simulate what GUI does: new_photos has the updated filename after encoding
        new_photos = ['safecontainer:/newphoto-sz2.5-pg3.jpg']
        
        result = update_page_layout(
            str(mcf_path),
            pageno=3,
            photos=photos,
            texts=[],
            make_backup=False,
            new_photos=new_photos,
            deleted_photos=[],
            rename_map={},
            validate_files=False
        )
        
        # Should add the new photo
        assert result['added_photos'] == 1, f"Expected 1 added photo, got {result['added_photos']}"
        assert result['modified_photos'] == 0, f"Expected 0 modified, got {result['modified_photos']}"
        assert len(result['warnings']) == 0, f"Got warnings: {result['warnings']}"
        
        # Verify XML has the photo with full metadata
        tree = etree.parse(str(mcf_path))
        image = tree.find('.//image')
        assert image is not None, "Image element not found"
        saved_filename = image.get('filename')
        assert saved_filename == 'safecontainer:/newphoto-sz2.5-pg3.jpg', \
            f"Expected 'safecontainer:/newphoto-sz2.5-pg3.jpg', got '{saved_filename}'"
        
        # Verify metadata
        base, size, page = extract_metadata_from_filename(saved_filename)
        assert size == 2.5, f"Expected size 2.5, got {size}"
        assert page == 3, f"Expected page 3, got {page}"
        
        print("✓ New photo added with size and page metadata")
        print(f"  Filename: {saved_filename}")
        print(f"  Extracted: size={size}, page={page}")


if __name__ == '__main__':
    test_save_photos_with_sz_suffix()
    test_save_multiple_photos_with_different_sizes()
    test_validation_detects_count_mismatch()
    test_validation_detects_missing_files()
    test_save_encodes_page_numbers()
    test_photo_moved_between_pages()
    test_xml_has_sz_already()
    test_new_photos_with_metadata()
    print("\n✓ All save tests passed")
