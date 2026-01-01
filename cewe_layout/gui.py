"""Simple Tkinter UI to browse pages and display layout rectangles."""
import tkinter as tk
from tkinter import ttk, filedialog

import math
import os
import platform
from pathlib import Path
import threading
import shutil
import logging
from typing import Literal, Any

from .pdf2cewe.pdf_extractor import performSegmentationOnPage

logger = logging.getLogger(__name__)

from .parser import extract_pages_info, parse_mcf_from_path
from .layout_ops import LayoutManager
from .page_gui import PageRenderer, PageRenderData
from .collage_wrapper import generate_layout_for_page
from .algorithms.evaluator import evaluate_layout
from .algorithms.collage_generator import CollageGeneratorAlgorithm
from .algorithms.fan_layout import FanLayoutAlgorithm
from .algorithms.tree_builder import TreeBuilderAlgorithm
from .algorithms.gridify import GridifyAlgorithm
from .algorithms.gap_perfecter import GapPerfecterAlgorithm
from .algorithms.long_gap_perfecter import LongGapPerfecterAlgorithm
from .photos import get_image_dimensions, get_photo_preferred_size
from .writer import update_page_layout
from .page_utils import determine_page_owner_of_area, page_sort_key
from .gap_utils import (
    analyze_gaps,
    analyze_gap_details,
    report_gap_variations,
    transform_page_to_gapfree,
    transform_item_to_gapfree,
    transform_item_for_gap_change,
    make_uniform_edge_gap,
    make_edge_gap
)
from .file_utils import (
    extract_metadata_from_filename,
    encode_metadata_in_filename
)


# Constants for MCF unit conversion and defaults
MM_TO_MCF = 10.0  # 1mm = 10 MCF units
MCF_TO_MM = 0.1   # 1 MCF unit = 0.1mm
DEFAULT_EDGE_GAP = make_uniform_edge_gap(140.0)  # 14mm in MCF units, uniform on all 4 edges
DEFAULT_INTERNAL_GAP = 90.0  # 9mm in MCF units


# Helper functions for common patterns

def is_macos():
    """Check if running on macOS."""
    return platform.system() == 'Darwin'


def get_modifier_key():
    """Get the primary modifier key for the current platform.
    
    Returns:
        'Command' for macOS, 'Control' for others
    """
    return 'Command' if is_macos() else 'Control'


def get_modifier_symbol():
    """Get the symbol for the primary modifier key.
    
    Returns:
        '⌘' for macOS, 'Ctrl+' for others
    """
    return '⌘' if is_macos() else 'Ctrl+'


