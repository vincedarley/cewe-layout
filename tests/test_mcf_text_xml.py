"""Tests for MCF text element XML generation.

Ensures that text elements are properly formatted with CDATA sections
and no extraneous whitespace.
"""

import xml.etree.ElementTree as ET
from cewe_layout.pdf2cewe.mcf_writer import create_text_area, prettify_xml


def test_text_element_basic_structure():
    """Test that text element has correct basic structure."""
    text_block = {
        'left': 100.0,
        'top': 200.0,
        'width': 500.0,
        'height': 100.0,
        'text': 'Hello World',
        'font': 'Arial',
        'size': 12,
        'color': 0x000000,
        'flags': 0
    }
    
    area = create_text_area(
        text_block, 
        z_position=1000,
        pdf_page_width=1900.0,
        pdf_page_height=1480.0,
        cewe_page_width=1900.0,
        cewe_page_height=1480.0
    )
    
    # Check basic structure
    assert area.tag == 'area'
    assert area.get('areatype') == 'textarea'
    
    # Check for text element
    text_elem = area.find('text')
    assert text_elem is not None
    assert text_elem.get('applySpotColor') == '0'
    assert text_elem.get('areaTextType') == 'content'
    
    # Check for outline element
    outline = text_elem.find('outline')
    assert outline is not None
    assert outline.get('width') == '0'
    
    # Check for textFormat element
    text_format = text_elem.find('textFormat')
    assert text_format is not None


def test_text_element_html_content():
    """Test that text element contains HTML in text content."""
    text_block = {
        'left': 100.0,
        'top': 200.0,
        'width': 500.0,
        'height': 100.0,
        'text': 'Test Text',
        'font': 'Helvetica',
        'size': 14,
        'color': 0x797979,
        'flags': 0
    }
    
    area = create_text_area(
        text_block, 
        z_position=1000,
        pdf_page_width=1900.0,
        pdf_page_height=1480.0,
        cewe_page_width=1900.0,
        cewe_page_height=1480.0
    )
    
    text_elem = area.find('text')
    html_content = text_elem.text
    
    # Check HTML content exists and has expected structure
    assert html_content is not None
    assert '<!DOCTYPE HTML' in html_content
    assert '<html>' in html_content
    assert '<body' in html_content
    assert 'Test Text' in html_content
    assert 'Helvetica' in html_content
    assert '14pt' in html_content


def test_prettified_xml_text_element_format():
    """Test that prettified XML has correct text element formatting.
    
    The text element should be formatted as:
    <text ...><![CDATA[...HTML...]]><outline width="0"/>
      <textFormat .../>
    </text>
    
    With no newlines between <text>, CDATA, and <outline>.
    """
    text_block = {
        'left': 100.0,
        'top': 200.0,
        'width': 500.0,
        'height': 100.0,
        'text': 'Sample text',
        'font': 'Arial',
        'size': 12,
        'color': 0x000000,
        'flags': 0
    }
    
    # Create a simple page structure with text area
    page = ET.Element('page')
    page.set('pagenr', '2')
    
    area = create_text_area(
        text_block, 
        z_position=1000,
        pdf_page_width=1900.0,
        pdf_page_height=1480.0,
        cewe_page_width=1900.0,
        cewe_page_height=1480.0
    )
    page.append(area)
    
    # Prettify the XML
    pretty_xml = prettify_xml(page)
    
    # Print the entire XML for inspection
    print("\n" + "="*80)
    print("GENERATED XML:")
    print("="*80)
    print(pretty_xml)
    print("="*80)
    
    # Check that CDATA markers are present (not escaped)
    assert '<![CDATA[' in pretty_xml, "CDATA opening marker not found"
    assert ']]>' in pretty_xml, "CDATA closing marker not found"
    
    # Check that CDATA markers are NOT escaped
    assert '&lt;![CDATA[' not in pretty_xml, "CDATA markers should not be escaped"
    assert ']]&gt;' not in pretty_xml, "CDATA markers should not be escaped"
    
    # Extract the text element line
    lines = pretty_xml.split('\n')
    text_lines = [line for line in lines if '<text ' in line]
    assert len(text_lines) > 0, "No text element found"
    
    text_line = text_lines[0]
    
    # Check structure on single line: <text ...><![CDATA[...]]><outline
    assert '<text ' in text_line
    assert '<![CDATA[' in text_line
    assert ']]><outline' in text_line
    
    # Check that there's no newline between them (everything on one line until outline)
    # Extract from <text to </text> to check full structure
    text_start = pretty_xml.find('<text ')
    text_end = pretty_xml.find('</text>', text_start) + len('</text>')
    text_block_xml = pretty_xml[text_start:text_end]
    
    # Split into lines
    text_lines_list = text_block_xml.split('\n')
    
    # First line should have: <text><![CDATA[...]]><outline/>
    first_line = text_lines_list[0]
    assert '<![CDATA[' in first_line, "CDATA should be on first line"
    assert ']]>' in first_line, "CDATA close should be on first line"
    assert '<outline' in first_line, "outline should be on first line"
    
    # CRITICAL: Check for the bug where extra CDATA markers appear
    # Count total CDATA markers - should be exactly 2 (one opening, one closing)
    cdata_open_count = text_block_xml.count('<![CDATA[')
    cdata_close_count = text_block_xml.count(']]>')
    assert cdata_open_count == 1, f"Expected exactly 1 CDATA opening marker, found {cdata_open_count}"
    assert cdata_close_count == 1, f"Expected exactly 1 CDATA closing marker, found {cdata_close_count}"
    
    # Check that there's no CDATA marker before </text>
    closing_tag_line = text_lines_list[-1]
    assert '<![CDATA[' not in closing_tag_line, "No CDATA markers should appear before </text>"
    assert '</text>' in closing_tag_line, "Last line should have closing </text> tag"
    
    # CRITICAL: Check there's only ONE <![CDATA[ marker in the entire text block
    # This catches the bug where extra CDATA markers were added
    cdata_count = text_block_xml.count('<![CDATA[')
    assert cdata_count == 1, f"Should have exactly 1 CDATA opening, found {cdata_count}"
    
    cdata_close_count = text_block_xml.count(']]>')
    assert cdata_close_count == 1, f"Should have exactly 1 CDATA closing, found {cdata_close_count}"
    
    # Check that there's no spurious CDATA before </text>
    assert '<![CDATA[</text>' not in text_block_xml, "Spurious CDATA found before closing tag"
    assert ']]></text>' not in text_block_xml, "CDATA should close before textFormat, not at end"


