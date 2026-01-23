#!/usr/bin/env python3
"""Test script to display MCF text blocks using tkhtmlview or tkinterweb.

This test allows comparing different HTML rendering engines for CEWE text blocks.

Requirements:
    pip install tkhtmlview
    pip install tkinterweb

Usage:
    python tests/test_tkhtmlview.py                    # Use tkhtmlview (default)
    python tests/test_tkhtmlview.py --tkinterweb       # Use tkinterweb
    python tests/test_tkhtmlview.py path/to/album.xmcf # Use specific album
"""

import tkinter as tk
from tkinter import ttk
import sys
from pathlib import Path

# Add parent directory to path to import cewe_layout modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.mcf_io.mcf_parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.text_utils import convert_qt_html_to_tkhtmlview

try:
    from tkhtmlview import HTMLLabel, HTMLScrolledText
    TKHTMLVIEW_AVAILABLE = True
except ImportError:
    TKHTMLVIEW_AVAILABLE = False
    print("WARNING: tkhtmlview not available. Install with: pip install tkhtmlview")

try:
    from tkinterweb import HtmlFrame
    TKINTERWEB_AVAILABLE = True
except ImportError:
    TKINTERWEB_AVAILABLE = False
    print("WARNING: tkinterweb not available. Install with: pip install tkinterweb")


def extract_text_blocks_from_mcf(mcf_path):
    """Extract all text blocks from an MCF file.
    
    Args:
        mcf_path: Path to the .mcf or .xmcf file
        
    Returns:
        List of dicts with 'pageno', 'raw_html', and other text properties
    """
    # Parse the MCF file - get XML root
    root = parse_mcf_from_path(str(mcf_path))
    
    # Extract pages info - returns CEWEPhotobook object
    photobook = extract_pages_info(root)
    
    text_blocks = []
    
    # Extract text blocks from all pages using photobook interface
    for page_idx in range(photobook.get_page_count()):
        page = photobook.get_page(page_idx)
        pageno = page.get_page_number()
        page_info = page.get_page_info()
        
        # Get page background color for hierarchy (page → textarea → textformat)
        page_bg_color = None
        page_bg_color_rgb = None
        page_background_id = page_info.get('background_id')
        if page_background_id:
            from cewe_layout.colour_utils import get_color_hex
            try:
                page_bg_int = int(page_background_id)
                page_bg_hex = get_color_hex(page_bg_int)
                # Page background doesn't have alpha in the color code system, so add fully opaque alpha
                page_bg_color = page_bg_hex + 'ff'  # RRGGBBAA format
                page_bg_color_rgb = page_bg_hex  # RRGGBB format
            except (ValueError, TypeError):
                pass  # Invalid background_id
        
        # Get text blocks for this page
        for text_area in page.get_text_blocks():
            # Implement color hierarchy: page → textarea → textformat
            # Start with page background (level 1)
            bg_color = page_bg_color
            bg_color_rgb = page_bg_color_rgb
            
            # Override with textarea background if present (level 2) - not currently in parsed data
            # (The MCF parser doesn't extract area backgroundcolor attribute yet)
            
            # Override with textformat background if present (level 3) - but only if not fully transparent
            textformat_bg = text_area.get('background_color')  # RRGGBBAA format
            if textformat_bg:
                # Check alpha channel - only override if not fully transparent
                alpha_hex = textformat_bg[-2:] if len(textformat_bg) >= 2 else 'ff'
                alpha_int = int(alpha_hex, 16) if alpha_hex else 255
                if alpha_int > 0:  # Not fully transparent
                    bg_color = textformat_bg
                    bg_color_rgb = text_area.get('background_color_rgb')
            
            # Extract text properties
            text_block = {
                'pageno': pageno,
                'raw_html': text_area.get('raw_html', ''),
                'area_left': text_area.get('left', 0),
                'area_top': text_area.get('top', 0),
                'area_width': text_area.get('width', 0),
                'area_height': text_area.get('height', 0),
                'background_color': bg_color,
                'background_color_rgb': bg_color_rgb,
                'foreground_color_rgb': text_area.get('foreground_color_rgb', '#000000'),
                'font_size': text_area.get('font_size', 12),
                'h_align': text_area.get('h_align', 'left'),
                'v_align': text_area.get('v_align', 'top'),
            }
            text_blocks.append(text_block)
    
    return text_blocks