class LayoutViewer:
    def __init__(self, root, mcf_root, mcf_file_path, pdf_content=None, insidecovers=False):
        # mcf_root is the parsed XML root; mcf_file_path is the full path to the .mcf file
        self.pages = extract_pages_info(mcf_root)
        self.mcf_file_path = mcf_file_path
        self.pdf_content = pdf_content  # Store PDF content if provided
        self.insidecovers = insidecovers  # Whether PDF includes inside cover pages
        # try to find the imagedir attribute on the root to locate images
        self.image_folder_attr = mcf_root.get('imagedir') or ''
        self.mcf_base_folder = '' if mcf_file_path is None else os.path.dirname(mcf_file_path)
        self.index = 0
        self.layout_mgr = LayoutManager()
        
        # Detect Canvas/Calendar mode from first page
        self.is_canvas = False
        self.is_calendar = False
        self.calendar_edge_gaps = None
        if self.pages:
            _, first_info = self.pages[0]
            self.is_canvas = first_info.get('is_canvas', False)
            self.is_calendar = first_info.get('is_calendar', False)
            if self.is_calendar:
                self.calendar_edge_gaps = first_info.get('calendar_edge_gaps')
                if self.calendar_edge_gaps:
                    # Set the calendar edge gaps in the layout manager
                    self.layout_mgr.calendar_edge_gaps = self.calendar_edge_gaps
                    print(f"\n=== Calendar Mode Detected ===")
                    print(f"Fixed edge gaps enforced for calendar layout:")
                    print(f"  Left:   {self.calendar_edge_gaps['left']}")
                    print(f"  Top:    {self.calendar_edge_gaps['top']}")
                    print(f"  Right:  {self.calendar_edge_gaps['right']}")
                    print(f"  Bottom: {self.calendar_edge_gaps['bottom']}")
                    print(f"==============================\n")
        
        # Algorithm selection
        self.algorithm_var = tk.StringVar(value='Collage-Gen')
        
        # Debug flag for diagnostic output
        self.debug_var = tk.BooleanVar(value=False)
        
        # Spread mode flag - when True, show two pages (even+odd) as a spread
        # For Canvas only (single page), this is forced to True and locked
        # For Calendar (multiple standalone pages), spread mode is disabled (single pages only)
        self.spread_mode = tk.BooleanVar(value=self.is_canvas)
        
        # Track current spread pages (list of 1 or 2 page numbers)
        self.current_spread_pages = []
        
        # Track which photos should use slot aspect ratio (dict: {(pageno, photo_idx): BooleanVar})
        self.use_slot_aspect = {}
        
        # Track slot aspect ratios for each item (dict: {(pageno, item_idx): aspect_ratio})
        # This allows users to override the slot aspect ratio
        self.slot_aspect_ratios = {}
        
        # Cache photo dimensions: {filename: (width, height)} to avoid re-reading images
        self.photo_dimensions = {}

        # Identify inside cover pages once (page 0 and last numeric page)
        self.inside_front_cover_page = 0  # Page 0 is always inside front cover
        self.inside_back_cover_page = None
        numeric_pages = [(p, info) for p, info in self.pages if isinstance(p, int) and p > 0]
        if numeric_pages:
            last_page_num, last_page_info = numeric_pages[-1]
            # Inside back cover is always the last numeric page, which must be odd (right side)
            if last_page_num % 2 == 0:
                raise RuntimeError(f"Inside back cover page {last_page_num} is even (left side). It should be odd (right side).")
            self.inside_back_cover_page = last_page_num
        
        # Track protected inside covers (pages that should be blank when --insidecovers not provided)
        self.protected_inside_covers = set()
        if not self.insidecovers:
            # Without --insidecovers flag, inside cover pages are protected (blank)
            self.protected_inside_covers.add(self.inside_front_cover_page)
            if self.inside_back_cover_page is not None:
                self.protected_inside_covers.add(self.inside_back_cover_page)
        
        # Track photo improvements (photos upgraded with -up suffix)
        self.improved_photos = {}  # Maps original_filename -> improved_filename
        
        # initialize layout manager with originals from file
        for pageno, info in self.pages:
            self.layout_mgr.set_original(pageno, info.get('photos', []), info.get('texts', []))
            photos = info.get('photos', [])
            texts = info.get('texts', [])
            all_items = photos + texts
            page_w = info.get('page_width')
            page_h = info.get('page_height')
            origin_left = info.get('origin_left', 0.0)
            
            # Estimate gap to compute gap-free areas (matching evaluation coordinate space)
            # Use internal gap preferentially
            edge_gap, inter_gap = analyze_gaps(all_items, page_w, page_h, origin_left, self.spread_mode.get()) if all_items else (make_uniform_edge_gap(0.0), 0.0)
            # For auto-gap display, use internal_gap if available, else use average of edge_gaps
            gap = inter_gap if inter_gap > 0 else (edge_gap['top'] + edge_gap['bottom'] + edge_gap['left'] + edge_gap['right']) / 4.0
            
            # Compute total area in gap-free space (add gap to each photo dimension)
            total_area = sum(((p.get('area_width', 0) or 0) + gap) * ((p.get('area_height', 0) or 0) + gap) for p in all_items)
            if total_area > 0:
                for p in photos:
                    fn = p.get('filename', '')
                    # Try to extract preferred size from filename first
                    base_fn, size_from_filename, page_from_filename = extract_metadata_from_filename(fn)
                    if size_from_filename is not None:
                        # Use size from filename (already in 10× scale)
                        preferred = size_from_filename
                    else:
                        # Fallback: use gap-free area normalized to 10× scale for readability
                        area = ((p.get('area_width', 0) or 0) + gap) * ((p.get('area_height', 0) or 0) + gap)
                        preferred = (area / total_area) * 10.0
                    # Always use base filename (without -sz-pg) as the key
                    self.layout_mgr.set_size(pageno, base_fn, preferred)
                for i, t in enumerate(texts):
                    # Text blocks use identifier TEXT_<index>
                    text_id = f"TEXT_{i}"
                    area = ((t.get('area_width', 0) or 0) + gap) * ((t.get('area_height', 0) or 0) + gap)
                    preferred = (area / total_area) * 10.0
                    self.layout_mgr.set_size(pageno, text_id, preferred)
            else:
                # Fallback to uniform sizes (10.0 for 10× scaling)
                for p in photos:
                    fn = p.get('filename', '')
                    base_fn, _, _ = extract_metadata_from_filename(fn)
                    self.layout_mgr.set_size(pageno, base_fn, 10.0)
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
        
        # Create transparent pixel images early for button sizing
        self.delete_button_pixel = tk.PhotoImage(width=1, height=1)  # For delete buttons
        self.button_pixel = tk.PhotoImage(width=1, height=1)  # For compact buttons

        # Calculate canvas dimensions based on actual page size from first page
        # Add 5mm (50 MCF units) margin on all sides, just for display purposes. 
        # It is not a part of the actual book!
        self.margin_mcf = 50.0
        _, first_page_info = self.pages[0]
        page_w = first_page_info.get('page_width')
        page_h = first_page_info.get('page_height')
        
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

        self.canvas = tk.Canvas(self.root, bg='white', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        
        # Enable drag-and-drop for photo files
        self._setup_drag_and_drop()
        
        # Bind window resize event to redraw
        self.root.bind('<Configure>', self._on_window_resize)
        self._resize_pending = False

        # Controls window
        self.ctrlWin = tk.Toplevel(self.root)
        self.ctrlWin.title('QLayout Controls')
        self.ctrlWin.geometry('+50+50')

        # Row 0: Navigation - organize in two frames for tight grouping
        # For Canvas mode, hide all page navigation controls
        # For Calendar mode, show navigation but with 'Month:' label
        nav_frame = ttk.Frame(self.ctrlWin)
        if not self.is_canvas:
            nav_frame.grid(row=0, column=0, sticky='w', padx=4, pady=4)
        if self.is_canvas:
            page_label = 'Canvas:'
        elif self.is_calendar:
            page_label = 'Month:'
        else:
            page_label = 'Page:'
        self.page_num_var = tk.StringVar(value=page_label)
        self.page_num_label = ttk.Label(nav_frame, textvariable=self.page_num_var, font=('TkDefaultFont', 9))
        self.page_num_label.pack(side='left', padx=(0,4))
        prev_btn = ttk.Button(nav_frame, text='Prev (←)', command=self.prev_page)
        prev_btn.pack(side='left')
        next_btn = ttk.Button(nav_frame, text='Next (→)', command=self.next_page)
        next_btn.pack(side='left')
        
        goto_frame = ttk.Frame(self.ctrlWin)
        if not self.is_canvas:
            goto_frame.grid(row=0, column=1, sticky='w', padx=4, pady=4)
        ttk.Label(goto_frame, text='Go to:').pack(side='left', pady=2)
        self.goto_var = tk.StringVar()
        goto_entry = ttk.Entry(goto_frame, textvariable=self.goto_var, width=6)
        goto_entry.pack(side='left', padx=2, pady=2)
        goto_entry.bind('<Return>', lambda e: self.goto_page())
        
        # Page range label (e.g., "Pages 2-58")
        self.page_range_var = tk.StringVar(value='')
        self.page_range_label = ttk.Label(goto_frame, textvariable=self.page_range_var, foreground='gray')
        self.page_range_label.pack(side='left', padx=(8,0))
        
        # Spread mode checkbox (disabled for Canvas and Calendar - always single pages)
        is_spread_disabled = self.is_canvas or self.is_calendar
        spread_check = ttk.Checkbutton(goto_frame, text='Spread', variable=self.spread_mode, 
                                       command=self._on_spread_mode_change,
                                       state='disabled' if is_spread_disabled else 'normal')
        spread_check.pack(side='left', padx=(8,0))
        
        # Draw cropped checkbox (applies cutout/scale transformations from MCF)
        self.draw_cropped_var = tk.BooleanVar(value=False)
        draw_cropped_check = ttk.Checkbutton(goto_frame, text='Draw cropped', variable=self.draw_cropped_var,
                                             command=self._on_draw_cropped_change)
        draw_cropped_check.pack(side='left', padx=(8,0))
        
        # Collect all available algorithms
        all_algorithms = [
            CollageGeneratorAlgorithm(),
            FanLayoutAlgorithm(),
            GapPerfecterAlgorithm(),
            LongGapPerfecterAlgorithm(),
            GridifyAlgorithm(),
            TreeBuilderAlgorithm()
        ]
        
        # Separate into layout generators and fine-tuning algorithms
        layout_algorithms = [algo for algo in all_algorithms if not algo.forcesUseOfCurrentLayout()]
        fine_tuning_algorithms = [algo for algo in all_algorithms if algo.forcesUseOfCurrentLayout()]
        
        # Build dynamic registry mapping algorithm names to classes
        # This avoids hard-coded string comparisons and is robust to name changes
        self.algorithm_registry = {}
        for algo in all_algorithms:
            self.algorithm_registry[algo.getName()] = type(algo)
        
        # Get names for layout algorithm dropdown
        layout_algo_names = [algo.getName() for algo in layout_algorithms]
        
        # Row 1: Algorithm selection and Generate button - pack in single frame
        algo_frame = ttk.Frame(self.ctrlWin)
        algo_frame.grid(row=1, column=0, columnspan=2, sticky='w', padx=4, pady=4)
        ttk.Label(algo_frame, text='Algorithm:').pack(side='left', padx=(0,4))
        
        # Set default to last layout algorithm
        default_algo = layout_algo_names[-1] if layout_algo_names else 'Fan-GA'
        algo_menu = ttk.OptionMenu(
            algo_frame, self.algorithm_var,
            default_algo,
            *layout_algo_names
        )
        algo_menu.pack(side='left', padx=(0,4))
        
        # Generate button (uses selected algorithm)
        mod_sym = get_modifier_symbol()
        self.gen_btn = ttk.Button(algo_frame, text=f'Generate Layout ({mod_sym}R)', command=self._generate_layout)
        self.gen_btn.pack(side='left', padx=(0,4))
        
        # Debug checkbox next to Generate button
        debug_check = ttk.Checkbutton(algo_frame, text='Debug', variable=self.debug_var)
        debug_check.pack(side='left')
        
        # Row 1.5: Fine-tuning buttons
        fine_tuning_frame = ttk.Frame(self.ctrlWin)
        fine_tuning_frame.grid(row=2, column=0, columnspan=2, sticky='w', padx=4, pady=(0,4))
        ttk.Label(fine_tuning_frame, text='Fine-tuning:').pack(side='left', padx=(0,4))
        
        for algo in fine_tuning_algorithms:
            algo_name = algo.getName()
            btn = ttk.Button(
                fine_tuning_frame, 
                text=algo_name,
                command=lambda name=algo_name: self._run_fine_tuning(name)
            )
            btn.pack(side='left', padx=(0,2))
        
        # Row 3: PDF controls (only shown if pdf_content is available)
        pdf_row = 3
        if self.pdf_content:
            pdf_frame = ttk.Frame(self.ctrlWin)
            pdf_frame.grid(row=2, column=0, columnspan=2, sticky='w', padx=4, pady=4)
            
            ttk.Label(pdf_frame, text='PDF:').pack(side='left', padx=(0,4))
            
            # Checkbox for showing PDF composite background (checked by default)
            self.show_pdf_composite_var = tk.BooleanVar(value=True)
            pdf_check = ttk.Checkbutton(pdf_frame, variable=self.show_pdf_composite_var,
                                       command=self.render_page)
            pdf_check.pack(side='left', padx=(0,8))
            
            ttk.Label(pdf_frame, text='Photo count:').pack(side='left', padx=(0,4))
            self.pdf_photo_count_var = tk.StringVar(value='0')
            self.pdf_photo_count_entry = ttk.Entry(pdf_frame, textvariable=self.pdf_photo_count_var, width=5)
            self.pdf_photo_count_entry.pack(side='left')
            self.pdf_photo_count_entry.bind('<Return>', self._on_pdf_photo_count_change)
            
            ttk.Label(pdf_frame, text='  Re-segment photo:').pack(side='left', padx=(10,4))
            self.pdf_photo_select_var = tk.StringVar(value='')
            self.pdf_photo_select_entry = ttk.Entry(pdf_frame, textvariable=self.pdf_photo_select_var, width=5)
            self.pdf_photo_select_entry.pack(side='left')
            ttk.Label(pdf_frame, text='(empty = whole page)').pack(side='left', padx=(4,0))
            
            ttk.Label(pdf_frame, text='  Algorithm:').pack(side='left', padx=(10,4))
            
            # Dynamically populate segmenters from registry
            from .pdf2cewe.segmenter_base import list_segmenters
            from .pdf2cewe import image_segmenter, grid_segmenter, tree_segmenter  # Ensure all segmenters are registered
            available_segmenters = list_segmenters()
            
            self.segmentation_algorithm_var = tk.StringVar(value=available_segmenters[0] if available_segmenters else 'morphological')
            self.segmentation_algorithm_combo = ttk.Combobox(
                pdf_frame, 
                textvariable=self.segmentation_algorithm_var,
                values=available_segmenters,
                width=15,
                state='readonly'
            )
            self.segmentation_algorithm_combo.pack(side='left')
        
        # Row 2.5: Photo improvement controls (only shown if pdf_content is available)
        if self.pdf_content:
            improve_frame = ttk.Frame(self.ctrlWin)
            row_num = 3 if self.pdf_content else 2
            improve_frame.grid(row=row_num, column=0, columnspan=2, sticky='w', padx=4, pady=4)
        
            ttk.Label(improve_frame, text='Improve:').pack(side='left', padx=(0,4))
            improve_search_btn = ttk.Button(improve_frame, text='Search', command=self._search_photo_improvements)
            improve_search_btn.pack(side='left', padx=(0,4))
            ttk.Label(improve_frame, text='(finds better quality photos in -photos directory)').pack(side='left', padx=(4,0))
        
        # Row 3: Modified pages label (pack label and value tightly)
        modified_frame = ttk.Frame(self.ctrlWin)
        row_num = 4 if self.pdf_content else 3
        modified_frame.grid(row=row_num, column=0, columnspan=3, sticky='w', padx=4, pady=(5,0))
        ttk.Label(modified_frame, text='Modified pages:').pack(side='left')
        self.modified_pages_var = tk.StringVar(value='(none)')
        self.modified_pages_label = ttk.Label(modified_frame, textvariable=self.modified_pages_var, 
                                              font=('TkDefaultFont', 9), foreground='blue')
        self.modified_pages_label.pack(side='left', padx=(2,0))
        
        # Row 4: Action buttons (indented)
        actions_frame = ttk.Frame(self.ctrlWin)
        row_num = 5 if self.pdf_content else 4
        actions_frame.grid(row=row_num, column=0, columnspan=3, sticky='w', padx=4, pady=4)
        ttk.Label(actions_frame, text='  ').pack(side='left')  # Indentation spacer
        mod_sym = get_modifier_symbol()
        undo_btn = ttk.Button(actions_frame, text=f'Undo ({mod_sym}Z)', command=self.undo_layout)
        undo_btn.pack(side='left', padx=(0,4))
        orig_btn = ttk.Button(actions_frame, text='Use Original Page', command=self.use_original)
        orig_btn.pack(side='left', padx=(0,4))
        save_btn = ttk.Button(actions_frame, text=f'Save Modified ({mod_sym}S)', command=self.save_layout)
        save_btn.pack(side='left', padx=(0,4))
        pdf_btn = ttk.Button(actions_frame, text=f'Export PDF ({mod_sym}P)', command=self.export_to_pdf)
        pdf_btn.pack(side='left', padx=(0,4))

        # Row 5: Status message with label
        status_frame = ttk.Frame(self.ctrlWin)
        row_num = 6 if self.pdf_content else 5
        status_frame.grid(row=row_num, column=0, columnspan=3, padx=4, pady=4, sticky='ew')
        ttk.Label(status_frame, text='Status:').pack(side='left', padx=(0,4))
        self.status_var = tk.StringVar(value='')
        self.status_entry = ttk.Entry(status_frame, textvariable=self.status_var, 
                                      state='readonly', font=('TkDefaultFont', 9))
        self.status_entry.pack(side='left', fill='x', expand=True)
        # Store the style for color changes
        self.status_style = ttk.Style()
        
        # Weights and cost display frame with label inside
        self.info_frame = ttk.Frame(self.ctrlWin, padding=8, relief='sunken', borderwidth=1)
        self.info_frame.grid(row=6, column=0, columnspan=5, padx=4, pady=8, sticky='ew')
        
        # Layout Info label inside the frame
        ttk.Label(self.info_frame, text='Layout Info:').grid(row=0, column=0, columnspan=2, sticky='w', padx=0, pady=(0,4))
        
        # Configure columns: left column (0) for photos, right column (1) for cost/params
        self.info_frame.columnconfigure(0, weight=1)
        self.info_frame.columnconfigure(1, weight=0)
        
        # LEFT COLUMN: Photo weights
        photo_frame = ttk.Frame(self.info_frame)
        photo_frame.grid(row=1, column=0, sticky='nw', padx=(0, 20))
        
        ttk.Label(photo_frame, text='Item', font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=0, padx=2, pady=(2,0))
        
        # DPI header (new) and Aspect Ratio parent header spanning its 3 sub-columns
        ttk.Label(photo_frame, text='DPI', font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=1, padx=2, pady=(2,0))
        # Center Aspect Ratio header over the three sub-columns (slot, use slot, photo)
        ttk.Label(photo_frame, text='Aspect Ratio', font=('TkDefaultFont', 9, 'bold'), anchor='center').grid(row=0, column=2, columnspan=3, pady=(2,0), sticky='ew')

        # Sub-headers in row 1, directly above their respective data columns
        ttk.Label(photo_frame, text='Slot', font=('TkDefaultFont', 8)).grid(row=1, column=2, padx=2, pady=(0,2))
        ttk.Label(photo_frame, text='Use\nslot', font=('TkDefaultFont', 8), justify='center').grid(row=1, column=3, padx=2, pady=(0,2))
        ttk.Label(photo_frame, text='Photo', font=('TkDefaultFont', 8)).grid(row=1, column=4, padx=2, pady=(0,2))
        
        # Preferred header with Equal/Original buttons in row 1, centered over column 4
        pref_header = ttk.Label(photo_frame, text='Preferred', font=('TkDefaultFont', 9, 'bold'))
        pref_header.grid(row=0, column=5, padx=2, pady=(2,0))
        # Center the label within its cell
        photo_frame.columnconfigure(5, weight=0)
        btn_frame = ttk.Frame(photo_frame)
        # Make the button frame expand horizontally and center its contents
        btn_frame.grid(row=1, column=5, padx=2, pady=(0,2), sticky='ew')
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(3, weight=1)
        # Use tk.Button with transparent pixel for precise compact sizing
        eq_btn = tk.Button(btn_frame, text='Equal', command=self.equal_sizes,
                   font=('TkDefaultFont', 7), width=30, height=12,
                   image=self.button_pixel, compound='center',
                   padx=0, pady=0, bd=1, highlightthickness=0)
        eq_btn.grid(row=0, column=1, padx=0)
        orig_btn = tk.Button(btn_frame, text='Original', command=self.stored_sizes,
                     font=('TkDefaultFont', 7), width=38, height=12,
                     image=self.button_pixel, compound='center',
                     padx=0, pady=0, bd=1, highlightthickness=0)
        orig_btn.grid(row=0, column=2, padx=0)
        
        # Actual header
        ttk.Label(photo_frame, text='Actual', font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=6, padx=2, pady=(2,0), sticky='w')
        
        # Item (photo/text) weight rows will be added dynamically to photo_frame
        self.photo_frame = photo_frame

        # Configure narrow columns so Item/DPI don't expand too much;
        # let the 'Preferred' column take remaining space.
        photo_frame.columnconfigure(0, minsize=40, weight=0)   # Item label (P1..)
        photo_frame.columnconfigure(1, minsize=48, weight=0)   # DPI
        photo_frame.columnconfigure(2, minsize=48, weight=0)   # Slot AR
        photo_frame.columnconfigure(3, minsize=28, weight=0)   # Use slot checkbox
        photo_frame.columnconfigure(4, minsize=44, weight=0)   # Photo AR
        photo_frame.columnconfigure(5, minsize=120, weight=1)  # Preferred (expandable)
        photo_frame.columnconfigure(6, minsize=60, weight=0)   # Actual
        
        # Add text box button (will be positioned below weight rows)
        mod_sym = get_modifier_symbol()
        self.add_text_btn = ttk.Button(photo_frame, text=f'New Text Box ({mod_sym}Shift+N)', command=self.add_text_box)
        # Position will be updated dynamically in update_weights_display()
        
        # RIGHT COLUMN: Cost info (top) and Parameters (bottom)
        right_col = ttk.Frame(self.info_frame)
        right_col.grid(row=1, column=1, sticky='ne')
        
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
        
        # Empty space threshold parameter
        ttk.Label(cost_param_frame, text='Empty space threshold (%):').grid(row=3, column=0, sticky='w', pady=2)
        self.empty_threshold_var = tk.StringVar(value='5.0')
        self.empty_threshold_entry = ttk.Entry(cost_param_frame, textvariable=self.empty_threshold_var, width=8)
        self.empty_threshold_entry.grid(row=3, column=1, sticky='w', padx=4, pady=2)
        self.empty_threshold_entry.bind('<Return>', lambda e: self.on_empty_threshold_changed())
        self.empty_threshold_entry.bind('<FocusOut>', lambda e: self.on_empty_threshold_changed())
        
        # Margins frame (bottom of right column)
        margins_frame = ttk.LabelFrame(right_col, text='Margins', padding=6)
        margins_frame.grid(row=2, column=0, sticky='ew')
        
        # Internal gap parameter (editable) - moved to row 0
        ttk.Label(margins_frame, text='Internal gap (mm):').grid(row=0, column=0, sticky='w', pady=2)
        self.internal_gap_var = tk.StringVar(value='0.0')
        self.internal_gap_entry = ttk.Entry(margins_frame, textvariable=self.internal_gap_var, width=8)
        self.internal_gap_entry.grid(row=0, column=1, sticky='w', padx=4, pady=2)
        self.internal_gap_entry.bind('<Return>', lambda e: self.on_internal_gap_changed())
        self.internal_gap_entry.bind('<FocusOut>', lambda e: self.on_internal_gap_changed())
        
        # Edge gap parameter (now editable, except for calendars which have fixed gaps)
        ttk.Label(margins_frame, text='Edge gap (mm):').grid(row=1, column=0, sticky='w', pady=2)
        self.edge_gap_var = tk.StringVar(value='0.0')
        if self.is_calendar:
            # Calendar: show fixed edge gaps (disabled entry)
            self.edge_gap_var.set('Fixed')
            self.edge_gap_entry = ttk.Entry(margins_frame, textvariable=self.edge_gap_var, width=18, state='disabled')
        else:
            # Photobook/Canvas: editable edge gap
            self.edge_gap_entry = ttk.Entry(margins_frame, textvariable=self.edge_gap_var, width=8)
            self.edge_gap_entry.bind('<Return>', lambda e: self.on_edge_gap_changed())
            self.edge_gap_entry.bind('<FocusOut>', lambda e: self.on_edge_gap_changed())
        self.edge_gap_entry.grid(row=1, column=1, sticky='w', padx=4, pady=2)
        
        # Add "(average)" label after edge gap entry
        ttk.Label(margins_frame, text='(average)', font=('TkDefaultFont', 9, 'italic')).grid(row=1, column=2, sticky='w', padx=(2,0), pady=2)
        
        # Individual edge gap controls (row 2) - only for non-calendars
        if not self.is_calendar:
            # Create a sub-frame for the 4 individual edge gaps
            individual_gaps_frame = ttk.Frame(margins_frame)
            individual_gaps_frame.grid(row=2, column=0, columnspan=3, sticky='w', pady=(4,2))
            
            # Top edge gap
            ttk.Label(individual_gaps_frame, text='  Top:', font=('TkDefaultFont', 9)).grid(row=0, column=0, sticky='w', padx=(0,2))
            self.edge_gap_top_var = tk.StringVar(value='0.0')
            self.edge_gap_top_entry = ttk.Entry(individual_gaps_frame, textvariable=self.edge_gap_top_var, width=6)
            self.edge_gap_top_entry.grid(row=0, column=1, sticky='w', padx=2)
            self.edge_gap_top_entry.bind('<Return>', lambda e: self.on_individual_edge_gap_changed())
            self.edge_gap_top_entry.bind('<FocusOut>', lambda e: self.on_individual_edge_gap_changed())
            
            # Right edge gap
            ttk.Label(individual_gaps_frame, text='Right:', font=('TkDefaultFont', 9)).grid(row=0, column=2, sticky='w', padx=(8,2))
            self.edge_gap_right_var = tk.StringVar(value='0.0')
            self.edge_gap_right_entry = ttk.Entry(individual_gaps_frame, textvariable=self.edge_gap_right_var, width=6)
            self.edge_gap_right_entry.grid(row=0, column=3, sticky='w', padx=2)
            self.edge_gap_right_entry.bind('<Return>', lambda e: self.on_individual_edge_gap_changed())
            self.edge_gap_right_entry.bind('<FocusOut>', lambda e: self.on_individual_edge_gap_changed())
            
            # Bottom edge gap
            ttk.Label(individual_gaps_frame, text='Bottom:', font=('TkDefaultFont', 9)).grid(row=1, column=0, sticky='w', padx=(0,2), pady=(2,0))
            self.edge_gap_bottom_var = tk.StringVar(value='0.0')
            self.edge_gap_bottom_entry = ttk.Entry(individual_gaps_frame, textvariable=self.edge_gap_bottom_var, width=6)
            self.edge_gap_bottom_entry.grid(row=1, column=1, sticky='w', padx=2, pady=(2,0))
            self.edge_gap_bottom_entry.bind('<Return>', lambda e: self.on_individual_edge_gap_changed())
            self.edge_gap_bottom_entry.bind('<FocusOut>', lambda e: self.on_individual_edge_gap_changed())
            
            # Left edge gap
            ttk.Label(individual_gaps_frame, text='Left:', font=('TkDefaultFont', 9)).grid(row=1, column=2, sticky='w', padx=(8,2), pady=(2,0))
            self.edge_gap_left_var = tk.StringVar(value='0.0')
            self.edge_gap_left_entry = ttk.Entry(individual_gaps_frame, textvariable=self.edge_gap_left_var, width=6)
            self.edge_gap_left_entry.grid(row=1, column=3, sticky='w', padx=2, pady=(2,0))
            self.edge_gap_left_entry.bind('<Return>', lambda e: self.on_individual_edge_gap_changed())
            self.edge_gap_left_entry.bind('<FocusOut>', lambda e: self.on_individual_edge_gap_changed())
        
        # Photo weight rows (will be populated dynamically)
        self.weight_widgets = []  # List of (item_label, desired_entry, actual_label) for photos and texts

        # Create page renderer (handles all visual rendering, no business logic)
        self.page_renderer = PageRenderer(
            canvas=self.canvas,
            mcf_base_folder=self.mcf_base_folder,
            image_folder_attr=self.image_folder_attr,
            photo_dimensions_cache=self.photo_dimensions
        )
        self.size_importance = 100.0  # Default size importance factor
        self.undersized_threshold = 0.5  # Default undersized threshold (50%)
        self.undersized_penalty = 5.0  # Default undersized penalty factor
        self.empty_threshold = 0.05  # Default empty space threshold (5%)
        self.modified_pages = set()  # Track pages with unsaved changes

        self.index = self._pageToStartOn()

        # Setup keyboard shortcuts
        self._setup_keyboard_shortcuts()
        
        # Setup macOS menu bar if on macOS
        if is_macos():
            self._setup_macos_menu()
        
        self.render_page()

    def _pageToStartOn(self) -> int:
        # Find the first page that needs work (is completely empty or has empty rects)
        # Skip inside cover pages UNLESS --insidecovers flag was given (then they have content)
        
        for idx, (pageno, info) in enumerate(self.pages):
            # Skip inside cover pages only if they're empty (no --insidecovers flag)
            if not self.insidecovers:
                if pageno == self.inside_front_cover_page or pageno == self.inside_back_cover_page:
                    continue
            
            photos = info.get('photos', [])
            texts = info.get('texts', [])

            # Check if page is completely empty (no photos, no texts)
            is_completely_empty = (len(photos) == 0 and len(texts) == 0)

            # Check if page has empty rects (photos without filenames)
            has_empty_rects = any(not p.get('filename') for p in photos)

            if is_completely_empty or has_empty_rects:
                return idx

        # Start at front cover if all pages are complete
        # Look for "F" (front cover) first, then first normal page (1)
        for idx, (pageno, _) in enumerate(self.pages):
            if pageno == "F":
                return idx
        
        # If no front cover, start at first normal page (page 1)
        for idx, (pageno, _) in enumerate(self.pages):
            if pageno == 1:
                return idx
        
        # This shouldn't happen - every photobook should have at least page 1
        raise RuntimeError(f"Unable to find valid starting page. Pages: {[p for p, _ in self.pages]}")

    def _setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for common actions."""
        modifier = get_modifier_key()
        
        # Cmd/Ctrl+S: Save Modified
        self.root.bind(f'<{modifier}-s>', lambda e: self.save_layout())
        self.root.bind(f'<{modifier}-S>', lambda e: self.save_layout())
        self.ctrlWin.bind(f'<{modifier}-s>', lambda e: self.save_layout())
        self.ctrlWin.bind(f'<{modifier}-S>', lambda e: self.save_layout())
        
        # Cmd/Ctrl+P: Export PDF
        self.root.bind(f'<{modifier}-p>', lambda e: self.export_to_pdf())
        self.root.bind(f'<{modifier}-P>', lambda e: self.export_to_pdf())
        self.ctrlWin.bind(f'<{modifier}-p>', lambda e: self.export_to_pdf())
        self.ctrlWin.bind(f'<{modifier}-P>', lambda e: self.export_to_pdf())
        
        # Cmd/Ctrl+Z: Undo
        self.root.bind(f'<{modifier}-z>', lambda e: self.undo_layout())
        self.root.bind(f'<{modifier}-Z>', lambda e: self.undo_layout())
        self.ctrlWin.bind(f'<{modifier}-z>', lambda e: self.undo_layout())
        self.ctrlWin.bind(f'<{modifier}-Z>', lambda e: self.undo_layout())
        
        # Cmd/Ctrl+R: Generate Layout
        self.root.bind(f'<{modifier}-r>', lambda e: self._generate_layout())
        self.root.bind(f'<{modifier}-R>', lambda e: self._generate_layout())
        self.ctrlWin.bind(f'<{modifier}-r>', lambda e: self._generate_layout())
        self.ctrlWin.bind(f'<{modifier}-R>', lambda e: self._generate_layout())
        
        # Cmd/Ctrl+Shift+N: New Text Box
        self.root.bind(f'<{modifier}-Shift-n>', lambda e: self.add_text_box())
        self.root.bind(f'<{modifier}-Shift-N>', lambda e: self.add_text_box())
        self.ctrlWin.bind(f'<{modifier}-Shift-n>', lambda e: self.add_text_box())
        self.ctrlWin.bind(f'<{modifier}-Shift-N>', lambda e: self.add_text_box())
        
        # Cmd/Ctrl+O: Open Photos
        self.root.bind(f'<{modifier}-o>', lambda e: self._prompt_add_photos())
        self.root.bind(f'<{modifier}-O>', lambda e: self._prompt_add_photos())
        self.ctrlWin.bind(f'<{modifier}-o>', lambda e: self._prompt_add_photos())
        self.ctrlWin.bind(f'<{modifier}-O>', lambda e: self._prompt_add_photos())
        
        # Cmd/Ctrl+W: Close/Quit (macOS convention)
        if is_macos():
            self.root.bind(f'<{modifier}-w>', lambda e: self.quit())
            self.root.bind(f'<{modifier}-W>', lambda e: self.quit())
            self.ctrlWin.bind(f'<{modifier}-w>', lambda e: self.quit())
            self.ctrlWin.bind(f'<{modifier}-W>', lambda e: self.quit())
        
        # Cmd/Ctrl+0: Focus render window
        self.root.bind(f'<{modifier}-0>', lambda e: self._focus_render_window())
        self.ctrlWin.bind(f'<{modifier}-0>', lambda e: self._focus_render_window())
        
        # Cmd/Ctrl+1: Focus controls window
        self.root.bind(f'<{modifier}-1>', lambda e: self._focus_controls_window())
        self.ctrlWin.bind(f'<{modifier}-1>', lambda e: self._focus_controls_window())
        # Also try with KeyPress in case the number key needs it
        self.root.bind(f'<{modifier}-KeyPress-1>', lambda e: self._focus_controls_window())
        self.ctrlWin.bind(f'<{modifier}-KeyPress-1>', lambda e: self._focus_controls_window())
        
        # Left/Right arrows: Prev/Next page (bind to both windows)
        self.root.bind('<Left>', lambda e: self.prev_page())
        self.root.bind('<Right>', lambda e: self.next_page())
        self.ctrlWin.bind('<Left>', lambda e: self.prev_page())
        self.ctrlWin.bind('<Right>', lambda e: self.next_page())
    
    def _setup_macos_menu(self):
        """Setup macOS-specific menu bar."""
        try:
            # Create menu bar
            menubar = tk.Menu(self.root)
            
            # File menu
            file_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label='File', menu=file_menu)
            file_menu.add_command(label='Open Photos...', accelerator='Cmd+O', command=self._prompt_add_photos)
            file_menu.add_separator()
            file_menu.add_command(label='Save Modified', accelerator='Cmd+S', command=self.save_layout)
            file_menu.add_command(label='Export PDF...', accelerator='Cmd+P', command=self.export_to_pdf)
            file_menu.add_separator()
            file_menu.add_command(label='Close Window', accelerator='Cmd+W', command=self.quit)
            
            # Edit menu
            edit_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label='Edit', menu=edit_menu)
            edit_menu.add_command(label='Undo Layout', accelerator='Cmd+Z', command=self.undo_layout)
            edit_menu.add_separator()
            edit_menu.add_command(label='Previous Page', accelerator='←', command=self.prev_page)
            edit_menu.add_command(label='Next Page', accelerator='→', command=self.next_page)
            edit_menu.add_separator()
            edit_menu.add_command(label='Use Original Page', command=self.use_original)
            
            # Layout menu
            layout_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label='Layout', menu=layout_menu)
            layout_menu.add_command(label='Generate Layout', accelerator='Cmd+R', command=self._generate_layout)
            layout_menu.add_command(label='New Text Box', accelerator='Cmd+Shift+N', command=self.add_text_box)
            
            # Window menu (standard macOS menu)
            window_menu = tk.Menu(menubar, name='window', tearoff=0)
            menubar.add_cascade(label='Window', menu=window_menu)
            # The window menu is automatically populated by Tk on macOS with open windows
            # Keyboard shortcuts Cmd+0 and Cmd+1 are bound directly, not via menu
            
            # Set app name in menu bar (attempts to override "Python")
            # This works if we're running as a bundled .app, but not from command line
            try:
                self.root.createcommand('tk::mac::ShowPreferences', self._show_preferences)
                self.root.createcommand('::tk::mac::Quit', self.quit)
                
                # Try to set app name (may not work from terminal)
                app_menu = tk.Menu(menubar, name='apple', tearoff=0)
                menubar.add_cascade(menu=app_menu)
                app_menu.add_command(label='About QLayout', command=self._show_about)
                app_menu.add_separator()
            except tk.TclError:
                # Not on macOS or commands not available
                pass
            
            # Apply menu to both windows
            self.root.config(menu=menubar)
            self.ctrlWin.config(menu=menubar)
                
        except Exception as e:
            # If menu setup fails, just log it and continue
            logger.warning(f'Failed to setup macOS menu: {e}')
    
    def _show_about(self):
        """Show about dialog."""
        from tkinter import messagebox
        messagebox.showinfo(
            'About QLayout',
            'cewe-layout — QLayout\n\nA layout tool for CEWE photobooks and canvases.\n\nVersion: Development'
        )
    
    def _show_preferences(self):
        """Show preferences dialog (placeholder)."""
        from tkinter import messagebox
        messagebox.showinfo('Preferences', 'Preferences dialog not yet implemented.')
    
    def _focus_render_window(self):
        """Bring the main render window to front."""
        self.root.lift()
        self.root.focus_force()
    
    def _focus_controls_window(self):
        """Bring the controls window to front."""
        self.ctrlWin.lift()
        self.ctrlWin.focus_force()
    
    def _get_canvas_dimensions(self):
        """Get current canvas dimensions in pixels.
        
        Returns:
            Tuple of (width, height) in pixels
        """
        self.root.update_idletasks()  # Ensure geometry is current
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        
        # On initial render, dimensions may not be available yet
        if canvas_w <= 1 or canvas_h <= 1:
            canvas_w = self.root.winfo_width()
            canvas_h = self.root.winfo_height()
        
        # Ensure minimum size
        if canvas_w < 100:
            canvas_w = 800
        if canvas_h < 100:
            canvas_h = int(800 / self.canvas_aspect_ratio)
        
        return canvas_w, canvas_h
    
    def _build_page_render_data(self, page_indices):
        """Build PageRenderData objects for the given page indices.
        
        Args:
            page_indices: List of page indices to render
        
        Returns:
            List of PageRenderData objects
        """
        page_data_list = []
        
        for page_idx in page_indices:
            pageno, info = self.pages[page_idx]
            current_layout = self.layout_mgr.get_current(pageno)
            photos = current_layout.photos if current_layout else info.get('photos', [])
            texts = current_layout.texts if current_layout else info.get('texts', [])
            
            # Get composite image from PDF content if available
            composite_image = None
            if self.pdf_content:
                from .pdf2cewe.pdf_extractor import get_page_content
                # Map UI page number to PDF page index
                pdf_page_index = self._ui_page_to_pdf_page(pageno)
                if pdf_page_index is not None:
                    pdf_data = get_page_content(self.pdf_content, pdf_page_index)
                    if pdf_data:
                        composite_image = pdf_data.get('composite_image')
                        # Add dimension information for aspect-ratio-preserving scaling
                        if composite_image:
                            # Get PDF page dimensions from this specific page (already in MCF units)
                            # Each page stores its own dimensions, so this handles varying page sizes
                            pdf_page_width_mcf = pdf_data['width']
                            pdf_page_height_mcf = pdf_data['height']
                            
                            # Get CEWE page dimensions in MCF units
                            cewe_page_width_mcf = info.get('page_width')
                            cewe_page_height_mcf = info.get('page_height')
                            
                            # Store in composite_image dict for use in rendering
                            composite_image['pdf_page_width_mcf'] = pdf_page_width_mcf
                            composite_image['pdf_page_height_mcf'] = pdf_page_height_mcf
                            composite_image['cewe_page_width_mcf'] = cewe_page_width_mcf
                            composite_image['cewe_page_height_mcf'] = cewe_page_height_mcf
            
            page_data = PageRenderData(
                pageno=pageno,
                photos=photos,
                texts=texts,
                page_width=info.get('page_width'),
                page_height=info.get('page_height'),
                origin_left=info.get('origin_left', 0.0),
                background_id=info.get('background_id'),
                composite_image=composite_image
            )
            page_data_list.append(page_data)
        
        return page_data_list
    
    def _handle_delete_button_click(self, item_type, item_index, pageno, identifier):
        """Handle delete button click from PageRenderer.
        
        Args:
            item_type: 'photo' or 'text'
            item_index: 0-based index within page's photos or texts
            pageno: Page number
            identifier: filename for photos, None for texts
        """
        if item_type == 'photo':
            self._delete_photo(item_index, pageno, identifier)
        else:  # 'text'
            self._delete_text(item_index, pageno)
    
    def _ui_page_to_pdf_page(self, ui_pageno):
        """Map UI page number to PDF page index.
        
        Args:
            ui_pageno: UI page number (can be "F", "B", 0, 1..N, N+1)
        
        Returns:
            PDF page index (0-indexed) or None if no PDF page exists
        """
        if not self.pdf_content:
            return None
        
        # Get total PDF page count
        from .pdf2cewe.pdf_extractor import get_page_content
        pdf_page_count = self.pdf_content.get('page_count', 0)
        
        # Map UI page to PDF index
        if ui_pageno == "F":
            # Front cover is PDF page 0
            return 0
        elif ui_pageno == "B":
            # Back cover is last PDF page if it exists
            if pdf_page_count > 0:
                return pdf_page_count - 1
            return None
        elif ui_pageno == self.inside_front_cover_page:
            # Inside front cover: PDF page 1 if --insidecovers, else None
            if self.insidecovers:
                return 1
            return None
        elif isinstance(ui_pageno, int):
            # Check if this is the inside back cover
            if ui_pageno == self.inside_back_cover_page:
                # Inside back cover: PDF page N-2 (second-to-last) if --insidecovers, else None
                if self.insidecovers and pdf_page_count >= 2:
                    return pdf_page_count - 2
                return None
            
            # Regular content pages
            if self.insidecovers:
                # With --insidecovers: UI page N maps to PDF page N+1 (shifted by inside front cover)
                return ui_pageno + 1
            else:
                # Without --insidecovers: UI page N maps to PDF page N
                return ui_pageno
        
        return None
    
    def render_page(self):
        """Orchestrate page rendering - control logic here, rendering delegated to PageRenderer."""
        # Clear status message when changing pages
        self.status_var.set('')

        if not self.pages:
            # Update page number display
            if self.is_canvas:
                self.page_num_var.set('Canvas:')
            elif self.is_calendar:
                self.page_num_var.set('Month:')
            else:
                self.page_num_var.set('Page:')
            
            # Render empty page
            canvas_w, canvas_h = self._get_canvas_dimensions()
            self.page_renderer.render_empty_page(canvas_w, canvas_h, 'No pages found')
            self._update_page_range_display()
            self.current_spread_pages = []
            return
        
        # Determine which page indices to render (1 or 2 if in spread mode)
        page_indices = self._getPagesToRender()

        # Collect all photos/texts for window title
        all_photos = []
        all_texts = []
        
        for page_idx in page_indices:
            pageno_i, info_i = self.pages[page_idx]
            current_layout_i = self.layout_mgr.get_current(pageno_i)
            photos_i = current_layout_i.photos if current_layout_i else info_i.get('photos', [])
            texts_i = current_layout_i.texts if current_layout_i else info_i.get('texts', [])
            all_photos.extend(photos_i)
            all_texts.extend(texts_i)
        
        # Get page dimensions for title
        first_page_info = self.pages[page_indices[0]][1]
        page_width_mcf = first_page_info.get('page_width')
        page_height_mcf = first_page_info.get('page_height')

        title = self._getPageWinTitle(all_photos, all_texts, page_width_mcf, page_height_mcf)
        self.root.title(title)
        
        # Update PDF photo count field if PDF content is available
        if self.pdf_content:
            self.pdf_photo_count_var.set(str(len(all_photos)))
        
        # Get canvas dimensions and build render data
        canvas_w, canvas_h = self._get_canvas_dimensions()
        page_data_list = self._build_page_render_data(page_indices)
        
        # Check if any rendered pages are protected inside covers
        protected_pages = []
        for page_idx in page_indices:
            pageno_i, _ = self.pages[page_idx]
            if pageno_i in self.protected_inside_covers:
                protected_pages.append(pageno_i)
        
        # Delegate rendering to PageRenderer
        show_composite = self.show_pdf_composite_var.get() if self.pdf_content else False
        
        self.page_renderer.render_pages(
            page_data_list=page_data_list,
            canvas_w=canvas_w,
            canvas_h=canvas_h,
            margin_mcf=self.margin_mcf,
            delete_callback=self._handle_delete_button_click,
            show_pdf_composite=show_composite,
            protected_inside_covers=protected_pages,
            swap_callback=self._on_photo_swap,
            draw_cropped=self.draw_cropped_var.get()
        )
        
        # Update control widgets
        self._update_page_range_display()
        self.update_weights_display()

    def _getPageWinTitle(self, all_photos: list[Any], all_texts: list[Any], page_width_mcf,
                         page_height_mcf) -> str:
        # Convert to cm (MCF / 100) and format to 1 decimal place
        # We have either 1 or 2 pages. Multiply the width by this.
        width_cm = (page_width_mcf * len(self.current_spread_pages)) / 100.0
        height_cm = page_height_mcf / 100.0
        dimensions_str = f'{width_cm:.1f}cm x {height_cm:.1f}cm'
        text_label = 'text' if len(all_texts) == 1 else 'texts'

        title = f'{self.photobook_name} - '
        # Update window title with photobook/canvas/calendar name and page info
        if self.is_canvas:
            title += 'Canvas' # Canvas mode: show as "Canvas" not "Page"
        elif self.is_calendar:
            title += f'Month {self.current_spread_pages[0]}' # Calendar mode: show as "Month" not "Page"
        elif len(self.current_spread_pages) == 2:
            title += f'Pages {self.current_spread_pages[0]}-{self.current_spread_pages[1]}'
        else:
            title += f'Page {self.current_spread_pages[0]}'

        title += f', {dimensions_str} : {len(all_photos)} photos'
        if all_texts: title += f', {len(all_texts)} {text_label}'
        return title

    def _getPagesToRender(self) -> list[int]:
        # Canvas mode: always treat as single page (no spread navigation)
        # Calendar mode: treat as single pages (no spreads), but allow navigation
        # Photobook mode: determine which pages to render based on spread mode
        if self.is_canvas or self.is_calendar or not self.spread_mode.get():
            # Single page modes
            page_indices = [self.index]
            self.current_spread_pages = [self.pages[self.index][0]]
        else:
            # Spread mode: handle covers specially. This chunk of code is ridiculously over-complicated
            # We should really simplify it a lot.  It tries to cope with edge-cases that don't exist.

            # Covers (page 0 and max page) can form a spread with each other
            # but NOT with normal pages (1...N)
            current_pageno = self.pages[self.index][0]
            current_info = self.pages[self.index][1]
            is_current_cover = current_info.get('is_cover', False)

            # Find max normal page and covers
            if is_current_cover:
                # Current page is a cover ("F" or "B")
                if current_pageno == "F":
                    # Front cover (page "F") - check if back cover exists for spread
                    back_cover_idx = None
                    for i, (pn, info) in enumerate(self.pages):
                        if pn == "B" and info.get('is_cover', False):
                            back_cover_idx = i
                            break

                    if back_cover_idx is not None:
                        # Show front and back cover as spread (back on left, front on right)
                        page_indices = [back_cover_idx, self.index]
                        self.current_spread_pages = ["B", "F"]
                    else:
                        # Only front cover exists
                        page_indices = [self.index]
                        self.current_spread_pages = [current_pageno]
                else:
                    # Back cover (page "B") - check if front cover exists for spread
                    front_cover_idx = None
                    for i, (pn, info) in enumerate(self.pages):
                        if pn == "F" and info.get('is_cover', False):
                            front_cover_idx = i
                            break

                    if front_cover_idx is not None:
                        # Show front and back cover as spread (back on left, front on right)
                        page_indices = [self.index, front_cover_idx]
                        self.current_spread_pages = ["B", "F"]
                    else:
                        # Only back cover exists
                        page_indices = [self.index]
                        self.current_spread_pages = [current_pageno]
            else:
                # Normal page spread logic (even on left, odd on right)
                # current_pageno should be an integer for normal pages
                if isinstance(current_pageno, int) and current_pageno % 2 == 0:
                    # Current page is even - it goes on left, find next odd page for right
                    left_idx = self.index
                    # Find next page (should be odd if pages are consecutive)
                    if self.index < len(self.pages) - 1:
                        right_pageno = self.pages[self.index + 1][0]
                        right_info = self.pages[self.index + 1][1]
                        # Don't pair with covers
                        if not right_info.get('is_cover', False):
                            right_idx = self.index + 1
                            page_indices = [left_idx, right_idx]
                            self.current_spread_pages = [self.pages[left_idx][0], self.pages[right_idx][0]]
                        else:
                            # Next page is a cover, show current alone
                            page_indices = [left_idx]
                            self.current_spread_pages = [self.pages[left_idx][0]]
                    else:
                        # Even page is last page - show it alone
                        page_indices = [left_idx]
                        self.current_spread_pages = [self.pages[left_idx][0]]
                elif isinstance(current_pageno, int):
                    # Current page is odd - find previous even page for left
                    if self.index > 0:
                        left_pageno = self.pages[self.index - 1][0]
                        left_info = self.pages[self.index - 1][1]
                        # Don't pair with covers
                        if not left_info.get('is_cover', False):
                            left_idx = self.index - 1
                            right_idx = self.index
                            page_indices = [left_idx, right_idx]
                            self.current_spread_pages = [self.pages[left_idx][0], self.pages[right_idx][0]]
                        else:
                            # Previous page is a cover, show current alone
                            page_indices = [self.index]
                            self.current_spread_pages = [self.pages[self.index][0]]
                    else:
                        # Odd page is first page - show it alone
                        page_indices = [self.index]
                        self.current_spread_pages = [self.pages[self.index][0]]
                else:
                    # Non-integer page number that's not a cover - shouldn't happen, show alone
                    page_indices = [self.index]
                    self.current_spread_pages = [current_pageno]

        # Update page number display
        if self.is_canvas:
            self.page_num_var.set('Canvas:')
        elif self.is_calendar:
            self.page_num_var.set(f'Month {self.current_spread_pages[0]}:')
        elif len(self.current_spread_pages) == 2:
            self.page_num_var.set(f'Pages {self.current_spread_pages[0]}-{self.current_spread_pages[1]}:')
        else:
            self.page_num_var.set(f'Page {self.current_spread_pages[0]}:')
        return page_indices

    def _on_photo_swap(self, source_pageno, source_photo_idx, dest_pageno, dest_photo_idx):
        """Handle photo swap request from PageRenderer.
        
        This is the business logic callback - it updates the data model and re-renders.
        All visual interaction logic stays in PageRenderer.
        
        Args:
            source_pageno: Page number of source photo
            source_photo_idx: Index of source photo in its page
            dest_pageno: Page number of destination photo
            dest_photo_idx: Index of destination photo in its page
        """
        # Debug: Log the swap attempt
        logger.info(f"Attempting swap: page {source_pageno} photo {source_photo_idx} <-> page {dest_pageno} photo {dest_photo_idx}")
        
        # Get photo filenames before swap for logging
        layout1_before = self.layout_mgr.get_current(source_pageno)
        layout2_before = self.layout_mgr.get_current(dest_pageno)
        if layout1_before and layout2_before:
            photo1_before = layout1_before.photos[source_photo_idx].get('filename', 'UNKNOWN')
            photo2_before = layout2_before.photos[dest_photo_idx].get('filename', 'UNKNOWN')
            logger.debug(f"Before swap: [{photo1_before}] <-> [{photo2_before}]")
        
        # Execute swap
        success = self.layout_mgr.swap_photos(
            source_pageno, source_photo_idx,
            dest_pageno, dest_photo_idx
        )
        
        if success:
            # Debug: Verify swap actually happened
            layout1_after = self.layout_mgr.get_current(source_pageno)
            layout2_after = self.layout_mgr.get_current(dest_pageno)
            if layout1_after and layout2_after:
                photo1_after = layout1_after.photos[source_photo_idx].get('filename', 'UNKNOWN')
                photo2_after = layout2_after.photos[dest_photo_idx].get('filename', 'UNKNOWN')
                logger.debug(f"After swap: [{photo1_after}] <-> [{photo2_after}]")
                if photo1_after == photo1_before and photo2_after == photo2_before:
                    logger.error("SWAP DID NOT ACTUALLY CHANGE THE LAYOUT!")
            
            # Mark page(s) as modified
            self.modified_pages.add(source_pageno)
            if dest_pageno != source_pageno:
                self.modified_pages.add(dest_pageno)
            self._update_modified_pages_display()
            
            # Re-render to show swapped photos
            self.render_page()
            self.show_status(f'Swapped photos')
        else:
            self.show_status('Failed to swap photos', error=True)
    
    def _delete_photo(self, photo_index, pageno, filename):
        """Delete a photo from a page layout.
        
        Args:
            photo_index: 0-based index of photo in the page's layout
            pageno: Page number that owns this photo
            filename: Filename of the photo to delete
        """
        if not self.pages:
            return
        
        current_layout = self.layout_mgr.get_current(pageno)
        if not current_layout:
            return
        
        photos = current_layout.photos
        texts = current_layout.texts
        
        # Verify index is valid
        if photo_index < 0 or photo_index >= len(photos):
            self.show_status(f'Invalid photo index: {photo_index}', error=True)
            return
        
        # Remove photo from list
        deleted_photo = photos[photo_index]
        deleted_filename = deleted_photo.get('filename', '')
        updated_photos = photos[:photo_index] + photos[photo_index+1:]
        
        # Mark as deleted for tracking
        if deleted_filename:
            self.layout_mgr.mark_photo_as_deleted(pageno, deleted_filename)
        
        # Push updated layout
        self.layout_mgr.push_layout(pageno, updated_photos, texts)
        
        # Shift cached data for items after deleted photo
        # When item at index N is deleted, items at indices > N shift down to indices > N-1
        # We need to preserve user edits (aspect ratios, checkbox states) by shifting them
        
        # Shift slot aspect ratios: delete entry for deleted item, shift higher indices down
        if (pageno, photo_index) in self.slot_aspect_ratios:
            del self.slot_aspect_ratios[(pageno, photo_index)]
        
        # Shift all higher photo indices down by 1
        num_photos = len(updated_photos)
        for idx in range(photo_index, num_photos):
            old_key = (pageno, idx + 1)
            new_key = (pageno, idx)
            if old_key in self.slot_aspect_ratios:
                self.slot_aspect_ratios[new_key] = self.slot_aspect_ratios[old_key]
                del self.slot_aspect_ratios[old_key]
        
        # Shift checkbox states similarly
        if (pageno, photo_index) in self.use_slot_aspect:
            del self.use_slot_aspect[(pageno, photo_index)]
        
        for idx in range(photo_index, num_photos):
            old_key = (pageno, idx + 1)
            new_key = (pageno, idx)
            if old_key in self.use_slot_aspect:
                self.use_slot_aspect[new_key] = self.use_slot_aspect[old_key]
                del self.use_slot_aspect[old_key]
        
        # Mark page(s) as modified
        self._mark_current_pages_modified()
        
        # Re-render to show updated layout
        self.render_page()
        
        shortfn = deleted_filename.split('/')[-1] if deleted_filename else f'photo {photo_index+1}'
        self.show_status(f'Deleted {shortfn} from page {pageno}')
    
    def _delete_text(self, text_index, pageno):
        """Delete a text box from a page layout.
        
        Args:
            text_index: 0-based index of text box in the page's layout
            pageno: Page number that owns this text
        """
        if not self.pages:
            return
        
        current_layout = self.layout_mgr.get_current(pageno)
        if not current_layout:
            return
        
        photos = current_layout.photos
        texts = current_layout.texts
        
        # Verify index is valid
        if text_index < 0 or text_index >= len(texts):
            self.show_status(f'Invalid text index: {text_index}', error=True)
            return
        
        # Remove text from list
        updated_texts = texts[:text_index] + texts[text_index+1:]
        
        # Push updated layout
        self.layout_mgr.push_layout(pageno, photos, updated_texts)
        
        # Shift cached data for items after deleted text
        # Text items come after photos in the combined item list
        # Text at text_index corresponds to item_index = len(photos) + text_index
        num_photos = len(photos)
        item_index = num_photos + text_index
        
        # Shift slot aspect ratios: delete entry for deleted text, shift higher indices down
        if (pageno, item_index) in self.slot_aspect_ratios:
            del self.slot_aspect_ratios[(pageno, item_index)]
        
        # Shift all higher text indices down by 1
        num_texts = len(updated_texts)
        for idx in range(text_index, num_texts):
            old_item_idx = num_photos + idx + 1
            new_item_idx = num_photos + idx
            old_key = (pageno, old_item_idx)
            new_key = (pageno, new_item_idx)
            if old_key in self.slot_aspect_ratios:
                self.slot_aspect_ratios[new_key] = self.slot_aspect_ratios[old_key]
                del self.slot_aspect_ratios[old_key]
        
        # Mark page(s) as modified
        self._mark_current_pages_modified()
        
        # Re-render to show updated layout
        self.render_page()
        
        self.show_status(f'Deleted text box {text_index+1} from page {pageno}')
    
    def _setup_drag_and_drop(self):
        """Setup drag-and-drop handlers for photo files."""
        # macOS drag-and-drop support using tkinterdnd2 or fallback
        drag_drop_available = False
        try:
            from tkinterdnd2 import DND_FILES, TkinterDnD
            # Register the canvas widget for drag-and-drop
            self.canvas.drop_target_register(DND_FILES)
            self.canvas.dnd_bind('<<Drop>>', self._on_drop)
            drag_drop_available = True
        except (ImportError, AttributeError, Exception) as e:
            # tkinterdnd2 not available or failed to initialize
            logger.info(f"Drag-and-drop not available ({e}). Use Cmd+O to open photos.")
        
        # Show one-time info if drag-drop is not available
        if not drag_drop_available:
            self.show_status("Drag-and-drop unavailable. Use Cmd+O to add photos.", duration_ms=3000)
        
        # allow cmd-O under all circumstances
        self.root.bind('<Command-o>', lambda e: self._prompt_add_photos())
        
    def _prompt_add_photos(self):
        """Prompt user to select photos to add to current page."""
        from tkinter import filedialog
        filetypes = [
            ('Image Files', '*.jpg;*.jpeg;*.JPG;*.JPEG;*.png;*.PNG;*.HEIC;*.heic;*.heif;*.HEIF'),
            ('JPEG Images', '*.jpg;*.jpeg;*.JPG;*.JPEG'),
            ('HEIC Images', '*.heic;*.HEIC;*.heif;*.HEIF'),
            ('PNG Images', '*.png;*.PNG'),
            ('All Files', '*.*')
        ]
        files = filedialog.askopenfilenames(
            title='Select photos to add to current page',
            filetypes=filetypes
        )
        if files:
            self._handle_dropped_files(list(files))
    
    def _on_drop(self, event):
        """Handle file drop event from tkinterdnd2."""
        # Parse dropped file paths
        files = self.root.tk.splitlist(event.data)
        self._handle_dropped_files(files)
        return event.action
    
    def _handle_dropped_files(self, file_paths):
        """Process dropped/selected photo files and add to current page."""
        if not self.pages:
            self.show_status('No pages available', error=True)
            return
        
        pageno, info = self.pages[self.index]
        
        # Check if this is a protected inside cover page (when --insidecovers not provided)
        if pageno in self.protected_inside_covers:
            logger.warning(f"Attempted to add photos to protected inside cover page {pageno} (--insidecovers not provided)")
            self.show_status(f'Inside cover page {pageno} is always blank (use --insidecovers flag to edit)', error=True)
            return
        
        # Filter for image files only
        image_exts = {'.jpg', '.jpeg', '.JPG', '.JPEG', '.PNG', '.png', '.HEIC', '.heic', '.heif', '.HEIF'}
        photo_files = [f for f in file_paths if Path(f).suffix in image_exts]
        
        if not photo_files:
            self.show_status('No image files found in selection', error=True)
            return
        
        # Show loading message
        self.show_status(f'Loading {len(photo_files)} photo(s)...')
        self.root.update_idletasks()  # Force UI update to show message
        
        # Stage photos (don't move yet - only on save)
        new_photos = self._stage_photos(photo_files)
        if not new_photos:
            self.show_status('Failed to stage photos', error=True)
            return
        
        # Get current layout (may include existing photos)
        current_layout = self.layout_mgr.get_current(pageno)
        existing_photos = current_layout.photos if current_layout else info.get('photos', [])
        existing_texts = current_layout.texts if current_layout else info.get('texts', [])
        
        # Filter out empty photo slots (photos with no filename) from existing layout
        non_empty_photos = [p for p in existing_photos if p.get('filename')]
        
        # Create initial layout positions ONLY for new photos (don't disturb existing layout)
        page_w = info.get('page_width')
        page_h = info.get('page_height')
        origin_left = info.get('origin_left', 0.0)
        
        new_photos_with_layout = self._create_initial_layout(new_photos, page_w, page_h, origin_left)
        
        # Append new photos to existing photos (preserves all existing positions and data)
        all_photos = list(non_empty_photos) + new_photos_with_layout
        
        # Store updated layout in layout manager
        self.layout_mgr.push_layout(pageno, all_photos, existing_texts)
        
        # DON'T clear cached slot aspect ratios - preserve user customizations
        # New photos won't have slot aspect ratios yet, which is fine
        
        # Mark only the page where photos were actually added as modified
        # (not both pages in spread mode, since photos are added to one page only)
        self.modified_pages.add(pageno)
        self._update_modified_pages_display()
        
        # Process all newly added photos: cache dimensions, set preferences, mark as new
        for photo in new_photos_with_layout:
            filename = photo['filename']
            img_path = Path(photo['_source_path'])
            
            # Populate dimensions cache for algorithm
            dims = get_image_dimensions(img_path)
            if dims:
                self.photo_dimensions[filename] = dims
            
            # Set preferred size
            preferred_size = get_photo_preferred_size(img_path)
            
            # Use base filename (without -sz-pg) as key for layout_mgr
            base_filename, _, _ = extract_metadata_from_filename(filename)
            self.layout_mgr.set_size(pageno, base_filename, preferred_size)
            
            # Mark as newly added for tracking
            self.layout_mgr.mark_photo_as_new(pageno, filename)
        
        # Re-render page to show new photos
        self.render_page()
        self.show_status(f'Added {len(new_photos)} photo(s) to page {pageno}')
    
    def _stage_photos(self, photo_paths):
        """Stage photo files for later moving to album (on save) and return photo data dicts.
        
        Photos are NOT moved yet - only validated and metadata created.
        Source paths are stored for later move operation during save.
        Photos are renamed to replace spaces with underscores for CEWE compatibility.
        
        Returns photo dicts with two path-related keys:
        - 'filename': The destination filename in MCF format (e.g., "safecontainer:/my_photo_1.jpg")
                      where the photo WILL BE after saving. Spaces replaced with underscores,
                      may have counter suffix (_1, _2) if naming conflicts. Used as key throughout
                      MCF and in caches.
        - '_source_path': The current absolute path where the photo file actually exists now
                         (e.g., "/Users/vince/Downloads/my photo with spaces.jpg").
                         Needed to read the image before it's moved. Only exists for newly
                         staged photos; existing album photos don't have this key.
        """
        if not self.mcf_base_folder:
            return []
        
        album_dir = Path(self.mcf_base_folder)
        
        new_photos = []
        for src_path in photo_paths:
            src = Path(src_path)
            if not src.exists():
                logging.error(f'Staging photo failed: source file does not exist: {src}')
                continue
            
            # Replace spaces with underscores in filename for CEWE compatibility
            original_name = src.name
            safe_name = original_name.replace(' ', '_')
            
            # Determine unique destination filename in album root
            dst_name = safe_name
            dst_path = album_dir / dst_name
            counter = 1
            while dst_path.exists():
                # Add counter to make unique
                stem = Path(safe_name).stem
                suffix = Path(safe_name).suffix
                dst_name = f"{stem}_{counter}{suffix}"
                dst_path = album_dir / dst_name
                counter += 1
            
            # Get image dimensions from SOURCE file (not copied yet)
            dims = get_image_dimensions(src)
            if dims:
                img_width, img_height = dims
            else:
                img_width, img_height = 4000, 3000  # fallback
            
            # Create photo data dict with safecontainer path format
            # Use destination filename (where it WILL be after save)
            filename = f"safecontainer:/{dst_name}"
            
            photo_data = {
                'filename': filename,
                'image_width': img_width,
                'image_height': img_height,
                # Initial layout position (will be set by _create_initial_layout)
                'area_left': 0,
                'area_top': 0,
                'area_width': 100,
                'area_height': 100,
                # CRITICAL: Store source path for move operation during save
                '_source_path': str(src),
            }
            new_photos.append(photo_data)
        
        return new_photos
    
    def _create_initial_layout(self, photos, page_w, page_h, origin_left):
        """Create initial diagonally overlapping layout rectangles for photos.
        
        Args:
            photos: List of photo dicts with filename, image_width, image_height
            page_w: Page width in MCF units
            page_h: Page height in MCF units
            origin_left: Origin offset for right pages
        
        Returns:
            List of photo dicts with area_left, area_top, area_width, area_height set
        """
        if not photos:
            return []
        
        # Edge gap: 5mm = 50 MCF units
        edge_gap = make_uniform_edge_gap(50.0)
        
        # Base size for small photo (1.0): approximately page_width/10 x page_height/10
        # but with correct aspect ratio from photo
        base_width = page_w / 10.0
        base_height = page_h / 10.0
        
        # Spacing between photos: 1mm = 10 MCF units
        spacing = 100.0
        
        # Starting position
        current_x = origin_left + edge_gap['left']
        current_y = edge_gap['top']
        
        layout_photos = []
        for photo in photos:
            # Get photo aspect ratio
            img_w = photo.get('image_width', 4000)
            img_h = photo.get('image_height', 3000)
            aspect_ratio = img_w / img_h if img_h > 0 else 4.0/3.0
            
            # Determine size multiplier from photo file
            filename = photo.get('filename', '')
            if filename and self.mcf_base_folder:
                # Resolve photo path
                safefn = filename.replace('safecontainer:/', '').lstrip('/')
                if self.image_folder_attr:
                    img_path = Path(self.mcf_base_folder) / self.image_folder_attr / safefn
                else:
                    img_path = Path(self.mcf_base_folder) / safefn
                
                if img_path.exists():
                    size_multiplier = get_photo_preferred_size(img_path)
                else:
                    size_multiplier = 1.0
            else:
                size_multiplier = 1.0
            
            # Calculate slot dimensions maintaining aspect ratio
            # Target area = base_width * base_height * size_multiplier
            target_area = base_width * base_height * size_multiplier
            # width * height = target_area, width/height = aspect_ratio
            # Solve: w * h = target_area, w/h = aspect_ratio
            # => w = sqrt(target_area * aspect_ratio), h = sqrt(target_area / aspect_ratio)
            slot_width = math.sqrt(target_area * aspect_ratio)
            slot_height = math.sqrt(target_area / aspect_ratio)
            
            # Create photo dict with layout position
            photo_copy = photo.copy()
            photo_copy['area_left'] = current_x
            photo_copy['area_top'] = current_y
            photo_copy['area_width'] = slot_width
            photo_copy['area_height'] = slot_height
            
            layout_photos.append(photo_copy)
            
            # Move position for next photo (diagonally overlapping)
            current_x += spacing
            current_y += spacing
        
        return layout_photos
    
    def update_weights_display(self):
        """Update the weights and cost display for the current page."""
        if not self.pages:
            return
        
        # In spread mode, combine data from both pages
        if self.spread_mode.get() and len(self.current_spread_pages) == 2:
            # Get data from both pages in the spread
            all_photos = []
            all_texts = []
            # Use first (left/even) page for dimensions and gaps
            pageno = self.current_spread_pages[0]
            # In spread mode, is_left_page is determined per-item based on position
            # (We'll set this to None here and determine it per-item below)
            is_left_page = None

            # Find the page info for both pages
            page_info_left = None
            page_info_right = None
            for pn, info in self.pages:
                if pn == self.current_spread_pages[0]:
                    page_info_left = info
                elif pn == self.current_spread_pages[1]:
                    page_info_right = info
            
            if not page_info_left:
                return
            
            # Collect photos and texts from both pages
            for pn in self.current_spread_pages:
                current_layout = self.layout_mgr.get_current(pn)
                if current_layout:
                    all_photos.extend(current_layout.photos)
                    all_texts.extend(current_layout.texts)
                else:
                    # Fallback to original
                    for pn_check, info_check in self.pages:
                        if pn_check == pn:
                            all_photos.extend(info_check.get('photos', []))
                            all_texts.extend(info_check.get('texts', []))
                            break
            
            photos = all_photos
            texts = all_texts
            info = page_info_left
            page_w = info.get('page_width') * 2  # Double width for spread
            page_h = info.get('page_height')
            origin_left = info.get('origin_left')
        else:
            # Single page mode
            pageno, info = self.pages[self.index]
            current_layout = self.layout_mgr.get_current(pageno)
            photos = current_layout.photos if current_layout else info.get('photos', [])
            texts = current_layout.texts if current_layout else info.get('texts', [])
            
            page_w = info.get('page_width')
            page_h = info.get('page_height')
            origin_left = info.get('origin_left', 0.0)  # Default to 0.0 for left pages
            is_left_page = origin_left == 0.0
        
        # Initialize gaps from ORIGINAL layout on first visit to this page
        # Check if gaps have been set (key exists, not value-based check)
        if not self.layout_mgr.has_edge_gap(pageno) or not self.layout_mgr.has_internal_gap(pageno):
            # Analyze gaps from original layout
            original_photos = info.get('photos', [])
            original_texts = info.get('texts', [])
            original_items = original_photos + original_texts

            if original_items:
                analysis = analyze_gap_details(original_items, page_w, page_h, origin_left, self.spread_mode.get())

                # For now, use negative edge_gap for bleed, positive for margin
                if analysis.bleed > 0:
                    self.layout_mgr.set_edge_gap(pageno, make_uniform_edge_gap(-analysis.bleed))
                else:
                    self.layout_mgr.set_edge_gap(pageno, analysis.edge_gap)

                # Set internal_gap: prefer internal, fallback to edge
                if analysis.internal_gap > 0:
                    self.layout_mgr.set_internal_gap(pageno, analysis.internal_gap)
                else:
                    self.layout_mgr.set_internal_gap(pageno, 0)
            else:
                # No items to analyze, set defaults (14mm edge, 9mm internal)
                self.layout_mgr.set_edge_gap(pageno, make_uniform_edge_gap(140.0))
                self.layout_mgr.set_internal_gap(pageno, 90.0)
        
        # Get current gap values (now guaranteed to be set)
        current_edge_gap = self.layout_mgr.get_edge_gap(pageno)
        current_internal_gap = self.layout_mgr.get_internal_gap(pageno)
        
        # Update gap displays (convert MCF units to mm: 1 MCF unit = 0.1mm)
        # For calendars with non-uniform edge gaps, show 'Fixed' in UI
        # For others, show average of all edge gaps
        if self.is_calendar:
            self.edge_gap_var.set('Fixed')
        else:
            # Show average of the 4 edge gaps (top, bottom, left, right)
            avg_edge_gap_mm = (current_edge_gap['top'] + current_edge_gap['bottom'] +
                                    current_edge_gap['left'] + current_edge_gap['right']) / 40.0
            self.edge_gap_var.set(f'{avg_edge_gap_mm:.1f}')
            
            # Update individual edge gap fields
            self.edge_gap_top_var.set(f'{current_edge_gap["top"] / 10.0:.1f}')
            self.edge_gap_right_var.set(f'{current_edge_gap["right"] / 10.0:.1f}')
            self.edge_gap_bottom_var.set(f'{current_edge_gap["bottom"] / 10.0:.1f}')
            self.edge_gap_left_var.set(f'{current_edge_gap["left"] / 10.0:.1f}')

        self.internal_gap_var.set(f'{current_internal_gap / 10.0:.1f}')         

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
        # For calendars, edge_gap is a dict; algorithms expect it as-is
        edge_gap = self.layout_mgr.get_edge_gap(pageno)
        internal_gap = self.layout_mgr.get_internal_gap(pageno)
        
        # Check if this page has full bleed (covers)
        has_full_bleed = info.get('has_full_bleed', False) or self.spread_mode.get()
        
        # Build LayoutRectangle list from CURRENT layout (photos and texts)
        # This is what we evaluate (algorithm output or original)
        # But we use gaps from layout manager as fixed parameters
        # Transform to gap-free coordinate space (same as algorithm uses)
        from .algorithms.base import LayoutRectangle
        rectangles = []
        item_identifiers = []  # Track (type, index, filename_or_id) for each rectangle
        
        # Add photos
        for i, p in enumerate(photos):
            # Get absolute MCF coordinates
            left_abs = p.get('area_left', 0)
            top = p.get('area_top', 0)
            w = p.get('area_width', 0)
            h = p.get('area_height', 0)
            # Convert to page-relative coordinates (subtract origin_left for right pages)
            left = left_abs - origin_left
            fn = p.get('filename', '')
            base_fn, _, _ = extract_metadata_from_filename(fn)
            preferred_size = self.layout_mgr.get_size(pageno, base_fn)
            gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
                left, top, w, h, edge_gap, internal_gap, is_left_page, has_full_bleed
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
            # Get absolute MCF coordinates
            left_abs = t.get('area_left', 0)
            top = t.get('area_top', 0)
            w = t.get('area_width', 0)
            h = t.get('area_height', 0)
            # Convert to page-relative coordinates (subtract origin_left for right pages)
            left = left_abs - origin_left
            text_id = f'TEXT_{i}'
            preferred_size = self.layout_mgr.get_size(pageno, text_id)
            gf_left, gf_top, gf_width, gf_height = transform_item_to_gapfree(
                left, top, w, h, edge_gap, internal_gap, is_left_page, has_full_bleed
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
            page_w, page_h, edge_gap, internal_gap, has_full_bleed
        )
        
        # DEBUG: Print evaluation inputs if debug flag is set
        if self.debug_var.get():
            print(f"\n=== GUI Evaluation Debug ===")
            print(f"  Page: {pageno}")
            print(f"  Eval page: {eval_page_w} x {eval_page_h}")
            print(f"  Edge gaps: top={edge_gap['top']}, bottom={edge_gap['bottom']}, left={edge_gap['left']}, right={edge_gap['right']}")
            print(f"  Internal gap: {internal_gap}")
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
            acceptable_empty_fraction=self.empty_threshold,
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
            row = 2 + i  # Row 0 has main headers, row 1 has sub-headers, data starts at row 2
            
            item_type, item_idx, item_id = item_info
            
            # Item label with type indicator: P1, P2, ... for photos, T1, T2, ... for texts
            type_prefix = 'P' if item_type == 'photo' else 'T'
            item_label = ttk.Label(self.photo_frame, text=f'{type_prefix}{item_idx+1}', font=('TkDefaultFont', 9))
            item_label.grid(row=row, column=0, padx=2, pady=1)

            # DPI column (photos only) - small font and colour coded
            dpi_text = ''
            dpi_color = 'black'
            if item_type == 'photo':
                # Compute DPI using slot dimensions in MCF units
                photo = photos[item_idx]
                slot_w = photo.get('area_width', 0)
                slot_h = photo.get('area_height', 0)
                dpi_val = self._calculate_photo_dpi(photo, slot_w, slot_h)
                if dpi_val is None:
                    dpi_text = '--'
                    dpi_color = 'black'
                else:
                    dpi_text = f'{dpi_val}'
                    if dpi_val < 100:
                        dpi_color = 'red'
                    elif dpi_val < 200:
                        dpi_color = 'yellow'
                    elif dpi_val < 300:
                        dpi_color = 'yellowgreen'
                    else:
                        dpi_color = 'green'
            else:
                dpi_text = ''

            dpi_label = ttk.Label(self.photo_frame, text=dpi_text, font=('TkDefaultFont', 8))
            dpi_label.grid(row=row, column=1, padx=4, pady=1)
            if dpi_text:
                try:
                    dpi_label.config(foreground=dpi_color)
                except Exception:
                    pass

            # Initialize slot aspect ratio from current layout if not already set
            ar_key = (pageno, item_idx)
            if ar_key not in self.slot_aspect_ratios:
                # Get from current slot dimensions IN GAP-FREE SPACE (what algorithms use)
                # This ensures the displayed aspect ratio matches what the algorithm sees
                if item_type == 'photo':
                    photo = photos[item_idx]
                    slot_width = photo.get('area_width', 0)
                    slot_height = photo.get('area_height', 0)
                    if slot_width > 0 and slot_height > 0:
                        # Transform to gap-free space to get true aspect ratio
                        gf_width = slot_width + internal_gap
                        gf_height = slot_height + internal_gap
                        self.slot_aspect_ratios[ar_key] = gf_width / gf_height
                    else:
                        self.slot_aspect_ratios[ar_key] = 1.5  # Default
                else:  # text block
                    text = texts[item_idx]
                    slot_width = text.get('area_width', 0)
                    slot_height = text.get('area_height', 0)
                    if slot_width > 0 and slot_height > 0:
                        # Transform to gap-free space to get true aspect ratio
                        gf_width = slot_width + internal_gap
                        gf_height = slot_height + internal_gap
                        self.slot_aspect_ratios[ar_key] = gf_width / gf_height
                    else:
                        self.slot_aspect_ratios[ar_key] = 2.0  # Default for text
            
            # Column 2: Slot aspect ratio (editable)
            slot_ar_var = tk.StringVar(value=f'{self.slot_aspect_ratios[ar_key]:.2f}')
            slot_ar_entry = ttk.Entry(self.photo_frame, textvariable=slot_ar_var, width=4)
            slot_ar_entry.grid(row=row, column=2, padx=2, pady=1)
            slot_ar_entry.bind('<Return>', lambda e, pg=pageno, idx=item_idx, var=slot_ar_var: self.on_slot_aspect_changed(pg, idx, var))
            slot_ar_entry.bind('<FocusOut>', lambda e, pg=pageno, idx=item_idx, var=slot_ar_var: self.on_slot_aspect_changed(pg, idx, var))

            # Column 3: "Use slot" checkbox
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
                        slot_aspect = slot_width / slot_height
                        # Load image to get its actual aspect ratio
                        dims = self._get_photo_dimensions(photo.get('filename', ''))
                        if dims:
                            img_w, img_h = dims
                            img_aspect = img_w / img_h
                            # Auto-check if aspect ratios differ by more than 30%
                            aspect_diff = abs(img_aspect - slot_aspect) / slot_aspect
                            if aspect_diff > 0.30:
                                should_auto_check = True
                    
                    self.use_slot_aspect[checkbox_key] = tk.BooleanVar(value=should_auto_check)
                
                checkbox_widget = ttk.Checkbutton(self.photo_frame, variable=self.use_slot_aspect[checkbox_key])
                checkbox_widget.grid(row=row, column=3, padx=2, pady=1)
            else:
                # For text blocks, always use slot aspect (checkbox always checked, disabled)
                checkbox_key = (pageno, item_idx)
                if checkbox_key not in self.use_slot_aspect:
                    self.use_slot_aspect[checkbox_key] = tk.BooleanVar(value=True)
                checkbox_widget = ttk.Checkbutton(self.photo_frame, variable=self.use_slot_aspect[checkbox_key], state='disabled')
                checkbox_widget.grid(row=row, column=3, padx=2, pady=1)
            
            # Column 3: Photo/Image aspect ratio (read-only, empty for text blocks)
            photo_ar_label = None
            if item_type == 'photo':
                photo = photos[item_idx]
                dims = self._get_photo_dimensions(photo.get('filename', ''))
                if dims:
                    img_w, img_h = dims
                    img_aspect = img_w / img_h
                    photo_ar_label = ttk.Label(self.photo_frame, text=f'{img_aspect:.2f}', font=('TkDefaultFont', 9))
                else:
                    photo_ar_label = ttk.Label(self.photo_frame, text='--', font=('TkDefaultFont', 9))
            else:
                # Empty for text blocks
                photo_ar_label = ttk.Label(self.photo_frame, text='', font=('TkDefaultFont', 9))
            
            photo_ar_label.grid(row=row, column=4, padx=2, pady=1)
            
            # Column 4: Desired weight entry (editable)
            desired_var = tk.StringVar(value=f'{rect.preferred_size:.1f}')
            desired_entry = ttk.Entry(self.photo_frame, textvariable=desired_var, width=6)
            desired_entry.grid(row=row, column=5, padx=2, pady=1)
            
            # Bind entry changes to update weights in layout manager
            desired_entry.bind('<Return>', lambda e, pg=pageno, iid=item_id, var=desired_var: self.on_size_changed(pg, iid, var))
            desired_entry.bind('<FocusOut>', lambda e, pg=pageno, iid=item_id, var=desired_var: self.on_size_changed(pg, iid, var))
            
            # Column 5: Actual weight label (computed from area)
            # Use the same coordinate space as evaluation
            total_area = (eval_page_w * eval_page_h)
            item_area = rect.width * rect.height
            actual_fraction = item_area / total_area if total_area > 0 else 0.0
            
            # Simpler: just show the area fraction as percentage of page
            actual_pct = actual_fraction * 100
            actual_label = ttk.Label(self.photo_frame, text=f'{actual_pct:.1f}%', font=('TkDefaultFont', 9))
            actual_label.grid(row=row, column=6, padx=2, pady=1)
            
            self.weight_widgets.append((item_label, dpi_label, slot_ar_entry, checkbox_widget, photo_ar_label, desired_entry, actual_label))
        
        # Position "Add text box" button below all items (skip row 0 and 1 for headers)
        next_row = 2 + len(rectangles)
        self.add_text_btn.grid(row=next_row, column=0, columnspan=7, padx=2, pady=4, sticky='w')
        
        # Report gap variations for current layout
        if photos or texts:
            all_items = photos + texts
            analysis = analyze_gap_details(all_items, page_w, page_h, origin_left, self.spread_mode.get())
            report_gap_variations(analysis, pageno)

    # Use cache where possible, and add to the cache if not currently there.
    def _get_photo_dimensions(self, fn: str or None) -> Tuple[int, int]:
        if not fn: return None
        # If not cached, then find it and cache.
        if fn not in self.photo_dimensions:
            # Load and cache dimensions
            safefn = fn.replace('safecontainer:/', '').lstrip('/')
            img_path = Path(self.mcf_base_folder) / safefn
            if img_path.exists():
                try:
                    dims = get_image_dimensions(img_path)
                    if dims is None: return None
                    self.photo_dimensions[fn] = dims
                except Exception:
                    return None
        # Use the cache.
        img_w, img_h = self.photo_dimensions[fn]
        if img_h == 0 or img_w == 0: return None

        return self.photo_dimensions[fn]

    def _calculate_photo_dpi(self, photo: dict, slot_width_mcf: float, slot_height_mcf: float) -> int:
        """Calculate rendered DPI for a photo in the given slot dimensions. Note that this does not
        take account of any scaling (zoom in) done in CEWE. 

        Args:
            photo: photo dict (may contain 'filename' or 'image_width'/'image_height')
            slot_width_mcf: slot width in MCF units (1 unit = 0.1 mm)
            slot_height_mcf: slot height in MCF units

        Returns:
            DPI as int (rounded), or None if not computable
        """
        # Get pixel dimensions from cache or from photo dict
        dims = None
        # Prefer explicit image dimensions stored on staged photos
        if 'image_width' in photo and 'image_height' in photo and photo.get('image_width') and photo.get('image_height'):
            dims = (int(photo.get('image_width')), int(photo.get('image_height')))
        else:
            fn = photo.get('filename')
            dims = self._get_photo_dimensions(fn) if fn else None

        if not dims:
            return None
        pix_w, pix_h = dims

        # Guard against zero slot sizes
        try:
            if slot_width_mcf <= 0 or slot_height_mcf <= 0:
                return None
        except Exception:
            return None

        # Convert MCF units (0.1 mm per unit) to inches: inches = (units * 0.1) / 25.4
        inches_w = (slot_width_mcf * 0.1) / 25.4
        inches_h = (slot_height_mcf * 0.1) / 25.4
        if inches_w <= 0 or inches_h <= 0:
            return None

        dpi_w = pix_w / inches_w
        dpi_h = pix_h / inches_h

        dpi = min(dpi_w, dpi_h)
        return int(round(dpi))

    def _write_debug_dump(self, pageno, page_w, page_h, origin_left, is_left_page, edge_gap, internal_gap,
                         photos, texts, preferred_sizes, algorithm_name, use_slot_aspect_for_photos, slot_aspect_ratios):
        """Write debug dump file with all data needed to reproduce layout generation.
        
        Args:
            pageno: Page number
            page_w, page_h: Page dimensions in MCF units
            origin_left: Origin left offset for right pages
            is_left_page: True if left/even page
            edge_gap, internal_gap: Gap values in MCF units
            photos: List of photo dicts with MCF coordinates
            texts: List of text dicts with MCF coordinates
            preferred_sizes: Dict mapping photo filename or text_id to preferred size
            algorithm_name: Name of algorithm being run
            use_slot_aspect_for_photos: Dict mapping photo index to bool (use slot AR)
            slot_aspect_ratios: Dict mapping item index to float aspect ratio
        """
        from pathlib import Path
        
        debug_file = Path(f"Debug-Page-{pageno}.txt")
        
        with open(debug_file, 'w') as f:
            f.write(f"Debug Dump for Page {pageno}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("PAGE PROPERTIES:\n")
            f.write(f"  page_width: {page_w}\n")
            f.write(f"  page_height: {page_h}\n")
            f.write(f"  origin_left: {origin_left}\n")
            f.write(f"  is_left_page: {is_left_page}\n")
            f.write(f"  spread_mode: {self.spread_mode.get()}\n")
            f.write("\n")
            
            f.write("GAP PARAMETERS:\n")
            f.write(f"  edge_gap: {edge_gap} ({edge_gap/10:.1f}mm)\n")
            f.write(f"  internal_gap: {internal_gap} ({internal_gap/10:.1f}mm)\n")
            f.write("\n")
            
            f.write("ALGORITHM:\n")
            f.write(f"  name: {algorithm_name}\n")
            f.write("\n")
            
            f.write(f"PHOTOS ({len(photos)} total):\n")
            for i, p in enumerate(photos):
                f.write(f"  Photo {i}:\n")
                f.write(f"    filename: {p.get('filename', 'N/A')}\n")
                f.write(f"    area_left: {p.get('area_left', 0)}\n")
                f.write(f"    area_top: {p.get('area_top', 0)}\n")
                f.write(f"    area_width: {p.get('area_width', 0)}\n")
                f.write(f"    area_height: {p.get('area_height', 0)}\n")
                fn = p.get('filename', '')
                if fn:
                    base_fn, _, _ = extract_metadata_from_filename(fn)
                    pref_size = preferred_sizes.get(fn, 1.0)
                    f.write(f"    preferred_size: {pref_size}\n")
                    use_slot = use_slot_aspect_for_photos.get(i, False)
                    f.write(f"    use_slot_aspect: {use_slot}\n")
                    if use_slot:
                        slot_ar = slot_aspect_ratios.get(i, None)
                        f.write(f"    slot_aspect_ratio: {slot_ar}\n")
                f.write("\n")
            
            f.write(f"TEXTS ({len(texts)} total):\n")
            for i, t in enumerate(texts):
                f.write(f"  Text {i}:\n")
                f.write(f"    area_left: {t.get('area_left', 0)}\n")
                f.write(f"    area_top: {t.get('area_top', 0)}\n")
                f.write(f"    area_width: {t.get('area_width', 0)}\n")
                f.write(f"    area_height: {t.get('area_height', 0)}\n")
                text_id = f'TEXT_{i}'
                pref_size = preferred_sizes.get(text_id, 1.0)
                f.write(f"    preferred_size: {pref_size}\n")
                f.write("\n")
            
            f.write("\nTo reproduce in test:\n")
            f.write("1. Transform items to gap-free coordinates using transform_item_to_gapfree()\n")
            f.write("2. Transform page dimensions using transform_page_to_gapfree()\n")
            f.write("3. Run algorithm\n")
            f.write("4. Transform results back using transform_item_from_gapfree()\n")
        
        logger.info(f"Debug dump written to {debug_file}")

    def add_text_box(self):
        """Add a new text box to the current page."""
        if not self.pages:
            self.show_status('No pages available', error=True)
            return
        
        pageno, info = self.pages[self.index]
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])
        texts = current_layout.texts if current_layout else info.get('texts', [])
        
        page_w = info.get('page_width')
        page_h = info.get('page_height')
        origin_left = info.get('origin_left', 0.0)
        
        # Create new text box with default dimensions (20% of page width, 10% of page height)
        # Position it in the center of the page
        text_w = page_w * 0.2
        text_h = page_h * 0.1
        text_left = origin_left + (page_w - text_w) / 2
        text_top = (page_h - text_h) / 2
        
        new_text = {
            'area_left': text_left,
            'area_top': text_top,
            'area_width': text_w,
            'area_height': text_h,
        }
        
        # Add to current texts
        updated_texts = list(texts) + [new_text]
        
        # Push updated layout
        self.layout_mgr.push_layout(pageno, photos, updated_texts)
        
        # Set default preferred size for new text box
        text_id = f'TEXT_{len(texts)}'
        self.layout_mgr.set_size(pageno, text_id, 1.0)
        
        # Mark page(s) as modified
        self._mark_current_pages_modified()
        
        # Re-render page
        self.render_page()
        self.show_status(f'Added text box to page {pageno}')
    
    def on_size_changed(self, pageno, item_id, var):
        """Handle preferred size entry change.
        
        Args:
            pageno: Page number
            item_id: Filename for photos, TEXT_N for text blocks
            var: StringVar containing the new size
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            new_size = float(var.get())
            if 0.0 <= new_size <= 200.0:  # Reasonable bounds (scaled by 10×)
                # Extract base filename (without -sz-pg) to use as key
                # For text blocks (TEXT_N), extract_metadata returns the same value
                if item_id.startswith('TEXT_'):
                    base_item_id = item_id
                else:
                    base_item_id, _, _ = extract_metadata_from_filename(item_id)
                logger.info(f"Page {pageno}: Setting preferred size for '{base_item_id}' to {new_size}")
                self.layout_mgr.set_size(pageno, base_item_id, new_size)
                
                # Mark page(s) as modified so file rename happens on save
                self._mark_current_pages_modified()
                
                self.update_weights_display()  # Refresh display
            else:
                logger.warning(f"Page {pageno}: Rejected preferred size {new_size} for '{item_id}' (out of range 0.0-200.0)")
        except ValueError as e:
            logger.warning(f"Page {pageno}: Invalid preferred size input '{var.get()}' for '{item_id}': {e}")
    
    def on_slot_aspect_changed(self, pageno, item_idx, var):
        """Handle slot aspect ratio entry change.
        
        Args:
            pageno: Page number
            item_idx: Item index (photo or text)
            var: StringVar containing the new aspect ratio
        """
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            new_aspect = float(var.get())
            if 0.1 <= new_aspect <= 10.0:  # Reasonable bounds for aspect ratio
                ar_key = (pageno, item_idx)
                logger.info(f"Page {pageno}, item {item_idx}: Setting slot aspect ratio to {new_aspect}")
                self.slot_aspect_ratios[ar_key] = new_aspect
                # No need to refresh display here, just store the value
                # The value will be used next time generate_layout is called
            else:
                logger.warning(f"Page {pageno}, item {item_idx}: Rejected slot aspect ratio {new_aspect} (out of range 0.1-10.0)")
        except ValueError as e:
            logger.warning(f"Page {pageno}, item {item_idx}: Invalid slot aspect ratio input '{var.get()}': {e}")
    
    def on_edge_gap_changed(self):
        """Handle edge gap entry change.
        
        When gap changes, transform layout: MCF → gap-free (old gaps) → MCF (new gaps).
        This adjusts item positions/sizes to match the new gap values.
        """
        if not self.pages:
            return
        try:
            pageno, info = self.pages[self.index]
            
            # For calendars, edge gap cannot be changed - return early
            if self.is_calendar:
                self.show_status("Edge gap is fixed for calendars and cannot be changed", error=False)
                return
            
            # Get OLD gaps before changing
            old_edge_gap = self.layout_mgr.get_edge_gap(pageno)
            old_internal_gap = self.layout_mgr.get_internal_gap(pageno)
            
            # Parse and validate NEW edge gap (uniform on all 4 edges for photobooks)
            edge_gap_mm = float(self.edge_gap_var.get())
            new_edge_gap_value = edge_gap_mm * 10.0  # Convert mm to MCF units
            if not (-200.0 <= new_edge_gap_value <= 200.0):  # Reasonable bounds (-20mm to +20mm)
                self.show_status(f"Invalid edge gap: {edge_gap_mm:.1f}mm (must be -20 to +20mm)", error=True)
                # Restore previous valid value (average of all edges)
                avg_old = (old_edge_gap['top'] + old_edge_gap['bottom'] + old_edge_gap['left'] + old_edge_gap['right']) / 40.0
                self.edge_gap_var.set(f"{avg_old:.1f}")
                return
            
            # Create uniform edge gap dict for photobooks
            new_edge_gap = make_uniform_edge_gap(new_edge_gap_value)
            
            # Transform current layout using gap change
            self._transform_layout_for_gap_change(
                pageno, old_edge_gap, old_internal_gap, new_edge_gap, old_internal_gap
            )
            
            # Update stored gap value
            self.layout_mgr.set_edge_gap(pageno, new_edge_gap)
            
            # Update individual edge gap displays to match the uniform value
            if not self.is_calendar:
                self.edge_gap_top_var.set(f'{edge_gap_mm:.1f}')
                self.edge_gap_right_var.set(f'{edge_gap_mm:.1f}')
                self.edge_gap_bottom_var.set(f'{edge_gap_mm:.1f}')
                self.edge_gap_left_var.set(f'{edge_gap_mm:.1f}')
            
            # Mark page(s) as modified
            self._mark_current_pages_modified()
            
            # Report gap variations after edge gap change
            current_layout = self.layout_mgr.get_current(pageno)
            if current_layout and (current_layout.photos or current_layout.texts):
                all_items = current_layout.photos + current_layout.texts
                page_w = info.get('page_width')
                page_h = info.get('page_height')
                origin_left = info.get('origin_left', 0.0)
                analysis = analyze_gap_details(all_items, page_w, page_h, origin_left, self.spread_mode.get())
                report_gap_variations(analysis, pageno)
            
            # Re-render with adjusted layout
            self.render_page()
        except ValueError as e:
            # Show error and restore previous value
            self.show_status(f"Invalid edge gap value: {self.edge_gap_var.get()}", error=True)
            self.edge_gap_var.set(f"{old_edge_gap / 10.0:.1f}")
    
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
            gap_mm = float(self.internal_gap_var.get())
            new_internal_gap = gap_mm * 10.0  # Convert mm to MCF units
            if not (0.0 <= new_internal_gap <= 200.0):  # Reasonable bounds (0-20mm)
                self.show_status(f"Invalid internal gap: {gap_mm:.1f}mm (must be 0 to 20mm)", error=True)
                # Restore previous valid value
                self.internal_gap_var.set(f"{old_internal_gap / 10.0:.1f}")
                return
            
            # Transform current layout using gap change
            self._transform_layout_for_gap_change(
                pageno, old_edge_gap, old_internal_gap, old_edge_gap, new_internal_gap
            )
            
            # Update stored gap value
            self.layout_mgr.set_internal_gap(pageno, new_internal_gap)
            
            # Mark page(s) as modified
            self._mark_current_pages_modified()
            
            # Report gap variations after internal gap change
            current_layout = self.layout_mgr.get_current(pageno)
            if current_layout and (current_layout.photos or current_layout.texts):
                all_items = current_layout.photos + current_layout.texts
                page_w = info.get('page_width')
                page_h = info.get('page_height')
                origin_left = info.get('origin_left', 0.0)
                analysis = analyze_gap_details(all_items, page_w, page_h, origin_left, self.spread_mode.get())
                report_gap_variations(analysis, pageno)
            
            # Re-render with adjusted layout
            self.render_page()
        except ValueError as e:
            # Show error and restore previous value
            self.show_status(f"Invalid internal gap value: {self.internal_gap_var.get()}", error=True)
            self.internal_gap_var.set(f"{old_internal_gap / 10.0:.1f}")
    
    def on_individual_edge_gap_changed(self):
        """Handle individual edge gap entry changes (top, right, bottom, left).
        
        When individual edge gaps change, transform layout: MCF → gap-free (old gaps) → MCF (new gaps).
        This adjusts item positions/sizes to match the new gap values.
        """
        if not self.pages:
            return
        try:
            pageno, info = self.pages[self.index]
            
            # For calendars, edge gap cannot be changed - return early
            if self.is_calendar:
                self.show_status("Edge gap is fixed for calendars and cannot be changed", error=False)
                return
            
            # Get OLD gaps before changing
            old_edge_gap = self.layout_mgr.get_edge_gap(pageno)
            old_internal_gap = self.layout_mgr.get_internal_gap(pageno)
            
            # Parse and validate NEW individual edge gaps
            try:
                top_mm = float(self.edge_gap_top_var.get())
                right_mm = float(self.edge_gap_right_var.get())
                bottom_mm = float(self.edge_gap_bottom_var.get())
                left_mm = float(self.edge_gap_left_var.get())
            except ValueError:
                self.show_status("Invalid edge gap value - must be a number", error=True)
                # Restore previous values
                self.edge_gap_top_var.set(f'{old_edge_gap["top"] / 10.0:.1f}')
                self.edge_gap_right_var.set(f'{old_edge_gap["right"] / 10.0:.1f}')
                self.edge_gap_bottom_var.set(f'{old_edge_gap["bottom"] / 10.0:.1f}')
                self.edge_gap_left_var.set(f'{old_edge_gap["left"] / 10.0:.1f}')
                return
            
            # Convert mm to MCF units
            top_mcf = top_mm * 10.0
            right_mcf = right_mm * 10.0
            bottom_mcf = bottom_mm * 10.0
            left_mcf = left_mm * 10.0
            
            # Validate bounds (-20mm to +20mm)
            if not all(-200.0 <= val <= 200.0 for val in [top_mcf, right_mcf, bottom_mcf, left_mcf]):
                self.show_status("Invalid edge gap: must be between -20mm and +20mm", error=True)
                # Restore previous values
                self.edge_gap_top_var.set(f'{old_edge_gap["top"] / 10.0:.1f}')
                self.edge_gap_right_var.set(f'{old_edge_gap["right"] / 10.0:.1f}')
                self.edge_gap_bottom_var.set(f'{old_edge_gap["bottom"] / 10.0:.1f}')
                self.edge_gap_left_var.set(f'{old_edge_gap["left"] / 10.0:.1f}')
                return
            
            # Create new edge gap dict with individual values
            new_edge_gap = make_edge_gap(top_mcf, bottom_mcf, left_mcf, right_mcf)
            
            # Transform current layout using gap change
            self._transform_layout_for_gap_change(
                pageno, old_edge_gap, old_internal_gap, new_edge_gap, old_internal_gap
            )
            
            # Update stored gap value
            self.layout_mgr.set_edge_gap(pageno, new_edge_gap)
            
            # Update average edge gap display
            avg_edge_gap_mm = (top_mcf + right_mcf + bottom_mcf + left_mcf) / 40.0
            self.edge_gap_var.set(f'{avg_edge_gap_mm:.1f}')
            
            # Mark page(s) as modified
            self._mark_current_pages_modified()
            
            # Report gap variations after edge gap change
            current_layout = self.layout_mgr.get_current(pageno)
            if current_layout and (current_layout.photos or current_layout.texts):
                all_items = current_layout.photos + current_layout.texts
                page_w = info.get('page_width')
                page_h = info.get('page_height')
                origin_left = info.get('origin_left', 0.0)
                analysis = analyze_gap_details(all_items, page_w, page_h, origin_left, self.spread_mode.get())
                report_gap_variations(analysis, pageno)
            
            # Re-render with adjusted layout
            self.render_page()
        except Exception as e:
            # Show error and restore previous values
            self.show_status(f"Error updating edge gaps: {e}", error=True)
            old_edge_gap = self.layout_mgr.get_edge_gap(pageno)
            self.edge_gap_top_var.set(f'{old_edge_gap["top"] / 10.0:.1f}')
            self.edge_gap_right_var.set(f'{old_edge_gap["right"] / 10.0:.1f}')
            self.edge_gap_bottom_var.set(f'{old_edge_gap["bottom"] / 10.0:.1f}')
            self.edge_gap_left_var.set(f'{old_edge_gap["left"] / 10.0:.1f}')
    
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
        page_w = info.get('page_width')
        page_h = info.get('page_height')
        origin_left = info.get('origin_left', 0.0)

        transformed_photos = self._transformItemsForGapChange(current_layout.photos, new_internal_gap, new_edge_gap,
                                                              old_internal_gap, old_edge_gap, origin_left, page_w,
                                                              page_h)
        transformed_texts = self._transformItemsForGapChange(current_layout.texts, new_internal_gap, new_edge_gap,
                                                              old_internal_gap, old_edge_gap, origin_left, page_w,
                                                              page_h)

        # Push transformed layout (replaces current layout)
        self.layout_mgr.push_layout(pageno, transformed_photos, transformed_texts)

    def _transformItemsForGapChange(self, items: list[dict], new_internal_gap, new_edge_gap, old_internal_gap,
                                    old_edge_gap, origin_left, page_w, page_h) -> list[Any]:
        # Transform photos using centralized helper
        transformed_items = []
        for i in items:
            # Coordinates in MCF file are spread-relative (origin_left offset for right pages)
            spread_left = i.get('area_left', 0)
            top = i.get('area_top', 0)
            width = i.get('area_width', 0)
            height = i.get('area_height', 0)

            # Convert to page-relative coordinates for transformation
            page_left = spread_left - origin_left
            # Determine spread mode for transformation
            new_left, new_top, new_width, new_height = transform_item_for_gap_change(
                page_left, top, width, height, page_w, page_h,
                old_edge_gap, old_internal_gap, new_edge_gap, new_internal_gap,
                origin_left == 0.0, self.spread_mode.get()
            )

            # Convert back to spread-relative coordinates
            new_spread_left = new_left + origin_left

            updated_item = i.copy()
            updated_item['area_left'] = new_spread_left
            updated_item['area_top'] = new_top
            updated_item['area_width'] = new_width
            updated_item['area_height'] = new_height
            transformed_items.append(updated_item)
        return transformed_items

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
    
    def on_empty_threshold_changed(self):
        """Handle empty space threshold parameter change."""
        try:
            new_threshold_pct = float(self.empty_threshold_var.get())
            if 0.0 <= new_threshold_pct <= 100.0:  # 0% to 100%
                self.empty_threshold = new_threshold_pct / 100.0  # Convert % to fraction
                self.update_weights_display()  # Refresh cost display
        except ValueError:
            pass  # Ignore invalid input

    def prev_page(self):
        if self.spread_mode.get():
            # In spread mode, navigate to previous even page (or cover spread)
            current_pageno = self.pages[self.index][0]
            current_info = self.pages[self.index][1]
            is_current_cover = current_info.get('is_cover', False)
            
            if is_current_cover:
                # Navigate from cover spread to last normal even page
                for i in range(len(self.pages) - 1, -1, -1):
                    pageno, info = self.pages[i]
                    if not info.get('is_cover', False) and isinstance(pageno, int) and pageno % 2 == 0:
                        # Found last normal even page
                        self._goto_page(i, f'Loading page {pageno}...')
                        return
                # No normal even pages, stay on cover
                return
            
            # Find previous even page (normal pages only)
            for i in range(self.index - 1, -1, -1):
                pageno, info = self.pages[i]
                if not info.get('is_cover', False) and isinstance(pageno, int) and pageno % 2 == 0:
                    self._goto_page(i, f'Loading pages {pageno}-{pageno+1}...')
                    return
            
            # No more even pages before - check for front cover
            for i in range(len(self.pages)):
                pageno, info = self.pages[i]
                if pageno == "F" and info.get('is_cover', False):
                    self._goto_page(i, 'Loading covers...')
                    return
            
            # No even page found before current - stay where we are
            return
        else:
            # Single page mode: move to previous page in list
            if self.index > 0:
                pageno = self.pages[self.index-1][0]
                self._goto_page(self.index -1, f'Loading page {pageno}...')
            else:
                return

    def next_page(self):
        if self.spread_mode.get():
            # In spread mode, navigate to next even page (or cover spread)
            current_pageno = self.pages[self.index][0]
            current_info = self.pages[self.index][1]
            is_current_cover = current_info.get('is_cover', False)
            
            if is_current_cover:
                # Navigate forward from cover spread to first normal page (page 1)
                for i in range(len(self.pages)):
                    pageno, info = self.pages[i]
                    if not info.get('is_cover', False):
                        # Found first normal page
                        self._goto_page(i, f'Loading page {pageno}...')
                        return
                # No normal pages, stay on cover
                self.show_status('Last page of book')
                return
            
            # Find next even page after current spread (normal pages only)
            if isinstance(current_pageno, int):
                start_search = self.index + 2 if current_pageno % 2 == 0 else self.index + 1
            else:
                # Current is a cover, shouldn't reach here but handle it
                start_search = self.index + 1
            
            for i in range(start_search, len(self.pages)):
                pageno, info = self.pages[i]
                if not info.get('is_cover', False) and isinstance(pageno, int) and pageno % 2 == 0:
                    msg = f'Loading page {pageno}...'

                    # Check if there's an odd page following
                    if i < len(self.pages) - 1:
                        next_pageno = self.pages[i + 1][0]
                        next_info = self.pages[i + 1][1]
                        if not next_info.get('is_cover', False):
                            msg = f'Loading pages {pageno}-{next_pageno}...'

                    self._goto_page(i, msg)
                    return
            
            # No more normal even pages - check for back cover
            for i in range(len(self.pages)):
                pageno, info = self.pages[i]
                if pageno == "B" and info.get('is_cover', False):
                    self._goto_page(i, 'Loading covers...')
                    return
            
            # No more even pages - we're at the end
            self.show_status('Last page of book')
            return
        else:
            # Single page mode: move to next page in list
            if self.index < len(self.pages) - 1:
                pageno = self.pages[self.index+1][0]
                self._goto_page(self.index+1,f'Loading page {pageno}...')
            else:
                self.show_status('Last page of book')
                return

    def goto_page(self):
        input_str = self.goto_var.get().strip().upper()
        if not input_str:
            return
        
        # Handle cover page identifiers: "F" for front cover, "B" for back cover
        if input_str in ["F", "B"]:
            v = input_str
        else:
            # Try to parse as integer for normal pages
            try:
                v = int(input_str)
            except Exception:
                return
        
        # find index for page number
        for i,(pn,_) in enumerate(self.pages):
            if pn == v:
                self._goto_page(i, f'Loading page {v}...')
                return

    def _goto_page(self, i: int, msg: str):
        self.index = i
        self.show_status(msg)
        self.root.update_idletasks()
        self.render_page()

    def quit(self):
        self.root.quit()
    
    def _update_page_range_display(self):
        """Update the page range label to show valid page numbers."""
        if not self.pages:
            self.page_range_var.set('')
            return
        
        # Find min/max numeric pages and check for covers
        has_front_cover = any(pn == "F" for pn, _ in self.pages)
        has_back_cover = any(pn == "B" for pn, _ in self.pages)
        numeric_pages = [pn for pn, _ in self.pages if isinstance(pn, int)]
        
        if numeric_pages:
            min_page = min(numeric_pages)
            max_page = max(numeric_pages)
            range_str = f'{min_page}-{max_page}'
        else:
            range_str = ''
        
        # Add cover indicators
        if has_front_cover and has_back_cover:
            if range_str:
                self.page_range_var.set(f'Pages F, {range_str}, B')
            else:
                self.page_range_var.set('Pages F, B')
        elif has_front_cover:
            if range_str:
                self.page_range_var.set(f'Pages F, {range_str}')
            else:
                self.page_range_var.set('Pages F')
        elif has_back_cover:
            if range_str:
                self.page_range_var.set(f'Pages {range_str}, B')
            else:
                self.page_range_var.set('Pages B')
        else:
            self.page_range_var.set(f'Pages {range_str}' if range_str else '')
    
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
        
        # Don't re-render if overlay is active (would hide it)
        if hasattr(self, 'overlay_items'):
            return
        
        self.render_page()
    
    def _on_spread_mode_change(self):
        """Handle spread mode checkbox toggle - re-render current page(s)."""
        # Update canvas aspect ratio and window geometry based on spread mode
        _, first_page_info = self.pages[0]
        page_w = first_page_info.get('page_width')
        page_h = first_page_info.get('page_height')
        
        if self.spread_mode.get():
            # Entering spread mode: navigate to nearest even page (unless on a cover)
            current_pageno = self.pages[self.index][0]
            current_info = self.pages[self.index][1]
            is_current_cover = current_info.get('is_cover', False)
            
            # Only navigate if not on a cover and on odd page
            if current_pageno % 2 != 0 and not is_current_cover:
                # Current page is odd - navigate to previous even page if possible
                for i in range(self.index - 1, -1, -1):
                    if self.pages[i][0] % 2 == 0:
                        self.index = i
                        break
            
            # Spread mode: double width for two pages
            total_w_mcf = (2 * page_w) + 2 * self.margin_mcf
            total_h_mcf = page_h + 2 * self.margin_mcf
        else:
            # Single page mode
            total_w_mcf = page_w + 2 * self.margin_mcf
            total_h_mcf = page_h + 2 * self.margin_mcf
        
        self.canvas_aspect_ratio = total_w_mcf / total_h_mcf
        
        # Update window aspect ratio
        ratio_num = int(self.canvas_aspect_ratio * 1000)
        ratio_denom = 1000
        
        # Re-render to immediately show the change
        self.render_page()
    
    def _on_draw_cropped_change(self):
        """Handle draw cropped checkbox toggle - re-render current page(s)."""
        # Simply re-render the current page with the new mode
        self.render_page()
    
    def _on_pdf_photo_count_change(self, event=None):
        """Handle PDF photo count change - re-analyze page with new target count."""

        if not self.pdf_content:
            return
        
        try:
            target_count = int(self.pdf_photo_count_var.get())
        except ValueError:
            print("Invalid photo count - must be an integer")
            return
        
        # Check if user wants to re-segment a specific photo or the whole page
        photo_select_str = self.pdf_photo_select_var.get().strip()
        specific_photo_index = None
        if photo_select_str:
            try:
                specific_photo_index = int(photo_select_str) - 1  # Convert to 0-based index
                if specific_photo_index < 0:
                    print("Invalid photo number - must be >= 1")
                    return
            except ValueError:
                print("Invalid photo number - must be an integer or empty")
                return
        
        # Get current page number (CEWE numbering: 0=cover, 1=first page, etc.)
        current_pageno = self.pages[self.index][0]
        
        # Map UI page to PDF page index
        pdf_page_index = self._ui_page_to_pdf_page(current_pageno)
        if pdf_page_index is None:
            print(f"Error: CEWE page {current_pageno} has no corresponding PDF page")
            self.status_var.set(f'Error: Page {current_pageno} has no PDF content')
            return
        
        if specific_photo_index is not None:
            print(f"Re-segmenting photo #{specific_photo_index+1} on CEWE page {current_pageno} (PDF page {pdf_page_index}) into {target_count} photos")
        else:
            print(f"Re-analyzing entire CEWE page {current_pageno} (PDF page {pdf_page_index}) with target photo count: {target_count}")
                
        # Get selected algorithm and segmenter
        from .pdf2cewe.segmenter_base import get_segmenter

        algorithm = self.segmentation_algorithm_var.get();
        segmenter = get_segmenter(algorithm)
        
        if segmenter is None:
            print(f"Unknown segmentation algorithm: {algorithm}")
            self.status_var.set(f'❌ Unknown algorithm: {algorithm}')
            return

        scaled_segments, image_data, image_format, image_to_segment, photos_to_replace = performSegmentationOnPage(self.pdf_content,
                                                                                                 self.pages, self.index,
                                                                                                 self.status_var,
                                                                                                 pdf_page_index,
                                                                                                 segmenter,
                                                                                                 specific_photo_index,
                                                                                                 target_count)

        if scaled_segments != None:
            # Show overlay with the new segmentation rectangles
            self._show_segmentation_overlay(scaled_segments, current_pageno, image_to_segment, image_data, image_format, photos_to_replace)

    def _show_segmentation_overlay(self, segments, pageno, composite_image, image_data, image_format, photos_to_replace):
        """Show overlay with segmentation rectangles and accept/reject buttons.
        
        Args:
            segments: List of segment dicts from segmentation (in PDF-based MCF coordinates)
            pageno: Page number being re-segmented
            composite_image: Original composite image dict from PDF
            image_data: Original image bytes
            image_format: Image format
            photos_to_replace: List of photo indices to replace (empty = all photos)
        """
        # Get page info for rendering and dimension calculations
        _, page_info = self.pages[self.index]
        page_width = page_info.get('page_width')
        page_height = page_info.get('page_height')
        origin_left = page_info.get('origin_left', 0.0)
        
        # Segments are already in PDF-based MCF spread coordinates from _makeScaledSegments()
        # Add dimension metadata to segments for overlay rendering
        
        # Get PDF page dimensions from composite_image if available
        # These are the dimensions used when extracting from PDF
        pdf_page_width = None
        pdf_page_height = None
        if composite_image:
            # Calculate PDF page dimensions from composite coordinates
            # composite_image has PDF-based MCF coordinates
            # For a full-page composite, width should be close to page width
            comp_width = composite_image.get('width', 0)
            comp_height = composite_image.get('height', 0)
            # Use composite dimensions as proxy for PDF page dimensions
            # This is approximate but should be close for full-page composites
            pdf_page_width = comp_width
            pdf_page_height = comp_height
            
            # Add dimension metadata to composite_image for use in _accept_segmentation
            composite_image = composite_image.copy()  # Don't modify original
            composite_image['pdf_page_width_mcf'] = pdf_page_width
            composite_image['pdf_page_height_mcf'] = pdf_page_height
            composite_image['cewe_page_width_mcf'] = page_width
            composite_image['cewe_page_height_mcf'] = page_height
            
            print(f"  Dimension metadata: PDF {pdf_page_width:.1f}x{pdf_page_height:.1f} MCF, "
                  f"CEWE {page_width:.1f}x{page_height:.1f} MCF")
            
            # Add dimension metadata to each segment for overlay rendering
            spread_relative_segments = []
            for seg in segments:
                seg_with_meta = seg.copy()
                seg_with_meta['_pdf_page_width_mcf'] = pdf_page_width
                seg_with_meta['_pdf_page_height_mcf'] = pdf_page_height
                spread_relative_segments.append(seg_with_meta)
        else:
            # No composite_image - pass segments through unchanged
            spread_relative_segments = segments
        
        # Store data for accept/reject handlers
        self.pending_segmentation = {
            'segments': segments,
            'pageno': pageno,
            'composite_image': composite_image,
            'image_data': image_data,
            'image_format': image_format,
            'photos_to_replace': photos_to_replace
        }
        
        # Use page renderer to show overlay (with spread-relative segments in points)
        # Pass origin_left in MCF units as expected by the overlay renderer
        canvas_w, canvas_h = self._get_canvas_dimensions()
        self.overlay_items, self.overlay_button_frame = self.page_renderer.show_segmentation_overlay(
            self.canvas, spread_relative_segments, canvas_w, canvas_h, page_width, page_height,
            self.margin_mcf, origin_left,
            self._accept_segmentation, self._reject_segmentation, self.ctrlWin
        )
    
    def _clear_overlay(self):
        """Clear the segmentation overlay and buttons."""
        # Clear canvas items and button frame via page renderer
        if hasattr(self, 'overlay_items'):
            self.page_renderer.clear_overlay_from_canvas(self.canvas, self.overlay_items)
            del self.overlay_items
        
        # Clear button frame
        if hasattr(self, 'overlay_button_frame'):
            self.overlay_button_frame.destroy()
            del self.overlay_button_frame
        
        # Clear pending segmentation
        if hasattr(self, 'pending_segmentation'):
            del self.pending_segmentation
    
    def _accept_segmentation(self):
        """Accept the new segmentation and update in-memory data structures.
        
        This does NOT save to disk - the user must click "Save Modified" to persist changes.
        """
        if not hasattr(self, 'pending_segmentation'):
            return
        
        seg_data = self.pending_segmentation
        pageno = seg_data['pageno']
        segments = seg_data['segments']
        image_data = seg_data['image_data']
        image_format = seg_data['image_format']
        photos_to_replace = seg_data.get('photos_to_replace', [])
        
        if photos_to_replace:
            print(f"Accepting new segmentation for page {pageno} with {len(segments)} photos (replacing photos: {[i+1 for i in photos_to_replace]})")
        else:
            print(f"Accepting new segmentation for page {pageno} with {len(segments)} photos (replacing all photos)")
        
        # Update in-memory structures (don't write to disk yet)
        self._update_page_with_segmentation(pageno, segments, image_data, image_format, photos_to_replace)
        
        # Clear overlay
        self._clear_overlay()
        
        # Re-render page
        self.render_page()
        
        self.status_var.set(f'✅ Applied new segmentation with {len(segments)} photos (not saved to disk yet)')
    
    def _reject_segmentation(self):
        """Reject the new segmentation and keep the existing layout."""
        print("Rejecting new segmentation")
        
        # Clear overlay
        self._clear_overlay()
        
        self.status_var.set('Segmentation rejected')
    
    def _update_page_with_segmentation(self, pageno, segments, image_data, image_format, photos_to_replace=None):
        """Update in-memory data structures with new segmentation.
        
        This does NOT save to disk or modify the MCF file. Changes are held in memory
        and will be written when the user clicks "Save Modified".
        
        Args:
            pageno: Page number to update
            segments: New segment list with both coordinate systems:
                     - left/top/width/height: PDF-based MCF spread coordinates
                     - pixel_left/pixel_top/pixel_width/pixel_height: Image pixel coordinates
            image_data: Original composite image data
            image_format: Image format (e.g., 'JPEG', 'PNG')
            photos_to_replace: List of photo indices to replace (None/empty = replace all)
        """
        from pathlib import Path
        from PIL import Image
        import io
        from .file_utils import encode_metadata_in_filename
        
        # Get album directory and create parallel -photos directory
        album_path = Path(self.mcf_file_path).parent
        album_name = album_path.name.replace('.xmcf', '').replace('.mcfx', '')
        photos_dir = album_path.parent / f"{album_name}-photos"
        photos_dir.mkdir(exist_ok=True)
        
        print(f"Saving segmentation images to: {photos_dir}")
        
        # Get page info for dimension information
        _, page_info = self.pages[self.index]
        
        # Get composite image metadata for scaling calculations
        composite_image = self.pending_segmentation.get('composite_image')
        if not composite_image:
            print("  Warning: No composite_image metadata in pending_segmentation")
            # Proceed anyway - segments should have 'data' field
        
        # Get dimension scaling factors from PDF to CEWE
        # These are stored in the composite_image metadata by _show_segmentation_overlay
        pdf_page_width = composite_image.get('pdf_page_width_mcf') if composite_image else None
        pdf_page_height = composite_image.get('pdf_page_height_mcf') if composite_image else None
        cewe_page_width = composite_image.get('cewe_page_width_mcf') if composite_image else None
        cewe_page_height = composite_image.get('cewe_page_height_mcf') if composite_image else None
        
        # Calculate scale factors from PDF MCF to CEWE MCF
        if pdf_page_width and cewe_page_width and pdf_page_height and cewe_page_height:
            scale_x = cewe_page_width / pdf_page_width
            scale_y = cewe_page_height / pdf_page_height
            print(f"  Scaling segments: PDF {pdf_page_width}x{pdf_page_height} → CEWE {cewe_page_width}x{cewe_page_height}")
            print(f"  Scale factors: x={scale_x:.6f}, y={scale_y:.6f}")
        else:
            # Fallback: no scaling (assume PDF dimensions match CEWE)
            scale_x = 1.0
            scale_y = 1.0
            print(f"  Warning: Missing dimension metadata, assuming PDF == CEWE dimensions")
        
        # Create new photo dicts from segments and save image files
        new_photo_dicts = []
        new_photo_filenames = []
        
        for i, seg in enumerate(segments):
            # Generate filename with metadata
            # Handle string page identifiers (F, B) and integer page numbers
            if isinstance(pageno, str):
                base_name = f"seg_p{pageno}_{i:02d}"
            else:
                base_name = f"seg_p{pageno:03d}_{i:02d}"
            ext = 'jpg' if image_format.upper() in ['JPEG', 'JPG'] else image_format.lower()
            # Encode metadata in filename (size=1.0, page=pageno)
            filename_with_meta = encode_metadata_in_filename(f"{base_name}.{ext}", 1.0, pageno)
            
            # Full path in -photos directory
            image_path = photos_dir / filename_with_meta
            
            # Extract and save this segment's image data
            # If seg has 'data' key, use it directly; otherwise extract from composite using pixel coords
            if 'data' in seg:
                # Segment already has image data (normal case from segmenter)
                image_path.write_bytes(seg['data'])
            else:
                # Fallback: Extract from composite image using pixel coordinates
                # This shouldn't happen with current segmenter, but handle it gracefully
                print(f"  Warning: Segment {i} missing 'data' field, extracting from composite")
                if 'pixel_left' in seg and 'pixel_top' in seg and 'pixel_width' in seg and 'pixel_height' in seg:
                    img = Image.open(io.BytesIO(image_data))
                    # Crop using pixel coordinates relative to composite image
                    pixel_x1 = int(seg['pixel_left'])
                    pixel_y1 = int(seg['pixel_top'])
                    pixel_x2 = int(seg['pixel_left'] + seg['pixel_width'])
                    pixel_y2 = int(seg['pixel_top'] + seg['pixel_height'])
                    cropped = img.crop((pixel_x1, pixel_y1, pixel_x2, pixel_y2))
                    cropped.save(image_path, quality=95)
                else:
                    print(f"  Error: Segment {i} missing both 'data' and pixel coordinates")
                    continue
            
            print(f"  Saved segment {i} to: {filename_with_meta}")
            
            # Scale coordinates from PDF-based MCF to CEWE MCF dimensions
            # Segments have 'left', 'top', 'width', 'height' in PDF-based MCF spread coordinates
            cewe_left = seg['left'] * scale_x
            cewe_top = seg['top'] * scale_y
            cewe_width = seg['width'] * scale_x
            cewe_height = seg['height'] * scale_y
            
            print(f"  Segment {i}: PDF MCF ({seg['left']:.1f}, {seg['top']:.1f}) {seg['width']:.1f}x{seg['height']:.1f}")
            print(f"           → CEWE MCF ({cewe_left:.1f}, {cewe_top:.1f}) {cewe_width:.1f}x{cewe_height:.1f}")
            
            # Create photo dict with safecontainer prefix
            safe_filename = f"safecontainer:/{filename_with_meta}"
            photo_dict = {
                'filename': safe_filename,
                'area_left': cewe_left,      # CEWE MCF spread coordinates
                'area_top': cewe_top,
                'area_width': cewe_width,
                'area_height': cewe_height,
                'area_rot': 0,
                'cutout': None,
                '_source_path': str(image_path)  # Track source for save_layout
            }
            new_photo_dicts.append(photo_dict)
            new_photo_filenames.append(safe_filename)
        
        # Use LayoutManager API to update the page with new photos
        success = self.layout_mgr.replace_photos_with_new(
            pageno=pageno,
            photos_to_remove_indices=photos_to_replace if photos_to_replace else None,
            new_photos=new_photo_dicts,
            new_photo_filenames=new_photo_filenames,
            preferred_sizes=None  # Will default to 1.0 for all
        )
        
        if not success:
            print(f"  Error: Failed to update layout for page {pageno}")
            return
        
        # Mark page as modified
        self._mark_current_pages_modified()
        
        if photos_to_replace:
            print(f"  ✅ Replaced {len(photos_to_replace)} photos with {len(new_photo_dicts)} new photos on page {pageno}")
        else:
            print(f"  ✅ Replaced all photos with {len(new_photo_dicts)} new photos on page {pageno}")
        
        print(f"  Page {pageno} marked as modified - will be saved when you click 'Save Modified'")
    
    def _update_modified_pages_display(self):
        """Update the modified pages label in Controls window."""
        if not self.modified_pages:
            self.modified_pages_var.set('(none)')
            self.modified_pages_label.config(foreground='blue')
        else:
            # Sort page numbers, handling mixed string ("F", "B") and integer types
            sorted_pages = sorted(self.modified_pages, key=page_sort_key)
            page_str = ', '.join(str(p) for p in sorted_pages)
            self.modified_pages_var.set(page_str)
            self.modified_pages_label.config(foreground='red')
    
    def _mark_current_pages_modified(self):
        """Mark the current page(s) as modified.
        
        In spread mode, marks both pages in the spread.
        In single page mode, marks only the current page.
        """
        if self.spread_mode.get() and len(self.current_spread_pages) == 2:
            # Spread mode - mark both pages
            self.modified_pages.add(self.current_spread_pages[0])
            self.modified_pages.add(self.current_spread_pages[1])
        else:
            # Single page mode - mark current page only
            pageno, _ = self.pages[self.index]
            self.modified_pages.add(pageno)
        self._update_modified_pages_display()
    
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

    def _write_debug_dump(self, pageno, page_w, page_h, origin_left, is_left_page, edge_gap, internal_gap,
                         photos, texts, preferred_sizes, algorithm_name, use_slot_aspect_for_photos, slot_aspect_ratios):
        """Write debug dump file with all data needed to reproduce layout generation.
        
        Args:
            pageno: Page number
            page_w, page_h: Page dimensions in MCF units
            origin_left: Origin left offset for right pages
            is_left_page: True if left/even page
            edge_gap, internal_gap: Gap values in MCF units
            photos: List of photo dicts with MCF coordinates
            texts: List of text dicts with MCF coordinates
            preferred_sizes: Dict mapping photo filename or text_id to preferred size
            algorithm_name: Name of algorithm being run
            use_slot_aspect_for_photos: Dict mapping photo index to bool (use slot AR)
            slot_aspect_ratios: Dict mapping (pageno, photo_idx) to float aspect ratio
        """
        from pathlib import Path
        
        debug_file = Path(f"Debug-Page-{pageno}.txt")
        
        with open(debug_file, 'w') as f:
            f.write(f"Debug Dump for Page {pageno}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write("PAGE PROPERTIES:\n")
            f.write(f"  page_width: {page_w}\n")
            f.write(f"  page_height: {page_h}\n")
            f.write(f"  origin_left: {origin_left}\n")
            f.write(f"  is_left_page: {is_left_page}\n")
            f.write(f"  spread_mode: {self.spread_mode.get()}\n")
            f.write("\n")
            
            f.write("GAP PARAMETERS:\n")
            f.write(f"  edge_gap: {edge_gap} ({edge_gap/10:.1f}mm)\n")
            f.write(f"  internal_gap: {internal_gap} ({internal_gap/10:.1f}mm)\n")
            f.write("\n")
            
            f.write("ALGORITHM:\n")
            f.write(f"  name: {algorithm_name}\n")
            f.write("\n")
            
            f.write(f"PHOTOS ({len(photos)} total):\n")
            for i, p in enumerate(photos):
                f.write(f"  Photo {i}:\n")
                f.write(f"    filename: {p.get('filename', 'N/A')}\n")
                f.write(f"    area_left: {p.get('area_left', 0)}\n")
                f.write(f"    area_top: {p.get('area_top', 0)}\n")
                f.write(f"    area_width: {p.get('area_width', 0)}\n")
                f.write(f"    area_height: {p.get('area_height', 0)}\n")
                fn = p.get('filename', '')
                if fn:
                    base_fn, _, _ = extract_metadata_from_filename(fn)
                    pref_size = preferred_sizes.get(fn, 1.0)
                    f.write(f"    preferred_size: {pref_size}\n")
                    use_slot = use_slot_aspect_for_photos.get(i, False)
                    f.write(f"    use_slot_aspect: {use_slot}\n")
                    if use_slot:
                        slot_ar = slot_aspect_ratios.get((pageno, i), None)
                        f.write(f"    slot_aspect_ratio: {slot_ar}\n")
                f.write("\n")
            
            f.write(f"TEXTS ({len(texts)} total):\n")
            for i, t in enumerate(texts):
                f.write(f"  Text {i}:\n")
                f.write(f"    area_left: {t.get('area_left', 0)}\n")
                f.write(f"    area_top: {t.get('area_top', 0)}\n")
                f.write(f"    area_width: {t.get('area_width', 0)}\n")
                f.write(f"    area_height: {t.get('area_height', 0)}\n")
                text_id = f'TEXT_{i}'
                pref_size = preferred_sizes.get(text_id, 1.0)
                f.write(f"    preferred_size: {pref_size}\n")
                f.write("\n")
            
            f.write("\nTo reproduce in test:\n")
            f.write("1. Transform items to gap-free coordinates using transform_item_to_gapfree()\n")
            f.write("2. Transform page dimensions using transform_page_to_gapfree()\n")
            f.write("3. Run algorithm\n")
            f.write("4. Transform results back using transform_item_from_gapfree()\n")
        
        logger.info(f"Debug dump written to {debug_file}")

    def _create_algorithm_instance(self, algo_name: str):
        """Create algorithm instance with appropriate parameters.
        
        Uses the algorithm registry to dynamically instantiate the correct algorithm class
        with parameters from the current GUI state.
        
        Args:
            algo_name: Name of algorithm (from getName())
            
        Returns:
            Algorithm instance, or None if algorithm not found
        """
        algo_class = self.algorithm_registry.get(algo_name)
        if algo_class is None:
            return None
        
        # Instantiate with class-specific parameters
        if algo_class is CollageGeneratorAlgorithm:
            return CollageGeneratorAlgorithm(temperature=1.0)
        elif algo_class is FanLayoutAlgorithm:
            return FanLayoutAlgorithm(
                size_importance=self.size_importance,
                undersized_threshold=self.undersized_threshold,
                undersized_penalty=self.undersized_penalty
            )
        elif algo_class is GridifyAlgorithm:
            return GridifyAlgorithm(debug=self.debug_var.get())
        elif algo_class is TreeBuilderAlgorithm:
            return TreeBuilderAlgorithm(tolerance=60.0)
        else:
            # GapPerfecterAlgorithm and LongGapPerfecterAlgorithm take no parameters
            return algo_class()
    
    def _run_fine_tuning(self, algo_name: str):
        """Run a fine-tuning algorithm on the current page layout.
        
        Fine-tuning algorithms refine existing layouts (Gap Perfecter, Long Gap Perfecter, etc.)
        and always use the current layout's slot dimensions.
        
        Args:
            algo_name: Name of the fine-tuning algorithm to run
        """
        self._generate_layout(algo_name)

    def _generate_layout(self, algo_name: str = None):
        """Create algorithm instance and run generate_layout.
        
        Args:
            algo_name: Name of algorithm to run, or None to use current selection
        """
        # Get algorithm name from parameter or current selection
        if algo_name is None:
            algo_name = self.algorithm_var.get()
        
        # Create algorithm instance using registry
        algorithm = self._create_algorithm_instance(algo_name)
        
        # Fallback to CollageGenerator if algorithm not found
        if algorithm is None:
            logger.error(f"Algorithm '{algo_name}' not found in registry")

        self.generate_layout(algorithm)

    def generate_layout(self, algorithm: LayoutAlgorithm):
        """Run layout algorithm on current page(s) in a background thread.

        In spread mode, combines photos from both pages, runs algorithm on double-width
        page, then splits results back to individual pages.
        
        The Generate button is disabled while the operation runs and re-enabled
        when finished. Errors are shown; successful completion updates the UI
        without a popup.
        """
        # disable the button immediately to prevent double clicks
        self.gen_btn.config(state='disabled')

        # Show "Running..." status
        self.show_status('Running...')

        def worker():
            from time import time
            
            # Start overall timing
            t_start = time()

            if self.spread_mode.get() and len(self.current_spread_pages) == 2:
                # Spread mode: work with both pages combined
                page_indices = [self.index, self.index + 1]
                page_numbers = self.current_spread_pages
                
                # Collect photos and texts from both pages
                all_photos = []
                all_texts = []
                page_infos = []
                
                # Track original photos/texts by page to restore order after split
                original_photos_by_page = {}  # pageno -> list of photos in original order
                original_texts_by_page = {}
                original_xml_photos_by_page = {}  # pageno -> set of filenames from ORIGINAL XML
                
                for page_idx in page_indices:
                    pageno, info = self.pages[page_idx]
                    page_infos.append((pageno, info))
                    
                    # Store original XML photos for later comparison
                    original_xml_photos = {p.get('filename') for p in info.get('photos', []) if p.get('filename')}
                    original_xml_photos_by_page[pageno] = original_xml_photos
                    
                    # Get CURRENT layout (may differ from XML if algorithm was run before)
                    current_layout = self.layout_mgr.get_current(pageno)
                    photos = current_layout.photos if current_layout else info.get('photos', [])
                    texts = current_layout.texts if current_layout else info.get('texts', [])
                    # Filter out empty photo slots (photos with no filename)
                    valid_photos = [p for p in photos if p.get('filename')]
                    
                    # Store current photos for algorithm processing
                    original_photos_by_page[pageno] = valid_photos
                    original_texts_by_page[pageno] = texts
                    
                    all_photos.extend(valid_photos)
                    all_texts.extend(texts)
                
                if not all_photos and not all_texts:
                    # re-enable on main thread
                    self.root.after(0, lambda: self.gen_btn.config(state='normal'))
                    self.show_status('Layout generation failed: No photos or texts on spread')
                    return
                
                # Use first page's dimensions (they should be identical)
                _, info0 = page_infos[0]
                page_w = info0.get('page_width')
                page_h = info0.get('page_height')
                
                # Double width for spread
                spread_w = 2 * page_w
                
                # Offset right page photos by page_w (they're currently relative to right page's origin)
                # First page photos are already correct (left-aligned)
                # Right page photos need their coordinates adjusted to be relative to spread origin
                _, info1 = page_infos[1]
                origin_left_1 = info1.get('origin_left', 0.0)
                num_photos_page0 = len(page_infos[0][1].get('photos', []))
                
                # Adjust right-page photo coordinates to be relative to spread (not individual page)
                # Right page photos start at index num_photos_page0
                for i in range(num_photos_page0, len(all_photos)):
                    photo = all_photos[i]
                    # Remove origin_left offset (which positioned it on right page)
                    # Then add page_w to position it on the right half of the spread
                    if 'area_left' in photo and photo['area_left'] is not None:
                        photo['area_left'] = (photo['area_left'] - origin_left_1) + page_w
                
                # Similar adjustment for texts
                num_texts_page0 = len(page_infos[0][1].get('texts', []))
                for i in range(num_texts_page0, len(all_texts)):
                    text = all_texts[i]
                    if 'area_left' in text and text['area_left'] is not None:
                        text['area_left'] = (text['area_left'] - origin_left_1) + page_w
                
                # Get gaps (use first page's gaps for the whole spread)
                pageno0 = page_numbers[0]
                internal_gap = self.layout_mgr.get_internal_gap(pageno0)
                edge_gap = self.layout_mgr.get_edge_gap(pageno0)
                
                # Build preferred_sizes from both pages
                preferred_sizes = {}
                for page_idx, (pageno, _) in enumerate(page_infos):
                    current_layout = self.layout_mgr.get_current(pageno)
                    photos_for_page = current_layout.photos if current_layout else page_infos[page_idx][1].get('photos', [])
                    texts_for_page = current_layout.texts if current_layout else page_infos[page_idx][1].get('texts', [])
                    
                    for p in photos_for_page:
                        fn = p.get('filename', '')
                        if fn:
                            base_fn, _, _ = extract_metadata_from_filename(fn)
                            preferred_sizes[fn] = self.layout_mgr.get_size(pageno, base_fn)
                    for i, t in enumerate(texts_for_page):
                        text_id = f'TEXT_{i}'
                        preferred_sizes[text_id] = self.layout_mgr.get_size(pageno, text_id)

                # Get slot aspect ratio info for all items.
                slot_aspect_ratios_combined, use_slot_aspect_for_photos =_collect_slot_aspect_ratio_info (page_infos)

                # Run algorithm on combined spread
                algo_start = time()
                success, updated_photos, updated_texts, error_msg = generate_layout_for_page(
                    all_photos, spread_w, page_h, self.photo_dimensions,
                    algorithm=algorithm, edge_gap=edge_gap, internal_gap=internal_gap, texts=all_texts,
                    preferred_sizes=preferred_sizes,
                    use_slot_aspect=use_slot_aspect_for_photos,
                    slot_aspect_ratios=slot_aspect_ratios_combined,
                    origin_left=0.0,  # Spread starts at 0
                    pageno=pageno0,  # For logging
                    has_full_bleed=True # Spread mode: two pages side-by-side
                )
                algo_time = time() - algo_start
                print(f"Algorithm: {algo_time:.3f}s")
                
                if not success:
                    def on_error():
                        self.gen_btn.config(state='normal')
                        self.show_status(f'Layout generation failed: {error_msg}', error=True)
                    self.root.after(0, on_error)
                    return
                
                # Split results back into two pages, preserving original order within each page
                # Match updated photos back to originals by filename
                photos_page0 = []
                photos_page1 = []
                texts_page0 = []
                texts_page1 = []
                
                # Get page numbers for owner determination
                pageno0, pageno1 = page_numbers
                
                # Collect new photos from both source pages to transfer tracking
                all_new_photos = set()
                for pn in page_numbers:
                    all_new_photos.update(self.layout_mgr.get_new_photos(pn))
                
                # Build lookup of updated photos by filename
                updated_by_filename = {p.get('filename'): p for p in updated_photos if p.get('filename')}
                
                # Validation: Check we got back all photos from algorithm
                expected_photo_count = len(all_photos)
                actual_photo_count = len(updated_photos)
                if actual_photo_count != expected_photo_count:
                    error_msg = f"Algorithm photo count mismatch: expected {expected_photo_count}, got {actual_photo_count}"
                    logger.error(error_msg)
                    def on_error():
                        self.gen_btn.config(state='normal')
                        self.show_status(error_msg, error=True)
                    self.root.after(0, on_error)
                    return
                
                # Validation: Check we got back all texts from algorithm
                expected_text_count = len(all_texts)
                actual_text_count = len(updated_texts)
                if actual_text_count != expected_text_count:
                    error_msg = f"Algorithm text count mismatch: expected {expected_text_count}, got {actual_text_count}"
                    logger.error(error_msg)
                    def on_error():
                        self.gen_btn.config(state='normal')
                        self.show_status(error_msg, error=True)
                    self.root.after(0, on_error)
                    return
                
                # Reconstruct photos for both pages
                # Process ALL photos (from both original pages) and assign to final page based on position
                all_original_photos = list(original_photos_by_page[pageno0]) + list(original_photos_by_page[pageno1])
                
                for orig_photo in all_original_photos:
                    filename = orig_photo.get('filename')
                    if filename not in updated_by_filename:
                        logger.error(f"Photo {filename} missing from algorithm results")
                        continue
                    
                    updated_photo = updated_by_filename[filename]
                    area_left = updated_photo.get('area_left', 0)
                    owner = determine_page_owner_of_area(area_left, page_w, pageno0, pageno1)
                    
                    if owner == pageno0:
                        photos_page0.append(updated_photo)
                    else:
                        # Adjust coordinates to be page-relative
                        photo_copy = dict(updated_photo)
                        photo_copy['area_left'] = (area_left - page_w) + origin_left_1
                        photos_page1.append(photo_copy)
                
                # Validation: Check reconstruction produced correct counts
                if len(photos_page0) + len(photos_page1) != expected_photo_count:
                    error_msg = f"Photo reconstruction mismatch: input={expected_photo_count}, output page {pageno0}={len(photos_page0)} + page {pageno1}={len(photos_page1)}"
                    logger.error(error_msg)
                    def on_error():
                        self.gen_btn.config(state='normal')
                        self.show_status(error_msg, error=True)
                    self.root.after(0, on_error)
                    return
                
                # Reconstruct texts for both pages by iterating the combined original
                # text list in the same order that was given to the algorithm. This
                # ensures texts moved between pages by the algorithm are handled
                # (previous code iterated the two page lists separately which could
                # drop texts that moved from page0->page1).
                updated_texts_by_idx = {i: t for i, t in enumerate(updated_texts)}
                combined_original_texts = list(original_texts_by_page[pageno0]) + list(original_texts_by_page[pageno1])
                for text_idx, _orig_text in enumerate(combined_original_texts):
                    if text_idx in updated_texts_by_idx:
                        updated_text = updated_texts_by_idx[text_idx]
                        area_left = updated_text.get('area_left', 0)
                        owner = determine_page_owner_of_area(area_left, page_w, pageno0, pageno1)
                        if owner == pageno0:
                            texts_page0.append(updated_text)
                        else:
                            text_copy = dict(updated_text)
                            text_copy['area_left'] = (area_left - page_w) + origin_left_1
                            texts_page1.append(text_copy)
                
                # Validation: Check text reconstruction produced correct counts
                if len(texts_page0) + len(texts_page1) != expected_text_count:
                    error_msg = f"Text reconstruction mismatch: input={expected_text_count}, output page {pageno0}={len(texts_page0)} + page {pageno1}={len(texts_page1)}"
                    logger.error(error_msg)
                    def on_error():
                        self.gen_btn.config(state='normal')
                        self.show_status(error_msg, error=True)
                    self.root.after(0, on_error)
                    return
                
                # Push layouts and mark both pages modified
                def on_spread_done():
                    ui_update_start = time()
                    
                    self.gen_btn.config(state='normal')
                    self.show_status(f'Layout generated successfully using {algorithm.getName()} (spread)')
                    
                    self.layout_mgr.push_layout(page_numbers[0], photos_page0, texts_page0)
                    self.layout_mgr.push_layout(page_numbers[1], photos_page1, texts_page1)

                    # Unlike with a single page, optimising a spread means we can be moving
                    # photos between pages which changes what is "new" for each individual page.
                    self._rebuildNewPhotoTrackingForSpread(page_numbers, original_xml_photos_by_page, photos_page0, photos_page1)

                    # Analyze and report gap variations for both pages
                    for pn, photos_list, texts_list in [(page_numbers[0], photos_page0, texts_page0), 
                                                         (page_numbers[1], photos_page1, texts_page1)]:
                        if photos_list or texts_list:
                            page_info = next((p[1] for p in self.pages if p[0] == pn), None)
                            if page_info:
                                page_w = page_info.get('page_width')
                                page_h = page_info.get('page_height')
                                origin_left = page_info.get('origin_left', 0.0)
                                all_items = photos_list + texts_list
                                analysis = analyze_gap_details(all_items, page_w, page_h, origin_left, self.spread_mode.get())
                                report_gap_variations(analysis, pn)

                    # Mark page(s) as modified
                    self._mark_current_pages_modified()

                    self.render_page()
                    
                    total_ui_time = time() - ui_update_start
                    print(f"UI update: {total_ui_time:.3f}s")

                self.root.after(0, on_spread_done)
                
            else:
                # Single page mode - original logic
                pageno, info = self.pages[self.index]
                current_layout = self.layout_mgr.get_current(pageno)
                photos = current_layout.photos if current_layout else info.get('photos', [])

                # Filter out empty photo slots (photos with no filename)
                photos = [p for p in photos if p.get('filename')]

                page_w = info.get('page_width')
                page_h = info.get('page_height')
                
                # Get current gaps for this page from layout manager
                internal_gap = self.layout_mgr.get_internal_gap(pageno)
                edge_gap = self.layout_mgr.get_edge_gap(pageno)

                # Get texts for this page (from current layout, not original)
                texts = current_layout.texts if current_layout else info.get('texts', [])

                if not photos and not texts:
                    # re-enable on main thread
                    self.root.after(0, lambda: self.gen_btn.config(state='normal'))
                    self.show_status('Layout generation failed: No photos or texts on page')
                    return

                # Get slot aspect ratio info for all items.
                # Pass a list containing a single (pageno, info) tuple so the helper
                # which expects a list of page_infos works correctly.
                slot_aspect_ratios_for_page, use_slot_aspect_for_photos = _collect_slot_aspect_ratio_info([(pageno, info)])

                for photo_idx in range(len(photos)):
                    checkbox_key = (pageno, photo_idx)
                    if checkbox_key in self.use_slot_aspect:
                        use_slot_aspect_for_photos[photo_idx] = self.use_slot_aspect[checkbox_key].get()
                
                # Collect custom slot aspect ratios for all items on this page
                slot_aspect_ratios_for_page = {}
                num_items = len(photos) + len(texts)
                for item_idx in range(num_items):
                    ar_key = (pageno, item_idx)
                    if ar_key in self.slot_aspect_ratios:
                        slot_aspect_ratios_for_page[item_idx] = self.slot_aspect_ratios[ar_key]

                # Build preferred_sizes dict from layout manager
                preferred_sizes = {}
                for i, p in enumerate(photos):
                    fn = p.get('filename', '')
                    if fn:
                        base_fn, _, _ = extract_metadata_from_filename(fn)
                        preferred_sizes[fn] = self.layout_mgr.get_size(pageno, base_fn)
                for i, t in enumerate(texts):
                    text_id = f'TEXT_{i}'
                    preferred_sizes[text_id] = self.layout_mgr.get_size(pageno, text_id)
                
                # Determine if this is a left or right page
                origin_left = info.get('origin_left', 0.0)
                is_left_page = origin_left == 0.0
                
                # Log origin_left for diagnostics
                logger.info(f"Single-page mode: pageno={pageno}, origin_left={origin_left}, is_left_page={is_left_page}")
                
                # Write debug dump if debug mode is enabled
                if self.debug_var.get():
                    self._write_debug_dump(
                        pageno=pageno,
                        page_w=page_w,
                        page_h=page_h,
                        origin_left=origin_left,
                        is_left_page=is_left_page,
                        edge_gap=edge_gap,
                        internal_gap=internal_gap,
                        photos=photos,
                        texts=texts,
                        preferred_sizes=preferred_sizes,
                        algorithm_name=algorithm.getName(),
                        use_slot_aspect_for_photos=use_slot_aspect_for_photos,
                        slot_aspect_ratios=slot_aspect_ratios_for_page
                    )
                
                algo_start = time()
                # Check if this is a special page
                has_full_bleed = info.get('has_full_bleed', False)
                success, updated_photos, updated_texts, error_msg = generate_layout_for_page(
                    photos, page_w, page_h, self.photo_dimensions,
                    algorithm=algorithm, edge_gap=edge_gap, internal_gap=internal_gap, texts=texts,
                    preferred_sizes=preferred_sizes,
                    use_slot_aspect=use_slot_aspect_for_photos, 
                    slot_aspect_ratios=slot_aspect_ratios_for_page,
                    origin_left=info.get('origin_left', 0.0), pageno=pageno,
                    has_full_bleed=has_full_bleed
                )
                algo_time = time() - algo_start
                print(f"Algorithm: {algo_time:.3f}s")
                
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
                    ui_update_start = time()
                    
                    # re-enable button
                    self.gen_btn.config(state='normal')

                    if not success:
                        self.show_status(f'Layout generation failed: {error_msg}', error=True)
                        return
                    
                    self.show_status(f'Layout generated successfully using {algorithm.getName()}')

                    # Push new layout (both photos and texts) to manager and refresh view
                    self.layout_mgr.push_layout(pageno, updated_photos, updated_texts)
                    
                    # Analyze and report gap variations for this page
                    if updated_photos or updated_texts:
                        all_items = updated_photos + updated_texts
                        analysis = analyze_gap_details(all_items, page_w, page_h, info.get('origin_left', 0.0), self.spread_mode.get())
                        report_gap_variations(analysis, pageno)
                    
                    # Mark page(s) as modified
                    self._mark_current_pages_modified()
                    
                    self.render_page()
                    
                    total_ui_time = time() - ui_update_start
                    print(f"UI update: {total_ui_time:.3f}s")

                self.root.after(0, on_done)

        def _collect_slot_aspect_ratio_info(page_infos: list[Any]) -> tuple[dict[Any, Any], dict[Any, Any]]:
            # Collect checkbox states and slot aspect ratios (combine from both pages)
            use_slot_aspect_for_photos = {}
            slot_aspect_ratios_combined = {}
            photo_offset = 0
            text_offset = 0

            for page_idx, (pageno, _) in enumerate(page_infos):
                current_layout = self.layout_mgr.get_current(pageno)
                photos_for_page = current_layout.photos if current_layout else page_infos[page_idx][1].get('photos', [])
                texts_for_page = current_layout.texts if current_layout else page_infos[page_idx][1].get('texts', [])

                for local_photo_idx in range(len(photos_for_page)):
                    checkbox_key = (pageno, local_photo_idx)
                    if checkbox_key in self.use_slot_aspect:
                        use_slot_aspect_for_photos[photo_offset + local_photo_idx] = self.use_slot_aspect[
                            checkbox_key].get()

                num_items = len(photos_for_page) + len(texts_for_page)
                for local_item_idx in range(num_items):
                    ar_key = (pageno, local_item_idx)
                    if ar_key in self.slot_aspect_ratios:
                        slot_aspect_ratios_combined[photo_offset + text_offset + local_item_idx] = \
                        self.slot_aspect_ratios[ar_key]

                photo_offset += len(photos_for_page)
                text_offset += len(texts_for_page)
            return slot_aspect_ratios_combined, use_slot_aspect_for_photos

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

    def export_to_pdf(self):
        """Export current page to PDF with photos and white text boxes only."""
        try:
            from .pdf_export import export_layout_to_pdf
        except ImportError:
            self.status_var.set('Error: reportlab not installed. Run: pip install reportlab')
            return
        
        # Ask user for save location
        default_name = f'page_{self.current_spread_pages[0]}.pdf' if self.current_spread_pages else 'page.pdf'
        filepath = filedialog.asksaveasfilename(
            defaultextension='.pdf',
            filetypes=[('PDF files', '*.pdf'), ('All files', '*.*')],
            initialfile=default_name
        )
        
        if not filepath:
            return  # User cancelled
        
        # Get current page info
        if not self.pages or self.index >= len(self.pages):
            self.status_var.set('No page to export')
            return
        
        pageno, info = self.pages[self.index]
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])
        texts = current_layout.texts if current_layout else info.get('texts', [])
        
        # Get page dimensions
        page_w = info.get('page_width', 0)
        page_h = info.get('page_height', 0)
        origin_left = info.get('origin_left', 0.0)
        
        # Export using shared function
        export_layout_to_pdf(photos, texts, page_w, page_h, origin_left,
                            self.mcf_base_folder, self.image_folder_attr, filepath)
        
        self.status_var.set(f'PDF saved: {filepath}')
        logger.info(f'Exported page {pageno} to PDF: {filepath}')

    def save_layout(self):
        """Write all modified layouts to disk and manage photo files.
        
        This function:
        1. Saves ALL pages that have modifications (not just current page)
        2. Moves newly added photos to the album directory (if needed)
        3. Moves deleted photos to the parallel -photos directory
        4. Writes layout changes to the MCF file (with backup)
        5. Clears the in-memory layout history and modified pages tracking
        """
        if not self.pages or not self.mcf_file_path:
            self.show_status('Cannot save: no MCF file path', error=True)
            return
        
        if not self.modified_pages:
            self.show_status('No modified pages to save', error=False)
            return
        
        # Process all modified pages (sorted by page_sort_key to handle mixed types)
        pages_to_save = sorted(self.modified_pages, key=page_sort_key)
        total_saved = 0
        total_warnings = 0
        
        try:
            album_dir = Path(self.mcf_file_path).parent
            
            for pageno in pages_to_save:
                # Get current layout for this page
                current_layout = self.layout_mgr.get_current(pageno)
                if not current_layout:
                    continue
                
                photos = current_layout.photos
                texts = current_layout.texts
                
                # Filter out empty photo slots (deleted photos with no filename)
                photos = [p for p in photos if p.get('filename')]
                
                # Ensure all photos have image_width and image_height before saving
                for photo in photos:
                    filename = photo.get('filename', '')

                    # Skip if already has dimensions
                    if 'image_width' in photo and 'image_height' in photo:
                        continue
                    
                    # Get dimensions from file
                    if '_source_path' in photo:
                        # Staged photo - use source path
                        img_path = Path(photo['_source_path'])
                    else:
                        # Existing photo in album
                        safefn = filename.replace('safecontainer:/', '').lstrip('/')
                        if self.image_folder_attr:
                            img_path = album_dir / self.image_folder_attr / safefn
                        else:
                            img_path = album_dir / safefn
                    
                    if img_path.exists():
                        from .photos import get_image_dimensions
                        dims = get_image_dimensions(img_path)
                        if dims:
                            photo['image_width'], photo['image_height'] = dims
                        else:
                            self.show_status(f'Page {pageno}: Could not read dimensions for {filename}', error=True)
                            return
                    else:
                        self.show_status(f'Page {pageno}: Photo file not found: {img_path}', error=True)
                        return
                
                # Get tracking info for new and deleted photos (need this first)
                new_photos = self.layout_mgr.get_new_photos(pageno)
                deleted_photos = self.layout_mgr.get_deleted_photos(pageno)
                
                logger.info(f"Save: Page {pageno} - new_photos={sorted(new_photos)}, deleted_photos={sorted(deleted_photos)}")
                
                # Rename photos to include preferred size and page number in filename
                # Skip newly added photos that haven't been moved yet
                rename_map = {}  # old_filename -> new_filename (for XML update)
                renamed_new_photos = {}  # old_filename -> new_filename for photos in new_photos
                for photo in photos:
                    old_filename = photo.get('filename', '')

                    # Get base filename (without any -sz or -pg suffixes)
                    base_filename, _, _ = extract_metadata_from_filename(old_filename)
                    
                    # Get preferred size for this photo
                    preferred_size = self.layout_mgr.get_size(pageno, base_filename)
                    
                    # Generate new filename with size and page number encoded
                    new_filename = encode_metadata_in_filename(old_filename, preferred_size, pageno)
                    
                    # Track if this photo was marked as new and is being renamed
                    if old_filename in new_photos and new_filename != old_filename:
                        renamed_new_photos[old_filename] = new_filename
                    
                    # Skip newly added photos that haven't been moved yet - they'll be moved with metadata already encoded
                    if old_filename in new_photos and '_source_path' in photo:
                        continue
                    
                    # Populate rename_map to handle XML filename matching
                    # Map old_filename (which may or may not have -sz-pg) to new_filename
                    # This handles the case where XML has the full safecontainer:/ path
                    if old_filename != new_filename:
                        rename_map[old_filename] = new_filename
                    
                    # Also map base filename (for backward compatibility and XML that might have base names)
                    # Reconstruct base filename WITH safecontainer prefix if present
                    if old_filename.startswith('safecontainer:/'):
                        base_with_prefix = f'safecontainer:/{base_filename}'
                        if base_with_prefix != new_filename:
                            rename_map[base_with_prefix] = new_filename
                    else:
                        if base_filename != new_filename:
                            rename_map[base_filename] = new_filename
                    
                    # Only rename file if filename changed
                    if new_filename != old_filename:
                        # Get actual file paths
                        old_safefn = old_filename.replace('safecontainer:/', '').lstrip('/')
                        new_safefn = new_filename.replace('safecontainer:/', '').lstrip('/')
                        
                        if self.image_folder_attr:
                            old_path = album_dir / self.image_folder_attr / old_safefn
                            new_path = album_dir / self.image_folder_attr / new_safefn
                        else:
                            old_path = album_dir / old_safefn
                            new_path = album_dir / new_safefn
                        
                        # Rename the actual file
                        if old_path.exists():
                            try:
                                old_path.rename(new_path)
                                # Update photo dict with new filename
                                photo['filename'] = new_filename
                                # rename_map already updated above with new_filename
                                # Note: layout_mgr uses base filename (without -sz-pg) so no update needed
                            except Exception as e:
                                self.show_status(f'Page {pageno}: Failed to rename {old_safefn} to {new_safefn}: {e}', error=True)
                                return
                        else:
                            import logging
                            logging.getLogger(__name__).warning(f"Page {pageno}: Cannot rename '{old_safefn}' - file not found at {old_path}")
                
                # Move staged photos from source to album root
                # Encode preferred size and page number into filename before moving
                moved_photos = []
                new_photos_final = set(new_photos)  # Start with tracked new photos
                
                # Update new_photos_final to reflect any renamed photos
                for old_fn, new_fn in renamed_new_photos.items():
                    new_photos_final.discard(old_fn)
                    new_photos_final.add(new_fn)
                
                for photo in photos:
                    if '_source_path' in photo and photo.get('filename') in new_photos:
                        src_path = Path(photo['_source_path'])
                        if not src_path.exists():
                            self.show_status(f'Page {pageno}: Source photo not found: {src_path}', error=True)
                            return
                        
                        # Get preferred size and encode into filename with page number
                        old_filename = photo['filename']
                        base_filename, _, _ = extract_metadata_from_filename(old_filename)
                        preferred_size = self.layout_mgr.get_size(pageno, base_filename)
                        new_filename = encode_metadata_in_filename(old_filename, preferred_size, pageno)
                        
                        # Update photo dict with encoded filename
                        photo['filename'] = new_filename
                        
                        # Update tracking: remove old filename, add new filename
                        new_photos_final.discard(old_filename)
                        new_photos_final.add(new_filename)
                        
                        # Destination is album root (not images/ folder)
                        safefn = new_filename.replace('safecontainer:/', '').lstrip('/')
                        dst_path = album_dir / safefn
                        
                        # Move file (not copy!)
                        try:
                            shutil.move(str(src_path), str(dst_path))
                            moved_photos.append(new_filename)
                            # Remove _source_path marker now that file is moved
                            del photo['_source_path']
                        except Exception as e:
                            self.show_status(f'Page {pageno}: Failed to move {src_path.name}: {e}', error=True)
                            return
                
                # Handle deleted photos: move to parallel -photos directory
                if deleted_photos:
                    album_name = album_dir.name
                    # Remove .xmcf or .mcf extension if present
                    if album_name.endswith('.xmcf') or album_name.endswith('.mcf'):
                        album_base = album_name.rsplit('.', 1)[0]
                    else:
                        album_base = album_name
                    photos_dir = album_dir.parent / f"{album_base}-photos"
                    photos_dir.mkdir(exist_ok=True)
                    
                    for filename in deleted_photos:
                        safefn = filename.replace('safecontainer:/', '').lstrip('/')
                        if self.image_folder_attr:
                            src_path = album_dir / self.image_folder_attr / safefn
                        else:
                            src_path = album_dir / safefn
                        
                        if src_path.exists():
                            dst_path = photos_dir / src_path.name
                            # Handle name conflicts
                            counter = 1
                            while dst_path.exists():
                                stem = src_path.stem
                                suffix = src_path.suffix
                                dst_path = photos_dir / f"{stem}_{counter}{suffix}"
                                counter += 1
                            shutil.move(str(src_path), str(dst_path))
                
                # Write to MCF file (makes backup automatically on first save)
                result = update_page_layout(
                    self.mcf_file_path, pageno, photos, texts, 
                    make_backup=(total_saved == 0),  # Only backup MCF when saving first new page
                    new_photos=list(new_photos_final), deleted_photos=list(deleted_photos),
                    rename_map=rename_map
                )
                
                # Update the original layout to match what we just saved
                self.layout_mgr.set_original(pageno, photos, texts)
                
                # Clear in-memory history (undo stack) and tracking for this page
                self.layout_mgr.clear_layouts(pageno)
                self.layout_mgr.clear_photo_tracking(pageno)
                
                # Push the saved layout as the current layout
                self.layout_mgr.push_layout(pageno, photos, texts)
                
                # Accumulate warnings
                warnings = result.get('warnings', [])
                if warnings:
                    print(f"\n[SAVE WARNINGS for page {pageno}]")
                    for warning in warnings:
                        print(f"  {warning}")
                    total_warnings += len(warnings)
                
                total_saved += 1
            
            # Clear modified pages tracking
            self.modified_pages.clear()
            self._update_modified_pages_display()
            
            # Update status with summary
            status_msg = f"Saved {total_saved} page(s)"
            if total_warnings > 0:
                status_msg += f" ({total_warnings} warnings - see console)"
            self.show_status(status_msg)
            
            # Re-render current page to reflect saved state
            self.render_page()
            
        except Exception as e:
            self.show_status(f'Save failed: {e}', error=True)
            import traceback
            traceback.print_exc()

    def equal_sizes(self):
        """Set all preferred sizes to 1.0 (baseline size like EXIF defaults)."""
        if not self.pages:
            return
        pageno, info = self.pages[self.index]
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])
        texts = current_layout.texts if current_layout else info.get('texts', [])
        
        # Set size to 1.0 for all photos (baseline like EXIF 1-star = 1.0)
        for p in photos:
            fn = p.get('filename', '')
            if fn:
                base_fn, _, _ = extract_metadata_from_filename(fn)
                self.layout_mgr.set_size(pageno, base_fn, 1.0)
        
        for i, t in enumerate(texts):
            text_id = f'TEXT_{i}'
            self.layout_mgr.set_size(pageno, text_id, 1.0)
        
        self.update_weights_display()
    
    def stored_sizes(self):
        """Restore preferred sizes from original layout areas."""
        if not self.pages:
            return
        pageno, info = self.pages[self.index]
        page_w = info.get('page_width')
        page_h = info.get('page_height')
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

    def _search_photo_improvements(self):
        """Search for higher-quality versions of photos on current page."""
        if not self.pages:
            self.show_status('No pages available', error=True)
            return
        
        pageno, info = self.pages[self.index]
        
        # Check if this is a protected inside cover page
        if pageno in self.protected_inside_covers:
            self.show_status('Inside cover pages have no photos to improve', error=True)
            return
        
        # Get current photos
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos
        photos = [p for p in photos if p.get('filename')]  # Filter empty slots
        
        if not photos:
            self.show_status('No photos on current page', error=True)
            return
        
        # Filter out already-improved photos (those with -up in filename)
        photos_to_search = []
        skipped_indices = []
        for i, photo in enumerate(photos):
            filename = photo.get('filename', '')
            filename_lower = filename.lower()
            # Check for -up- anywhere in filename or -up at end before extension
            is_improved = '-up-' in filename_lower or any(
                filename_lower.endswith(f'-up.{ext}') 
                for ext in ['jpg', 'jpeg', 'png', 'heif', 'heic']
            )
            if is_improved:
                skipped_indices.append(i + 1)  # 1-based for user display
            else:
                photos_to_search.append(photo)
        
        if not photos_to_search:
            self.show_status('All photos already improved', error=False)
            return
        
        # Build status message
        if skipped_indices:
            skipped_str = ', '.join(str(i) for i in skipped_indices)
            status_msg = f'Searching for improvements: {len(photos_to_search)} photos ({len(skipped_indices)} skipped: {skipped_str})'
        else:
            status_msg = f'Searching for improvements for {len(photos_to_search)} photos...'
        self.show_status(status_msg)
        
        # Call photoimprover interface
        from .photoimprover import search_and_show_improvements
        
        def on_photo_replaced(old_filename: str, new_filename: str):
            """Handle photo replacement in layout."""
            # Use layout manager helper to replace the photo with proper tracking
            success = self.layout_mgr.replace_photo_by_filename(pageno, old_filename, new_filename)
            
            if not success:
                logger.error(f"Failed to replace photo {old_filename} with {new_filename}")
                self.show_status(f'Error: Could not replace photo', error=True)
                return
            
            logger.info(f"Replaced photo in layout: {old_filename} -> {new_filename}")
            
            # Track improvement
            self.improved_photos[old_filename] = new_filename
            
            # Mark page as modified
            self.modified_pages.add(pageno)
            self._update_modified_pages_display()
            
            # Re-render to show new photo
            self.render_page()
            self.show_status(f'Replaced photo with improved version')
        
        search_and_show_improvements(
            self.root,
            self.mcf_file_path,
            photos_to_search,
            on_photo_replaced,
            scope='page'
        )

    def _rebuildNewPhotoTrackingForSpread(self, page_numbers, original_xml_photos_by_page, photos_page0, photos_page1):
        # Rebuild new photo tracking for both pages after algorithm split
        # A photo is "new" to a page if it wasn't on that page in the original XML
        # This includes both genuinely new photos AND photos that moved from the other page

        # Clear existing tracking
        self.layout_mgr.clear_new_photos(page_numbers[0])
        self.layout_mgr.clear_new_photos(page_numbers[1])

        # Get original XML photos for each page (what was in XML before any algorithms)
        original_page0_photos = original_xml_photos_by_page.get(page_numbers[0], set())
        original_page1_photos = original_xml_photos_by_page.get(page_numbers[1], set())

        logger.info(f"Rebuilding new photo tracking:")
        logger.info(f"  Page {page_numbers[0]} original XML photos: {sorted(original_page0_photos)}")
        logger.info(f"  Page {page_numbers[1]} original XML photos: {sorted(original_page1_photos)}")
        logger.info(f"  Page {page_numbers[0]} current photos: {[p.get('filename') for p in photos_page0]}")
        logger.info(f"  Page {page_numbers[1]} current photos: {[p.get('filename') for p in photos_page1]}")

        for photo in photos_page0:
            filename = photo.get('filename', '')
            if filename and filename not in original_page0_photos:
                # Photo is new to page 0 (either genuinely new or moved from page 1)
                logger.info(f"  Marking {filename} as new to page {page_numbers[0]}")
                self.layout_mgr.mark_photo_as_new(page_numbers[0], filename)

        for photo in photos_page1:
            filename = photo.get('filename', '')
            if filename and filename not in original_page1_photos:
                # Photo is new to page 1 (either genuinely new or moved from page 0)
                logger.info(f"  Marking {filename} as new to page {page_numbers[1]}")
                self.layout_mgr.mark_photo_as_new(page_numbers[1], filename)


def launch_gui(mcf_path, pdf_content, insidecovers=False):
    # Configure logging for the GUI
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    
    root_el = parse_mcf_from_path(mcf_path)
    
    # Try to use TkinterDnD.Tk for drag-and-drop support
    try:
        from tkinterdnd2 import TkinterDnD
        root = TkinterDnD.Tk()
    except ImportError:
        # Fall back to regular Tk
        root = tk.Tk()
    
    app = LayoutViewer(root, root_el, mcf_path, pdf_content=pdf_content, insidecovers=insidecovers)
    root.mainloop()
