"""Quick test of PDFPhotobook implementation."""

from pathlib import Path
from cewe_layout.pdf2cewe.pdf_extractor import extract_pdf_content

# Test with a small PDF if available
test_pdf = Path("../Test-album-photos/test.pdf")
if not test_pdf.exists():
    print(f"Test PDF not found at {test_pdf}")
    print("Skipping test")
else:
    print(f"Testing PDFPhotobook with {test_pdf}")
    
    # Extract content - should return PDFPhotobook now
    photobook = extract_pdf_content(test_pdf, page_range=[0], verbose=True, insidecovers=False)
    
    print(f"\nPhotobook type: {type(photobook)}")
    print(f"Page count: {photobook.get_page_count()}")
    print(f"Has inside covers: {photobook.has_inside_covers()}")
    print(f"Content page count: {photobook.get_content_page_count()}")
    print(f"Native unit: {photobook.get_native_unit_name()}")
    
    # Get front cover page
    try:
        front_cover = photobook.get_front_cover_page()
        print(f"\nFront cover page:")
        print(f"  Width: {front_cover.get_width()}")
        print(f"  Height: {front_cover.get_height()}")
        print(f"  Type: {front_cover.get_page_type()}")
        print(f"  Images: {len(front_cover.get_images())}")
        print(f"  Text blocks: {len(front_cover.get_text_blocks())}")
    except ValueError as e:
        print(f"\nError getting front cover: {e}")
    
    # Test backward compatibility with dict access
    pdf_dict = photobook.pdf_content_dict
    print(f"\nBackward compat dict access:")
    print(f"  Dict page_count: {pdf_dict.get('page_count')}")
    print(f"  Dict pages length: {len(pdf_dict.get('pages', []))}")
    
    print("\n✅ PDFPhotobook test passed!")