def create_demo(text_blocks, use_tkinterweb=False):
    """Create a tkinter window demonstrating HTML rendering with MCF text blocks.
    
    Args:
        text_blocks: List of text block dicts from extract_text_blocks_from_mcf
        use_tkinterweb: If True, use tkinterweb instead of tkhtmlview
    """
    if use_tkinterweb:
        if not TKINTERWEB_AVAILABLE:
            print("ERROR: tkinterweb is required. Install with: pip install tkinterweb")
            return
        renderer_name = "tkinterweb"
    else:
        if not TKHTMLVIEW_AVAILABLE:
            print("ERROR: tkhtmlview is required. Install with: pip install tkhtmlview")
            return
        renderer_name = "tkhtmlview"
    
    root = tk.Tk()
    root.title(f"{renderer_name} Demo - MCF Text Blocks")
    root.geometry("900x700")
    
    # Create main frame
    main_frame = ttk.Frame(root, padding=10)
    main_frame.pack(fill='both', expand=True)
    
    # Info label
    info_text = f"Found {len(text_blocks)} text blocks. Select one to view its HTML rendering:"
    info_label = ttk.Label(main_frame, text=info_text, font=('TkDefaultFont', 10, 'bold'))
    info_label.pack(pady=(0, 10))
    
    # Create paned window for list and preview
    paned = ttk.PanedWindow(main_frame, orient='horizontal')
    paned.pack(fill='both', expand=True)
    
    # Left panel: list of text blocks
    left_frame = ttk.Frame(paned)
    paned.add(left_frame, weight=1)
    
    ttk.Label(left_frame, text="Text Blocks:", font=('TkDefaultFont', 9, 'bold')).pack()
    
    # Listbox with scrollbar
    list_frame = ttk.Frame(left_frame)
    list_frame.pack(fill='both', expand=True, pady=(5, 0))
    
    scrollbar = ttk.Scrollbar(list_frame)
    scrollbar.pack(side='right', fill='y')
    
    listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=('TkDefaultFont', 9))
    listbox.pack(side='left', fill='both', expand=True)
    scrollbar.config(command=listbox.yview)
    
    # Populate listbox
    for i, block in enumerate(text_blocks):
        # Extract first few words as preview
        raw_html = block['raw_html']
        # Simple text extraction for preview
        import re
        import html as html_module
        preview = re.sub(r'<[^>]+>', '', raw_html)  # Remove tags
        preview = html_module.unescape(preview)  # Decode entities
        preview = ' '.join(preview.split())  # Clean whitespace
        preview = preview[:50] + '...' if len(preview) > 50 else preview
        
        list_text = f"Page {block['pageno']}: {preview}"
        listbox.insert('end', list_text)
    
    # Right panel: HTML preview
    right_frame = ttk.Frame(paned)
    paned.add(right_frame, weight=2)
    
    ttk.Label(right_frame, text=f"HTML Preview ({renderer_name}):", font=('TkDefaultFont', 9, 'bold')).pack()
    
    # Info about selected block
    info_frame = ttk.Frame(right_frame)
    info_frame.pack(fill='x', pady=(5, 5))
    
    block_info_label = ttk.Label(info_frame, text="", font=('TkDefaultFont', 8))
    block_info_label.pack()
    
    # HTML display area - choose renderer
    if use_tkinterweb:
        html_display = HtmlFrame(right_frame)
        html_display.load_html("<p>Select a text block to preview</p>")
        html_display.pack(fill='both', expand=True)
    else:
        # HTML display area using HTMLScrolledText (better for long content)
        html_display = HTMLScrolledText(right_frame, html="<p>Select a text block to preview</p>")
        html_display.pack(fill='both', expand=True)
    
    # Raw HTML display (for comparison)
    raw_frame = ttk.LabelFrame(right_frame, text="HTML Source (Original vs Converted)", padding=5)
    raw_frame.pack(fill='both', expand=True, pady=(10, 0))
    
    raw_text = tk.Text(raw_frame, height=12, wrap='word', font=('Courier', 9))
    raw_text.pack(side='left', fill='both', expand=True)
    
    raw_scrollbar = ttk.Scrollbar(raw_frame, command=raw_text.yview)
    raw_scrollbar.pack(side='right', fill='y')
    raw_text.config(yscrollcommand=raw_scrollbar.set)
    
    def on_select(event):
        """Handle selection of a text block."""
        selection = listbox.curselection()
        if not selection:
            return
        
        idx = selection[0]
        block = text_blocks[idx]
        
        # Extract background color from MCF data
        bg_color_rgba = block.get('background_color')  # '#RRGGBBAA' format
        bg_color_rgb = block.get('background_color_rgb')  # '#RRGGBB' format
        fg_color = block.get('foreground_color_rgb', '#000000')
        
        # Check if background is transparent (alpha channel)
        use_background = False
        if bg_color_rgba and bg_color_rgb:
            # Extract alpha from RRGGBBAA
            alpha_hex = bg_color_rgba[-2:]  # Last 2 characters
            alpha_int = int(alpha_hex, 16) if alpha_hex else 255
            # Only use background if it's not fully transparent
            use_background = alpha_int > 0
        
        # Update info label
        bg_info = f"BG: {bg_color_rgb or 'none'}" if use_background else "BG: transparent"
        info = (f"Page {block['pageno']} | "
                f"Position: ({block['area_left']:.0f}, {block['area_top']:.0f}) | "
                f"Size: {block['area_width']:.0f}×{block['area_height']:.0f} | "
                f"Font: {block['font_size']}pt | "
                f"Color: {fg_color} | {bg_info} | "
                f"Align: {block['h_align']}/{block['v_align']}")
        block_info_label.config(text=info)
        
        # Get raw HTML
        raw_html = block['raw_html']
        
        # Convert Qt HTML to tkhtmlview-compatible HTML
        converted_html = convert_qt_html_to_tkhtmlview(raw_html)
        
        # Wrap with background and foreground colors, and base font size from MCF metadata
        style_parts = [f'color: {fg_color}']
        if use_background and bg_color_rgb:
            style_parts.append(f'background-color: {bg_color_rgb}')
        # Apply base font size from MCF metadata (HTML may override with inline styles)
        # tkhtmlview only supports 'px' and '%' units, not 'pt'
        style_parts.append(f'font-size: {block["font_size"]}px')
        # Add padding to make background visible
        style_parts.append('padding: 10px')
        
        style_attr = '; '.join(style_parts)
        final_html = f'<div style="{style_attr}">{converted_html}</div>'
        
        # Update HTML display with styled version
        if use_tkinterweb:
            html_display.load_html(final_html)
        else:
            html_display.set_html(final_html)
        
        # Update raw HTML display to show ALL versions
        raw_text.delete('1.0', 'end')
        raw_text.insert('1.0', '=== ORIGINAL QT HTML ===\n\n')
        raw_text.insert('end', raw_html)
        raw_text.insert('end', '\n\n=== CONVERTED FOR TKHTMLVIEW ===\n\n')
        raw_text.insert('end', converted_html)
        raw_text.insert('end', '\n\n=== FINAL WITH MCF COLORS ===\n\n')
        raw_text.insert('end', final_html)
    
    listbox.bind('<<ListboxSelect>>', on_select)
    
    # Select first item by default
    if text_blocks:
        listbox.selection_set(0)
        on_select(None)
    
    root.mainloop()


