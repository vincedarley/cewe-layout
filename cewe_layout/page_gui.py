"""Pure rendering engine for photobook pages - no business logic, only visualization."""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
from dataclasses import dataclass
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


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


class PageRenderer:
    """Pure rendering engine for photobook pages. No business logic, only visualization.
    
    This class handles ONLY visual display of page layouts. It has:
    - NO business logic
    - NO state modification
    - NO file I/O (except image loading)
    
    All rendering state (caches, displayed images) is managed here.
    All business state (layouts, modifications, algorithms) stays in LayoutViewer.
    """
    
    def __init__(self, img_label: ttk.Label, mcf_base_folder: str, image_folder_attr: str,
                 photo_dimensions_cache: dict):
        """Initialize the page renderer.
        
        Args:
            img_label: Tkinter label widget to render into
            mcf_base_folder: Base folder for resolving photo paths
            image_folder_attr: Image folder attribute from MCF
            photo_dimensions_cache: Reference to LayoutViewer's photo dimensions cache
                                   (shared because algorithms need it too)
        """
        self.img_label = img_label
        self.mcf_base_folder = mcf_base_folder
        self.image_folder_attr = image_folder_attr
        self.photo_dimensions = photo_dimensions_cache  # Shared with LayoutViewer
        
        # Rendering state (caches, pixel images for buttons)
        self.photo_image = None  # Current displayed PhotoImage
        self.delete_button_pixel = tk.PhotoImage(width=1, height=1)
        self.delete_buttons = []  # Currently displayed delete button widgets
        
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
                    delete_callback) -> None:
        """Render one or more pages to the display.
        
        Args:
            page_data_list: List of PageRenderData objects (1 for single, 2 for spread)
            canvas_w, canvas_h: Canvas dimensions in pixels
            margin_mcf: Display margin in MCF units
            is_canvas: Whether this is canvas mode (affects crease line)
            delete_callback: Function to call when delete button clicked
                           Signature: (item_type, page_index, pageno, identifier)
                           where item_type is 'photo' or 'text'
        """
        if not page_data_list:
            self.render_empty_page(canvas_w, canvas_h, "No page data")
            return
        
        # Get page dimensions from first page
        first_page = page_data_list[0]
        page_w = first_page.page_width
        page_h = first_page.page_height
        
        # Determine page background color from designElementId
        background_id = first_page.background_id
        if background_id == '212':
            page_bg_color = 'black'
            frame_color = 'white'  # White frame for black background
        else:  # '201' or None or any other value defaults to white
            page_bg_color = 'white'
            frame_color = 'black'  # Black frame for white background
        
        # Create canvas image
        img = Image.new('RGB', (canvas_w, canvas_h), page_bg_color)
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
        
        # Store delete button info for later widget creation
        delete_button_info = []
        photo_counter = 1
        text_counter = 1
        
        # Render each page
        for page_offset, page_data in enumerate(page_data_list):
            # Calculate frame position for this page
            # In spread mode, second page is offset by page_w
            page_x_offset = page_offset * page_w if len(page_data_list) == 2 else 0
            frame_x = margin_mcf * scale + page_x_offset * scale
            frame_y = margin_mcf * scale
            frame_w = page_w * scale
            frame_h = page_h * scale
            
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
            
            # Draw page frame for this page
            self._draw_page_frame(draw, frame_x, frame_y, frame_w, frame_h, frame_color)
        
        # In spread mode, draw dotted line down the crease (center)
        # But not for Canvas mode (single large page, no crease)
        if len(page_data_list) == 2 and not is_canvas:
            crease_x = margin_mcf * scale + page_w * scale
            self._draw_crease_line(draw, crease_x, frame_y, frame_h, frame_color)
        
        # Show image and create delete buttons
        self._show_image(img)
        self._create_delete_buttons(delete_button_info, delete_callback)
    
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
    
    def _render_photos(self, img, draw, photos, frame_x, frame_y, scale, origin_left, 
                      start_number, pageno, delete_button_info, page_bg_color):
        """Render photos for a single page."""
        from .file_utils import extract_metadata_from_filename
        
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

            # draw text block background
            draw.rectangle([x0, y0, x1, y1], fill='#ffffcc')  # Light yellow background
            # wireframe overlay in green
            draw.rectangle([x0, y0, x1, y1], outline='green', width=2)
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
    
    def _draw_crease_line(self, draw, crease_x, crease_y, crease_h, color):
        """Draw dotted line down the center crease in spread mode."""
        dot_length = 5
        gap_length = 5
        
        y_pos = crease_y
        while y_pos < crease_y + crease_h:
            end_y = min(y_pos + dot_length, crease_y + crease_h)
            draw.line([(crease_x, y_pos), (crease_x, end_y)], fill=color, width=1)
            y_pos += dot_length + gap_length

    def _show_image(self, pil_img):
        """Display PIL image in the label widget."""
        self.photo_image = ImageTk.PhotoImage(pil_img)
        self.img_label.configure(image=self.photo_image)
    
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
                self.img_label,
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
