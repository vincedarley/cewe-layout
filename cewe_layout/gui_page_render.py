"""Pure rendering engine for photobook pages - no business logic, only visualization."""
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk
from dataclasses import dataclass
import os
from pathlib import Path
import logging
import re
import html
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        self.delete_button_info_list = []  # List of button info for hover state management
        self.drag_rectangles = []  # Currently displayed drag rectangle canvas items
        try:
            from PIL import ImageFont
            self.label_font = ImageFont.truetype('Arial', 16)
        except:
            self.label_font = None
        
        # Hover state for delete button visibility
        self.hovered_item_idx = None  # Index of currently hovered item (or None)
        self.hide_button_timer = None  # Timer ID for delayed button hiding
        
        # Cropping/scaling mode
        self.functional_rendering = True  # If false, render for accuracy and apply cutout/scale transformations
        
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
        
        # Persistent thread pool for parallel thumbnail loading (avoids shutdown overhead)
        self.thumbnail_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="thumbnail_loader")
    
    def render_pages(self, 
                    page_data_list: list,  # List of PageRenderData
                    canvas_w: int,
                    canvas_h: int,
                    margin_mcf: float,
                    delete_callback,
                    show_pdf_composite: bool = False,
                    protected_inside_covers: list = None,
                    swap_callback = None,
                    functional_rendering: bool = True) -> None:
        """Render one or more pages to the display.
        
        Args:
            page_data_list: List of PageRenderData objects (1 for single, 2 for spread)
            canvas_w, canvas_h: Canvas dimensions in pixels
            margin_mcf: Display margin in MCF units
            delete_callback: Function to call when delete button clicked
                           Signature: (item_type, item_index, pageno, identifier)
                           where item_type is 'photo' or 'text'
            protected_inside_covers: List of page numbers that are protected (inside covers)
            swap_callback: Optional callback for photo swap completion
                          Signature: (source_pageno, source_photo_idx, dest_pageno, dest_photo_idx)
                          Called when user successfully drags and drops to swap two photos
            functional_rendering: If True, render UI in a rougher form optimised for functionality,
                          If false, then try to be as accurate as possible in the render.
        """
        # Store functional_rendering mode
        self.functional_rendering = functional_rendering
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
        
        # Create canvas image with grey background (will draw page backgrounds per-page)
        # the grey border that will remain shows what will be cut-off during printing process.
        img = Image.new('RGB', (canvas_w, canvas_h), 'grey')
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
        
        # Render each page background first (avoids issues where photos overlap spread)
        # Skip if showing PDF composite (composite serves as background)
        if not show_pdf_composite:
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
                draw.rectangle(
                    [frame_x, frame_y, frame_x + frame_w, frame_y + frame_h],
                    fill=page_bg_color
                )

        # Render contents and framing of each page
        for page_offset, page_data in enumerate(page_data_list):
            # Get background and frame colors for this specific page
            page_bg_color, frame_color = getBackgroundAndFrameColour(page_data.background_id)
            
            # Calculate frame position for this page
            # In spread mode, second page is offset by page_w
            page_x_offset = page_offset * page_w if len(page_data_list) == 2 else 0
            frame_x = margin_mcf * scale + page_x_offset * scale
            frame_y = margin_mcf * scale
            
            # Render photos for this page
            self._render_photos(img, draw, page_data.photos, frame_x, frame_y, scale, 
                               page_data.origin_left, photo_counter, page_data.pageno, 
                               delete_button_info, page_bg_color)
            photo_counter += len(page_data.photos)
            
            # Render texts for this page
            self._render_texts(draw, page_data.texts, frame_x, frame_y, scale,
                              page_data.origin_left, text_counter, page_data.pageno,
                              delete_button_info)
            text_counter += len(page_data.texts)
            
            frame_w = page_w * scale
            frame_h = page_h * scale
            # Lastly, draw page frame for this page
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
        
        # Create invisible hover rectangles for all items (always needed for delete button hover)
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
        # Cancel any pending hide timers
        if self.hide_button_timer:
            self.canvas.after_cancel(self.hide_button_timer)
            self.hide_button_timer = None
        
        for btn in self.delete_buttons:
            btn.destroy()
        self.delete_buttons.clear()
        self.delete_button_info_list.clear()
        self.hovered_item_idx = None
    
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
            comp_left_mcf = page_data.composite_image.get('area_left', 0)
            comp_top_mcf = page_data.composite_image.get('area_top', 0)
            comp_width_mcf = page_data.composite_image.get('area_width', 0)
            comp_height_mcf = page_data.composite_image.get('area_height', 0)
            
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
    
    def _preload_thumbnails_parallel(self, photos, frame_x, frame_y, scale, origin_left, start_number):
        """Preload all thumbnails for a page in parallel using threads.
        
        Args:
            photos: List of photo dictionaries
            frame_x, frame_y: Frame offset coordinates
            scale: Scaling factor
            origin_left: Left origin for page positioning
            start_number: Starting photo number
            
        Returns:
            Dict mapping photo index -> PIL Image (thumbnail)
        """
        thumbnail_map = {}
        
        # Build list of (index, path, width, height, mcf_filename) tuples
        load_tasks = []
        for i, p in enumerate(photos, start=start_number):
            fn = p.get('filename') or ''
            if not fn:
                continue
            
            # Calculate thumbnail dimensions
            left = p.get('area_left') or 0
            top = p.get('area_top') or 0
            w = p.get('area_width') or 0
            h = p.get('area_height') or 0
            local_left = left - origin_left
            x0 = frame_x + local_left * scale
            y0 = frame_y + top * scale
            x1 = frame_x + (local_left + w) * scale
            y1 = frame_y + (top + h) * scale
            thumb_w = int(x1 - x0)
            thumb_h = int(y1 - y0)
            
            # Resolve image path
            if '_source_path' in p:
                img_path = p['_source_path']
            else:
                from .file_utils import split_safecontainer_prefix
                prefix, clean_fn = split_safecontainer_prefix(fn)
                
                if self.image_folder_attr:
                    img_path = os.path.join(self.mcf_base_folder, self.image_folder_attr, clean_fn)
                else:
                    img_path = os.path.join(self.mcf_base_folder, clean_fn)
                
                # Try alternative location if not found
                if not os.path.exists(img_path):
                    alt_path = os.path.join(self.mcf_base_folder, clean_fn)
                    if os.path.exists(alt_path):
                        img_path = alt_path
                    else:
                        img_path = None
            
            if img_path and os.path.exists(img_path):
                # Extract cutout/scale info if available
                cutout_left = p.get('cutout_left')
                cutout_top = p.get('cutout_top')
                cutout_scale = p.get('cutout_scale')
                slot_width_mcf = w  # Slot dimensions in MCF units
                slot_height_mcf = h
                load_tasks.append((i, img_path, thumb_w, thumb_h, fn, cutout_left, cutout_top, cutout_scale, slot_width_mcf, slot_height_mcf))
        
        # Load thumbnails in parallel using ThreadPoolExecutor
        def load_one(task):
            idx, path, w, h, mcf_fn, cleft, ctop, cscale, slot_w, slot_h = task
            try:
                thumb = self.get_thumbnail(path, w, h, mcf_filename=mcf_fn,
                                          cutout_left=cleft, cutout_top=ctop, cutout_scale=cscale,
                                          slot_width_mcf=slot_w, slot_height_mcf=slot_h)
                return (idx, thumb)
            except Exception as e:
                logger.error(f"Failed to load thumbnail {idx}: {e}")
                return (idx, None)
        
        # Use persistent thread pool (no shutdown overhead)
        futures = [self.thumbnail_executor.submit(load_one, task) for task in load_tasks]
        for future in as_completed(futures):
            idx, thumb = future.result()
            if thumb is not None:
                thumbnail_map[idx] = thumb
        
        return thumbnail_map
    
    def _render_photos(self, img, draw, photos, frame_x, frame_y, scale, origin_left, 
                      start_number, pageno, delete_button_info, page_bg_color):
        """Render photos for a single page.
        
        """

        # Preload all thumbnails in parallel
        thumbnail_map = self._preload_thumbnails_parallel(photos, frame_x, frame_y, scale, origin_left, start_number)
        
        # NOTE: Grey borders appear when the image is smaller than the slot because:
        # 1. PIL's thumbnail() preserves aspect ratio and never upscales
        # 2. If image pixels < slot pixels, the thumbnail stays at original size
        # 3. We center the smaller thumbnail, leaving grey borders visible
        # This commonly happens with because photo pixel dimensions
        # will not exactly match the MCF area_width/area_height values.
        draw_background_and_frame = self.functional_rendering

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
                # Get preloaded thumbnail
                thumb = thumbnail_map.get(i)
                
                if thumb is not None:
                    # Draw grey background first
                    if draw_background_and_frame:
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
                    # draw a light placeholder for missing/failed thumbnail
                    logger.error(f"Photo {i}: Thumbnail not found in preload map (filename: {fn})")
                    draw.rectangle([x0, y0, x1, y1], fill='#eeeeee')

            # wireframe overlay for photo slot - draw if we need to, or if there is no photo then we have to.
            if draw_background_and_frame or not fn:
                draw.rectangle([x0, y0, x1, y1], outline='blue', width=2)

            if not self.functional_rendering:
                border_color = p.get('border_color_rgb')
                border_width = p.get('border_width', 0)  # 0.1mm units
                
                # Draw frame if specified
                if border_color and border_width > 0:
                    border_width_px = max(1, int(border_width * scale))
                    draw.rectangle([x0, y0, x1, y1], outline=border_color, width=border_width_px)

            # Photo number label with light grey background
            label_text = f'{i}'
            if self.label_font:
                bbox = draw.textbbox((x0+4, y0+4), label_text, font=self.label_font)
            else:
                # Fallback bounding box estimation
                bbox = (x0+4, y0+4, x0+30, y0+24)
            
            # Add padding around text
            padding = 3
            bg_bbox = (bbox[0]-padding, bbox[1]-padding, bbox[2]+padding, bbox[3]+padding)
            draw.rectangle(bg_bbox, fill='#cccccc')  # Light grey background
            draw.text((x0+4, y0+4), label_text, fill='black', font=self.label_font)
            
            # Store delete button position info (for both filled and empty photo slots)
            delete_button_info.append({
                'photo_index': i - 1,  # Convert to 0-based (within combined list)
                'item_index': i - start_number,  # 0-based index within this page's photos
                'pageno': pageno,  # Which page this photo belongs to
                'filename': fn,  # May be None or empty string for empty slots
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

            # Decide which rendering mode to use based on functional_rendering flag
            if self.functional_rendering:
                # Functional rendering mode: use old default visualization colors
                from PIL import Image
                overlay = Image.new('RGBA', (int(x1-x0), int(y1-y0)), (255, 255, 204, 128))  # Light yellow, 50% opacity
                draw._image.paste(overlay, (int(x0), int(y0)), overlay)
                
                # Draw default dashed green frame
                self._draw_dashed_rectangle(draw, x0, y0, x1, y1, 'green', dash_length=5, gap_length=3, line_width=2)
                
                # Use black text
                text_color = 'black'
            else:
                # Accurate rendering mode: use MCF colors (no fallback)
                bg_color = t.get('background_color_rgb')  # RGB format for PIL
                border_color = t.get('border_color_rgb')
                border_width = t.get('border_width', 0)  # 0.1mm units
                
                # Draw text block background if specified
                if bg_color:
                    from PIL import Image, ImageColor
                    rgb_tuple = ImageColor.getrgb(bg_color)  # Convert '#rrggbb' to (r, g, b)
                    overlay = Image.new('RGBA', (int(x1-x0), int(y1-y0)), rgb_tuple + (255,))  # Fully opaque
                    draw._image.paste(overlay, (int(x0), int(y0)), overlay)
                
                # Draw text block frame if specified
                if border_color and border_width > 0:
                    border_width_px = max(1, int(border_width * scale))
                    draw.rectangle([x0, y0, x1, y1], outline=border_color, width=border_width_px)
                
                # Use foreground color from MCF if available
                text_color = t.get('foreground_color_rgb', 'black')
            
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
                            
                            # text_color was already set above based on functional_rendering mode
                            draw.text((x_pos, y_offset), line, fill=text_color, font=text_font)
                            y_offset += line_height
                        else:
                            break
            
            # Draw label in top-left corner
            draw.text((x0+4, y0+4), f'T{i}', fill='green', font=self.label_font)
            
            # Store delete button position info for text boxes
            delete_button_info.append({
                'text_index': i - 1,  # Convert to 0-based (within combined list)
                'item_index': i - start_number,  # 0-based index within this page's texts
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
                           Signature: (item_type, item_index, pageno, identifier)
        """
        # Destroy any existing delete buttons from previous render
        self.clear_delete_buttons()
        
        # Store button info for hover state management
        self.delete_button_info_list = button_info
        
        # Create new delete buttons (initially hidden)
        for idx, info in enumerate(button_info):
            x = info['x']
            y = info['y']
            
            # Determine if this is a photo or text box
            if 'photo_index' in info:
                item_idx = info['item_index']
                pn = info['pageno']
                filename = info['filename']
                cmd = lambda idx=item_idx, pageno=pn, fn=filename: delete_callback('photo', idx, pageno, fn)
            else:  # text_index
                item_idx = info['item_index']
                pn = info['pageno']
                cmd = lambda idx=item_idx, pageno=pn: delete_callback('text', idx, pageno, None)
            
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
            # Place button at position (makes it visible)
            btn.place(x=x, y=y)
            
            # Immediately hide it (will be shown on hover)
            btn.place_forget()
            
            # Bind hover events to button itself to keep it visible when mouse moves onto it
            btn.bind('<Enter>', lambda e, i=idx: self._on_button_enter(i))
            btn.bind('<Leave>', lambda e, i=idx: self._on_button_leave(i))
            
            self.delete_buttons.append(btn)
    
    def _create_drag_rectangles(self, button_info):
        """Create invisible canvas rectangles for drag-and-drop photo swapping.
        
        Args:
            button_info: List of dicts with photo position info (rect_x0, rect_y0, rect_x1, rect_y1, etc.)
        """
        # Clear any existing drag rectangles
        self.clear_drag_rectangles()
        
        # Create invisible rectangles for each photo and text box
        for idx, info in enumerate(button_info):
            x0 = info.get('rect_x0')
            y0 = info.get('rect_y0')
            x1 = info.get('rect_x1')
            y1 = info.get('rect_y1')
            
            # For text boxes, rect coordinates may not be stored, calculate from x/y position
            if x0 is None or x1 is None:
                # Text box - estimate rectangle from button position
                # Button is at top-right, so we need to guess the text box area
                # This is approximate, but good enough for hover detection
                btn_x = info['x']
                btn_y = info['y']
                # Assume text box is roughly 200px wide and 100px tall, button at top-right
                x0 = btn_x - 200
                y0 = btn_y
                x1 = btn_x + 20  # Include button width
                y1 = btn_y + 100
            
            # Build tag list - always include item_idx for hover
            # For photos, also add photo_pageno_idx tag for drag-drop detection
            tag_list = ['item_hover', f'item_{idx}']
            if 'photo_index' in info:
                pageno = info['pageno']
                photo_idx = info['item_index']
                tag_list.append(f'photo_{pageno}_{photo_idx}')
            
            # Create invisible rectangle (no fill, no outline initially)
            rect_id = self.canvas.create_rectangle(
                x0, y0, x1, y1,
                outline='',
                width=0,
                tags=tuple(tag_list)
            )
            self.canvas.tag_raise(f'item_{idx}')  # Bring to front

            # Bind hover events for delete button visibility
            self.canvas.tag_bind(f'item_{idx}', '<Enter>',
                                lambda e, i=idx: self._on_photo_enter(i))
            self.canvas.tag_bind(f'item_{idx}', '<Leave>',
                                lambda e, i=idx: self._on_photo_leave(i))
            
            # Bind drag events only for photos (not text boxes)
            if 'photo_index' in info:
                pageno = info['pageno']
                photo_idx = info['item_index']
                self.canvas.tag_bind(f'item_{idx}', '<ButtonPress-1>',
                                    lambda e, pn=pageno, idx=photo_idx: self._on_drag_press(pn, idx, e))
                self.canvas.tag_bind(f'item_{idx}', '<B1-Motion>',
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
    
    # ========== Delete button hover management ==========
    
    def _on_photo_enter(self, idx):
        """Handle mouse entering a photo/text rectangle - show delete button.
        
        Args:
            idx: Index in delete_button_info_list
        """
        self.hovered_item_idx = idx
        self._show_delete_button(idx)
    
    def _on_photo_leave(self, idx):
        """Handle mouse leaving a photo/text rectangle - hide delete button with delay.
        
        Args:
            idx: Index in delete_button_info_list
        """
        # Only clear hover state if we're leaving the currently hovered item
        if self.hovered_item_idx == idx:
            self.hovered_item_idx = None
            # Delay hiding slightly to allow mouse to reach button
            self.hide_button_timer = self.canvas.after(50, lambda: self._check_and_hide_button(idx))
    
    def _on_button_enter(self, idx):
        """Handle mouse entering a delete button - keep it visible.
        
        Args:
            idx: Index in delete_button_info_list
        """
        self.hovered_item_idx = idx  # Keep button visible
        # Cancel any pending hide timer
        if self.hide_button_timer:
            self.canvas.after_cancel(self.hide_button_timer)
            self.hide_button_timer = None
    
    def _on_button_leave(self, idx):
        """Handle mouse leaving a delete button - hide it.
        
        Args:
            idx: Index in delete_button_info_list
        """
        self.hovered_item_idx = None
        self._hide_delete_button(idx)
    
    def _show_delete_button(self, idx):
        """Show delete button at specified index.
        
        Args:
            idx: Index in delete_button_info_list and delete_buttons
        """
        if 0 <= idx < len(self.delete_buttons):
            btn = self.delete_buttons[idx]
            info = self.delete_button_info_list[idx]
            btn.place(x=info['x'], y=info['y'])
    
    def _hide_delete_button(self, idx):
        """Hide delete button at specified index.
        
        Args:
            idx: Index in delete_button_info_list and delete_buttons
        """
        if 0 <= idx < len(self.delete_buttons):
            self.delete_buttons[idx].place_forget()
    
    def _check_and_hide_button(self, idx):
        """Check if button should be hidden (delayed hide callback).
        
        Args:
            idx: Index in delete_button_info_list
        """
        # Hide button if we're not hovering over this specific item anymore
        if self.hovered_item_idx != idx:
            self._hide_delete_button(idx)
        
        # Clear timer reference
        self.hide_button_timer = None
    
    def get_thumbnail(self, path: str, w: int, h: int, mcf_filename: str = None,
                     cutout_left: float = None, cutout_top: float = None, cutout_scale: float = None,
                     slot_width_mcf: float = None, slot_height_mcf: float = None):
        """Get thumbnail for an image, using cache if available.
        
        Two modes:
        1. cache_full_images=True: Cache full image, render on-the-fly (faster, more RAM)
        2. cache_full_images=False: Cache size-specific thumbnails (slower, less RAM)
        
        Args:
            path: Path to the image file
            w: Thumbnail width in pixels
            h: Thumbnail height in pixels
            mcf_filename: MCF filename (e.g., safecontainer:/path/img.jpg) for dimension caching
            cutout_left: Cutout left offset in MCF units (from XML)
            cutout_top: Cutout top offset in MCF units (from XML)
            cutout_scale: Scale factor from XML
            slot_width_mcf: Slot width in MCF units (for default cropping)
            slot_height_mcf: Slot height in MCF units (for default cropping)
        
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
                    
                    # Cache dimensions to avoid reloading image later
                    # Use MCF filename if provided (matches key used in update_weights_display)
                    cache_key_dim = mcf_filename if mcf_filename else filename
                    if cache_key_dim not in self.photo_dimensions:
                        self.photo_dimensions[cache_key_dim] = im.size
                    
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
                # Apply cropping/scaling if not in functional_rendering mode
                if not self.functional_rendering and slot_width_mcf is not None and slot_height_mcf is not None:
                    # Calculate what portion of the image to extract
                    img_w, img_h = full_img.size
                    
                    # If we have cutout info from XML, use it
                    if cutout_scale is not None and cutout_left is not None and cutout_top is not None:
                        # CEWE scale formula: scaled_width_mcf = image_width_px × scale
                        # This means scale tells us MCF units per pixel
                        scaled_width_mcf = img_w * cutout_scale
                        scaled_height_mcf = img_h * cutout_scale
                        
                        # Cutout offsets tell us which part of the scaled image is visible
                        # They're NEGATIVE when cropping from left/top edge
                        # visible_left_mcf = -cutout_left (offset into scaled image)
                        # We need to convert this to pixel coordinates in the original image
                        crop_left_px = -cutout_left / cutout_scale
                        crop_top_px = -cutout_top / cutout_scale
                        crop_right_px = crop_left_px + (slot_width_mcf / cutout_scale)
                        crop_bottom_px = crop_top_px + (slot_height_mcf / cutout_scale)
                        
                        # Clamp to image bounds
                        crop_left_px_clamped = max(0, min(img_w, crop_left_px))
                        crop_top_px_clamped = max(0, min(img_h, crop_top_px))
                        crop_right_px_clamped = max(0, min(img_w, crop_right_px))
                        crop_bottom_px_clamped = max(0, min(img_h, crop_bottom_px))
                        
                        #logger.debug(f"CROP [{base_filename}]: Using XML cutout - img={img_w}x{img_h}px, scale={cutout_scale:.4f}, slot={slot_width_mcf:.0f}x{slot_height_mcf:.0f}mcf, cutout_offset=({cutout_left:.1f},{cutout_top:.1f})mcf → crop_px=({crop_left_px:.1f},{crop_top_px:.1f})-({crop_right_px:.1f},{crop_bottom_px:.1f}) clamped=({crop_left_px_clamped:.0f},{crop_top_px_clamped:.0f})-({crop_right_px_clamped:.0f},{crop_bottom_px_clamped:.0f})")
                        
                        # Crop the image
                        cropped = full_img.crop((int(crop_left_px_clamped), int(crop_top_px_clamped), 
                                                int(crop_right_px_clamped), int(crop_bottom_px_clamped)))
                    else:
                        # No cutout info - use default: zoom to fill slot (crop equally from all sides)
                        img_aspect = img_w / img_h
                        slot_aspect = slot_width_mcf / slot_height_mcf
                        
                        if img_aspect > slot_aspect:
                            # Image is wider than slot - crop left/right
                            target_width = img_h * slot_aspect
                            crop_left = (img_w - target_width) / 2
                            #logger.info(f"CROP [{base_filename}]: Default crop (wide img) - img={img_w}x{img_h}px (aspect={img_aspect:.3f}), slot={slot_width_mcf:.0f}x{slot_height_mcf:.0f}mcf (aspect={slot_aspect:.3f}) → crop left/right by {crop_left:.1f}px")
                            cropped = full_img.crop((int(crop_left), 0, 
                                                    int(crop_left + target_width), img_h))
                        else:
                            # Image is taller than slot - crop top/bottom
                            target_height = img_w / slot_aspect
                            crop_top = (img_h - target_height) / 2
                            #logger.info(f"CROP [{base_filename}]: Default crop (tall img) - img={img_w}x{img_h}px (aspect={img_aspect:.3f}), slot={slot_width_mcf:.0f}x{slot_height_mcf:.0f}mcf (aspect={slot_aspect:.3f}) → crop top/bottom by {crop_top:.1f}px")
                            cropped = full_img.crop((0, int(crop_top), 
                                                    img_w, int(crop_top + target_height)))
                    
                    # Resize cropped image to thumbnail size
                    thumb = cropped.resize((w, h), Image.Resampling.LANCZOS)
                    logger.debug(f"get_thumbnail: Created cropped thumbnail {w}x{h} from {path}")
                    return thumb
                else:
                    # Normal thumbnail mode (current behavior)
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
                    
                    # Cache dimensions BEFORE thumbnail modifies the image
                    # Use MCF filename if provided (matches key used in update_weights_display)
                    cache_key_dim = mcf_filename if mcf_filename else filename
                    if cache_key_dim not in self.photo_dimensions:
                        self.photo_dimensions[cache_key_dim] = im.size
                    
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