def test_text_element_no_leading_trailing_whitespace():
    """Test that text content has no leading/trailing whitespace in CDATA."""
    text_block = {
        'left': 100.0,
        'top': 200.0,
        'width': 500.0,
        'height': 100.0,
        'text': 'No whitespace',
        'font': 'Arial',
        'size': 12,
        'color': 0x000000,
        'flags': 0
    }
    
    page = ET.Element('page')
    area = create_text_area(
        text_block, 
        z_position=1000,
        pdf_page_width=1900.0,
        pdf_page_height=1480.0,
        cewe_page_width=1900.0,
        cewe_page_height=1480.0
    )
    page.append(area)
    
    pretty_xml = prettify_xml(page)
    
    # Print for inspection
    print("\n" + "="*80)
    print("WHITESPACE TEST XML:")
    print("="*80)
    print(pretty_xml)
    print("="*80)
    
    # Extract CDATA content
    cdata_start = pretty_xml.find('<![CDATA[')
    cdata_end = pretty_xml.find(']]>', cdata_start)
    
    assert cdata_start != -1, "CDATA start not found"
    assert cdata_end != -1, "CDATA end not found"
    
    cdata_content = pretty_xml[cdata_start + len('<![CDATA['):cdata_end]
    
    # CDATA content should not start or end with whitespace
    assert not cdata_content.startswith(' '), "CDATA content should not start with space"
    assert not cdata_content.startswith('\n'), "CDATA content should not start with newline"
    assert not cdata_content.endswith(' '), "CDATA content should not end with space"
    assert not cdata_content.endswith('\n'), "CDATA content should not end with newline"
    
    # CDATA content should not contain the text "No whitespace" surrounded by extra whitespace
    # It should be cleanly in the HTML: <span>No whitespace</span>
    assert 'No whitespace' in cdata_content


