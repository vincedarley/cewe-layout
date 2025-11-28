"""Simple Tkinter UI to browse pages and display layout rectangles."""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk, ImageOps
import math
import os
from pathlib import Path
import threading
import traceback
import cv2

from .parser import extract_pages_info, parse_mcf_from_path
from .layout_ops import LayoutManager
from .collage_wrapper import generate_layout_for_page
from .algorithms.evaluator import evaluate_layout
from .algorithms.collage_generator import CollageGeneratorAlgorithm
from .algorithms.genetic_photo_layout import GeneticPhotoLayoutAlgorithm
from .algorithms.fan_layout import FanLayoutAlgorithm
from .gap_utils import (
    estimate_gap,
    estimate_gaps,
    analyze_gaps,
    transform_page_to_gapfree,
    transform_item_to_gapfree
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
        
        # Track which photos should use slot aspect ratio (dict: {(pageno, photo_idx): BooleanVar})
        self.use_slot_aspect = {}

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
        self.root.title('cewe-layout — Page Viewer')

        self.canvas_w = 900
        self.canvas_h = 1200

        self.img_label = ttk.Label(self.root)
        self.img_label.pack(fill='both', expand=True)

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
            'Collage-Gen',  # default
            'Collage-Gen', 'Generic-GA', 'Fan-GA'
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
        weights_btn = ttk.Button(self.ctrl, text='Adjust Sizes', command=self.adjust_sizes)
        weights_btn.grid(row=3, column=0, padx=4, pady=4)
        
        quit_btn = ttk.Button(self.ctrl, text='Quit (q)', command=self.quit)
        quit_btn.grid(row=3, column=1, padx=8)
        
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
        ttk.Label(photo_frame, text='Preferred', font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=2, padx=2, pady=2, sticky='w')
        ttk.Label(photo_frame, text='Actual', font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=3, padx=2, pady=2, sticky='w')
        
        # Item (photo/text) weight rows will be added dynamically to photo_frame
        self.photo_frame = photo_frame
        
        # RIGHT COLUMN: Cost info (top) and Parameters (bottom)
        right_col = ttk.Frame(self.info_frame)
        right_col.grid(row=0, column=1, sticky='ne')
        
        # Cost display frame (top of right column)
        # Use a simple frame (no redundant title)
        cost_frame = ttk.Frame(right_col, padding=6)
        cost_frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        
        ttk.Label(cost_frame, text='Total cost:', font=('TkDefaultFont', 11, 'bold')).grid(row=0, column=0, sticky='w', pady=1)
        self.cost_total_label = ttk.Label(cost_frame, text='--', font=('TkDefaultFont', 11))
        self.cost_total_label.grid(row=0, column=1, sticky='w', padx=4, pady=1)
        
        ttk.Label(cost_frame, text='Empty space:', font=('TkDefaultFont', 10)).grid(row=1, column=0, sticky='w', pady=1)
        self.cost_empty_label = ttk.Label(cost_frame, text='--', font=('TkDefaultFont', 10))
        self.cost_empty_label.grid(row=1, column=1, sticky='w', padx=4, pady=1)
        
        ttk.Label(cost_frame, text='Size mismatch:', font=('TkDefaultFont', 10)).grid(row=2, column=0, sticky='w', pady=1)
        self.cost_size_label = ttk.Label(cost_frame, text='--', font=('TkDefaultFont', 10))
        self.cost_size_label.grid(row=2, column=1, sticky='w', padx=4, pady=1)
        
        # Indented sub-components of size mismatch
        ttk.Label(cost_frame, text='  Normal:', font=('TkDefaultFont', 9)).grid(row=3, column=0, sticky='w', pady=1)
        self.cost_size_normal_label = ttk.Label(cost_frame, text='--', font=('TkDefaultFont', 9))
        self.cost_size_normal_label.grid(row=3, column=1, sticky='w', padx=4, pady=1)
        
        ttk.Label(cost_frame, text='  Undersized:', font=('TkDefaultFont', 9)).grid(row=4, column=0, sticky='w', pady=1)
        self.cost_size_undersized_label = ttk.Label(cost_frame, text='--', font=('TkDefaultFont', 9))
        self.cost_size_undersized_label.grid(row=4, column=1, sticky='w', padx=4, pady=1)
        
        ttk.Label(cost_frame, text='  Count:', font=('TkDefaultFont', 9)).grid(row=5, column=0, sticky='w', pady=1)
        self.undersized_count_label = ttk.Label(cost_frame, text='--', font=('TkDefaultFont', 9))
        self.undersized_count_label.grid(row=5, column=1, sticky='w', padx=4, pady=1)

        # Formula display: Total = Empty% + λ × SizeMismatch%-sq (normal) + λ × k × SizeMismatch%-sq (undersized)
        self.cost_formula_label = ttk.Label(cost_frame, text='', font=('TkDefaultFont', 10, 'italic'))
        self.cost_formula_label.grid(row=6, column=0, columnspan=2, sticky='w', pady=(4,0))
        
        # Parameters frame (bottom of right column)
        param_frame = ttk.LabelFrame(right_col, text='Parameters', padding=6)
        param_frame.grid(row=1, column=0, sticky='ew')
        
        # Edge gap parameter (read-only display)
        ttk.Label(param_frame, text='Edge gap (mm):').grid(row=0, column=0, sticky='w', pady=2)
        self.edge_gap_var = tk.StringVar(value='0.0')
        edge_gap_entry = ttk.Entry(param_frame, textvariable=self.edge_gap_var, width=8, state='readonly')
        edge_gap_entry.grid(row=0, column=1, sticky='w', padx=4, pady=2)
        
        # Internal gap parameter (editable)
        ttk.Label(param_frame, text='Internal gap (mm):').grid(row=1, column=0, sticky='w', pady=2)
        self.gap_var = tk.StringVar(value='0.0')
        self.gap_entry = ttk.Entry(param_frame, textvariable=self.gap_var, width=8)
        self.gap_entry.grid(row=1, column=1, sticky='w', padx=4, pady=2)
        self.gap_entry.bind('<Return>', lambda e: self.on_gap_changed())
        self.gap_entry.bind('<FocusOut>', lambda e: self.on_gap_changed())
        
        # Weight importance parameter
        ttk.Label(param_frame, text='Size importance (λ):').grid(row=2, column=0, sticky='w', pady=2)
        self.size_importance_var = tk.StringVar(value='100.0')
        self.size_importance_entry = ttk.Entry(param_frame, textvariable=self.size_importance_var, width=8)
        self.size_importance_entry.grid(row=2, column=1, sticky='w', padx=4, pady=2)
        self.size_importance_entry.bind('<Return>', lambda e: self.on_size_importance_changed())
        self.size_importance_entry.bind('<FocusOut>', lambda e: self.on_size_importance_changed())
        
        # Undersized threshold parameter
        ttk.Label(param_frame, text='Undersized threshold:').grid(row=3, column=0, sticky='w', pady=2)
        self.undersized_threshold_var = tk.StringVar(value='0.5')
        self.undersized_threshold_entry = ttk.Entry(param_frame, textvariable=self.undersized_threshold_var, width=8)
        self.undersized_threshold_entry.grid(row=3, column=1, sticky='w', padx=4, pady=2)
        self.undersized_threshold_entry.bind('<Return>', lambda e: self.on_undersized_threshold_changed())
        self.undersized_threshold_entry.bind('<FocusOut>', lambda e: self.on_undersized_threshold_changed())
        
        # Undersized penalty parameter
        ttk.Label(param_frame, text='Undersized penalty (k):').grid(row=4, column=0, sticky='w', pady=2)
        self.undersized_penalty_var = tk.StringVar(value='5.0')
        self.undersized_penalty_entry = ttk.Entry(param_frame, textvariable=self.undersized_penalty_var, width=8)
        self.undersized_penalty_entry.grid(row=4, column=1, sticky='w', padx=4, pady=2)
        self.undersized_penalty_entry.bind('<Return>', lambda e: self.on_undersized_penalty_changed())
        self.undersized_penalty_entry.bind('<FocusOut>', lambda e: self.on_undersized_penalty_changed())

        # Equal sizes button
        equal_btn = ttk.Button(param_frame, text='Equal sizes', command=self.equal_sizes)
        equal_btn.grid(row=5, column=0, columnspan=2, sticky='ew', pady=(6,2))
        
        # Stored sizes button
        stored_btn = ttk.Button(param_frame, text='Stored sizes', command=self.stored_sizes)
        stored_btn.grid(row=6, column=0, columnspan=2, sticky='ew', pady=2)
        
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
        
        if not self.pages:
            img = Image.new('RGB', (self.canvas_w, self.canvas_h), 'white')
            draw = ImageDraw.Draw(img)
            draw.text((10,10), 'No pages found', fill='black')
            self._show_image(img)
            return

        pageno, info = self.pages[self.index]
        # Fetch current layout from layout manager (may be modified or original)
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])
        texts = current_layout.texts if current_layout else info.get('texts', [])

        img = Image.new('RGB', (self.canvas_w, self.canvas_h), 'white')
        draw = ImageDraw.Draw(img)

        # Draw header
        text_info = f', {len(texts)} text blocks' if texts else ''
        draw.text((8,8), f'Page {pageno} — {len(photos)} photos{text_info}', fill='black')

        # Use page meta to map coordinates. page_width/height are in MCF units (0.1mm)
        page_w = info.get('page_width', 2100.0)
        page_h = info.get('page_height', 2970.0)
        origin_left = info.get('origin_left', 0.0)

        margin = 20
        header_offset = 50  # Extra space below header to prevent overlap with page number
        # scale to fit width (maintain aspect ratio)
        scale_x = (self.canvas_w - 2*margin) / page_w
        scale_y = (self.canvas_h - 2*margin - header_offset) / page_h
        scale = min(scale_x, scale_y)

        # Calculate frame position (draw it after photos/texts so it's on top in bleed situations)
        frame_w = page_w * scale
        frame_h = page_h * scale
        frame_x = margin
        frame_y = margin + header_offset

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
        
        # Analyze gaps from ORIGINAL layout only (never from algorithm output)
        # This ensures gap is a fixed parameter that algorithms don't modify
        original_photos = info.get('photos', [])
        original_texts = info.get('texts', [])
        original_items = original_photos + original_texts
        
        edge_gap = 0.0
        internal_gap = 0.0
        if original_items:
            analysis = analyze_gaps(original_items, page_w, page_h, origin_left)
            edge_gap = analysis.edge_gap
            internal_gap = analysis.internal_gap
            
            # Display edge gap (or negative for bleed)
            if analysis.bleed > 0:
                self.edge_gap_var.set(f'-{analysis.bleed / 10.0:.1f}')
            else:
                self.edge_gap_var.set(f'{edge_gap / 10.0:.1f}')
        else:
            self.edge_gap_var.set('0.0')
        
        # Initialize gap from original layout once, then never change it
        current_gap = self.layout_mgr.get_gap(pageno)
        if current_gap == 0.0 and internal_gap > 0:
            self.layout_mgr.set_gap(pageno, internal_gap)
            current_gap = internal_gap
        elif current_gap == 0.0 and edge_gap > 0:
            self.layout_mgr.set_gap(pageno, edge_gap)
            current_gap = edge_gap
        
        # Update internal gap display (convert MCF units to mm: 1 MCF unit = 0.1mm)
        gap_mm = current_gap / 10.0
        self.gap_var.set(f'{gap_mm:.1f}')
        
        # Clear existing weight widgets
        for widgets in self.weight_widgets:
            for w in widgets:
                w.destroy()
        self.weight_widgets.clear()
        
        if not photos and not texts:
            self.cost_total_label.config(text='--')
            self.cost_empty_label.config(text='No items')
            self.cost_size_label.config(text='--')
            self.cost_size_normal_label.config(text='--')
            self.cost_size_undersized_label.config(text='--')
            return
        
        # Build LayoutRectangle list from CURRENT layout (photos and texts)
        # This is what we evaluate (algorithm output or original)
        # But we use gaps from ORIGINAL layout (above) as fixed parameters
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
        
        cost = evaluate_layout(
            eval_page_w, eval_page_h, rectangles,
            size_importance=self.size_importance,
            acceptable_empty_fraction=0.05,
            undersized_threshold=self.undersized_threshold,
            undersized_penalty=self.undersized_penalty
        )
        
        # Update cost labels with human-readable format
        self.cost_total_label.config(text=f'{cost.total_cost:.1f}')
        
        # Empty space as percentage (fraction of page unused)
        empty_pct = cost.empty_space_fraction * 100
        self.cost_empty_label.config(text=f'{empty_pct:.1f}%')
        
        # Total size mismatch
        size_pct_sq = cost.size_mismatch_cost / self.size_importance if self.size_importance > 0 else 0.0
        self.cost_size_label.config(text=f'{size_pct_sq:.2f} %-sq')
        
        # Normal size mismatch component
        size_normal_pct_sq = cost.size_mismatch_normal_cost / self.size_importance if self.size_importance > 0 else 0.0
        self.cost_size_normal_label.config(text=f'{size_normal_pct_sq:.2f} %-sq')
        
        # Undersized size mismatch component (includes penalty)
        size_undersized_pct_sq = cost.size_mismatch_undersized_cost / (self.size_importance * self.undersized_penalty) if (self.size_importance > 0 and self.undersized_penalty > 0) else 0.0
        self.cost_size_undersized_label.config(text=f'{size_undersized_pct_sq:.2f} %-sq')
        
        # Undersized count
        total_items = len(rectangles)
        self.undersized_count_label.config(text=f'{cost.undersized_count}/{total_items}')

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
                            safefn = fn.replace('safecontainer:/', '').lstrip('/')
                            img_path = Path(self.mcf_base_folder) / safefn
                            if img_path.exists():
                                try:
                                    arr = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
                                    if arr is not None:
                                        img_h, img_w = arr.shape[:2]
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
    
    def on_gap_changed(self):
        """Handle gap entry change."""
        if not self.pages:
            return
        try:
            pageno, info = self.pages[self.index]
            gap_mm = float(self.gap_var.get())
            # Convert mm to MCF units (1mm = 10 MCF units)
            gap_mcf = gap_mm * 10.0
            if 0.0 <= gap_mcf <= 200.0:  # Reasonable bounds (0-20mm)
                self.layout_mgr.set_gap(pageno, gap_mcf)
                self.update_weights_display()  # Refresh cost display
        except ValueError:
            pass  # Ignore invalid input
    
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
        # Avoid creating huge thumbnails; enforce minimums
        if w <= 0 or h <= 0:
            return None
        key = (path, w, h)
        if key in self.thumb_cache:
            return self.thumb_cache[key]
        try:
            im = Image.open(path)
            # Auto-rotate based on EXIF orientation (support older Pillow)
            exif_transpose = getattr(Image, 'exif_transpose', None) or getattr(ImageOps, 'exif_transpose', None)
            if exif_transpose:
                try:
                    im = exif_transpose(im)
                except Exception:
                    # If transpose fails, continue without raising noisy traceback
                    pass
            im = im.convert('RGB')
            im.thumbnail((w, h), Image.LANCZOS)
            # create a background image exactly the size of slot and paste centered
            bg = Image.new('RGB', (w, h), 'white')
            x = max(0, (w - im.width) // 2)
            y = max(0, (h - im.height) // 2)
            bg.paste(im, (x, y))
            self.thumb_cache[key] = bg
            return bg
        except Exception as e:
            # Detailed diagnostic for failures: print exception and try OpenCV fallback
            print(f"[thumb] PIL failed to open {path}: {e}")
            traceback.print_exc()
            try:
                arr = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if arr is None:
                    print(f"[thumb] OpenCV failed to read {path} (imread returned None)")
                    return None
                arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
                im2 = Image.fromarray(arr)
                im2.thumbnail((w, h), Image.LANCZOS)
                bg = Image.new('RGB', (w, h), 'white')
                x = max(0, (w - im2.width) // 2)
                y = max(0, (h - im2.height) // 2)
                bg.paste(im2, (x, y))
                self.thumb_cache[key] = bg
                return bg
            except Exception as e2:
                print(f"[thumb] OpenCV fallback also failed for {path}: {e2}")
                traceback.print_exc()
                return None

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
            
            # Get current gap for this page
            gap = self.layout_mgr.get_gap(pageno)

            # Get texts for this page
            texts = info.get('texts', [])

            # Get gap analysis for this page
            all_items = info.get('photos', []) + info.get('texts', [])
            if all_items:
                analysis = analyze_gaps(all_items, page_w, page_h, info.get('origin_left', 0.0))
                edge_gap = analysis.edge_gap
                internal_gap = analysis.internal_gap
            else:
                edge_gap = 0.0
                internal_gap = 0.0
            
            # Create algorithm instance based on selection
            algo_name = self.algorithm_var.get()
            if algo_name == 'Collage-Gen':
                algorithm = CollageGeneratorAlgorithm(temperature=1.0)
            elif algo_name == 'Generic-GA':
                algorithm = GeneticPhotoLayoutAlgorithm()
            elif algo_name == 'Fan-GA':
                algorithm = FanLayoutAlgorithm(
                    size_importance=self.size_importance,
                    undersized_threshold=self.undersized_threshold,
                    undersized_penalty=self.undersized_penalty
                )
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
            
            success, updated_photos, updated_texts, error_msg = generate_layout_for_page(
                photos, page_w, page_h, Path(self.mcf_base_folder), 
                algorithm=algorithm, edge_gap=edge_gap, internal_gap=internal_gap, texts=texts,
                use_slot_aspect=use_slot_aspect_for_photos, original_photos=original_photos
            )

            # If this page has an origin_left (right-hand page), the parser
            # stores area_left as absolute coordinates relative to the full spread.
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
        """Accept current layout and clear in-memory variants."""
        pageno, info = self.pages[self.index]
        self.layout_mgr.clear_layouts(pageno)
        self.show_status(f'Layout for page {pageno} saved. Memory cleared.')
        self.render_page()

    def adjust_sizes(self):
        """Open dialog to adjust per-photo preferred sizes for layout generation."""
        pageno, info = self.pages[self.index]
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])
        
        if not photos:
            self.show_status('No photos on this page.')
            return
        
        # Create top-level weight dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f'Photo Sizes - Page {pageno}')
        dialog.geometry('400x500')
        
        # Header
        tk.Label(dialog, text=f'Adjust preferred sizes for page {pageno} photos:', 
                font=('Helvetica', 10, 'bold')).pack(pady=10)
        
        # Scrollable frame
        canvas = tk.Canvas(dialog)
        scrollbar = ttk.Scrollbar(dialog, orient='vertical', command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            '<Configure>',
            lambda e: canvas.configure(scrollregion=canvas.bbox('all'))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Weight controls for each photo
        size_vars = {}
        for i, photo in enumerate(photos):
            fn = photo.get('filename', '').split('/')[-1]
            current_size = self.layout_mgr.get_size(pageno, photo.get('filename', ''))
            
            frame = ttk.Frame(scrollable_frame)
            frame.pack(fill='x', padx=5, pady=5)
            
            label = ttk.Label(frame, text=f'{i+1}. {fn[:30]}', width=35, anchor='w')
            label.pack(side='left', padx=5)
            
            var = tk.DoubleVar(value=current_size)
            size_vars[photo.get('filename', '')] = var
            
            spinbox = ttk.Spinbox(frame, from_=0.0, to=50.0, increment=0.5, 
                                 textvariable=var, width=6)
            spinbox.pack(side='right', padx=5)
        
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # OK/Cancel buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(side='bottom', fill='x', padx=10, pady=10)
        
        def apply_sizes():
            for fn, var in size_vars.items():
                self.layout_mgr.set_size(pageno, fn, var.get())
            dialog.destroy()
            self.show_status('Photo preferred sizes updated. Use them in next layout generation.')
            self.render_page()
        
        ttk.Button(button_frame, text='OK', command=apply_sizes).pack(side='left', padx=5)
        ttk.Button(button_frame, text='Cancel', command=dialog.destroy).pack(side='left', padx=5)

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
        self.show_status(f'Reverted page {pageno} to original layout.')
        self.render_page()


def launch_gui(mcf_path):
    root_el = parse_mcf_from_path(mcf_path)
    root = tk.Tk()
    app = LayoutViewer(root, root_el, mcf_path)
    root.mainloop()
