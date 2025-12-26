"""Pure rendering engine for photobook pages - no business logic, only visualization."""
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk
from dataclasses import dataclass
import os
from pathlib import Path
import logging
import re
import html

from cewe_layout.colour_utils import getBackgroundAndFrameColour

logger = logging.getLogger(__name__)

# Register HEIF/HEIC support if available
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    logger.info("HEIF/HEIC support enabled via pillow-heif")
except ImportError:
    logger.info("pillow-heif not available - HEIC files will not be supported")

def _extract_text_from_html(html_text):
    """Extract plain text from HTML CDATA content.
    
    Args:
        html_text: HTML string, possibly wrapped in CDATA
        
    Returns:
        Plain text string with HTML tags removed
    """
    if not html_text:
        return ""
    
    # Remove CDATA wrapper if present
    text = re.sub(r'<!\[CDATA\[(.*?)\]\]>', r'\1', html_text, flags=re.DOTALL)
    
    # Remove <style>...</style> blocks (including CSS content)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove <head>...</head> blocks
    text = re.sub(r'<head[^>]*>.*?</head>', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove all HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    
    # Decode HTML entities
    text = html.unescape(text)
    
    # Clean up whitespace
    text = ' '.join(text.split())
    
    return text.strip()




@dataclass
class PageRenderData:
    """Immutable data for rendering a single page."""
    pageno: int
    photos: list  # List of photo dicts with area_*, filename, etc.
    texts: list   # List of text dicts
    page_width: float
    page_height: float
    origin_left: float
    background_id: str  # '212' for black, '201' for white
    composite_image: dict = None  # Optional PDF composite image data: {'data', 'format', 'left', 'top', 'width', 'height'}


class PageRenderer:
    """Pure rendering engine for photobook pages. No business logic, only visualization.
    
    This class handles ONLY visual display of page layouts. It has:
    - NO business logic
    - NO state modification
    - NO file I/O (except image loading)
    
    All rendering state (caches, displayed images) is managed here.
    All business state (layouts, modifications, algorithms) stays in LayoutViewer.
    """
    
    def __init__(self, canvas: tk.Canvas, mcf_base_folder: str, image_folder_attr: str,
                 photo_dimensions_cache: dict):
        """Initialize the page renderer.
        
        Args:
            canvas: Tkinter Canvas widget to render into
            mcf_base_folder: Base folder for resolving photo paths
            image_folder_attr: Image folder attribute from MCF
            photo_dimensions_cache: Reference to LayoutViewer's photo dimensions cache
                                   (shared because algorithms need it too)
        """
        self.canvas = canvas
        self.mcf_base_folder = mcf_base_folder
        self.image_folder_attr = image_folder_attr
        self.photo_dimensions = photo_dimensions_cache  # Shared with LayoutViewer
        
        # Rendering state (caches, pixel images for buttons)
        self.photo_image = None  # Current displayed PhotoImage
        self.canvas_image_id = None  # Canvas image item ID
        self.delete_button_pixel = tk.PhotoImage(width=1, height=1)
        self.delete_buttons = []  # Currently displayed delete button widgets
        self.drag_rectangles = []  # Currently displayed drag rectangle canvas items
        
        # Photo drag-and-drop state for swapping
        self.drag_active = False
        self.drag_source_pageno = None
        self.drag_source_photo_idx = None
        self.drag_source_rect_id = None  # Canvas item ID being highlighted as source
        self.drag_hover_pageno = None
        self.drag_hover_photo_idx = None
        self.drag_hover_rect_id = None  # Canvas item ID being highlighted as destination
        self.drag_thumbnail_id = None  # Canvas item following cursor
        self.swap_callback = None  # Callback to business logic for executing swap
        
        # Image caches (for rendering optimization)
        self.cache_full_images = True
        self.thumb_cache = {}  # For thumbnail mode: (base_filename, file_size, w, h) -> thumbnail
        self.full_image_cache = {}  # For full image mode: (base_filename, file_size) -> full PIL Image
    
    def render_pages(self, 
                    page_data_list: list,  # List of PageRenderData
                    canvas_w: int,
                    canvas_h: int,
                    margin_mcf: float,
                    is_canvas: bool,
                    delete_callback,
                    show_pdf_composite: bool = False,
                    protected_inside_covers: list = None,
                    swap_callback = None) -> None:
        """Render one or more pages to the display.
        
        Args:
            page_data_list: List of PageRenderData objects (1 for single, 2 for spread)
            canvas_w, canvas_h: Canvas dimensions in pixels
            margin_mcf: Display margin in MCF units
            is_canvas: Whether this is canvas mode (affects crease line)
            delete_callback: Function to call when delete button clicked
                           Signature: (item_type, page_index, pageno, identifier)
                           where item_type is 'photo' or 'text'
            protected_inside_covers: List of page numbers that are protected (inside covers)
            swap_callback: Optional callback for photo swap completion
                          Signature: (source_pageno, source_photo_idx, dest_pageno, dest_photo_idx)
                          Called when user successfully drags and drops to swap two photos
        """
        # Store swap callback for later use
        self.swap_callback = swap_callback
        if protected_inside_covers is None:
            protected_inside_covers = []
        if not page_data_list:
            self.render_empty_page(canvas_w, canvas_h, "No page data")
            return
        
        # Get page dimensions from first page
        first_page = page_data_list[0]
        page_w = first_page.page_width
        page_h = first_page.page_height
        
        # Create canvas image with white background (will draw page backgrounds per-page)
        img = Image.new('RGB', (canvas_w, canvas_h), 'white')
        draw = ImageDraw.Draw(img)
        
        # Calculate scale to fit page(s) + margins in canvas
        if len(page_data_list) == 2:
            # Spread mode: double width
            total_w_mcf = (2 * page_w) + 2 * margin_mcf
        else:
            # Single page mode
            total_w_mcf = page_w + 2 * margin_mcf
        total_h_mcf = page_h + 2 * margin_mcf
        scale = min(canvas_w / total_w_mcf, canvas_h / total_h_mcf)
        
        # Draw PDF composite backgrounds FIRST (before any other rendering)
        if show_pdf_composite:
            for page_offset, page_data in enumerate(page_data_list):
                if page_data.composite_image:
                    page_x_offset = page_offset * page_w if len(page_data_list) == 2 else 0
                    frame_x = margin_mcf * scale + page_x_offset * scale
                    frame_y = margin_mcf * scale
                    self._draw_single_pdf_composite(img, page_data, frame_x, frame_y, scale)
        
        # Store delete button info for later widget creation
        delete_button_info = []
        photo_counter = 1
        text_counter = 1
        
        # Render each page
        for page_offset, page_data in enumerate(page_data_list):
            # Get background and frame colors for this specific page
            page_bg_color, frame_color = getBackgroundAndFrameColour(page_data.background_id)
            
            # Calculate frame position for this page
            # In spread mode, second page is offset by page_w
            page_x_offset = page_offset * page_w if len(page_data_list) == 2 else 0
            frame_x = margin_mcf * scale + page_x_offset * scale
            frame_y = margin_mcf * scale
            frame_w = page_w * scale
            frame_h = page_h * scale
            
            # Draw the page background rectangle for this page
            # Skip if showing PDF composite (composite serves as background)
            if not show_pdf_composite:
                draw.rectangle(
                    [frame_x, frame_y, frame_x + frame_w, frame_y + frame_h],
                    fill=page_bg_color
                )
            
            # Render photos for this page
            self._render_photos(img, draw, page_data.photos, frame_x, frame_y, scale, 
                               page_data.origin_left, photo_counter, page_data.pageno, 
                               delete_button_info, page_bg_color, swap_callback)
            photo_counter += len(page_data.photos)
            
            # Render texts for this page
            self._render_texts(draw, page_data.texts, frame_x, frame_y, scale,
                              page_data.origin_left, text_counter, page_data.pageno,
                              delete_button_info)
            text_counter += len(page_data.texts)
            
            # Draw page frame for this page
            self._draw_page_frame(draw, frame_x, frame_y, frame_w, frame_h, frame_color)
        
        # In spread mode, draw dotted line down the crease (center)
        if len(page_data_list) == 2:
            # Use the first page's frame color for the crease line
            _, crease_frame_color = getBackgroundAndFrameColour(page_data_list[0].background_id)
            crease_x = margin_mcf * scale + page_w * scale
            self._draw_crease_line(draw, crease_x, frame_y, frame_h, crease_frame_color)
        
        # Draw overlay text for protected inside cover pages
        if protected_inside_covers:
            for page_offset, page_data in enumerate(page_data_list):
                if page_data.pageno in protected_inside_covers:
                    page_x_offset = page_offset * page_w if len(page_data_list) == 2 else 0
                    frame_x = margin_mcf * scale + page_x_offset * scale
                    frame_y = margin_mcf * scale
                    frame_w = page_w * scale
                    frame_h = page_h * scale
                    self._draw_protected_overlay(draw, frame_x, frame_y, frame_w, frame_h)
        
        # Show image and create delete buttons
        self._show_image(img)
        self._create_delete_buttons(delete_button_info, delete_callback)
        
        # Create invisible drag rectangles for photos if swap_callback provided
        if swap_callback:
            self._create_drag_rectangles(delete_button_info)

    def render_empty_page(self, canvas_w: int, canvas_h: int, message: str) -> None:
        """Render empty page with message.
        
        Args:
            canvas_w, canvas_h: Canvas dimensions
            message: Message to display
        """
        img = Image.new('RGB', (canvas_w, canvas_h), 'white')
        draw = ImageDraw.Draw(img)
        draw.text((10, 10), message, fill='black')
        self._show_image(img)
        self.clear_delete_buttons()
    
    def clear_delete_buttons(self) -> None:
        """Clear all delete button widgets."""
        for btn in self.delete_buttons:
            btn.destroy()
        self.delete_buttons.clear()
    
    def clear_caches(self) -> None:
        """Clear all image caches."""
        self.thumb_cache.clear()
        self.full_image_cache.clear()
    
    # ========== Private rendering methods ==========
    
    def _draw_single_pdf_composite(self, img, page_data, frame_x, frame_y, scale):
        """Draw PDF composite image as grayscale background for a single page.
        
        Args:
            img: PIL Image to draw on
            page_data: PageRenderData for this page
            frame_x, frame_y: Frame position on canvas
            scale: Scale factor from MCF to pixels
        """
        from io import BytesIO
        from PIL import ImageOps
                
        if page_data.composite_image is None:
            logger.error(f"Page {page_data.pageno}: composite_image is None!")
            raise ValueError(f"Page {page_data.pageno}: No composite_image data provided")
        
        # Extract metadata without dumping binary data
        comp_info = {k: v for k, v in page_data.composite_image.items() if k != 'data'}
        comp_info['data_size'] = len(page_data.composite_image.get('data', b''))
        
        try:
            # Load composite image
            composite_data = page_data.composite_image.get('data')
            
            if not composite_data:
                logger.error(f"Page {page_data.pageno}: composite_image.get('data') returned empty!")
                raise ValueError(f"Page {page_data.pageno}: composite_image has no 'data' field")
                
            composite_pil = Image.open(BytesIO(composite_data))
            
            # Convert to grayscale
            composite_gray = ImageOps.grayscale(composite_pil)
            composite_gray = composite_gray.convert('RGB')  # Convert back to RGB for pasting
            
            # Calculate uniform scale factor to preserve aspect ratio
            # Get dimension information from composite_image dict
            pdf_page_width_mcf = page_data.composite_image.get('pdf_page_width_mcf')
            pdf_page_height_mcf = page_data.composite_image.get('pdf_page_height_mcf')
            cewe_page_width_mcf = page_data.composite_image.get('cewe_page_width_mcf')
            cewe_page_height_mcf = page_data.composite_image.get('cewe_page_height_mcf')
            
            # Calculate position on canvas
            # Composite image coordinates are in MCF spread units from PDF extraction
            comp_left_mcf = page_data.composite_image.get('left', 0)
            comp_top_mcf = page_data.composite_image.get('top', 0)
            comp_width_mcf = page_data.composite_image.get('width', 0)
            comp_height_mcf = page_data.composite_image.get('height', 0)
            
            # Composite coordinates are in PDF MCF spread units - convert to page-relative
            # For left pages: comp_left_mcf starts from 0
            # For right pages: comp_left_mcf starts from pdf_page_width_mcf
            # Subtract PDF page width to make page-relative (avoids rounding issues with origin_left which is CEWE dimensions)
            if page_data.origin_left > 0:
                # Right page: subtract PDF page width to zero out
                comp_left_page_pdf = comp_left_mcf - pdf_page_width_mcf
            else:
                # Left page: already zeroed
                comp_left_page_pdf = comp_left_mcf
            
            comp_top_page_pdf = comp_top_mcf  # Top is the same
            
            # Calculate scale factors from PDF to CEWE dimensions
            pdf_to_cewe_width_scale = cewe_page_width_mcf / pdf_page_width_mcf
            pdf_to_cewe_height_scale = cewe_page_height_mcf / pdf_page_height_mcf
            
            # Choose scale factor closest to 1.0 to minimize distortion
            width_diff = abs(pdf_to_cewe_width_scale - 1.0)
            height_diff = abs(pdf_to_cewe_height_scale - 1.0)
            
            if width_diff < height_diff:
                uniform_pdf_scale = pdf_to_cewe_width_scale
                logger.debug(f"Using width scale factor {uniform_pdf_scale:.4f} (closer to 1.0)")
            else:
                uniform_pdf_scale = pdf_to_cewe_height_scale
                logger.debug(f"Using height scale factor {uniform_pdf_scale:.4f} (closer to 1.0)")
            
            # Transform to canvas coordinates
            # First scale from PDF dimensions to CEWE dimensions, then to canvas pixels
            # frame_x already includes margin and page positioning
            canvas_x = int(frame_x + comp_left_page_pdf * uniform_pdf_scale * scale)
            canvas_y = int(frame_y + comp_top_page_pdf * uniform_pdf_scale * scale)
            canvas_w = int(comp_width_mcf * uniform_pdf_scale * scale)
            canvas_h = int(comp_height_mcf * uniform_pdf_scale * scale)
            
            # Resize composite to canvas scale
            if canvas_w > 0 and canvas_h > 0:
                composite_resized = composite_gray.resize((canvas_w, canvas_h), Image.Resampling.LANCZOS)
                
                # Paste onto canvas
                img.paste(composite_resized, (canvas_x, canvas_y))
                logger.debug(f"  ✅ Successfully pasted composite at ({canvas_x}, {canvas_y})")
            else:
                logger.error(f"Page {page_data.pageno}: Invalid canvas dimensions: {canvas_w}x{canvas_h}")
                raise ValueError(f"Page {page_data.pageno}: Invalid canvas dimensions for composite")
                
        except Exception as e:
            logger.error(f"Error drawing composite image for page {page_data.pageno}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise  # Re-raise the exception instead of silently failing
    
    def _render_photos(self, img, draw, photos, frame_x, frame_y, scale, origin_left, 
                      start_number, pageno, delete_button_info, page_bg_color, swap_callback=None):
        """Render photos for a single page.
        
        Args:
            swap_callback: Optional callback for photo swap events
        """

        try:
            from PIL import ImageFont
            label_font = ImageFont.truetype('Arial', 16)
        except:
            label_font = None
        
        for i, p in enumerate(photos, start=start_number):
            left = p.get('area_left') or 0
            top = p.get('area_top') or 0
            w = p.get('area_width') or 0
            h = p.get('area_height') or 0

            # subtract origin_left so right-page areas are positioned relative to their page
            local_left = left - origin_left

            x0 = frame_x + local_left * scale
            y0 = frame_y + top * scale
            x1 = frame_x + (local_left + w) * scale
            y1 = frame_y + (top + h) * scale

            # draw image thumbnail if available
            fn = p.get('filename') or ''
            if fn:
                # Check if this is a staged photo (has _source_path)
                if '_source_path' in p:
                    img_path = p['_source_path']
                    logger.debug(f"Photo {i}: Using staged path: {img_path}")
                else:
                    # Resolve photo path from mcf_base_folder
                    # Strip safecontainer prefix but keep the full filename with -szN-pgN suffixes
                    from .file_utils import split_safecontainer_prefix
                    prefix, clean_fn = split_safecontainer_prefix(fn)
                    logger.debug(f"Photo {i}: filename={fn} -> clean={clean_fn}")
                    
                    if self.image_folder_attr:
                        img_path = os.path.join(self.mcf_base_folder, self.image_folder_attr, clean_fn)
                        logger.debug(f"Photo {i}: Trying path with image_folder_attr: {img_path}")
                    else:
                        img_path = os.path.join(self.mcf_base_folder, clean_fn)
                        logger.debug(f"Photo {i}: Trying path without image_folder_attr: {img_path}")
                    
                    # Try alternative locations if not found
                    if not os.path.exists(img_path):
                        logger.warning(f"Photo {i}: Image not found at {img_path}")
                        # Try without imagedir
                        alt_path = os.path.join(self.mcf_base_folder, clean_fn)
                        if os.path.exists(alt_path):
                            logger.info(f"Photo {i}: Found at alternative path: {alt_path}")
                            img_path = alt_path
                        else:
                            logger.error(f"Photo {i}: Image not found at alternative path: {alt_path}")
                            img_path = None
                    else:
                        logger.debug(f"Photo {i}: Found image at {img_path}")

                if img_path is not None and os.path.exists(img_path):
                    thumb = self.get_thumbnail(img_path, int(x1-x0), int(y1-y0))
                    if thumb is not None:
                        # Draw grey background first
                        # NOTE: Grey borders appear when the image is smaller than the slot because:
                        # 1. PIL's thumbnail() preserves aspect ratio and never upscales
                        # 2. If image pixels < slot pixels, the thumbnail stays at original size
                        # 3. We center the smaller thumbnail, leaving grey borders visible
                        # This commonly happens with segmented photos whose pixel dimensions
                        # don't match the MCF area_width/area_height values.
                        draw.rectangle([x0, y0, x1, y1], fill='#cccccc')
                        
                        # Center the thumbnail in the slot
                        thumb_w, thumb_h = thumb.size
                        slot_w = int(x1 - x0)
                        slot_h = int(y1 - y0)
                        
                        # Calculate centered position
                        paste_x = int(x0 + (slot_w - thumb_w) / 2)
                        paste_y = int(y0 + (slot_h - thumb_h) / 2)
                        
                        img.paste(thumb, (paste_x, paste_y))
                        logger.debug(f"Photo {i}: Successfully rendered thumbnail {thumb_w}x{thumb_h} centered in {slot_w}x{slot_h} slot")
                    else:
                        logger.error(f"Photo {i}: get_thumbnail returned None for {img_path}")
                        draw.rectangle([x0, y0, x1, y1], fill='#eeeeee')
                else:
                    # draw a light placeholder for missing file
                    logger.error(f"Photo {i}: No valid image path found (original filename: {fn})")
                    draw.rectangle([x0, y0, x1, y1], fill='#eeeeee')

            # wireframe overlay
            draw.rectangle([x0, y0, x1, y1], outline='blue', width=2)
            
            # Photo number label with light grey background
            label_text = f'{i}'
            if label_font:
                bbox = draw.textbbox((x0+4, y0+4), label_text, font=label_font)
            else:
                # Fallback bounding box estimation
                bbox = (x0+4, y0+4, x0+30, y0+24)
            
            # Add padding around text
            padding = 3
            bg_bbox = (bbox[0]-padding, bbox[1]-padding, bbox[2]+padding, bbox[3]+padding)
            draw.rectangle(bg_bbox, fill='#cccccc')  # Light grey background
            draw.text((x0+4, y0+4), label_text, fill='black', font=label_font)
            
            # Store delete button position info
            if fn:  # Only add delete button if photo has a filename
                delete_button_info.append({
                    'photo_index': i - 1,  # Convert to 0-based (within combined list)
                    'page_index': i - start_number,  # 0-based index within this page's photos
                    'pageno': pageno,  # Which page this photo belongs to
                    'filename': fn,
                    'x': int(x1) - 20,  # 20px from right edge
                    'y': int(y0) + 2,   # 2px from top edge
                    # Store full rectangle coordinates for drag handling
                    'rect_x0': int(x0),
                    'rect_y0': int(y0),
                    'rect_x1': int(x1),
                    'rect_y1': int(y1),
                })
    
    def _render_texts(self, draw, texts, frame_x, frame_y, scale, origin_left,
                     start_number, pageno, delete_button_info):
        """Render text blocks for a single page."""
        try:
            from PIL import ImageFont
            label_font = ImageFont.truetype('Arial', 16)
        except:
            label_font = None
        
        for i, t in enumerate(texts, start=start_number):
            left = t.get('area_left') or 0
            top = t.get('area_top') or 0
            w = t.get('area_width') or 0
            h = t.get('area_height') or 0

            # subtract origin_left so right-page areas are positioned relative to their page
            local_left = left - origin_left

            x0 = frame_x + local_left * scale
            y0 = frame_y + top * scale
            x1 = frame_x + (local_left + w) * scale
            y1 = frame_y + (top + h) * scale

            # Draw text block background (translucent light yellow)
            # Create a semi-transparent overlay
            from PIL import Image
            overlay = Image.new('RGBA', (int(x1-x0), int(y1-y0)), (255, 255, 204, 128))  # Light yellow, 50% opacity
            draw._image.paste(overlay, (int(x0), int(y0)), overlay)
            
            # Draw dashed frame (similar to page frame)
            self._draw_dashed_rectangle(draw, x0, y0, x1, y1, 'green', dash_length=5, gap_length=3, line_width=2)
            
            # Extract and display the actual text content
            raw_html = t.get('raw_html', '')
            plain_text = _extract_text_from_html(raw_html)
            
            # Get font size and alignment from parsed data
            font_size = t.get('font_size', 12)
            h_align = t.get('h_align', 'left')
            v_align = t.get('v_align', 'top')
            
            # Create font at the appropriate size (scale appropriately for display)
            try:
                # MCF coordinate system uses 254 DPI (10 units per mm)
                # Font sizes are in points (72 points = 1 inch)
                # So: 1 point = 254/72 ≈ 3.528 MCF units
                # Then scale converts MCF units to screen pixels
                display_font_size = max(8, int(font_size * 3.528 * scale))
                text_font = ImageFont.truetype('Arial', display_font_size)
            except:
                text_font = None
            
            if plain_text:
                # Draw the text content with alignment
                max_width = int(x1 - x0 - 8)  # 4px padding on each side
                if max_width > 0:
                    # Simple word wrapping
                    words = plain_text.split()
                    lines = []
                    current_line = []
                    
                    for word in words:
                        test_line = ' '.join(current_line + [word])
                        if text_font:
                            bbox = draw.textbbox((0, 0), test_line, font=text_font)
                            text_width = bbox[2] - bbox[0]
                        else:
                            text_width = len(test_line) * 6  # Rough estimate
                        
                        if text_width <= max_width:
                            current_line.append(word)
                        else:
                            if current_line:
                                lines.append(' '.join(current_line))
                                current_line = [word]
                            else:
                                lines.append(word)  # Word too long, add anyway
                    
                    if current_line:
                        lines.append(' '.join(current_line))
                    
                    # Calculate line height from font
                    if text_font:
                        # Get actual line height from font metrics
                        bbox = draw.textbbox((0, 0), 'Ay', font=text_font)
                        line_height = int((bbox[3] - bbox[1]) * 1.2)  # Add 20% for line spacing
                    else:
                        line_height = 14
                    
                    total_text_height = len(lines) * line_height
                    box_height = y1 - y0
                    
                    # Calculate vertical position based on alignment
                    if v_align == 'center':
                        y_start = y0 + (box_height - total_text_height) / 2
                    elif v_align == 'bottom':
                        y_start = y1 - total_text_height - 4
                    else:  # top
                        y_start = y0 + 4
                    
                    # Draw each line with horizontal alignment
                    y_offset = y_start
                    for line in lines:
                        if y_offset < y1:  # Only draw if within bounds
                            # Calculate horizontal position based on alignment
                            if text_font:
                                bbox = draw.textbbox((0, 0), line, font=text_font)
                                line_width = bbox[2] - bbox[0]
                            else:
                                line_width = len(line) * 6
                            
                            if h_align == 'center':
                                x_pos = x0 + (x1 - x0 - line_width) / 2
                            elif h_align == 'right':
                                x_pos = x1 - line_width - 4
                            else:  # left
                                x_pos = x0 + 4
                            
                            draw.text((x_pos, y_offset), line, fill='black', font=text_font)
                            y_offset += line_height
                        else:
                            break
            
            # Draw label in top-left corner
            draw.text((x0+4, y0+4), f'T{i}', fill='green', font=label_font)
            
            # Store delete button position info for text boxes
            delete_button_info.append({
                'text_index': i - 1,  # Convert to 0-based (within combined list)
                'page_index': i - start_number,  # 0-based index within this page's texts
                'pageno': pageno,  # Which page this text belongs to
                'x': int(x1) - 20,  # 20px from right edge
                'y': int(y0) + 2,   # 2px from top edge
            })
    
    def _draw_page_frame(self, draw, frame_x, frame_y, frame_w, frame_h, frame_color):
        """Draw dashed frame around a page."""
        dash_length = 10
        gap_length = 5
        line_width = 2
        
        # Helper function to draw dashed line
        def draw_dashed_line(x1, y1, x2, y2):
            # Calculate line length and direction
            dx = x2 - x1
            dy = y2 - y1
            length = (dx**2 + dy**2)**0.5
            if length == 0:
                return
            
            # Unit vector
            ux = dx / length
            uy = dy / length
            
            # Draw dashes
            pos = 0
            while pos < length:
                # Start of dash
                start_x = x1 + ux * pos
                start_y = y1 + uy * pos
                # End of dash
                end_pos = min(pos + dash_length, length)
                end_x = x1 + ux * end_pos
                end_y = y1 + uy * end_pos
                
                draw.line([(start_x, start_y), (end_x, end_y)], fill=frame_color, width=line_width)
                pos += dash_length + gap_length
        
        # Draw four sides as dashed lines
        draw_dashed_line(frame_x, frame_y, frame_x + frame_w, frame_y)  # Top
        draw_dashed_line(frame_x + frame_w, frame_y, frame_x + frame_w, frame_y + frame_h)  # Right
        draw_dashed_line(frame_x + frame_w, frame_y + frame_h, frame_x, frame_y + frame_h)  # Bottom
        draw_dashed_line(frame_x, frame_y + frame_h, frame_x, frame_y)  # Left
    
    def _draw_dashed_rectangle(self, draw, x0, y0, x1, y1, color, dash_length=5, gap_length=3, line_width=2):
        """Draw a dashed rectangle outline.
        
        Args:
            draw: PIL ImageDraw object
            x0, y0: Top-left corner coordinates
            x1, y1: Bottom-right corner coordinates
            color: Line color
            dash_length: Length of each dash
            gap_length: Length of gap between dashes
            line_width: Width of the line
        """
        # Helper function to draw dashed line
        def draw_dashed_line(xa, ya, xb, yb):
            # Calculate line length and direction
            dx = xb - xa
            dy = yb - ya
            length = (dx**2 + dy**2)**0.5
            if length == 0:
                return
            
            # Unit vector
            ux = dx / length
            uy = dy / length
            
            # Draw dashes
            pos = 0
            while pos < length:
                # Start of dash
                start_x = xa + ux * pos
                start_y = ya + uy * pos
                # End of dash
                end_pos = min(pos + dash_length, length)
                end_x = xa + ux * end_pos
                end_y = ya + uy * end_pos
                
                draw.line([(start_x, start_y), (end_x, end_y)], fill=color, width=line_width)
                pos += dash_length + gap_length
        
        # Draw four sides as dashed lines
        draw_dashed_line(x0, y0, x1, y0)  # Top
        draw_dashed_line(x1, y0, x1, y1)  # Right
        draw_dashed_line(x1, y1, x0, y1)  # Bottom
        draw_dashed_line(x0, y1, x0, y0)  # Left
    
    def _draw_crease_line(self, draw, crease_x, crease_y, crease_h, color):
        """Draw dotted line down the center crease in spread mode."""
        dot_length = 5
        gap_length = 5
        
        y_pos = crease_y
        while y_pos < crease_y + crease_h:
            end_y = min(y_pos + dot_length, crease_y + crease_h)
            draw.line([(crease_x, y_pos), (crease_x, end_y)], fill=color, width=1)
            y_pos += dot_length + gap_length

    def _draw_protected_overlay(self, draw, frame_x, frame_y, frame_w, frame_h):
        """Draw grey overlay text for protected inside cover pages.
        
        Args:
            draw: PIL ImageDraw object
            frame_x, frame_y: Frame position on canvas
            frame_w, frame_h: Frame dimensions in pixels
        """
        # Draw semi-transparent grey text in center of page
        text = "inside cover page always blank"
        
        # Try to use a reasonable font size
        try:
            from PIL import ImageFont
            # Try to find a system font - use smaller size for overlay
            font_size = int(min(frame_w, frame_h) / 20)  # 1/20th of smaller dimension
            try:
                # Try to load a system font
                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
            except:
                # Fall back to default font
                font = ImageFont.load_default()
        except:
            font = None
        
        # Get text bounding box for centering
        if font:
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        else:
            # Rough estimate for default font
            text_w = len(text) * 6
            text_h = 10
        
        # Center text in frame
        text_x = frame_x + (frame_w - text_w) / 2
        text_y = frame_y + (frame_h - text_h) / 2
        
        # Draw text in grey
        draw.text((text_x, text_y), text, fill='#888888', font=font)

    def _show_image(self, pil_img):
        """Display PIL image on the canvas."""
        self.photo_image = ImageTk.PhotoImage(pil_img)
        
        # Clear existing image if any
        if self.canvas_image_id is not None:
            self.canvas.delete(self.canvas_image_id)
        
        # Create image centered on canvas
        self.canvas_image_id = self.canvas.create_image(
            0, 0, anchor='nw', image=self.photo_image, tags='page_image'
        )
        
        # Ensure the image is at the bottom layer (below buttons and overlays)
        self.canvas.tag_lower('page_image')
    
    def _create_delete_buttons(self, button_info, delete_callback):
        """Create delete button widgets overlaid on photo/text thumbnails.
        
        Args:
            button_info: List of dicts with either:
                - 'photo_index', 'filename', 'x', 'y' for photos
                - 'text_index', 'x', 'y' for text boxes
            delete_callback: Function to call when button clicked
                           Signature: (item_type, page_index, pageno, identifier)
        """
        # Destroy any existing delete buttons from previous render
        self.clear_delete_buttons()
        
        # Create new delete buttons
        for info in button_info:
            x = info['x']
            y = info['y']
            
            # Determine if this is a photo or text box
            if 'photo_index' in info:
                page_idx = info['page_index']
                pn = info['pageno']
                filename = info['filename']
                cmd = lambda idx=page_idx, pageno=pn, fn=filename: delete_callback('photo', idx, pageno, fn)
            else:  # text_index
                page_idx = info['page_index']
                pn = info['pageno']
                cmd = lambda idx=page_idx, pageno=pn: delete_callback('text', idx, pageno, None)
            
            # Create small white X button with red text and precise pixel sizing
            btn = tk.Button(
                self.canvas,
                text='×',
                font=('Arial', 12, 'bold'),
                fg='red',
                bg='white',
                activeforeground='#cc0000',
                activebackground='#f0f0f0',
                width=18,
                height=18,
                image=self.delete_button_pixel,
                compound='center',
                bd=0,
                relief='flat',
                highlightthickness=0,
                padx=0,
                pady=0,
                command=cmd
            )
            btn.place(x=x, y=y)
            self.delete_buttons.append(btn)
    
    def _create_drag_rectangles(self, button_info):
        """Create invisible canvas rectangles for drag-and-drop photo swapping.
        
        Args:
            button_info: List of dicts with photo position info (rect_x0, rect_y0, rect_x1, rect_y1, etc.)
        """
        # Clear any existing drag rectangles
        self.clear_drag_rectangles()
        
        # Create invisible rectangles for each photo
        for info in button_info:
            if 'photo_index' not in info:
                continue  # Skip text boxes
            
            x0 = info['rect_x0']
            y0 = info['rect_y0']
            x1 = info['rect_x1']
            y1 = info['rect_y1']
            pageno = info['pageno']
            photo_idx = info['page_index']  # Use page_index (0-based within page)
            
            # Create invisible rectangle (no fill, no outline initially)
            rect_id = self.canvas.create_rectangle(
                x0, y0, x1, y1,
                outline='',
                width=0,
                tags=('photo_drag', f'photo_{pageno}_{photo_idx}')
            )
            self.canvas.tag_raise(f'photo_{pageno}_{photo_idx}')  # Bring to front

            # Bind drag events to this rectangle
            self.canvas.tag_bind(f'photo_{pageno}_{photo_idx}', '<ButtonPress-1>',
                                lambda e, pn=pageno, idx=photo_idx: self._on_drag_press(pn, idx, e))
            self.canvas.tag_bind(f'photo_{pageno}_{photo_idx}', '<B1-Motion>',
                                lambda e, pn=pageno, idx=photo_idx: self._on_drag_motion(pn, idx, e))
            
            self.drag_rectangles.append(rect_id)
        
        # Bind ButtonRelease globally on canvas (not per-photo) because mouse might
        # be over a different photo when released
        if self.drag_rectangles:
            self.canvas.bind('<ButtonRelease-1>', lambda e: self._on_drag_release(e))
    
    def clear_drag_rectangles(self):
        """Clear all drag rectangle canvas items."""
        for rect_id in self.drag_rectangles:
            self.canvas.delete(rect_id)
        self.drag_rectangles.clear()
    
    def highlight_photo_as_source(self, rect_id, highlight=True):
        """Highlight a photo rectangle as drag source (green border).
        
        Args:
            rect_id: Canvas rectangle ID
            highlight: True to highlight, False to un-highlight
        """
        if highlight:
            self.canvas.itemconfig(rect_id, outline='green', width=3)
        else:
            self.canvas.itemconfig(rect_id, outline='', width=0)
    
    def highlight_photo_as_target(self, rect_id, highlight=True):
        """Highlight a photo rectangle as drop target (green border).
        
        Args:
            rect_id: Canvas rectangle ID
            highlight: True to highlight, False to un-highlight
        """
        if highlight:
            self.canvas.itemconfig(rect_id, outline='green', width=3)
        else:
            self.canvas.itemconfig(rect_id, outline='', width=0)
    
    def create_drag_thumbnail(self, x, y):
        """Create a small colored rectangle that follows the cursor during drag.
        
        Args:
            x, y: Canvas coordinates for thumbnail center
            
        Returns:
            Canvas rectangle ID
        """
        size = 50  # 50x50 pixel square
        rect_id = self.canvas.create_rectangle(
            x - size//2, y - size//2,
            x + size//2, y + size//2,
            outline='blue', width=2,
            fill='lightblue', stipple='gray50',
            tags='drag_thumbnail'
        )
        # Ensure thumbnail is on top
        self.canvas.tag_raise('drag_thumbnail')
        return rect_id
    
    def update_drag_thumbnail(self, rect_id, x, y):
        """Update drag thumbnail position to follow cursor.
        
        Args:
            rect_id: Canvas rectangle ID of the thumbnail
            x, y: New canvas coordinates for thumbnail center
        """
        size = 50
        self.canvas.coords(rect_id,
                          x - size//2, y - size//2,
                          x + size//2, y + size//2)
    
    def delete_drag_thumbnail(self, rect_id):
        """Delete the drag thumbnail rectangle.
        
        Args:
            rect_id: Canvas rectangle ID to delete
        """
        self.canvas.delete(rect_id)
    
    def _on_drag_press(self, pageno, photo_idx, event):
        """Handle mouse press on a photo rectangle - start drag operation.
        
        Args:
            pageno: Page number of the photo
            photo_idx: Index of photo within the page (0-based)
            event: Tkinter event object
        """
        # Start drag operation
        self.drag_active = True
        self.drag_source_pageno = pageno
        self.drag_source_photo_idx = photo_idx
        
        # Find and highlight the source rectangle
        tag = f'photo_{pageno}_{photo_idx}'
        items = self.canvas.find_withtag(tag)
        if items:
            self.drag_source_rect_id = items[0]
            self.highlight_photo_as_source(self.drag_source_rect_id, True)
    
    def _on_drag_motion(self, pageno, photo_idx, event):
        """Handle mouse motion during drag - update thumbnail and detect target.
        
        Args:
            pageno: Page number where drag started
            photo_idx: Index of photo where drag started
            event: Tkinter event object
        """
        if not self.drag_active:
            return
        
        # Find which photo rectangle contains the cursor
        # We programmatically check which rectangle contains the point
        new_hover_pageno = None
        new_hover_photo_idx = None
        new_hover_rect_id = None
        
        for rect_id in self.drag_rectangles:
            # Get rectangle coordinates
            coords = self.canvas.coords(rect_id)
            if len(coords) == 4:
                x0, y0, x1, y1 = coords
                # Check if cursor is inside this rectangle
                if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                    # Get tags to extract pageno and photo_idx
                    tags = self.canvas.gettags(rect_id)
                    for tag in tags:
                        if tag.startswith('photo_') and '_' in tag[6:]:
                            parts = tag.split('_')
                            if len(parts) == 3:
                                try:
                                    hover_pn = int(parts[1])
                                    hover_idx = int(parts[2])
                                    # Don't highlight source photo as destination
                                    if not (hover_pn == self.drag_source_pageno and hover_idx == self.drag_source_photo_idx):
                                        new_hover_pageno = hover_pn
                                        new_hover_photo_idx = hover_idx
                                        new_hover_rect_id = rect_id
                                        break
                                except ValueError:
                                    continue
                    if new_hover_rect_id:
                        break
        
        # Update highlighting if hover target changed
        if new_hover_rect_id != self.drag_hover_rect_id:
            # Un-highlight old target
            if self.drag_hover_rect_id:
                self.highlight_photo_as_target(self.drag_hover_rect_id, False)
            
            # Highlight new target
            if new_hover_rect_id:
                self.highlight_photo_as_target(new_hover_rect_id, True)
            
            # Update state
            self.drag_hover_rect_id = new_hover_rect_id
            self.drag_hover_pageno = new_hover_pageno
            self.drag_hover_photo_idx = new_hover_photo_idx
        
        # Update or create thumbnail at new position
        if not self.drag_thumbnail_id:
            self.drag_thumbnail_id = self.create_drag_thumbnail(event.x, event.y)
        else:
            self.update_drag_thumbnail(self.drag_thumbnail_id, event.x, event.y)
    
    def _on_drag_release(self, event):
        """Handle mouse release - complete drag operation and execute swap if valid.
        
        Args:
            event: Tkinter event object
        """
        if not self.drag_active:
            return
        
        # Check if we have a valid swap target
        if self.drag_hover_rect_id and self.drag_hover_pageno is not None and self.swap_callback:
            # Execute swap via callback to business logic
            self.swap_callback(
                self.drag_source_pageno, self.drag_source_photo_idx,
                self.drag_hover_pageno, self.drag_hover_photo_idx
            )
        
        # Clean up visual state
        self._clear_drag_state()
    
    def _clear_drag_state(self):
        """Reset all drag-related visual state."""
        if self.drag_source_rect_id:
            self.highlight_photo_as_source(self.drag_source_rect_id, False)
        if self.drag_hover_rect_id:
            self.highlight_photo_as_target(self.drag_hover_rect_id, False)
        if self.drag_thumbnail_id:
            self.delete_drag_thumbnail(self.drag_thumbnail_id)
        
        self.drag_active = False
        self.drag_source_pageno = None
        self.drag_source_photo_idx = None
        self.drag_source_rect_id = None
        self.drag_hover_pageno = None
        self.drag_hover_photo_idx = None
        self.drag_hover_rect_id = None
        self.drag_thumbnail_id = None
    
    def get_thumbnail(self, path: str, w: int, h: int):
        """Get thumbnail for an image, using cache if available.
        
        Two modes:
        1. cache_full_images=True: Cache full image, render on-the-fly (faster, more RAM)
        2. cache_full_images=False: Cache size-specific thumbnails (slower, less RAM)
        
        Args:
            path: Path to the image file
            w: Thumbnail width in pixels
            h: Thumbnail height in pixels
        
        Returns:
            PIL Image of size (w, h), or None if load fails
        """
        from .file_utils import extract_metadata_from_filename
        
        # Avoid creating huge thumbnails
        if w <= 0 or h <= 0:
            return None
        
        # Get cache key components
        path_obj = Path(path)
        filename = path_obj.name
        base_filename, _, _ = extract_metadata_from_filename(filename)
        
        try:
            file_size = os.path.getsize(path) if os.path.exists(path) else 0
        except:
            file_size = 0
        
        if self.cache_full_images:
            # MODE 1: Cache full image, render on-the-fly
            cache_key = (base_filename, file_size)
            
            if cache_key not in self.full_image_cache:
                # Cache miss - load full image
                if not path or not path_obj.exists():
                    logger.error(f"get_thumbnail: Path does not exist: {path}")
                    return None
                
                try:
                    logger.debug(f"get_thumbnail: Loading full image from {path}")
                    im = Image.open(path)
                    # Auto-orient based on EXIF
                    from PIL import ImageOps
                    im = ImageOps.exif_transpose(im)
                    # Convert to RGB if needed (handles RGBA, grayscale, etc.)
                    if im.mode != 'RGB':
                        im = im.convert('RGB')
                    self.full_image_cache[cache_key] = im
                    logger.debug(f"get_thumbnail: Cached full image {path}, size={im.size}")
                except Exception as e:
                    logger.error(f"get_thumbnail: Failed to load image {path}: {e}")
                    return None
            else:
                logger.debug(f"get_thumbnail: Using cached image for {base_filename}")
            
            # Get cached full image
            full_img = self.full_image_cache.get(cache_key)
            if full_img is None:
                logger.error(f"get_thumbnail: Cache returned None for {path}")
                return None
            
            # Render thumbnail from full image
            try:
                thumb = full_img.copy()
                thumb.thumbnail((w, h), Image.Resampling.LANCZOS)
                logger.debug(f"get_thumbnail: Created thumbnail {w}x{h} from {path}, actual size={thumb.size}")
                return thumb
            except Exception as e:
                logger.error(f"get_thumbnail: Failed to create thumbnail for {path}: {e}")
                return None
        
        else:
            # MODE 2: Cache size-specific thumbnails
            cache_key = (base_filename, file_size, w, h)
            
            if cache_key not in self.thumb_cache:
                # Cache miss - load and create thumbnail
                if not path or not path_obj.exists():
                    return None
                
                try:
                    im = Image.open(path)
                    from PIL import ImageOps
                    im = ImageOps.exif_transpose(im)
                    if im.mode != 'RGB':
                        im = im.convert('RGB')
                    im.thumbnail((w, h), Image.Resampling.LANCZOS)
                    self.thumb_cache[cache_key] = im
                except Exception as e:
                    logger.warning(f"Failed to load/thumbnail image {path}: {e}")
                    return None
            
            return self.thumb_cache.get(cache_key)
    
    def draw_segmentation_overlay(self, segments: list, canvas_w: int, canvas_h: int, 
                                   page_width: float, page_height: float, 
                                   margin_mcf: float, origin_left: float = 0.0):
        """Draw overlay showing segmentation rectangles on the current page image.
        
        Args:
            segments: List of segment dicts with 'left', 'top', 'width', 'height' in image coordinates
            canvas_w: Canvas width in pixels
            canvas_h: Canvas height in pixels
            page_width: Page width in MCF units
            page_height: Page height in MCF units
            margin_mcf: Display margin in MCF units
            origin_left: Left origin offset for right pages in MCF units
        """
        if not self.photo_image:
            logger.warning("No current page image to draw overlay on")
            return
        
        # Get the underlying PIL Image
        # We need to draw on a copy since PhotoImage doesn't support direct drawing
        # Get current displayed image dimensions
        display_img = self.photo_image
        
        # Create a copy of the current display as PIL Image
        # Since we can't easily extract from PhotoImage, we'll draw on top of it using canvas items
        # Store overlay data for canvas rendering
        self.overlay_segments = segments
        self.overlay_canvas_w = canvas_w
        self.overlay_canvas_h = canvas_h
        self.overlay_page_width = page_width
        self.overlay_page_height = page_height
        self.overlay_margin_mcf = margin_mcf
        self.overlay_origin_left = origin_left
    
    def get_overlay_rectangles(self):
        """Get overlay rectangle coordinates in spread-relative canvas pixels.
        
        This function converts segment coordinates from PDF-based MCF to CEWE MCF,
        then to canvas pixels, keeping them in SPREAD-RELATIVE space. This means:
        - Left pages (origin_left=0): rectangles have small x values (0 to page_width pixels)
        - Right pages (origin_left=page_width): rectangles have LARGE x values (page_width to 2*page_width pixels)
        
        The actual drawing code (_draw_overlay_rectangles_on_canvas) is responsible for
        converting these spread-relative coordinates to screen coordinates by subtracting
        the x-offset for single-page display.
        
        Returns:
            List of (x1, y1, x2, y2) tuples in spread-relative canvas pixel coordinates
        """
        if not hasattr(self, 'overlay_segments') or not self.overlay_segments:
            return []
        
        segments = self.overlay_segments
        canvas_w = self.overlay_canvas_w
        canvas_h = self.overlay_canvas_h
        page_width = self.overlay_page_width  # CEWE page dimensions
        page_height = self.overlay_page_height
        margin_mcf = self.overlay_margin_mcf
        origin_left = self.overlay_origin_left
        
        logger.info(f"Overlay calculation: canvas={canvas_w}x{canvas_h}, CEWE page={page_width}x{page_height} MCF, margin={margin_mcf}")
        
        # Get PDF-to-CEWE scale factors from segment metadata if available
        # Segments have PDF-based MCF coordinates that need scaling to CEWE dimensions
        first_seg = segments[0] if segments else {}
        pdf_page_width = first_seg.get('_pdf_page_width_mcf')
        pdf_page_height = first_seg.get('_pdf_page_height_mcf')
        
        if pdf_page_width and pdf_page_height:
            # Calculate scale factors from PDF MCF to CEWE MCF
            pdf_to_cewe_scale_x = page_width / pdf_page_width
            pdf_to_cewe_scale_y = page_height / pdf_page_height
            logger.info(f"  PDF→CEWE scale: x={pdf_to_cewe_scale_x:.6f}, y={pdf_to_cewe_scale_y:.6f}")
        else:
            # Fallback: assume PDF == CEWE dimensions
            pdf_to_cewe_scale_x = 1.0
            pdf_to_cewe_scale_y = 1.0
            logger.warning(f"  No PDF dimension metadata in segments, assuming PDF == CEWE")
        
        scale = self._getScale()

        logger.info(f"Scale factor (CEWE MCF to pixels): {scale} pixels/MCF")
        
        rectanglesSpreadRelative = []
        for i, seg in enumerate(segments):
            # Segment coordinates are in PDF-based MCF spread units from PDF extraction
            # Scale them to CEWE MCF dimensions first
            seg_left_pdf = seg['left']
            seg_top_pdf = seg['top']
            seg_width_pdf = seg['width']
            seg_height_pdf = seg['height']
            
            seg_left_mcf = seg_left_pdf * pdf_to_cewe_scale_x
            seg_top_mcf = seg_top_pdf * pdf_to_cewe_scale_y
            seg_width_mcf = seg_width_pdf * pdf_to_cewe_scale_x
            seg_height_mcf = seg_height_pdf * pdf_to_cewe_scale_y
            
            logger.info(f"  Segment {i} (PDF MCF): left={seg_left_pdf:.1f}, top={seg_top_pdf:.1f}, "
                       f"width={seg_width_pdf:.1f}, height={seg_height_pdf:.1f}")
            logger.info(f"           (CEWE MCF): left={seg_left_mcf:.1f}, top={seg_top_mcf:.1f}, "
                       f"width={seg_width_mcf:.1f}, height={seg_height_mcf:.1f}")
            logger.info(f"  origin_left={origin_left}")
            
            # Convert from MCF spread coordinates to canvas pixels
            # Keep coordinates in spread-relative space (large x values for right pages)
            # The actual drawing code will adjust for single-page vs spread view
            x1 = int((margin_mcf + seg_left_mcf) * scale)
            y1 = int((margin_mcf + seg_top_mcf) * scale)
            x2 = int((margin_mcf + seg_left_mcf + seg_width_mcf) * scale)
            y2 = int((margin_mcf + seg_top_mcf + seg_height_mcf) * scale)
            
            logger.info(f"  Canvas coords: ({x1}, {y1}) to ({x2}, {y2}), size={x2-x1}x{y2-y1}")
            
            rectanglesSpreadRelative.append((x1, y1, x2, y2))
        
        return rectanglesSpreadRelative
    
    def clear_overlay(self):
        """Clear the segmentation overlay."""
        if hasattr(self, 'overlay_segments'):
            del self.overlay_segments
            del self.overlay_canvas_w
            del self.overlay_canvas_h
            del self.overlay_page_width
            del self.overlay_page_height
            del self.overlay_margin_mcf
            del self.overlay_origin_left
    
    def show_segmentation_overlay(self, canvas, segments, canvas_w, canvas_h,
                                   page_width, page_height, margin_mcf, origin_left,
                                   accept_callback, reject_callback, button_frame_parent):
        """Show overlay with segmentation rectangles and accept/reject buttons.
        
        Args:
            canvas: Canvas widget to draw on
            segments: List of segment dicts from segmentation
            canvas_w, canvas_h: Canvas dimensions
            page_width, page_height: Page dimensions in MCF units
            margin_mcf: Display margin in MCF units
            origin_left: Left origin offset for right pages
            accept_callback: Function to call when user accepts
            reject_callback: Function to call when user rejects
            button_frame_parent: Parent widget for button frame
            
        Returns:
            Tuple of (overlay_items, button_frame) for cleanup
        """
        # Store overlay data for coordinate calculation
        self.draw_segmentation_overlay(
            segments, canvas_w, canvas_h, page_width, page_height,
            margin_mcf, origin_left
        )
        
        # Draw rectangles on canvas
        overlay_items = self._draw_overlay_rectangles_on_canvas(canvas)
        
        # Create button frame
        button_frame = self._create_overlay_buttons(
            button_frame_parent, accept_callback, reject_callback
        )
        
        return overlay_items, button_frame
    
    def _draw_overlay_rectangles_on_canvas(self, canvas):
        """Draw the overlay rectangles on the canvas.
        
        Args:
            canvas: Canvas widget to draw on
            
        Returns:
            List of canvas item IDs for cleanup
        """
        # Get rectangle coordinates (in spread-relative canvas pixels)
        rectangles = self.get_overlay_rectangles()
        
        logger.info(f"Drawing {len(rectangles)} overlay rectangles")
        
        # Calculate pixel offset for single-page display
        # In spread view, this would be 0; in single-page view, we subtract the page offset
        origin_left = self.overlay_origin_left
        scale = self._getScale()

        # Calculate the pixel offset to subtract for single-page view
        # This is THE single point where spread-relative coordinates are converted to screen coordinates
        x_offset_pixels = origin_left * scale
        
        logger.info(f"Drawing with origin_left={origin_left} MCF, x_offset={x_offset_pixels:.1f} pixels")
        
        overlay_items = []
        
        # Draw each rectangle as a green outline
        for i, (x1, y1, x2, y2) in enumerate(rectangles):
            # Adjust x coordinates for single-page display (subtract offset for right pages)
            # For left pages: origin_left=0 → x_offset_pixels=0 → no change
            # For right pages: origin_left=page_width → subtract page_width to make page-relative
            display_x1 = x1 - x_offset_pixels
            display_x2 = x2 - x_offset_pixels
            
            logger.info(f"  Drawing rectangle {i}: spread=({x1}, {y1})-({x2}, {y2}) → display=({display_x1:.0f}, {y1})-({display_x2:.0f}, {y2})")
            
            # Draw green outline only (no fill)
            rect_id = canvas.create_rectangle(
                display_x1, y1, display_x2, y2,
                fill='',  # No fill
                outline='#00ff00',  # Bright green outline
                width=5,
                tags='overlay'
            )
            overlay_items.append(rect_id)
        
        # Ensure overlay rectangles appear above the image
        for item_id in overlay_items:
            canvas.tag_raise(item_id)
        
        logger.info(f"Created {len(overlay_items)} overlay items")
        return overlay_items

    def _getScale(self) -> float:
        margin_mcf = self.overlay_margin_mcf
        canvas_w = self.overlay_canvas_w
        canvas_h = self.overlay_canvas_h
        page_width = self.overlay_page_width
        page_height = self.overlay_page_height

        total_w_mcf = page_width + 2 * margin_mcf
        total_h_mcf = page_height + 2 * margin_mcf
        scale = min(canvas_w / total_w_mcf, canvas_h / total_h_mcf)
        return scale

    def _create_overlay_buttons(self, parent, accept_callback, reject_callback):
        """Create accept/reject buttons in the overlay.
        
        Args:
            parent: Parent widget for button frame
            accept_callback: Function to call when user accepts
            reject_callback: Function to call when user rejects
            
        Returns:
            Button frame widget
        """
        from tkinter import ttk
        
        logger.info("Creating overlay accept/reject buttons in control window")
        
        button_frame = ttk.Frame(parent)
        button_frame.grid(row=10, column=0, columnspan=3, sticky='ew', padx=4, pady=10)
        
        ttk.Label(button_frame, text='New segmentation:', font=('TkDefaultFont', 10, 'bold')).pack(side='left', padx=(0, 10))
        
        accept_btn = ttk.Button(button_frame, text='✓ Accept', command=accept_callback)
        accept_btn.pack(side='left', padx=(0, 5))
        
        reject_btn = ttk.Button(button_frame, text='✗ Reject', command=reject_callback)
        reject_btn.pack(side='left')
        
        return button_frame
    
    def clear_overlay_from_canvas(self, canvas, overlay_items):
        """Clear overlay items from canvas.
        
        Args:
            canvas: Canvas widget
            overlay_items: List of canvas item IDs to remove
        """
        for item_id in overlay_items:
            canvas.delete(item_id)
        
        # Clear stored overlay data
        self.clear_overlay()