def main():
    """Main entry point."""
    # Check for --tkinterweb flag
    use_tkinterweb = '--tkinterweb' in sys.argv
    if use_tkinterweb:
        sys.argv.remove('--tkinterweb')
    
    # Default album path (relative to script location)
    script_dir = Path(__file__).parent
    default_album = script_dir.parent.parent / "2009-2010-album.xmcf"
    
    # Use command line argument if provided
    if len(sys.argv) > 1:
        album_path = Path(sys.argv[1])
    else:
        album_path = default_album
    
    # Check if album exists
    if not album_path.exists():
        print(f"ERROR: Album not found: {album_path}")
        print(f"\nUsage: {sys.argv[0]} [--tkinterweb] [path/to/album.xmcf]")
        print(f"  --tkinterweb: Use tkinterweb instead of tkhtmlview")
        sys.exit(1)
    
    # Handle .xmcf (directory) vs .mcf (file)
    if album_path.is_dir() and album_path.suffix == '.xmcf':
        mcf_file = album_path / 'data.mcf'
    else:
        mcf_file = album_path
    
    if not mcf_file.exists():
        print(f"ERROR: MCF file not found: {mcf_file}")
        sys.exit(1)
    
    print(f"Loading text blocks from: {mcf_file}")
    
    # Extract text blocks
    text_blocks = extract_text_blocks_from_mcf(mcf_file)
    
    print(f"Found {len(text_blocks)} text blocks")
    
    if not text_blocks:
        print("No text blocks found in album. Nothing to display.")
        sys.exit(0)
    
    # Create demo window
    renderer = "tkinterweb" if use_tkinterweb else "tkhtmlview"
    print(f"Using renderer: {renderer}")
    create_demo(text_blocks, use_tkinterweb=use_tkinterweb)


if __name__ == '__main__':
    main()
