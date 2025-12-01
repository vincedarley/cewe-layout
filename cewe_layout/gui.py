"""Simple Tkinter UI to browse pages and display layout rectangles."""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
import math
import os
from pathlib import Path
import threading

from .parser import extract_pages_info, parse_mcf_from_path
from .layout_ops import LayoutManager
from .collage_wrapper import generate_layout_for_page
from .algorithms.evaluator import evaluate_layout
from .algorithms.collage_generator import CollageGeneratorAlgorithm
from .algorithms.fan_layout import FanLayoutAlgorithm
from .algorithms.tree_builder import TreeBuilderAlgorithm
from .algorithms.gridify import GridifyAlgorithm
from .photos import get_image_dimensions, load_thumbnail
from .writer import update_page_layout
from .gap_utils import (
    estimate_gaps,
    analyze_gaps,
    transform_page_to_gapfree,
    transform_item_to_gapfree,
    transform_item_from_gapfree,
    transform_item_for_gap_change
)


class LayoutViewer:
    def __init__(self, root, mcf_root, mcf_file_path):
        # mcf_root is the parsed XML root; mcf_file_path is the full path to the .mcf file
        self.pages = extract_pages_info(mcf_root)
        self.mcf_file_path = mcf_file_path
        # try to find the imagedir attribute on the root to locate images
        self.image_folder_attr = mcf_root.get('imagedir') or ''
        self.mcf_base_folder = '' if mcf_file_path is None else os.path.dirname(mcf_file_path)
        self.index = 0
        self.layout_mgr = LayoutManager()
        
        # Algorithm selection
        self.algorithm_var = tk.StringVar(value='Collage-Gen')
        
        # Debug flag for diagnostic output
        self.debug_var = tk.BooleanVar(value=False)
        
        # Track which photos should use slot aspect ratio (dict: {(pageno, photo_idx): BooleanVar})
        self.use_slot_aspect = {}
        
        # Cache photo dimensions: {filename: (width, height)} to avoid re-reading images
        self.photo_dimensions = {}

        # initialize layout manager with originals from file
        for pageno, info in self.pages:
            self.layout_mgr.set_original(pageno, info.get('photos', []), info.get('texts', []))
            # Initialize default preferred sizes from current layout areas (scaled by 10× for readability)
            photos = info.get('photos', [])
            texts = info.get('texts', [])
            all_items = photos + texts
            page_w = info.get('page_width', 2100.0)
            page_h = info.get('page_height', 2970.0)
            origin_left = info.get('origin_left', 0.0)
            
            # Estimate gap to compute gap-free areas (matching evaluation coordinate space)
            # Use internal gap preferentially
            edge_gap, inter_gap = estimate_gaps(all_items, page_w, page_h, origin_left) if all_items else (0.0, 0.0)
            gap = inter_gap if inter_gap > 0 else edge_gap
            
            # Compute total area in gap-free space (add gap to each photo dimension)
            total_area = sum(((p.get('area_width', 0) or 0) + gap) * ((p.get('area_height', 0) or 0) + gap) for p in all_items)
            if total_area > 0:
                for p in photos:
                    fn = p.get('filename', '')
                    # Use gap-free area (add gap back to stored dimensions)
                    area = ((p.get('area_width', 0) or 0) + gap) * ((p.get('area_height', 0) or 0) + gap)
                    preferred = (area / total_area) * 10.0
                    self.layout_mgr.set_size(pageno, fn, preferred)
                for i, t in enumerate(texts):
                    # Text blocks use identifier TEXT_<index>
                    text_id = f"TEXT_{i}"
                    area = ((t.get('area_width', 0) or 0) + gap) * ((t.get('area_height', 0) or 0) + gap)
                    preferred = (area / total_area) * 10.0
                    self.layout_mgr.set_size(pageno, text_id, preferred)
            else:
                # Fallback to uniform sizes (10.0 for 10× scaling)
                for p in photos:
                    self.layout_mgr.set_size(pageno, p.get('filename', ''), 10.0)
                for i, t in enumerate(texts):
                    self.layout_mgr.set_size(pageno, f"TEXT_{i}", 10.0)

        # Main window for page display
        self.root = root
        # Extract photobook filename (the directory containing data.mcf, not data.mcf itself)
        if mcf_file_path:
            # Get the parent directory name (e.g., "Test-album.xmcf" not "data.mcf")
            self.photobook_name = os.path.basename(os.path.dirname(mcf_file_path))
        else:
            self.photobook_name = 'Unknown'
        self.root.title('cewe-layout — Page Viewer')

        # Calculate canvas dimensions based on actual page size from first page
        # Add 5mm (50 MCF units) margin on all sides
        self.margin_mcf = 50.0
        if self.pages:
            _, first_page_info = self.pages[0]
            page_w = first_page_info.get('page_width', 2100.0)
            page_h = first_page_info.get('page_height', 2970.0)
        else:
            # Fallback if no pages
            page_w = 2100.0
            page_h = 2970.0
        
        # Total dimensions including margins (this is our fixed aspect ratio)
        total_w_mcf = page_w + 2 * self.margin_mcf
        total_h_mcf = page_h + 2 * self.margin_mcf
        self.canvas_aspect_ratio = total_w_mcf / total_h_mcf
        
        # Get screen dimensions to fit window appropriately
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Target size: use 80% of screen width or height (whichever constrains more)
        # leaving room for the controls window and window decorations
        max_width = int(screen_width * 0.8)
        max_height = int(screen_height * 0.8)
        
        # Calculate initial window size maintaining aspect ratio
        if max_width / self.canvas_aspect_ratio <= max_height:
            # Width is the constraint
            initial_width = max_width
            initial_height = int(max_width / self.canvas_aspect_ratio)
        else:
            # Height is the constraint
            initial_height = max_height
            initial_width = int(max_height * self.canvas_aspect_ratio)
        
        # Set minimum window size (e.g., 400 pixels on smaller dimension)
        min_width = int(400 * self.canvas_aspect_ratio) if self.canvas_aspect_ratio > 1 else 400
        min_height = int(400 / self.canvas_aspect_ratio) if self.canvas_aspect_ratio > 1 else 400
        
        # Configure window geometry and aspect ratio
        self.root.geometry(f'{initial_width}x{initial_height}')
        self.root.minsize(min_width, min_height)
        
        # Set aspect ratio constraint (num, denom format)
        # Convert ratio to integers for Tk's aspect() method
        ratio_num = int(self.canvas_aspect_ratio * 1000)
        ratio_denom = 1000
        self.root.aspect(ratio_num, ratio_denom, ratio_num, ratio_denom)

        self.img_label = ttk.Label(self.root)
        self.img_label.pack(fill='both', expand=True)
        
        # Bind window resize event to redraw
        self.root.bind('<Configure>', self._on_window_resize)
        self._resize_pending = False

        # Controls window
        self.ctrl = tk.Toplevel(self.root)
        self.ctrl.title('Controls')
        self.ctrl.geometry('+50+50')

        # Row 0: Navigation
        prev_btn = ttk.Button(self.ctrl, text='Prev (←)', command=self.prev_page)
        prev_btn.grid(row=0, column=0, padx=4, pady=4)
        next_btn = ttk.Button(self.ctrl, text='Next (→)', command=self.next_page)
        next_btn.grid(row=0, column=1, padx=4, pady=4)
        ttk.Label(self.ctrl, text='Go to:').grid(row=0, column=2)
        self.goto_var = tk.StringVar()
        goto_entry = ttk.Entry(self.ctrl, textvariable=self.goto_var, width=6)
        goto_entry.grid(row=0, column=3, padx=4)
        goto_btn = ttk.Button(self.ctrl, text='Go', command=self.goto_page)
        goto_btn.grid(row=0, column=4, padx=4)
        
        # Row 1: Algorithm selection and Generate button
        ttk.Label(self.ctrl, text='Algorithm:').grid(row=1, column=0, padx=(4, 2), pady=4, sticky='e')
        algo_menu = ttk.OptionMenu(
            self.ctrl, self.algorithm_var,
            'Fan-GA',  # default
            'Collage-Gen', 'Fan-GA', 'Gridify', 'Tree-Builder'
        )
        algo_menu.grid(row=1, column=1, padx=(0, 8), pady=4, sticky='ew')
        
        # Generate button (uses selected algorithm)
        self.gen_btn = ttk.Button(self.ctrl, text='Generate Layout', command=self.generate_layout)
        self.gen_btn.grid(row=1, column=2, columnspan=2, padx=4, pady=4, sticky='ew')
        
        # Row 2: Actions
        undo_btn = ttk.Button(self.ctrl, text='Back', command=self.undo_layout)
        undo_btn.grid(row=2, column=0, padx=4, pady=4)
        save_btn = ttk.Button(self.ctrl, text='Save', command=self.save_layout)
        save_btn.grid(row=2, column=1, padx=4, pady=4)
        orig_btn = ttk.Button(self.ctrl, text='Use Original', command=self.use_original)
        orig_btn.grid(row=2, column=2, padx=4, pady=4)
        
        # Row 3: Additional options
        # Debug checkbox
        debug_check = ttk.Checkbutton(self.ctrl, text='Debug Output', variable=self.debug_var)
        debug_check.grid(row=3, column=0, padx=4, pady=4, sticky='w')
        
        quit_btn = ttk.Button(self.ctrl, text='Quit (q)', command=self.quit)
        quit_btn.grid(row=3, column=2, padx=8)


        
        # Status message entry (read-only but selectable for copying)
        self.status_var = tk.StringVar(value='')
        self.status_entry = ttk.Entry(self.ctrl, textvariable=self.status_var, 
                                      state='readonly', font=('TkDefaultFont', 9))
        self.status_entry.grid(row=3, column=2, columnspan=3, padx=4, pady=4, sticky='ew')
        # Store the style for color changes
        self.status_style = ttk.Style()
        
        # Weights and cost display frame
        self.info_frame = ttk.LabelFrame(self.ctrl, text='Layout Info', padding=8)
        self.info_frame.grid(row=4, column=0, columnspan=5, padx=4, pady=8, sticky='ew')
        
        # Configure columns: left column (0) for photos, right column (1) for cost/params
        self.info_frame.columnconfigure(0, weight=1)
        self.info_frame.columnconfigure(1, weight=0)
        
        # LEFT COLUMN: Photo weights
        photo_frame = ttk.Frame(self.info_frame)
        photo_frame.grid(row=0, column=0, sticky='nw', padx=(0, 20))
        
        ttk.Label(photo_frame, text='Item', font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=0, padx=2, pady=2, sticky='w')
        ttk.Label(photo_frame, text='Slot AR', font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=1, padx=2, pady=2, sticky='w')
        # Preferred label with Equal/Original buttons below it
        pref_container = ttk.Frame(photo_frame)
        pref_container.grid(row=0, column=2, padx=2, pady=2, sticky='w')
        ttk.Label(pref_container, text='Preferred', font=('TkDefaultFont', 9, 'bold')).pack()
        btn_frame = ttk.Frame(pref_container)
        btn_frame.pack()
        # Use tk.Button (not ttk) for tighter control over padding
        tk.Button(btn_frame, text='Equal', command=self.equal_sizes, 
                  font=('TkDefaultFont', 7), padx=0, pady=0, bd=1, highlightthickness=0).pack(side='left', padx=0)
        tk.Button(btn_frame, text='Original', command=self.stored_sizes, 
                  font=('TkDefaultFont', 7), padx=0, pady=0, bd=1, highlightthickness=0).pack(side='left', padx=0)
        ttk.Label(photo_frame, text='Actual', font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=3, padx=2, pady=2, sticky='w')
        
        # Item (photo/text) weight rows will be added dynamically to photo_frame
        self.photo_frame = photo_frame
        
        # RIGHT COLUMN: Cost info (top) and Parameters (bottom)
        right_col = ttk.Frame(self.info_frame)
        right_col.grid(row=0, column=1, sticky='ne')
        
        # Cost display frame (top of right column)
        # LabelFrame with total cost in title
        self.cost_frame = ttk.LabelFrame(right_col, text='Total cost: --', padding=6)
        self.cost_frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        
        cost_frame = self.cost_frame  # for compatibility with code below
        
        ttk.Label(cost_frame, text='Empty space:', font=('TkDefaultFont', 10)).grid(row=0, column=0, sticky='w', pady=1)
        self.cost_empty_label = ttk.Label(cost_frame, text='--', font=('TkDefaultFont', 10))
        self.cost_empty_label.grid(row=0, column=1, sticky='w', padx=4, pady=1)
        
        ttk.Label(cost_frame, text='Size mismatch:', font=('TkDefaultFont', 10)).grid(row=1, column=0, sticky='w', pady=1)
        self.cost_size_label = ttk.Label(cost_frame, text='--', font=('TkDefaultFont', 10))
        self.cost_size_label.grid(row=1, column=1, sticky='w', padx=4, pady=1)
        
        # Indented sub-components of size mismatch
        self.cost_size_normal_heading = ttk.Label(cost_frame, text='  Normal:', font=('TkDefaultFont', 9))
        self.cost_size_normal_heading.grid(row=2, column=0, sticky='w', pady=1)
        self.cost_size_normal_label = ttk.Label(cost_frame, text='--', font=('TkDefaultFont', 9))
        self.cost_size_normal_label.grid(row=2, column=1, sticky='w', padx=4, pady=1)
        
        self.cost_size_undersized_heading = ttk.Label(cost_frame, text='  Undersized:', font=('TkDefaultFont', 9))
        self.cost_size_undersized_heading.grid(row=3, column=0, sticky='w', pady=1)
        self.cost_size_undersized_label = ttk.Label(cost_frame, text='--', font=('TkDefaultFont', 9))
        self.cost_size_undersized_label.grid(row=3, column=1, sticky='w', padx=4, pady=1)

        # Formula display: Total = Empty% + λ × SizeMismatch%-sq (normal) + λ × k × SizeMismatch%-sq (undersized)
        self.cost_formula_label = ttk.Label(cost_frame, text='', font=('TkDefaultFont', 10, 'italic'))
        self.cost_formula_label.grid(row=4, column=0, columnspan=2, sticky='w', pady=(4,0))
        
        # Cost Parameters frame (middle of right column)
        cost_param_frame = ttk.LabelFrame(right_col, text='Cost Parameters', padding=6)
        cost_param_frame.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        
        # Weight importance parameter
        ttk.Label(cost_param_frame, text='Size importance (λ):').grid(row=0, column=0, sticky='w', pady=2)
        self.size_importance_var = tk.StringVar(value='100.0')
        self.size_importance_entry = ttk.Entry(cost_param_frame, textvariable=self.size_importance_var, width=8)
        self.size_importance_entry.grid(row=0, column=1, sticky='w', padx=4, pady=2)
        self.size_importance_entry.bind('<Return>', lambda e: self.on_size_importance_changed())
        self.size_importance_entry.bind('<FocusOut>', lambda e: self.on_size_importance_changed())
        
        # Undersized threshold parameter
        ttk.Label(cost_param_frame, text='Undersized threshold:').grid(row=1, column=0, sticky='w', pady=2)
        self.undersized_threshold_var = tk.StringVar(value='0.5')
        self.undersized_threshold_entry = ttk.Entry(cost_param_frame, textvariable=self.undersized_threshold_var, width=8)
        self.undersized_threshold_entry.grid(row=1, column=1, sticky='w', padx=4, pady=2)
        self.undersized_threshold_entry.bind('<Return>', lambda e: self.on_undersized_threshold_changed())
        self.undersized_threshold_entry.bind('<FocusOut>', lambda e: self.on_undersized_threshold_changed())
        
        # Undersized penalty parameter
        ttk.Label(cost_param_frame, text='Undersized penalty (k):').grid(row=2, column=0, sticky='w', pady=2)
        self.undersized_penalty_var = tk.StringVar(value='5.0')
        self.undersized_penalty_entry = ttk.Entry(cost_param_frame, textvariable=self.undersized_penalty_var, width=8)
        self.undersized_penalty_entry.grid(row=2, column=1, sticky='w', padx=4, pady=2)
        self.undersized_penalty_entry.bind('<Return>', lambda e: self.on_undersized_penalty_changed())
        self.undersized_penalty_entry.bind('<FocusOut>', lambda e: self.on_undersized_penalty_changed())
        
        # Margins frame (bottom of right column)
        margins_frame = ttk.LabelFrame(right_col, text='Margins', padding=6)
        margins_frame.grid(row=2, column=0, sticky='ew')
        
        # Edge gap parameter (now editable)
        ttk.Label(margins_frame, text='Edge gap (mm):').grid(row=0, column=0, sticky='w', pady=2)
        self.edge_gap_var = tk.StringVar(value='0.0')
        self.edge_gap_entry = ttk.Entry(margins_frame, textvariable=self.edge_gap_var, width=8)
        self.edge_gap_entry.grid(row=0, column=1, sticky='w', padx=4, pady=2)
        self.edge_gap_entry.bind('<Return>', lambda e: self.on_edge_gap_changed())
        self.edge_gap_entry.bind('<FocusOut>', lambda e: self.on_edge_gap_changed())
        
        # Internal gap parameter (editable)
        ttk.Label(margins_frame, text='Internal gap (mm):').grid(row=1, column=0, sticky='w', pady=2)
        self.gap_var = tk.StringVar(value='0.0')
        self.gap_entry = ttk.Entry(margins_frame, textvariable=self.gap_var, width=8)
        self.gap_entry.grid(row=1, column=1, sticky='w', padx=4, pady=2)
        self.gap_entry.bind('<Return>', lambda e: self.on_internal_gap_changed())
        self.gap_entry.bind('<FocusOut>', lambda e: self.on_internal_gap_changed())
        
        # Photo weight rows (will be populated dynamically)
        self.weight_widgets = []  # List of (item_label, desired_entry, actual_label) for photos and texts

        # keyboard bindings
        self.root.bind('<Left>', lambda e: self.prev_page())
        self.root.bind('<Right>', lambda e: self.next_page())
        self.root.bind('<q>', lambda e: self.quit())
        self.ctrl.bind('<Return>', lambda e: self.goto_page())

        self.photo_image = None
        self.thumb_cache = {}  # filename -> PIL.Image (thumbnail)
        self.size_importance = 100.0  # Default size importance factor
        self.undersized_threshold = 0.5  # Default undersized threshold (50%)
        self.undersized_penalty = 5.0  # Default undersized penalty factor
        self.render_page()

    def render_page(self):
        # Clear status message when changing pages
        self.status_var.set('')
        
        # Get current canvas dimensions from the window
        self.root.update_idletasks()  # Ensure geometry is current
        canvas_w = self.img_label.winfo_width()
        canvas_h = self.img_label.winfo_height()
        
        # On initial render, dimensions may not be available yet
        if canvas_w <= 1 or canvas_h <= 1:
            canvas_w = self.root.winfo_width()
            canvas_h = self.root.winfo_height()
        
        # Ensure minimum size
        if canvas_w < 100:
            canvas_w = 800
        if canvas_h < 100:
            canvas_h = int(800 / self.canvas_aspect_ratio)
        
        if not self.pages:
            img = Image.new('RGB', (canvas_w, canvas_h), 'white')
            draw = ImageDraw.Draw(img)
            draw.text((10,10), 'No pages found', fill='black')
            self._show_image(img)
            return

        pageno, info = self.pages[self.index]
        # Fetch current layout from layout manager (may be modified or original)
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])
        texts = current_layout.texts if current_layout else info.get('texts', [])

        # Update window title with photobook name and page info
        text_label = 'text' if len(texts) == 1 else 'texts'
        if texts:
            title = f'{self.photobook_name} - Page {pageno} : {len(photos)} photos, {len(texts)} {text_label}'
        else:
            title = f'{self.photobook_name} - Page {pageno} : {len(photos)} photos'
        self.root.title(title)
        
        img = Image.new('RGB', (canvas_w, canvas_h), 'white')
        draw = ImageDraw.Draw(img)

        # Use page meta to map coordinates. page_width/height are in MCF units (0.1mm)
        page_w = info.get('page_width', 2100.0)
        page_h = info.get('page_height', 2970.0)
        origin_left = info.get('origin_left', 0.0)

        # 5mm margin on all sides (50 MCF units)
        margin_mcf = self.margin_mcf
        
        # Calculate scale to fit page + margins in canvas
        # Canvas dimensions were set to match (page + 2*margin) aspect ratio
        total_w_mcf = page_w + 2 * margin_mcf
        total_h_mcf = page_h + 2 * margin_mcf
        scale = min(canvas_w / total_w_mcf, canvas_h / total_h_mcf)

        # Calculate frame size and position
        # Page frame starts at margin offset and has size of page
        frame_w = page_w * scale
        frame_h = page_h * scale
        frame_x = margin_mcf * scale
        frame_y = margin_mcf * scale

        for i, p in enumerate(photos, start=1):
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
                # construct image path from mcf base folder and imagedir attribute if present
                img_path = None
                safefn = fn.replace('safecontainer:/', '').lstrip('/')
                if self.image_folder_attr:
                    candidate = os.path.join(self.mcf_base_folder, self.image_folder_attr, safefn)
                    if os.path.exists(candidate):
                        img_path = candidate
                # fallback: check relative to mcf base
                if img_path is None:
                    candidate = os.path.join(self.mcf_base_folder, safefn)
                    if os.path.exists(candidate):
                        img_path = candidate

                if img_path is not None:
                    thumb = self._get_thumbnail(img_path, int(x1-x0), int(y1-y0))
                    if thumb is not None:
                        img.paste(thumb, (int(x0), int(y0)))
                    else:
                        # draw a light placeholder for missing thumbnail
                        draw.rectangle([x0, y0, x1, y1], fill='#eeeeee')

            # wireframe overlay
            draw.rectangle([x0, y0, x1, y1], outline='blue', width=2)
            # filename text
            shortfn = (fn or '').split('/')[-1]
            draw.text((x0+4, y0+4), f'{i}: {shortfn}', fill='black')
        
        # Draw text blocks
        for i, t in enumerate(texts, start=1):
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
            # label
            draw.text((x0+4, y0+4), f'T{i}', fill='green')

        # Draw page frame LAST so it's on top of photos/texts in bleed situations
        draw.rectangle([frame_x, frame_y, frame_x+frame_w, frame_y+frame_h], outline='black', width=2)

        self._show_image(img)
        self.update_weights_display()

    def _show_image(self, pil_img):
        self.photo_image = ImageTk.PhotoImage(pil_img)
        self.img_label.configure(image=self.photo_image)
    
    def update_weights_display(self):
        """Update the weights and cost display for the current page."""
        if not self.pages:
            return
        
        pageno, info = self.pages[self.index]
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])
        texts = current_layout.texts if current_layout else info.get('texts', [])
        
        page_w = info.get('page_width', 2100.0)
        page_h = info.get('page_height', 2970.0)
        origin_left = info.get('origin_left', 0.0)
        
        # Initialize gaps from ORIGINAL layout on first visit to this page
        # Check if gaps have been set (key exists, not value-based check)
        if not self.layout_mgr.has_edge_gap(pageno) or not self.layout_mgr.has_internal_gap(pageno):
            # Analyze gaps from original layout
            original_photos = info.get('photos', [])
            original_texts = info.get('texts', [])
            original_items = original_photos + original_texts
            
            if original_items:
                analysis = analyze_gaps(original_items, page_w, page_h, origin_left)
                
                # Set edge_gap: use negative value for bleed, positive for margin
                if analysis.bleed > 0:
                    # Bleed detected: use negative edge_gap
                    self.layout_mgr.set_edge_gap(pageno, -analysis.bleed)
                else:
                    # No bleed: use positive edge_gap (margin)
                    self.layout_mgr.set_edge_gap(pageno, analysis.edge_gap)
                
                # Set internal_gap: prefer internal, fallback to edge
                if analysis.internal_gap > 0:
                    self.layout_mgr.set_internal_gap(pageno, analysis.internal_gap)
                else:
                    # No internal gaps detected, use edge_gap as fallback
                    self.layout_mgr.set_internal_gap(pageno, analysis.edge_gap)
            else:
                # No items to analyze, set defaults
                self.layout_mgr.set_edge_gap(pageno, 0.0)
                self.layout_mgr.set_internal_gap(pageno, 0.0)
        
        # Get current gap values (now guaranteed to be set)
        current_edge_gap = self.layout_mgr.get_edge_gap(pageno)
        current_internal_gap = self.layout_mgr.get_internal_gap(pageno)
        
        # Update gap displays (convert MCF units to mm: 1 MCF unit = 0.1mm)
        edge_gap_mm = current_edge_gap / 10.0
        self.edge_gap_var.set(f'{edge_gap_mm:.1f}')
        
        gap_mm = current_internal_gap / 10.0
        self.gap_var.set(f'{gap_mm:.1f}')
        
        # Clear existing weight widgets
        for widgets in self.weight_widgets:
            for w in widgets:
                w.destroy()
        self.weight_widgets.clear()
        
        if not photos and not texts:
            self.cost_frame.config(text='Total cost: --')
            self.cost_empty_label.config(text='No items')
            self.cost_size_label.config(text='--')
            self.cost_size_normal_label.config(text='--')
            self.cost_size_undersized_label.config(text='--')
            return
        
        # Get current gaps from layout manager for evaluation
        edge_gap = self.layout_mgr.get_edge_gap(pageno)
        internal_gap = self.layout_mgr.get_internal_gap(pageno)
        
        # Build LayoutRectangle list from CURRENT layout (photos and texts)
        # This is what we evaluate (algorithm output or original)
        # But we use gaps from layout manager as fixed parameters
        # Transform to gap-free coordinate space (same as algorithm uses)
        from .algorithms.base import LayoutRectangle
        rectangles = []
        item_identifiers = []  # Track (type, index, filename_or_id) for each rectangle
        
        # Add photos
        for i, p in enumerate(photos):
            left = p.get('area_left', 0)
            top = p.get('area_top', 0)
            w = p.get('area_width', 0)
            h = p.get('area_height', 0)
            
            fn = p.get('filename', '')
            preferred_size = self.layout_mgr.get_size(pageno, fn)
            
            # Transform to gap-free space using centralized function
            gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
                left, top, w, h, edge_gap, internal_gap
            )
            
            rect = LayoutRectangle(
                item_id=str(i),
                width=gf_width,
                height=gf_height,
                preferred_size=preferred_size,
                preserve_aspect_ratio=True,
                x=gf_left,
                y=gf_top
            )
            rect.actual_size = preferred_size  # Placeholder; evaluator will compute
            rectangles.append(rect)
            item_identifiers.append(('photo', i, fn))
        
        # Add texts
        for i, t in enumerate(texts):
            left = t.get('area_left', 0)
            top = t.get('area_top', 0)
            w = t.get('area_width', 0)
            h = t.get('area_height', 0)
            
            text_id = f'TEXT_{i}'
            preferred_size = self.layout_mgr.get_size(pageno, text_id)
            
            # Transform to gap-free space using centralized function
            gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
                left, top, w, h, edge_gap, internal_gap
            )
            
            rect = LayoutRectangle(
                item_id=text_id,
                width=gf_width,
                height=gf_height,
                preferred_size=preferred_size,
                preserve_aspect_ratio=False,
                x=gf_left,
                y=gf_top
            )
            rect.actual_size = preferred_size
            rectangles.append(rect)
            item_identifiers.append(('text', i, text_id))
        
        # Evaluate in gap-free coordinate space using centralized transformation
        eval_page_w, eval_page_h = transform_page_to_gapfree(
            page_w, page_h, edge_gap, internal_gap
        )
        
        # DEBUG: Print evaluation inputs if debug flag is set
        if self.debug_var.get():
            print(f"\n=== GUI Evaluation Debug ===")
            print(f"  Page: {pageno}")
            print(f"  Eval page: {eval_page_w} x {eval_page_h}")
            print(f"  Edge gap: {edge_gap}, Internal gap: {internal_gap}")
            print(f"  Rectangles passed to evaluator ({len(rectangles)} total):")
            for i, (rect, item_info) in enumerate(zip(rectangles, item_identifiers)):
                item_type, item_idx, item_id = item_info
                area = rect.width * rect.height
                print(f"    {i} ({item_type}): preferred_size={rect.preferred_size:.6f}, dims={rect.width:.2f}x{rect.height:.2f}, area={area:.2f}")
            print(f"  Sum of preferred_sizes: {sum(r.preferred_size for r in rectangles):.6f}")
            print()
        
        cost = evaluate_layout(
            eval_page_w, eval_page_h, rectangles,
            size_importance=self.size_importance,
            acceptable_empty_fraction=0.05,
            undersized_threshold=self.undersized_threshold,
            undersized_penalty=self.undersized_penalty
        )
        
        # DEBUG: Print evaluation results if debug flag is set
        if self.debug_var.get():
            print(f"\n=== GUI Evaluation Results ===")
            print(f"  Page: {pageno}")
            print(f"  Total cost: {cost.total_cost:.4f}")
            print(f"  Empty space cost: {cost.empty_space_cost:.4f}")
            print(f"  Size mismatch cost: {cost.size_mismatch_cost:.4f}")
            print(f"  Size mismatch / size_importance: {cost.size_mismatch_cost / self.size_importance:.6f}")
            if cost.size_errors:
                print(f"  Size errors:")
                for item_id, pref_norm, actual_norm, sq_err, undersized in cost.size_errors:
                    print(f"    {item_id}: pref={pref_norm:.6f}, actual={actual_norm:.6f}, sq_err={sq_err:.8f}, undersized={undersized}")
            print()
        
        # Update cost labels with human-readable format
        self.cost_frame.config(text=f'Total cost: {cost.total_cost:.1f}')
        
        # Empty space as percentage (fraction of page unused)
        empty_pct = cost.empty_space_fraction * 100
        self.cost_empty_label.config(text=f'{empty_pct:.1f}%')
        
        # Total size mismatch
        size_pct_sq = cost.size_mismatch_cost / self.size_importance if self.size_importance > 0 else 0.0
        self.cost_size_label.config(text=f'{size_pct_sq:.2f} %-sq')
        
        # Normal size mismatch component
        total_items = len(rectangles)
        normal_count = total_items - cost.undersized_count
        size_normal_pct_sq = cost.size_mismatch_normal_cost / self.size_importance if self.size_importance > 0 else 0.0
        self.cost_size_normal_heading.config(text=f'  Normal ({normal_count}/{total_items}):')
        self.cost_size_normal_label.config(text=f'{size_normal_pct_sq:.2f} %-sq')
        
        # Undersized size mismatch component (includes penalty)
        size_undersized_pct_sq = cost.size_mismatch_undersized_cost / (self.size_importance * self.undersized_penalty) if (self.size_importance > 0 and self.undersized_penalty > 0) else 0.0
        self.cost_size_undersized_heading.config(text=f'  Undersized ({cost.undersized_count}/{total_items}):')
        self.cost_size_undersized_label.config(text=f'{size_undersized_pct_sq:.2f} %-sq')

        # Show formula: Total = Empty% + λ × SizeMismatch%-sq
        # This is for readability; units are mixed intentionally as requested
        # Use empty space COST (percent above acceptable threshold) in the formula,
        # not the raw empty fraction. Also show threshold annotation on the line above.
        empty_cost_pct = cost.empty_space_cost
        threshold_pct = 5.0
        comparator = '< 5%' if empty_pct < threshold_pct else '≥ 5%'
        self.cost_empty_label.config(text=f'{empty_pct:.1f}% (cost = {empty_cost_pct:.1f}%, since {comparator})')

        self.cost_formula_label.config(
            text=f'{cost.total_cost:.1f} = {empty_cost_pct:.1f}% + λ×{size_pct_sq:.2f} %-sq'
        )
        
        # Create weight display rows for each item (photos and texts)
        for i, (rect, item_info) in enumerate(zip(rectangles, item_identifiers)):
            row = 1 + i  # Row 0 has headers, data starts at row 1
            
            item_type, item_idx, item_id = item_info
            
            # Item label with type indicator: P1, P2, ... for photos, T1, T2, ... for texts
            type_prefix = 'P' if item_type == 'photo' else 'T'
            item_label = ttk.Label(self.photo_frame, text=f'{type_prefix}{item_idx+1}', font=('TkDefaultFont', 9))
            item_label.grid(row=row, column=0, padx=2, pady=1)
            
            # Checkbox for using slot aspect ratio (photos only)
            checkbox_widget = None
            if item_type == 'photo':
                # Get or create checkbox state
                checkbox_key = (pageno, item_idx)
                if checkbox_key not in self.use_slot_aspect:
                    # Auto-check if photo aspect ratio differs significantly from slot
                    should_auto_check = False
                    photo = photos[item_idx]
                    slot_width = photo.get('area_width', 0)
                    slot_height = photo.get('area_height', 0)
                    
                    if slot_width > 0 and slot_height > 0:
                        # Load image to get its actual aspect ratio
                        fn = photo.get('filename', '')
                        if fn:
                            # Check cache first
                            if fn in self.photo_dimensions:
                                img_w, img_h = self.photo_dimensions[fn]
                                img_aspect = img_w / img_h
                                slot_aspect = slot_width / slot_height
                                # Auto-check if aspect ratios differ by more than 30%
                                aspect_diff = abs(img_aspect - slot_aspect) / slot_aspect
                                if aspect_diff > 0.30:
                                    should_auto_check = True
                            else:
                                # Load and cache dimensions
                                safefn = fn.replace('safecontainer:/', '').lstrip('/')
                                img_path = Path(self.mcf_base_folder) / safefn
                                if img_path.exists():
                                    try:
                                        dims = get_image_dimensions(img_path)
                                        if dims is not None:
                                            img_w, img_h = dims
                                            # Cache for future use
                                            self.photo_dimensions[fn] = (img_w, img_h)
                                            if img_h > 0 and img_w > 0:
                                                img_aspect = img_w / img_h
                                                slot_aspect = slot_width / slot_height
                                                # Auto-check if aspect ratios differ by more than 30%
                                                aspect_diff = abs(img_aspect - slot_aspect) / slot_aspect
                                                if aspect_diff > 0.30:
                                                    should_auto_check = True
                                    except Exception:
                                        pass
                    
                    self.use_slot_aspect[checkbox_key] = tk.BooleanVar(value=should_auto_check)
                
                checkbox_widget = ttk.Checkbutton(self.photo_frame, variable=self.use_slot_aspect[checkbox_key])
                checkbox_widget.grid(row=row, column=1, padx=2, pady=1)
            else:
                # Placeholder for text blocks (no checkbox needed)
                checkbox_widget = ttk.Label(self.photo_frame, text='', font=('TkDefaultFont', 9))
                checkbox_widget.grid(row=row, column=1, padx=2, pady=1)
            
            # Desired weight entry (editable)
            desired_var = tk.StringVar(value=f'{rect.preferred_size:.1f}')
            desired_entry = ttk.Entry(self.photo_frame, textvariable=desired_var, width=6)
            desired_entry.grid(row=row, column=2, padx=2, pady=1)
            
            # Bind entry changes to update weights in layout manager
            desired_entry.bind('<Return>', lambda e, pg=pageno, iid=item_id, var=desired_var: self.on_size_changed(pg, iid, var))
            desired_entry.bind('<FocusOut>', lambda e, pg=pageno, iid=item_id, var=desired_var: self.on_size_changed(pg, iid, var))
            
            # Actual weight label (computed from area)
            # Use the same coordinate space as evaluation
            total_area = (eval_page_w * eval_page_h)
            item_area = rect.width * rect.height
            actual_fraction = item_area / total_area if total_area > 0 else 0.0
            
            # Simpler: just show the area fraction as percentage of page
            actual_pct = actual_fraction * 100
            actual_label = ttk.Label(self.photo_frame, text=f'{actual_pct:.1f}%', font=('TkDefaultFont', 9))
            actual_label.grid(row=row, column=3, padx=2, pady=1)
            
            self.weight_widgets.append((item_label, checkbox_widget, desired_entry, actual_label))
    
    def on_size_changed(self, pageno, item_id, var):
        """Handle preferred size entry change.
        
        Args:
            pageno: Page number
            item_id: Filename for photos, TEXT_N for text blocks
            var: StringVar containing the new size
        """
        try:
            new_size = float(var.get())
            if 0.0 <= new_size <= 50.0:  # Reasonable bounds (scaled by 10×)
                self.layout_mgr.set_size(pageno, item_id, new_size)
                self.update_weights_display()  # Refresh display
        except ValueError:
            pass  # Ignore invalid input
    
    def on_edge_gap_changed(self):
        """Handle edge gap entry change.
        
        When gap changes, transform layout: MCF → gap-free (old gaps) → MCF (new gaps).
        This adjusts item positions/sizes to match the new gap values.
        """
        if not self.pages:
            return
        try:
            pageno, info = self.pages[self.index]
            
            # Get OLD gaps before changing
            old_edge_gap = self.layout_mgr.get_edge_gap(pageno)
            old_internal_gap = self.layout_mgr.get_internal_gap(pageno)
            
            # Parse and validate NEW edge gap
            edge_gap_mm = float(self.edge_gap_var.get())
            new_edge_gap = edge_gap_mm * 10.0  # Convert mm to MCF units
            if not (-200.0 <= new_edge_gap <= 200.0):  # Reasonable bounds (-20mm to +20mm)
                return  # Invalid value, abort
            
            # Transform current layout using gap change
            self._transform_layout_for_gap_change(
                pageno, old_edge_gap, old_internal_gap, new_edge_gap, old_internal_gap
            )
            
            # Update stored gap value
            self.layout_mgr.set_edge_gap(pageno, new_edge_gap)
            
            # Re-render with adjusted layout
            self.render_page()
        except ValueError:
            pass  # Ignore invalid input
    
    def on_internal_gap_changed(self):
        """Handle internal gap entry change.
        
        When gap changes, transform layout: MCF → gap-free (old gaps) → MCF (new gaps).
        This adjusts item positions/sizes to match the new gap values.
        """
        if not self.pages:
            return
        try:
            pageno, info = self.pages[self.index]
            
            # Get OLD gaps before changing
            old_edge_gap = self.layout_mgr.get_edge_gap(pageno)
            old_internal_gap = self.layout_mgr.get_internal_gap(pageno)
            
            # Parse and validate NEW internal gap
            gap_mm = float(self.gap_var.get())
            new_internal_gap = gap_mm * 10.0  # Convert mm to MCF units
            if not (0.0 <= new_internal_gap <= 200.0):  # Reasonable bounds (0-20mm)
                return  # Invalid value, abort
            
            # Transform current layout using gap change
            self._transform_layout_for_gap_change(
                pageno, old_edge_gap, old_internal_gap, old_edge_gap, new_internal_gap
            )
            
            # Update stored gap value
            self.layout_mgr.set_internal_gap(pageno, new_internal_gap)
            
            # Re-render with adjusted layout
            self.render_page()
        except ValueError:
            pass  # Ignore invalid input
    
    def _transform_layout_for_gap_change(self, pageno, old_edge_gap, old_internal_gap,
                                          new_edge_gap, new_internal_gap):
        """Transform current layout when gaps change.
        
        Uses transform_item_for_gap_change() from gap_utils to handle the transformation.
        See that function for detailed documentation of the algorithm.
        
        Args:
            pageno: Page number
            old_edge_gap: Previous edge gap in MCF units
            old_internal_gap: Previous internal gap in MCF units
            new_edge_gap: New edge gap in MCF units
            new_internal_gap: New internal gap in MCF units
        """
        # Get current layout and page info
        current_layout = self.layout_mgr.get_current(pageno)
        if not current_layout:
            return  # No layout to transform
        
        _, info = self.pages[self.index]
        page_w = info.get('page_width', 2100.0)
        page_h = info.get('page_height', 2970.0)
        
        # Transform photos using centralized helper
        transformed_photos = []
        for p in current_layout.photos:
            left = p.get('area_left', 0)
            top = p.get('area_top', 0)
            width = p.get('area_width', 0)
            height = p.get('area_height', 0)
            
            new_left, new_top, new_width, new_height = transform_item_for_gap_change(
                left, top, width, height, page_w, page_h,
                old_edge_gap, old_internal_gap, new_edge_gap, new_internal_gap
            )
            
            updated_photo = p.copy()
            updated_photo['area_left'] = new_left
            updated_photo['area_top'] = new_top
            updated_photo['area_width'] = new_width
            updated_photo['area_height'] = new_height
            transformed_photos.append(updated_photo)
        
        # Transform texts using centralized helper
        transformed_texts = []
        for t in current_layout.texts:
            left = t.get('area_left', 0)
            top = t.get('area_top', 0)
            width = t.get('area_width', 0)
            height = t.get('area_height', 0)
            
            new_left, new_top, new_width, new_height = transform_item_for_gap_change(
                left, top, width, height, page_w, page_h,
                old_edge_gap, old_internal_gap, new_edge_gap, new_internal_gap
            )
            
            updated_text = t.copy()
            updated_text['area_left'] = new_left
            updated_text['area_top'] = new_top
            updated_text['area_width'] = new_width
            updated_text['area_height'] = new_height
            transformed_texts.append(updated_text)
        
        # Push transformed layout (replaces current layout)
        self.layout_mgr.push_layout(pageno, transformed_photos, transformed_texts)
    
    def on_size_importance_changed(self):
        """Handle size importance parameter change."""
        try:
            new_importance = float(self.size_importance_var.get())
            if 0.1 <= new_importance <= 1000.0:  # Reasonable bounds
                self.size_importance = new_importance
                self.update_weights_display()  # Refresh cost display
        except ValueError:
            pass  # Ignore invalid input
    
    def on_undersized_threshold_changed(self):
        """Handle undersized threshold parameter change."""
        try:
            new_threshold = float(self.undersized_threshold_var.get())
            if 0.1 <= new_threshold <= 1.0:  # Reasonable bounds (10% to 100%)
                self.undersized_threshold = new_threshold
                self.update_weights_display()  # Refresh cost display
        except ValueError:
            pass  # Ignore invalid input
    
    def on_undersized_penalty_changed(self):
        """Handle undersized penalty parameter change."""
        try:
            new_penalty = float(self.undersized_penalty_var.get())
            if 0.1 <= new_penalty <= 100.0:  # Reasonable bounds
                self.undersized_penalty = new_penalty
                self.update_weights_display()  # Refresh cost display
        except ValueError:
            pass  # Ignore invalid input

    def _get_thumbnail(self, path, w, h):
        """Get thumbnail for an image, using cache if available.
        
        Args:
            path: Path to the image file
            w: Thumbnail width in pixels
            h: Thumbnail height in pixels
        
        Returns:
            PIL Image of size (w, h), or None if load fails
        """
        # Avoid creating huge thumbnails; enforce minimums
        if w <= 0 or h <= 0:
            return None
        key = (path, w, h)
        if key in self.thumb_cache:
            return self.thumb_cache[key]
        
        # Load thumbnail using shared function
        thumb = load_thumbnail(Path(path), w, h, verbose=True)
        if thumb is not None:
            self.thumb_cache[key] = thumb
        return thumb

    def prev_page(self):
        if self.index > 0:
            self.index -= 1
            self.render_page()

    def next_page(self):
        if self.index < len(self.pages)-1:
            self.index += 1
            self.render_page()

    def goto_page(self):
        try:
            v = int(self.goto_var.get())
        except Exception:
            return
        # find index for page number
        for i,(pn,_) in enumerate(self.pages):
            if pn == v:
                self.index = i
                self.render_page()
                return

    def quit(self):
        self.root.quit()
    
    def _on_window_resize(self, event):
        """Handle window resize events by redrawing the page at the new scale.
        
        Use debouncing to avoid excessive redraws during continuous resizing.
        """
        # Only respond to resize events on the root window itself
        if event.widget != self.root:
            return
        
        # Cancel any pending resize render
        if self._resize_pending:
            self.root.after_cancel(self._resize_pending)
        
        # Schedule a new render after a short delay (debouncing)
        self._resize_pending = self.root.after(100, self._do_resize_render)
    
    def _do_resize_render(self):
        """Actually perform the render after resize."""
        self._resize_pending = False
        self.render_page()
    
    def show_status(self, message, error=False):
        """Display a status message in the UI.
        
        Args:
            message: Message to display
            error: If True, show in red; otherwise blue
        """
        color = 'red' if error else 'blue'
        self.status_var.set(message)
        # Update Entry foreground color
        self.status_entry.config(foreground=color)
        # Message persists until page change or new message

    def generate_layout(self):
        """Run collage-generator on current page photos in a background thread.

        The Generate button is disabled while the operation runs and re-enabled
        when finished. Errors are shown; successful completion updates the UI
        without a popup.
        """
        # disable the button immediately to prevent double clicks
        try:
            self.gen_btn.config(state='disabled')
        except Exception:
            pass
        
        # Show "Running..." status
        self.show_status('Running...')

        def worker():
            pageno, info = self.pages[self.index]
            current_layout = self.layout_mgr.get_current(pageno)
            photos = current_layout.photos if current_layout else info.get('photos', [])

            if not photos:
                # re-enable on main thread
                self.root.after(0, lambda: self.gen_btn.config(state='normal'))
                return

            page_w = info.get('page_width', 2100.0)
            page_h = info.get('page_height', 2970.0)
            
            # Get current gaps for this page from layout manager
            internal_gap = self.layout_mgr.get_internal_gap(pageno)
            edge_gap = self.layout_mgr.get_edge_gap(pageno)

            # Get texts for this page
            texts = info.get('texts', [])
            
            # Create algorithm instance based on selection
            algo_name = self.algorithm_var.get()
            if algo_name == 'Collage-Gen':
                algorithm = CollageGeneratorAlgorithm(temperature=1.0)
            elif algo_name == 'Fan-GA':
                algorithm = FanLayoutAlgorithm(
                    size_importance=self.size_importance,
                    undersized_threshold=self.undersized_threshold,
                    undersized_penalty=self.undersized_penalty
                )
            elif algo_name == 'Gridify':
                algorithm = GridifyAlgorithm(debug=self.debug_var.get())
            elif algo_name == 'Tree-Builder':
                algorithm = TreeBuilderAlgorithm(tolerance=20.0)
            else:
                algorithm = CollageGeneratorAlgorithm(temperature=1.0)  # fallback
            
            # Collect checkbox states for photos on this page
            use_slot_aspect_for_photos = {}
            for photo_idx in range(len(photos)):
                checkbox_key = (pageno, photo_idx)
                if checkbox_key in self.use_slot_aspect:
                    use_slot_aspect_for_photos[photo_idx] = self.use_slot_aspect[checkbox_key].get()

            # Get original photos for slot aspect ratio preservation
            original_layout = self.layout_mgr.get_original(pageno)
            original_photos = original_layout.photos if original_layout else None
            
            # Build preferred_sizes dict from layout manager
            preferred_sizes = {}
            for i, p in enumerate(photos):
                fn = p.get('filename', '')
                if fn:
                    preferred_sizes[fn] = self.layout_mgr.get_size(pageno, fn)
            for i, t in enumerate(texts):
                text_id = f'TEXT_{i}'
                preferred_sizes[text_id] = self.layout_mgr.get_size(pageno, text_id)
            
            success, updated_photos, updated_texts, error_msg = generate_layout_for_page(
                photos, page_w, page_h, self.photo_dimensions,
                algorithm=algorithm, edge_gap=edge_gap, internal_gap=internal_gap, texts=texts,
                preferred_sizes=preferred_sizes,
                use_slot_aspect=use_slot_aspect_for_photos, original_photos=original_photos,
                origin_left=info.get('origin_left', 0.0)
            )
            
            # MCF stores area_left as absolute coordinates relative to the full spread.
            # The collage generator returns coordinates relative to the single-page
            # width (0..page_w). Add origin_left back so updated area_left matches
            # the original absolute coordinate system.
            if success and updated_photos:
                origin_left = info.get('origin_left', 0.0)
                if origin_left:
                    for up in updated_photos:
                        # Some items may lack area_left; guard the addition
                        if 'area_left' in up and up['area_left'] is not None:
                            up['area_left'] = up['area_left'] + origin_left
            
            # Apply origin_left to updated_texts as well
            if success and updated_texts:
                origin_left = info.get('origin_left', 0.0)
                if origin_left:
                    for ut in updated_texts:
                        if 'area_left' in ut and ut['area_left'] is not None:
                            ut['area_left'] = ut['area_left'] + origin_left

            def on_done():
                # re-enable button
                try:
                    self.gen_btn.config(state='normal')
                except Exception:
                    pass

                if not success:
                    self.show_status(f'Layout generation failed: {error_msg}', error=True)
                    return
                
                self.show_status(f'Layout generated successfully using {self.algorithm_var.get()}')

                # Push new layout (both photos and texts) to manager and refresh view
                self.layout_mgr.push_layout(pageno, updated_photos, updated_texts)
                self.render_page()

            self.root.after(0, on_done)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def undo_layout(self):
        """Revert to previous layout variant."""
        pageno, info = self.pages[self.index]
        if self.layout_mgr.undo_layout(pageno):
            self.show_status(f'Reverted to previous layout for page {pageno}')
            self.render_page()
        else:
            self.show_status('No more layouts to go back to.')

    def save_layout(self):
        """Write current layout to disk and clear in-memory variants.
        
        This function:
        1. Gets the current layout (modified or original)
        2. Writes it back to the MCF file (with backup)
        3. Clears the in-memory layout history for this page
        4. Keeps the layout visible (now matches what's on disk)
        """
        if not self.pages or not self.mcf_file_path:
            self.show_status('Cannot save: no MCF file path', error=True)
            return
        
        pageno, info = self.pages[self.index]
        
        # Get current layout (modified or original)
        current_layout = self.layout_mgr.get_current(pageno)
        if not current_layout:
            self.show_status('No layout to save', error=True)
            return
        
        photos = current_layout.photos
        texts = current_layout.texts
        
        try:
            # Write to MCF file (makes backup automatically)
            result = update_page_layout(
                self.mcf_file_path, pageno, photos, texts, make_backup=True
            )
            
            # Clear in-memory history for this page (layout now matches disk)
            self.layout_mgr.clear_layouts(pageno)
            
            # Update status with backup info
            backup_name = os.path.basename(result['backup_path']) if result['backup_path'] else 'none'
            self.show_status(
                f"Page {pageno} saved to disk ({result['modified_photos']} photos, "
                f"{result['modified_texts']} texts). Backup: {backup_name}"
            )
            
            # No need to re-render; layout is unchanged visually
            # But update weights display to clear any pending changes indicator
            self.update_weights_display()
            
        except Exception as e:
            self.show_status(f'Save failed: {e}', error=True)

    def equal_sizes(self):
        """Set all photos and texts to equal preferred size (10.0)."""
        if not self.pages:
            return
        pageno, info = self.pages[self.index]
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])
        texts = current_layout.texts if current_layout else info.get('texts', [])
        
        # Set equal size for all photos
        for p in photos:
            fn = p.get('filename', '')
            self.layout_mgr.set_size(pageno, fn, 10.0)
        
        # Set equal size for all texts
        for i, t in enumerate(texts):
            text_id = f'TEXT_{i}'
            self.layout_mgr.set_size(pageno, text_id, 10.0)
        
        self.update_weights_display()
    
    def stored_sizes(self):
        """Restore preferred sizes from original layout areas."""
        if not self.pages:
            return
        pageno, info = self.pages[self.index]
        page_w = info.get('page_width', 2100.0)
        page_h = info.get('page_height', 2970.0)
        origin_left = info.get('origin_left', 0.0)
        stored = self.layout_mgr.get_stored_sizes_for_page(pageno, page_w, page_h, origin_left)
        if not stored:
            return
        # stored dict contains both filenames (for photos) and TEXT_N (for texts)
        for item_id, size in stored.items():
            self.layout_mgr.set_size(pageno, item_id, size)
        self.update_weights_display()

    def use_original(self):
        """Discard current layout and revert to original from file."""
        pageno, info = self.pages[self.index]
        self.layout_mgr.clear_layouts(pageno)
        self.layout_mgr.clear_gaps(pageno)  # Also reset gap values to original
        self.show_status(f'Reverted page {pageno} to original layout.')
        self.render_page()


def launch_gui(mcf_path):
    root_el = parse_mcf_from_path(mcf_path)
    root = tk.Tk()
    app = LayoutViewer(root, root_el, mcf_path)
    root.mainloop()
