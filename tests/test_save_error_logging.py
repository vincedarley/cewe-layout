"""Test that save operations FAIL instead of silently losing data."""
import sys
from pathlib import Path
import tempfile
import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.writer import update_page_layout


def test_raises_when_new_photo_not_in_list():
    """Test that an exception is raised when a photo is expected to be new but isn't in new_photos list."""
    
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
        
        # Photo that should be added
        photos = [
            {
                'filename': 'safecontainer:/photo1.jpg',
                'area_left': 2200.0,
                'area_top': 100.0,
                'area_width': 800.0,
                'area_height': 600.0,
                'image_width': 3000,
                'image_height': 2000,
            },
        ]
        
        # BUT new_photos list is empty (simulates the bug we just fixed)
        new_photos = []
        
        # Should RAISE an exception, not silently skip
        with pytest.raises(ValueError, match=r"not in new_photos list"):
            update_page_layout(
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
        
        print("✓ Exception raised when photo not in new_photos list")


def test_raises_when_xml_photo_not_matched():
    """Test that an exception is raised when XML photo can't be matched to layout."""
    
    # XML has a photo
    mcf_content = """<?xml version="1.0" encoding="utf-8"?>
<fotobook>
  <page pagenr="2" type="normalpage">
    <bundlesize width="4200" height="2970"/>
    <area areatype="imagearea">
      <position left="2200" top="100" width="800" height="600"/>
      <image filename="safecontainer:/oldphoto.jpg" backgroundposition="1">
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
        
        # Layout has a different photo (no match possible)
        photos = [
            {
                'filename': 'safecontainer:/newphoto.jpg',
                'area_left': 2200.0,
                'area_top': 100.0,
                'area_width': 800.0,
                'area_height': 600.0,
                'image_width': 3000,
                'image_height': 2000,
            },
        ]
        
        # No rename map to help matching
        rename_map = {}
        
        # Should RAISE an exception, not silently skip
        with pytest.raises(ValueError, match=r"not found in layout"):
            update_page_layout(
                str(mcf_path),
                pageno=3,
                photos=photos,
                texts=[],
                make_backup=False,
                new_photos=[],
                deleted_photos=[],
                rename_map=rename_map,
                validate_files=False
            )
        
        print("✓ Exception raised when XML photo can't be matched")


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v', '-s'])