def test_special_characters_in_text():
    """Test that special characters are properly handled in text content."""
    text_block = {
        'left': 100.0,
        'top': 200.0,
        'width': 500.0,
        'height': 100.0,
        'text': 'Test & <special> "characters"',
        'font': 'Arial',
        'size': 12,
        'color': 0x000000,
        'flags': 0
    }
    
    page = ET.Element('page')
    area = create_text_area(
        text_block, 
        z_position=1000,
        pdf_page_width=1900.0,
        pdf_page_height=1480.0,
        cewe_page_width=1900.0,
        cewe_page_height=1480.0
    )
    page.append(area)
    
    pretty_xml = prettify_xml(page)
    
    # Extract CDATA content
    cdata_start = pretty_xml.find('<![CDATA[')
    cdata_end = pretty_xml.find(']]>', cdata_start)
    cdata_content = pretty_xml[cdata_start + len('<![CDATA['):cdata_end]
    
    # Inside CDATA, HTML entities should be properly escaped in the HTML
    # The text "Test & <special> "characters"" should be escaped as HTML entities
    assert '&amp;' in cdata_content or '&' in cdata_content  # & should be in the HTML
    assert 'special' in cdata_content
    assert 'characters' in cdata_content


def test_multiple_text_elements_in_page():
    """Test that multiple text elements in the same page are handled correctly.
    
    This reproduces the real-world scenario where a page has multiple text areas,
    and ensures that the CDATA wrapping doesn't create spurious markers.
    """
    # Create a page with multiple text elements
    page = ET.Element('page')
    page.set('pagenr', '26')
    page.set('type', 'normalpage')
    page.set('rotation', '0')
    
    # Add first text area
    text_block1 = {
        'left': 756.65,
        'top': 974.55,
        'width': 391.63,
        'height': 55.43,
        'text': 'Troy and Raúl 2009',
        'font': 'HelveticaNeue-Light',
        'size': 14,
        'color': 0x000000,
        'flags': 0
    }
    area1 = create_text_area(
        text_block1, 
        z_position=1001,
        pdf_page_width=1900.0,
        pdf_page_height=1480.0,
        cewe_page_width=1900.0,
        cewe_page_height=1480.0
    )
    page.append(area1)
    
    # Add second text area
    text_block2 = {
        'left': 198.32,
        'top': 1328.26,
        'width': 1486.22,
        'height': 84.30,
        'text': 'A horrible day - Raúl broke his leg',
        'font': 'HelveticaNeue',
        'size': 11,
        'color': 0x797979,
        'flags': 0
    }
    area2 = create_text_area(
        text_block2, 
        z_position=1002,
        pdf_page_width=1900.0,
        pdf_page_height=1480.0,
        cewe_page_width=1900.0,
        cewe_page_height=1480.0
    )
    page.append(area2)
    
    # Prettify the XML
    pretty_xml = prettify_xml(page)
    
    # Print for inspection
    print("\n" + "="*80)
    print("MULTIPLE TEXT ELEMENTS TEST:")
    print("="*80)
    print(pretty_xml)
    print("="*80)
    
    # Count CDATA markers
    cdata_open_count = pretty_xml.count('<![CDATA[')
    cdata_close_count = pretty_xml.count(']]>')
    
    # Should have exactly 2 opening and 2 closing CDATA markers (one pair per text element)
    assert cdata_open_count == 2, f"Expected 2 <![CDATA[ markers, found {cdata_open_count}"
    assert cdata_close_count == 2, f"Expected 2 ]]> markers, found {cdata_close_count}"
    
    # Extract both text elements
    text_elements = pretty_xml.split('<text ')
    assert len(text_elements) == 3, "Expected 2 text elements plus the part before first text"
    
    # Check first text element
    first_text = '<text ' + text_elements[1]
    first_text_end = first_text.find('</text>')
    first_text_block = first_text[:first_text_end + len('</text>')]
    
    # First text should have CDATA properly formatted
    assert '<![CDATA[' in first_text_block
    assert ']]><outline' in first_text_block
    # Should NOT have extra CDATA markers
    assert first_text_block.count('<![CDATA[') == 1, "First text element should have exactly one <![CDATA["
    assert first_text_block.count(']]>') == 1, "First text element should have exactly one ]]>"
    
    # Check second text element
    second_text = '<text ' + text_elements[2]
    second_text_end = second_text.find('</text>')
    second_text_block = second_text[:second_text_end + len('</text>')]
    
    # Second text should have CDATA properly formatted
    assert '<![CDATA[' in second_text_block
    assert ']]><outline' in second_text_block
    # Should NOT have extra CDATA markers
    assert second_text_block.count('<![CDATA[') == 1, "Second text element should have exactly one <![CDATA["
    assert second_text_block.count(']]>') == 1, "Second text element should have exactly one ]]>"
    
    # Check for spurious CDATA before </text> closing tags
    assert '<![CDATA[</text>' not in pretty_xml, "Should not have <![CDATA[ immediately before </text>"
    assert ']]><![CDATA[' not in pretty_xml, "Should not have adjacent CDATA markers"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])
