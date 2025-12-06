"""Simple Tkinter UI to browse pages and display layout rectangles."""
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk
import math
import os
from pathlib import Path
import threading
import shutil
import logging

logger = logging.getLogger(__name__)

from .parser import extract_pages_info, parse_mcf_from_path
from .layout_ops import LayoutManager
from .collage_wrapper import generate_layout_for_page
from .algorithms.evaluator import evaluate_layout
from .algorithms.collage_generator import CollageGeneratorAlgorithm
from .algorithms.fan_layout import FanLayoutAlgorithm
from .algorithms.tree_builder import TreeBuilderAlgorithm
from .algorithms.gridify import GridifyAlgorithm
from .photos import get_image_dimensions, load_thumbnail, get_photo_preferred_size
from .writer import update_page_layout
from .gap_utils import (
    analyze_gaps,
    analyze_gap_details,
    transform_page_to_gapfree,
    transform_item_to_gapfree,
    transform_item_from_gapfree,
    transform_item_for_gap_change
)


# Constants for MCF unit conversion and defaults
MM_TO_MCF = 10.0  # 1mm = 10 MCF units
MCF_TO_MM = 0.1   # 1 MCF unit = 0.1mm
DEFAULT_EDGE_GAP = 140.0  # 14mm in MCF units
DEFAULT_INTERNAL_GAP = 90.0  # 9mm in MCF units


# Helper functions for common patterns

def _split_safecontainer_prefix(filename):
    """Split filename into (prefix, clean_name) tuple.
    
    Args:
        filename: Filename that may have safecontainer:/ prefix
        
    Returns:
        Tuple of (prefix, clean_name) where prefix is 'safecontainer:/' or ''
    """
    if not filename or not filename.startswith('safecontainer:/'):
        return '', filename
    return 'safecontainer:/', filename[len('safecontainer:/'):].lstrip('/')


def _safe_parse_number(value_str, field_name, filename):
    """Parse number with consistent error handling.
    
    Args:
        value_str: String to parse as number
        field_name: Name of field being parsed (for error messages)
        filename: Filename being processed (for error messages)
        
    Returns:
        Parsed float/int or None if parsing fails
    """
    try:
        # Parse as float if it has decimal point, otherwise int
        return float(value_str) if '.' in value_str else int(value_str)
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse {field_name} from '{filename}': {e}")
        return None


def extract_metadata_from_filename(filename: str) -> tuple:
    """
    Extract both size and page number from filename.
    
    Args:
        filename: Filename like 'photo-sz2.5-pg10.jpg' or 'safecontainer:/photo-sz1.0-pg5.png'
    
    Returns:
        Tuple of (base_filename, preferred_size_or_None, page_number_or_None)
        For 'photo-sz2.5-pg10.jpg' returns ('photo.jpg', 2.5, 10)
        For 'photo-sz2.5.png' returns ('photo.png', 2.5, None)
        For 'photo-pg10.jpg' returns ('photo.jpg', None, 10)
        For 'photo.jpg' returns ('photo.jpg', None, None)
    """
    # Handle None or empty filename
    if not filename:
        return filename, None, None
    
    # Handle safecontainer prefix using helper
    prefix, clean_name = _split_safecontainer_prefix(filename)
    
    import re
    
    # Split into name and extension first
    p = Path(clean_name)
    extension = p.suffix
    name_part = p.stem
    
    # Extract size and page in any order
    size = None
    page_num = None
    
    # Look for -szN.NN pattern
    size_match = re.search(r'-sz([0-9]+(?:[.][0-9]{1,2})?)', name_part)
    if size_match:
        size = _safe_parse_number(size_match.group(1), 'size', filename)
    
    # Look for -pgN pattern
    page_match = re.search(r'-pg([0-9]+)', name_part)
    if page_match:
        page_num = _safe_parse_number(page_match.group(1), 'page number', filename)
    
    # Remove both patterns to get base name
    base_name = name_part
    if size_match:
        base_name = base_name.replace(size_match.group(0), '')
    if page_match:
        base_name = base_name.replace(page_match.group(0), '')
    
    base_filename = base_name + extension
    return prefix + base_filename, size, page_num


def encode_metadata_in_filename(filename: str, preferred_size: float = None, page_number: int = None) -> str:
    """
    Encode both preferred size and page number into filename.
    
    Args:
        filename: Original filename (may already have -sz or -pg suffixes)
        preferred_size: Size value to encode (e.g., 3.45), or None to preserve existing
        page_number: Page number to encode (e.g., 10), or None to preserve existing
    
    Returns:
        Filename with metadata encoded like 'photo-sz3.45-pg10.jpg' or 'photo-sz2.0.png'
        Order is always: basename + -sz + -pg + extension
    """
    # Handle None or empty filename
    if not filename:
        return filename
    
    # Handle safecontainer prefix using helper
    prefix, clean_name = _split_safecontainer_prefix(filename)
    
    # Extract existing metadata
    base_name, existing_size, existing_page = extract_metadata_from_filename(clean_name)
    
    # Remove prefix from base_name if it got added
    if base_name.startswith('safecontainer:/'):
        base_name = base_name[len('safecontainer:/'):]
    
    # Use provided values or fall back to existing
    final_size = preferred_size if preferred_size is not None else existing_size
    final_page = page_number if page_number is not None else existing_page
    
    # Split into name and extension
    p = Path(base_name)
    stem = p.stem
    suffix = p.suffix
    
    # Build new filename: always use order -sz then -pg
    new_name = stem
    
    if final_size is not None:
        size_str = f"{final_size:.2f}".rstrip('0').rstrip('.')
        new_name += f"-sz{size_str}"
    
    if final_page is not None:
        new_name += f"-pg{final_page}"
    
    new_name += suffix
    
    return prefix + new_name


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
        
        # Spread mode flag - when True, show two pages (even+odd) as a spread
        self.spread_mode = tk.BooleanVar(value=False)
        
        # Track current spread pages (list of 1 or 2 page numbers)
        self.current_spread_pages = []
        
        # Track which photos should use slot aspect ratio (dict: {(pageno, photo_idx): BooleanVar})
        self.use_slot_aspect = {}
        
        # Track slot aspect ratios for each item (dict: {(pageno, item_idx): aspect_ratio})
        # This allows users to override the slot aspect ratio
        self.slot_aspect_ratios = {}
        
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
            edge_gap, inter_gap = analyze_gaps(all_items, page_w, page_h, origin_left) if all_items else (0.0, 0.0)
            gap = inter_gap if inter_gap > 0 else edge_gap
            
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
                        # Fallback: use gap-free area normalized to 10× scale
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
        
        # Enable drag-and-drop for photo files
        self._setup_drag_and_drop()
        
        # Bind window resize event to redraw
        self.root.bind('<Configure>', self._on_window_resize)
        self._resize_pending = False

        # Controls window
        self.ctrl = tk.Toplevel(self.root)
        self.ctrl.title('QLayout Controls')
        self.ctrl.geometry('+50+50')

        # Row 0: Navigation - organize in two frames for tight grouping
        nav_frame = ttk.Frame(self.ctrl)
        nav_frame.grid(row=0, column=0, sticky='w', padx=4, pady=4)
        self.page_num_var = tk.StringVar(value='Page:')
        ttk.Label(nav_frame, textvariable=self.page_num_var, font=('TkDefaultFont', 9)).pack(side='left', padx=(0,4))
        prev_btn = ttk.Button(nav_frame, text='Prev (←)', command=self.prev_page)
        prev_btn.pack(side='left')
        next_btn = ttk.Button(nav_frame, text='Next (→)', command=self.next_page)
        next_btn.pack(side='left')
        
        goto_frame = ttk.Frame(self.ctrl)
        goto_frame.grid(row=0, column=1, sticky='w', padx=4, pady=4)
        ttk.Label(goto_frame, text='Go to:').pack(side='left', pady=2)
        self.goto_var = tk.StringVar()
        goto_entry = ttk.Entry(goto_frame, textvariable=self.goto_var, width=6)
        goto_entry.pack(side='left', padx=2, pady=2)
        goto_btn = ttk.Button(goto_frame, text='Go', command=self.goto_page)
        goto_btn.pack(side='left', pady=2)
        
        # Page range label (e.g., "Pages 2-58")
        self.page_range_var = tk.StringVar(value='')
        self.page_range_label = ttk.Label(goto_frame, textvariable=self.page_range_var, foreground='gray')
        self.page_range_label.pack(side='left', padx=(8,0))
        
        # Spread mode checkbox
        spread_check = ttk.Checkbutton(goto_frame, text='Spread', variable=self.spread_mode, command=self._on_spread_mode_change)
        spread_check.pack(side='left', padx=(8,0))
        
        # Row 1: Algorithm selection and Generate button - pack in single frame
        algo_frame = ttk.Frame(self.ctrl)
        algo_frame.grid(row=1, column=0, columnspan=2, sticky='w', padx=4, pady=4)
        ttk.Label(algo_frame, text='Algorithm:').pack(side='left', padx=(0,4))
        algo_menu = ttk.OptionMenu(
            algo_frame, self.algorithm_var,
            'Fan-GA',  # default
            'Collage-Gen', 'Fan-GA', 'Gridify', 'Tree-Builder'
        )
        algo_menu.pack(side='left', padx=(0,4))
        
        # Generate button (uses selected algorithm)
        self.gen_btn = ttk.Button(algo_frame, text='Generate Layout', command=self.generate_layout)
        self.gen_btn.pack(side='left', padx=(0,4))
        
        # Debug checkbox next to Generate button
        debug_check = ttk.Checkbutton(algo_frame, text='Debug', variable=self.debug_var)
        debug_check.pack(side='left')
        
        # Row 2: Modified pages label (pack label and value tightly)
        modified_frame = ttk.Frame(self.ctrl)
        modified_frame.grid(row=2, column=0, columnspan=3, sticky='w', padx=4, pady=(5,0))
        ttk.Label(modified_frame, text='Modified pages:').pack(side='left')
        self.modified_pages_var = tk.StringVar(value='(none)')
        self.modified_pages_label = ttk.Label(modified_frame, textvariable=self.modified_pages_var, 
                                              font=('TkDefaultFont', 9), foreground='blue')
        self.modified_pages_label.pack(side='left', padx=(2,0))
        
        # Row 3: Action buttons (indented)
        actions_frame = ttk.Frame(self.ctrl)
        actions_frame.grid(row=3, column=0, columnspan=3, sticky='w', padx=4, pady=4)
        ttk.Label(actions_frame, text='  ').pack(side='left')  # Indentation spacer
        undo_btn = ttk.Button(actions_frame, text='Undo', command=self.undo_layout)
        undo_btn.pack(side='left', padx=(0,4))
        save_btn = ttk.Button(actions_frame, text='Save Modified', command=self.save_layout)
        save_btn.pack(side='left', padx=(0,4))
        orig_btn = ttk.Button(actions_frame, text='Use Original Page', command=self.use_original)
        orig_btn.pack(side='left')

        # Row 4: Status message with label
        status_frame = ttk.Frame(self.ctrl)
        status_frame.grid(row=4, column=0, columnspan=3, padx=4, pady=4, sticky='ew')
        ttk.Label(status_frame, text='Status:').pack(side='left', padx=(0,4))
        self.status_var = tk.StringVar(value='')
        self.status_entry = ttk.Entry(status_frame, textvariable=self.status_var, 
                                      state='readonly', font=('TkDefaultFont', 9))
        self.status_entry.pack(side='left', fill='x', expand=True)
        # Store the style for color changes
        self.status_style = ttk.Style()
        
        # Weights and cost display frame with label inside
        self.info_frame = ttk.Frame(self.ctrl, padding=8, relief='sunken', borderwidth=1)
        self.info_frame.grid(row=5, column=0, columnspan=5, padx=4, pady=8, sticky='ew')
        
        # Layout Info label inside the frame
        ttk.Label(self.info_frame, text='Layout Info:').grid(row=0, column=0, columnspan=2, sticky='w', padx=0, pady=(0,4))
        
        # Configure columns: left column (0) for photos, right column (1) for cost/params
        self.info_frame.columnconfigure(0, weight=1)
        self.info_frame.columnconfigure(1, weight=0)
        
        # LEFT COLUMN: Photo weights
        photo_frame = ttk.Frame(self.info_frame)
        photo_frame.grid(row=1, column=0, sticky='nw', padx=(0, 20))
        
        ttk.Label(photo_frame, text='Item', font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=0, padx=2, pady=(2,0))
        
        # Aspect Ratio parent header spanning all 3 sub-columns
        # Center it properly over the 3 columns by using a label with sticky='ew' in a grid
        ttk.Label(photo_frame, text='Aspect Ratio', font=('TkDefaultFont', 9, 'bold'), anchor='center').grid(row=0, column=1, columnspan=3, pady=(2,0), sticky='ew')
        
        # Sub-headers in row 1, directly above their respective data columns
        ttk.Label(photo_frame, text='Slot', font=('TkDefaultFont', 8)).grid(row=1, column=1, padx=2, pady=(0,2))
        ttk.Label(photo_frame, text='Use\nslot', font=('TkDefaultFont', 8), justify='center').grid(row=1, column=2, padx=2, pady=(0,2))
        ttk.Label(photo_frame, text='Photo', font=('TkDefaultFont', 8)).grid(row=1, column=3, padx=2, pady=(0,2))
        
        # Preferred header with Equal/Original buttons in row 1, centered over column 4
        pref_header = ttk.Label(photo_frame, text='Preferred', font=('TkDefaultFont', 9, 'bold'))
        pref_header.grid(row=0, column=4, padx=2, pady=(2,0))
        # Center the label within its cell
        photo_frame.columnconfigure(4, weight=0)
        btn_frame = ttk.Frame(photo_frame)
        btn_frame.grid(row=1, column=4, padx=2, pady=(0,2), sticky='w')
        # Use tk.Button with transparent pixel for precise compact sizing
        tk.Button(btn_frame, text='Equal', command=self.equal_sizes, 
                  font=('TkDefaultFont', 7), width=30, height=12,
                  image=self.button_pixel, compound='center',
                  padx=0, pady=0, bd=1, highlightthickness=0).pack(side='left', padx=0)
        tk.Button(btn_frame, text='Original', command=self.stored_sizes, 
                  font=('TkDefaultFont', 7), width=38, height=12,
                  image=self.button_pixel, compound='center',
                  padx=0, pady=0, bd=1, highlightthickness=0).pack(side='left', padx=0)
        
        # Actual header
        ttk.Label(photo_frame, text='Actual', font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=5, padx=2, pady=(2,0), sticky='w')
        
        # Item (photo/text) weight rows will be added dynamically to photo_frame
        self.photo_frame = photo_frame
        
        # Add text box button (will be positioned below weight rows)
        self.add_text_btn = ttk.Button(photo_frame, text='Add text box', command=self.add_text_box)
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
        self.delete_buttons = []  # List of delete button widgets
        self.size_importance = 100.0  # Default size importance factor
        self.undersized_threshold = 0.5  # Default undersized threshold (50%)
        self.undersized_penalty = 5.0  # Default undersized penalty factor
        self.modified_pages = set()  # Track pages with unsaved changes
        
        # Find the last page with actual photos (non-empty filenames)
        last_page_with_photos = 0
        for idx, (pageno, info) in enumerate(self.pages):
            photos = info.get('photos', [])
            # Check if page has any photos with actual filenames (not empty slots)
            has_photos = any(p.get('filename') for p in photos)
            if has_photos:
                last_page_with_photos = idx
        
        # Start at the last page with photos (skip page 0)
        self.index = max(1, last_page_with_photos)
        
        self.render_page()

    def render_page(self):
        # Clear status message when changing pages
        self.status_var.set('')
        
        # Determine pages to render based on spread mode
        in_spread_mode = self.spread_mode.get()
        
        if not self.pages:
            # Update page number display
            self.page_num_var.set('Page:')
            
            # Get current canvas dimensions
            self.root.update_idletasks()
            canvas_w = self.img_label.winfo_width()
            canvas_h = self.img_label.winfo_height()
            if canvas_w <= 1 or canvas_h <= 1:
                canvas_w = self.root.winfo_width()
                canvas_h = self.root.winfo_height()
            if canvas_w < 100:
                canvas_w = 800
            if canvas_h < 100:
                canvas_h = int(800 / self.canvas_aspect_ratio)
            
            img = Image.new('RGB', (canvas_w, canvas_h), 'white')
            draw = ImageDraw.Draw(img)
            draw.text((10,10), 'No pages found', fill='black')
            self._show_image(img)
            self._update_page_range_display()
            self.current_spread_pages = []
            return
        
        # Determine which pages to render
        if in_spread_mode:
            # Spread mode: ensure even page on left, odd page on right
            current_pageno = self.pages[self.index][0]
            
            if current_pageno % 2 == 0:
                # Current page is even - it goes on left, find next odd page for right
                left_idx = self.index
                # Find next page (should be odd if pages are consecutive)
                if self.index < len(self.pages) - 1:
                    right_idx = self.index + 1
                    page_indices = [left_idx, right_idx]
                    self.current_spread_pages = [self.pages[left_idx][0], self.pages[right_idx][0]]
                else:
                    # Even page is last page - show it alone
                    page_indices = [left_idx]
                    self.current_spread_pages = [self.pages[left_idx][0]]
            else:
                # Current page is odd - find previous even page for left
                if self.index > 0:
                    left_idx = self.index - 1
                    right_idx = self.index
                    page_indices = [left_idx, right_idx]
                    self.current_spread_pages = [self.pages[left_idx][0], self.pages[right_idx][0]]
                else:
                    # Odd page is first page - show it alone
                    page_indices = [self.index]
                    self.current_spread_pages = [self.pages[self.index][0]]
        else:
            # Single page mode
            page_indices = [self.index]
            self.current_spread_pages = [self.pages[self.index][0]]
        
        # Update page number display
        if len(self.current_spread_pages) == 2:
            self.page_num_var.set(f'Pages {self.current_spread_pages[0]}-{self.current_spread_pages[1]}:')
        else:
            self.page_num_var.set(f'Page {self.current_spread_pages[0]}:')
        
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
        
        # Collect all photos/texts for title and determine background color
        all_photos = []
        all_texts = []
        background_id = None
        page_w = 2100.0
        page_h = 2970.0
        
        for page_idx in page_indices:
            pageno_i, info_i = self.pages[page_idx]
            current_layout_i = self.layout_mgr.get_current(pageno_i)
            photos_i = current_layout_i.photos if current_layout_i else info_i.get('photos', [])
            texts_i = current_layout_i.texts if current_layout_i else info_i.get('texts', [])
            all_photos.extend(photos_i)
            all_texts.extend(texts_i)
            
            # Use first page's dimensions and background
            if page_idx == page_indices[0]:
                page_w = info_i.get('page_width', 2100.0)
                page_h = info_i.get('page_height', 2970.0)
                background_id = info_i.get('background_id')
        
        # Update window title with photobook name and page info
        text_label = 'text' if len(all_texts) == 1 else 'texts'
        if len(self.current_spread_pages) == 2:
            if all_texts:
                title = f'{self.photobook_name} - Pages {self.current_spread_pages[0]}-{self.current_spread_pages[1]} : {len(all_photos)} photos, {len(all_texts)} {text_label}'
            else:
                title = f'{self.photobook_name} - Pages {self.current_spread_pages[0]}-{self.current_spread_pages[1]} : {len(all_photos)} photos'
        else:
            if all_texts:
                title = f'{self.photobook_name} - Page {self.current_spread_pages[0]} : {len(all_photos)} photos, {len(all_texts)} {text_label}'
            else:
                title = f'{self.photobook_name} - Page {self.current_spread_pages[0]} : {len(all_photos)} photos'
        self.root.title(title)
        
        # Determine page background color from designElementId
        if background_id == '212':
            page_bg_color = 'black'
            frame_color = 'white'  # White frame for black background
        else:  # '201' or None or any other value defaults to white
            page_bg_color = 'white'
            frame_color = 'black'  # Black frame for white background
        
        img = Image.new('RGB', (canvas_w, canvas_h), page_bg_color)
        draw = ImageDraw.Draw(img)
        
        # 5mm margin on all sides (50 MCF units)
        margin_mcf = self.margin_mcf
        
        # Calculate scale to fit page(s) + margins in canvas
        if len(page_indices) == 2:
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
        for page_offset, page_idx in enumerate(page_indices):
            pageno, info = self.pages[page_idx]
            current_layout = self.layout_mgr.get_current(pageno)
            photos = current_layout.photos if current_layout else info.get('photos', [])
            texts = current_layout.texts if current_layout else info.get('texts', [])
            origin_left = info.get('origin_left', 0.0)
            
            # Calculate frame position for this page
            # In spread mode, second page is offset by page_w
            page_x_offset = page_offset * page_w if len(page_indices) == 2 else 0
            frame_x = margin_mcf * scale + page_x_offset * scale
            frame_y = margin_mcf * scale
            frame_w = page_w * scale
            frame_h = page_h * scale
            
            # Render photos for this page
            self._render_photos(img, draw, photos, frame_x, frame_y, scale, origin_left, 
                               photo_counter, pageno, delete_button_info, page_bg_color)
            photo_counter += len(photos)
            
            # Render texts for this page
            self._render_texts(draw, texts, frame_x, frame_y, scale, origin_left,
                              text_counter, pageno, delete_button_info)
            text_counter += len(texts)
            
            # Draw page frame for this page
            self._draw_page_frame(draw, frame_x, frame_y, frame_w, frame_h, frame_color)
        
        # In spread mode, draw dotted line down the crease (center)
        if len(page_indices) == 2:
            crease_x = margin_mcf * scale + page_w * scale
            self._draw_crease_line(draw, crease_x, frame_y, frame_h, frame_color)
        
        self._show_image(img)
        
        # Update page range display
        self._update_page_range_display()
        
        # Create delete buttons AFTER image is shown so they overlay on top
        self._create_delete_buttons(delete_button_info)
        
        self.update_weights_display()
    
    def _render_photos(self, img, draw, photos, frame_x, frame_y, scale, origin_left, 
                      start_number, pageno, delete_button_info, page_bg_color):
        """Render photos for a single page.
        
        Args:
            img: PIL Image object
            draw: PIL ImageDraw object
            photos: List of photo dicts
            frame_x, frame_y: Frame position in pixels
            scale: MCF to pixel scale factor
            origin_left: Origin left for right-page adjustment
            start_number: Starting number for photo labels
            pageno: Page number for logging
            delete_button_info: List to append delete button info to
            page_bg_color: Background color for placeholders
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
                    # Staged photo - use source path for thumbnail
                    img_path = p['_source_path']
                else:
                    # Existing photo in album - resolve from album directory
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
                    
                    # Log if photo file was not found
                    if img_path is None:
                        logger.warning(f"Page {pageno}: Photo file not found: {safefn}")

                if img_path is not None and os.path.exists(img_path):
                    thumb = self._get_thumbnail(img_path, int(x1-x0), int(y1-y0))
                    if thumb is not None:
                        img.paste(thumb, (int(x0), int(y0)))
                    else:
                        # draw a light placeholder for missing thumbnail
                        draw.rectangle([x0, y0, x1, y1], fill='#eeeeee')
                else:
                    # draw a light placeholder for missing file
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
        """Render text blocks for a single page.
        
        Args:
            draw: PIL ImageDraw object
            texts: List of text dicts
            frame_x, frame_y: Frame position in pixels
            scale: MCF to pixel scale factor
            origin_left: Origin left for right-page adjustment
            start_number: Starting number for text labels
            pageno: Page number for this text
            delete_button_info: List to append delete button info to
        """
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
        """Draw dashed frame around a page.
        
        Args:
            draw: PIL ImageDraw object
            frame_x, frame_y: Frame top-left position
            frame_w, frame_h: Frame dimensions
            frame_color: Color for the frame
        """
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
        """Draw dotted line down the center crease in spread mode.
        
        Args:
            draw: PIL ImageDraw object
            crease_x: X position of crease
            crease_y: Y start position
            crease_h: Height of crease line
            color: Color for the crease line
        """
        dot_length = 5
        gap_length = 5
        
        y_pos = crease_y
        while y_pos < crease_y + crease_h:
            end_y = min(y_pos + dot_length, crease_y + crease_h)
            draw.line([(crease_x, y_pos), (crease_x, end_y)], fill=color, width=1)
            y_pos += dot_length + gap_length

    def _show_image(self, pil_img):
        self.photo_image = ImageTk.PhotoImage(pil_img)
        self.img_label.configure(image=self.photo_image)
    
    def _create_delete_buttons(self, button_info):
        """Create delete button widgets overlaid on photo/text thumbnails.
        
        Args:
            button_info: List of dicts with either:
                - 'photo_index', 'filename', 'x', 'y' for photos
                - 'text_index', 'x', 'y' for text boxes
        """
        # Destroy any existing delete buttons from previous render
        for btn in self.delete_buttons:
            btn.destroy()
        self.delete_buttons.clear()
        
        # Create new delete buttons
        for info in button_info:
            x = info['x']
            y = info['y']
            
            # Determine if this is a photo or text box
            if 'photo_index' in info:
                page_idx = info['page_index']
                pn = info['pageno']
                filename = info['filename']
                cmd = lambda idx=page_idx, pageno=pn, fn=filename: self._delete_photo(idx, pageno, fn)
            else:  # text_index
                page_idx = info['page_index']
                pn = info['pageno']
                cmd = lambda idx=page_idx, pageno=pn: self._delete_text(idx, pageno)
            
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
            # Register the label widget for drag-and-drop
            self.img_label.drop_target_register(DND_FILES)
            self.img_label.dnd_bind('<<Drop>>', self._on_drop)
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
            ('Image Files', '*.jpg;*.jpeg;*.JPG;*.JPEG;*.png;*.PNG'),
            ('JPEG Images', '*.jpg;*.jpeg;*.JPG;*.JPEG'),
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
        
        # Filter for image files only
        image_exts = {'.jpg', '.jpeg', '.JPG', '.JPEG', '.png', '.PNG'}
        photo_files = [f for f in file_paths if Path(f).suffix in image_exts]
        
        if not photo_files:
            self.show_status('No image files found in selection', error=True)
            return
        
        # Show loading message
        self.show_status(f'Loading {len(photo_files)} photo(s)...')
        self.root.update_idletasks()  # Force UI update to show message
        
        pageno, info = self.pages[self.index]
        
        # Stage photos (don't move yet - only on save)
        new_photos = self._stage_photos(photo_files)
        if not new_photos:
            self.show_status('Failed to stage photos', error=True)
            return
        
        # Get current layout (may include existing photos)
        current_layout = self.layout_mgr.get_current(pageno)
        existing_photos = current_layout.photos if current_layout else info.get('photos', [])
        existing_texts = current_layout.texts if current_layout else info.get('texts', [])
        
        # Filter out empty photo slots (photos with no filename)
        non_empty_photos = [p for p in existing_photos if p.get('filename')]
        
        # Combine non-empty existing photos and new photos
        all_photos = list(non_empty_photos) + new_photos
        
        # Create initial layout rectangles for all photos
        page_w = info.get('page_width', 2100.0)
        page_h = info.get('page_height', 2970.0)
        origin_left = info.get('origin_left', 0.0)
        
        layout_photos = self._create_initial_layout(all_photos, page_w, page_h, origin_left)
        
        # Store new layout in layout manager
        self.layout_mgr.push_layout(pageno, layout_photos, existing_texts)
        
        # Clear cached slot aspect ratios for this page since layout has changed
        # (item indices may have shifted after filtering empty slots)
        keys_to_remove = [k for k in self.slot_aspect_ratios.keys() if k[0] == pageno]
        for key in keys_to_remove:
            del self.slot_aspect_ratios[key]
        
        # Mark only the page where photos were actually added as modified
        # (not both pages in spread mode, since photos are added to one page only)
        self.modified_pages.add(pageno)
        self._update_modified_pages_display()
        
        # Set preferred sizes for ALL photos (existing + new) based on EXIF data
        # and populate photo_dimensions cache for algorithm use
        for photo in all_photos:
            filename = photo.get('filename', '')
            if not filename:
                continue
            
            # Resolve photo path: use _source_path for staged photos, album path for existing
            if '_source_path' in photo:
                # Staged photo - read from source
                img_path = Path(photo['_source_path'])
            else:
                # Existing photo in album
                safefn = filename.replace('safecontainer:/', '').lstrip('/')
                if self.image_folder_attr:
                    img_path = Path(self.mcf_base_folder) / self.image_folder_attr / safefn
                else:
                    img_path = Path(self.mcf_base_folder) / safefn
            
            if img_path.exists():
                preferred_size = get_photo_preferred_size(img_path)
                # Populate dimensions cache for algorithm
                dims = get_image_dimensions(img_path)
                if dims:
                    self.photo_dimensions[filename] = dims
            else:
                preferred_size = 1.0
            
            # Use base filename (without -sz-pg) as key for layout_mgr
            base_filename, _, _ = extract_metadata_from_filename(filename)
            self.layout_mgr.set_size(pageno, base_filename, preferred_size)
        
        # Mark newly added photos for tracking
        for photo in new_photos:
            filename = photo.get('filename', '')
            if filename:
                self.layout_mgr.mark_photo_as_new(pageno, filename)
        
        # Re-render page to show new photos
        self.render_page()
        self.show_status(f'Added {len(new_photos)} photo(s) to page {pageno}')
    
    def _stage_photos(self, photo_paths):
        """Stage photo files for later moving to album (on save) and return photo data dicts.
        
        Photos are NOT moved yet - only validated and metadata created.
        Source paths are stored for later move operation during save.
        Photos are renamed to replace spaces with underscores for CEWE compatibility.
        """
        if not self.mcf_base_folder:
            return []
        
        album_dir = Path(self.mcf_base_folder)
        
        new_photos = []
        for src_path in photo_paths:
            src = Path(src_path)
            if not src.exists():
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
        edge_gap = 50.0
        
        # Base size for small photo (1.0): approximately page_width/10 x page_height/10
        # but with correct aspect ratio from photo
        base_width = page_w / 10.0
        base_height = page_h / 10.0
        
        # Spacing between photos: 1mm = 10 MCF units
        spacing = 100.0
        
        # Starting position
        current_x = origin_left + edge_gap
        current_y = edge_gap
        
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
            page_w = info.get('page_width', 2100.0) * 2  # Double width for spread
            page_h = info.get('page_height', 2970.0)
            origin_left = info.get('origin_left', 0.0)
        else:
            # Single page mode
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
                analysis = analyze_gap_details(original_items, page_w, page_h, origin_left)
                
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
                # No items to analyze, set defaults (14mm edge, 9mm internal)
                # MCF units are 0.1mm, so 14mm = 140 units, 9mm = 90 units
                self.layout_mgr.set_edge_gap(pageno, 140.0)
                self.layout_mgr.set_internal_gap(pageno, 90.0)
        
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
            base_fn, _, _ = extract_metadata_from_filename(fn)
            preferred_size = self.layout_mgr.get_size(pageno, base_fn)
            
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
            row = 2 + i  # Row 0 has main headers, row 1 has sub-headers, data starts at row 2
            
            item_type, item_idx, item_id = item_info
            
            # Item label with type indicator: P1, P2, ... for photos, T1, T2, ... for texts
            type_prefix = 'P' if item_type == 'photo' else 'T'
            item_label = ttk.Label(self.photo_frame, text=f'{type_prefix}{item_idx+1}', font=('TkDefaultFont', 9))
            item_label.grid(row=row, column=0, padx=2, pady=1)
            
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
            
            # Column 1: Slot aspect ratio (editable)
            slot_ar_var = tk.StringVar(value=f'{self.slot_aspect_ratios[ar_key]:.2f}')
            slot_ar_entry = ttk.Entry(self.photo_frame, textvariable=slot_ar_var, width=4)
            slot_ar_entry.grid(row=row, column=1, padx=2, pady=1)
            slot_ar_entry.bind('<Return>', lambda e, pg=pageno, idx=item_idx, var=slot_ar_var: self.on_slot_aspect_changed(pg, idx, var))
            slot_ar_entry.bind('<FocusOut>', lambda e, pg=pageno, idx=item_idx, var=slot_ar_var: self.on_slot_aspect_changed(pg, idx, var))
            
            # Column 2: "Use slot" checkbox
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
                        fn = photo.get('filename', '')
                        if fn:
                            # Check cache first, or load if not cached
                            if fn not in self.photo_dimensions:
                                safefn = fn.replace('safecontainer:/', '').lstrip('/')
                                img_path = Path(self.mcf_base_folder) / safefn
                                if img_path.exists():
                                    try:
                                        dims = get_image_dimensions(img_path)
                                        if dims is not None:
                                            self.photo_dimensions[fn] = dims
                                    except Exception:
                                        pass
                            
                            # Now check if we have dimensions (from cache or just loaded)
                            if fn in self.photo_dimensions:
                                img_w, img_h = self.photo_dimensions[fn]
                                if img_h > 0:
                                    img_aspect = img_w / img_h
                                    # Auto-check if aspect ratios differ by more than 30%
                                    aspect_diff = abs(img_aspect - slot_aspect) / slot_aspect
                                    if aspect_diff > 0.30:
                                        should_auto_check = True
                    
                    self.use_slot_aspect[checkbox_key] = tk.BooleanVar(value=should_auto_check)
                
                checkbox_widget = ttk.Checkbutton(self.photo_frame, variable=self.use_slot_aspect[checkbox_key])
                checkbox_widget.grid(row=row, column=2, padx=2, pady=1)
            else:
                # For text blocks, always use slot aspect (checkbox always checked, disabled)
                checkbox_key = (pageno, item_idx)
                if checkbox_key not in self.use_slot_aspect:
                    self.use_slot_aspect[checkbox_key] = tk.BooleanVar(value=True)
                checkbox_widget = ttk.Checkbutton(self.photo_frame, variable=self.use_slot_aspect[checkbox_key], state='disabled')
                checkbox_widget.grid(row=row, column=2, padx=2, pady=1)
            
            # Column 3: Photo/Image aspect ratio (read-only, empty for text blocks)
            photo_ar_label = None
            if item_type == 'photo':
                photo = photos[item_idx]
                fn = photo.get('filename', '')
                if fn:
                    # Check cache first
                    if fn in self.photo_dimensions:
                        img_w, img_h = self.photo_dimensions[fn]
                        if img_h > 0:
                            img_aspect = img_w / img_h
                            photo_ar_label = ttk.Label(self.photo_frame, text=f'{img_aspect:.2f}', font=('TkDefaultFont', 9))
                        else:
                            photo_ar_label = ttk.Label(self.photo_frame, text='--', font=('TkDefaultFont', 9))
                    else:
                        # Load and cache dimensions
                        safefn = fn.replace('safecontainer:/', '').lstrip('/')
                        img_path = Path(self.mcf_base_folder) / safefn
                        if img_path.exists():
                            try:
                                dims = get_image_dimensions(img_path)
                                if dims is not None:
                                    img_w, img_h = dims
                                    self.photo_dimensions[fn] = (img_w, img_h)
                                    if img_h > 0:
                                        img_aspect = img_w / img_h
                                        photo_ar_label = ttk.Label(self.photo_frame, text=f'{img_aspect:.2f}', font=('TkDefaultFont', 9))
                                    else:
                                        photo_ar_label = ttk.Label(self.photo_frame, text='--', font=('TkDefaultFont', 9))
                                else:
                                    photo_ar_label = ttk.Label(self.photo_frame, text='--', font=('TkDefaultFont', 9))
                            except Exception:
                                photo_ar_label = ttk.Label(self.photo_frame, text='--', font=('TkDefaultFont', 9))
                        else:
                            photo_ar_label = ttk.Label(self.photo_frame, text='--', font=('TkDefaultFont', 9))
                else:
                    photo_ar_label = ttk.Label(self.photo_frame, text='--', font=('TkDefaultFont', 9))
            else:
                # Empty for text blocks
                photo_ar_label = ttk.Label(self.photo_frame, text='', font=('TkDefaultFont', 9))
            
            photo_ar_label.grid(row=row, column=3, padx=2, pady=1)
            
            # Column 4: Desired weight entry (editable)
            desired_var = tk.StringVar(value=f'{rect.preferred_size:.1f}')
            desired_entry = ttk.Entry(self.photo_frame, textvariable=desired_var, width=6)
            desired_entry.grid(row=row, column=4, padx=2, pady=1)
            
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
            actual_label.grid(row=row, column=5, padx=2, pady=1)
            
            self.weight_widgets.append((item_label, slot_ar_entry, checkbox_widget, photo_ar_label, desired_entry, actual_label))
        
        # Position "Add text box" button below all items (skip row 0 and 1 for headers)
        next_row = 2 + len(rectangles)
        self.add_text_btn.grid(row=next_row, column=0, columnspan=2, padx=2, pady=4, sticky='w')
    
    def add_text_box(self):
        """Add a new text box to the current page."""
        if not self.pages:
            self.show_status('No pages available', error=True)
            return
        
        pageno, info = self.pages[self.index]
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])
        texts = current_layout.texts if current_layout else info.get('texts', [])
        
        page_w = info.get('page_width', 2100.0)
        page_h = info.get('page_height', 2970.0)
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
            
            # Get OLD gaps before changing
            old_edge_gap = self.layout_mgr.get_edge_gap(pageno)
            old_internal_gap = self.layout_mgr.get_internal_gap(pageno)
            
            # Parse and validate NEW edge gap
            edge_gap_mm = float(self.edge_gap_var.get())
            new_edge_gap = edge_gap_mm * 10.0  # Convert mm to MCF units
            if not (-200.0 <= new_edge_gap <= 200.0):  # Reasonable bounds (-20mm to +20mm)
                self.show_status(f"Invalid edge gap: {edge_gap_mm:.1f}mm (must be -20 to +20mm)", error=True)
                # Restore previous valid value
                self.edge_gap_var.set(f"{old_edge_gap / 10.0:.1f}")
                return
            
            # Transform current layout using gap change
            self._transform_layout_for_gap_change(
                pageno, old_edge_gap, old_internal_gap, new_edge_gap, old_internal_gap
            )
            
            # Update stored gap value
            self.layout_mgr.set_edge_gap(pageno, new_edge_gap)
            
            # Mark page(s) as modified
            self._mark_current_pages_modified()
            
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
            gap_mm = float(self.gap_var.get())
            new_internal_gap = gap_mm * 10.0  # Convert mm to MCF units
            if not (0.0 <= new_internal_gap <= 200.0):  # Reasonable bounds (0-20mm)
                self.show_status(f"Invalid internal gap: {gap_mm:.1f}mm (must be 0 to 20mm)", error=True)
                # Restore previous valid value
                self.gap_var.set(f"{old_internal_gap / 10.0:.1f}")
                return
            
            # Transform current layout using gap change
            self._transform_layout_for_gap_change(
                pageno, old_edge_gap, old_internal_gap, old_edge_gap, new_internal_gap
            )
            
            # Update stored gap value
            self.layout_mgr.set_internal_gap(pageno, new_internal_gap)
            
            # Mark page(s) as modified
            self._mark_current_pages_modified()
            
            # Re-render with adjusted layout
            self.render_page()
        except ValueError as e:
            # Show error and restore previous value
            self.show_status(f"Invalid internal gap value: {self.gap_var.get()}", error=True)
            self.gap_var.set(f"{old_internal_gap / 10.0:.1f}")
    
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
        origin_left = info.get('origin_left', 0.0)
        
        # Transform photos using centralized helper
        transformed_photos = []
        for p in current_layout.photos:
            # Coordinates in MCF file are spread-relative (origin_left offset for right pages)
            spread_left = p.get('area_left', 0)
            top = p.get('area_top', 0)
            width = p.get('area_width', 0)
            height = p.get('area_height', 0)
            
            # Convert to page-relative coordinates for transformation
            page_left = spread_left - origin_left
            
            new_left, new_top, new_width, new_height = transform_item_for_gap_change(
                page_left, top, width, height, page_w, page_h,
                old_edge_gap, old_internal_gap, new_edge_gap, new_internal_gap
            )
            
            # Convert back to spread-relative coordinates
            new_spread_left = new_left + origin_left
            
            updated_photo = p.copy()
            updated_photo['area_left'] = new_spread_left
            updated_photo['area_top'] = new_top
            updated_photo['area_width'] = new_width
            updated_photo['area_height'] = new_height
            transformed_photos.append(updated_photo)
        
        # Transform texts using centralized helper
        transformed_texts = []
        for t in current_layout.texts:
            # Coordinates in MCF file are spread-relative (origin_left offset for right pages)
            spread_left = t.get('area_left', 0)
            top = t.get('area_top', 0)
            width = t.get('area_width', 0)
            height = t.get('area_height', 0)
            
            # Convert to page-relative coordinates for transformation
            page_left = spread_left - origin_left
            
            new_left, new_top, new_width, new_height = transform_item_for_gap_change(
                page_left, top, width, height, page_w, page_h,
                old_edge_gap, old_internal_gap, new_edge_gap, new_internal_gap
            )
            
            # Convert back to spread-relative coordinates
            new_spread_left = new_left + origin_left
            
            updated_text = t.copy()
            updated_text['area_left'] = new_spread_left
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
        if self.spread_mode.get():
            # In spread mode, navigate to previous even page
            current_pageno = self.pages[self.index][0]
            
            # Find previous even page
            for i in range(self.index - 1, -1, -1):
                pageno = self.pages[i][0]
                if pageno % 2 == 0:
                    self.index = i
                    self.show_status(f'Loading pages {pageno}-{pageno+1}...')
                    self.root.update_idletasks()
                    self.render_page()
                    return
            
            # No even page found before current - stay where we are
            return
        else:
            if self.index > 0:
                self.index -= 1
                pageno = self.pages[self.index][0]
                self.show_status(f'Loading page {pageno}...')
                self.root.update_idletasks()
                self.render_page()
            else:
                return

    def next_page(self):
        if self.spread_mode.get():
            # In spread mode, navigate to next even page
            current_pageno = self.pages[self.index][0]
            
            # Find next even page after current spread
            start_search = self.index + 2 if current_pageno % 2 == 0 else self.index + 1
            
            for i in range(start_search, len(self.pages)):
                pageno = self.pages[i][0]
                if pageno % 2 == 0:
                    self.index = i
                    # Check if there's an odd page following
                    if i < len(self.pages) - 1:
                        next_pageno = self.pages[i + 1][0]
                        self.show_status(f'Loading pages {pageno}-{next_pageno}...')
                    else:
                        self.show_status(f'Loading page {pageno}...')
                    self.root.update_idletasks()
                    self.render_page()
                    return
            
            # No more even pages - we're at the end
            self.show_status('Last page of book')
            return
        else:
            if self.index < len(self.pages) - 1:
                self.index += 1
                pageno = self.pages[self.index][0]
                self.show_status(f'Loading page {pageno}...')
                self.root.update_idletasks()
                self.render_page()
            else:
                self.show_status('Last page of book')
                return

    def goto_page(self):
        try:
            v = int(self.goto_var.get())
        except Exception:
            return
        # find index for page number
        for i,(pn,_) in enumerate(self.pages):
            if pn == v:
                self.index = i
                self.show_status(f'Loading page {v}...')
                self.root.update_idletasks()
                self.render_page()
                return

    def quit(self):
        self.root.quit()
    
    def _update_page_range_display(self):
        """Update the page range label to show valid page numbers."""
        if not self.pages:
            self.page_range_var.set('')
            return
        
        min_page = min(pn for pn, _ in self.pages)
        max_page = max(pn for pn, _ in self.pages)
        self.page_range_var.set(f'Pages {min_page}-{max_page}')
    
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
    
    def _on_spread_mode_change(self):
        """Handle spread mode checkbox toggle - re-render current page(s)."""
        # Update canvas aspect ratio and window geometry based on spread mode
        if self.pages:
            _, first_page_info = self.pages[0]
            page_w = first_page_info.get('page_width', 2100.0)
            page_h = first_page_info.get('page_height', 2970.0)
        else:
            page_w = 2100.0
            page_h = 2970.0
        
        if self.spread_mode.get():
            # Entering spread mode: navigate to nearest even page
            current_pageno = self.pages[self.index][0]
            if current_pageno % 2 != 0:
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
        self.root.aspect(ratio_num, ratio_denom, ratio_num, ratio_denom)
        
        # Clear gaps for all pages so they get recalculated with new page dimensions
        # When switching to spread mode, gaps need to be analyzed across double-width spread
        # When switching to single page, gaps need to be analyzed for single page width
        for pageno, _ in self.pages:
            self.layout_mgr.clear_gaps(pageno)
        
        # Re-render with new mode (this will trigger update_weights_display which recalculates gaps)
        self.render_page()
    
    def _update_modified_pages_display(self):
        """Update the modified pages label in Controls window."""
        if not self.modified_pages:
            self.modified_pages_var.set('(none)')
            self.modified_pages_label.config(foreground='blue')
        else:
            # Sort page numbers and display as comma-separated list
            sorted_pages = sorted(self.modified_pages)
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

    def generate_layout(self):
        """Run layout algorithm on current page(s) in a background thread.

        In spread mode, combines photos from both pages, runs algorithm on double-width
        page, then splits results back to individual pages.
        
        The Generate button is disabled while the operation runs and re-enabled
        when finished. Errors are shown; successful completion updates the UI
        without a popup.
        """
        # disable the button immediately to prevent double clicks
        try:
            self.gen_btn.config(state='disabled')
        except Exception as e:
            logger.error(f"Failed to disable Generate Layout button: {e}")
        
        # Show "Running..." status
        self.show_status('Running...')

        def worker():
            in_spread_mode = self.spread_mode.get()
            
            if in_spread_mode and len(self.current_spread_pages) == 2:
                # Spread mode: work with both pages combined
                page_indices = [self.index, self.index + 1]
                page_numbers = self.current_spread_pages
                
                # Collect photos and texts from both pages
                all_photos = []
                all_texts = []
                page_infos = []
                
                for page_idx in page_indices:
                    pageno, info = self.pages[page_idx]
                    page_infos.append((pageno, info))
                    current_layout = self.layout_mgr.get_current(pageno)
                    photos = current_layout.photos if current_layout else info.get('photos', [])
                    texts = current_layout.texts if current_layout else info.get('texts', [])
                    all_photos.extend(photos)
                    all_texts.extend(texts)
                
                if not all_photos:
                    self.root.after(0, lambda: self.gen_btn.config(state='normal'))
                    return
                
                # Use first page's dimensions (they should be identical)
                _, info0 = page_infos[0]
                page_w = info0.get('page_width', 2100.0)
                page_h = info0.get('page_height', 2970.0)
                
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
                
                # Create algorithm instance
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
                    algorithm = TreeBuilderAlgorithm(tolerance=60.0)
                else:
                    algorithm = CollageGeneratorAlgorithm(temperature=1.0)
                
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
                            use_slot_aspect_for_photos[photo_offset + local_photo_idx] = self.use_slot_aspect[checkbox_key].get()
                    
                    num_items = len(photos_for_page) + len(texts_for_page)
                    for local_item_idx in range(num_items):
                        ar_key = (pageno, local_item_idx)
                        if ar_key in self.slot_aspect_ratios:
                            slot_aspect_ratios_combined[photo_offset + text_offset + local_item_idx] = self.slot_aspect_ratios[ar_key]
                    
                    photo_offset += len(photos_for_page)
                    text_offset += len(texts_for_page)
                
                # Run algorithm on combined spread
                success, updated_photos, updated_texts, error_msg = generate_layout_for_page(
                    all_photos, spread_w, page_h, self.photo_dimensions,
                    algorithm=algorithm, edge_gap=edge_gap, internal_gap=internal_gap, texts=all_texts,
                    preferred_sizes=preferred_sizes,
                    use_slot_aspect=use_slot_aspect_for_photos,
                    slot_aspect_ratios=slot_aspect_ratios_combined,
                    origin_left=0.0,  # Spread starts at 0
                    pageno=pageno0  # For logging
                )
                
                if not success:
                    def on_error():
                        try:
                            self.gen_btn.config(state='normal')
                        except Exception as e:
                            logger.error(f"Failed to re-enable Generate Layout button: {e}")
                        self.show_status(f'Layout generation failed: {error_msg}', error=True)
                    self.root.after(0, on_error)
                    return
                
                # Split results back into two pages
                # Photos/texts on left half (x < page_w) go to page 0
                # Photos/texts on right half (x >= page_w) go to page 1
                photos_page0 = []
                photos_page1 = []
                texts_page0 = []
                texts_page1 = []
                
                for photo in updated_photos:
                    area_left = photo.get('area_left', 0)
                    if area_left < page_w:
                        # Left page - coordinates stay as-is
                        photos_page0.append(photo)
                    else:
                        # Right page - adjust coordinates
                        photo_copy = dict(photo)
                        # Subtract page_w to get page-relative coordinate, then add origin_left
                        photo_copy['area_left'] = (area_left - page_w) + origin_left_1
                        photos_page1.append(photo_copy)
                
                for text in updated_texts:
                    area_left = text.get('area_left', 0)
                    if area_left < page_w:
                        texts_page0.append(text)
                    else:
                        text_copy = dict(text)
                        text_copy['area_left'] = (area_left - page_w) + origin_left_1
                        texts_page1.append(text_copy)
                
                # Push layouts and mark both pages modified
                def on_spread_done():
                    try:
                        self.gen_btn.config(state='normal')
                    except Exception as e:
                        logger.error(f"Failed to re-enable Generate Layout button: {e}")
                    
                    self.show_status(f'Layout generated successfully using {self.algorithm_var.get()} (spread)')
                    
                    self.layout_mgr.push_layout(page_numbers[0], photos_page0, texts_page0)
                    self.layout_mgr.push_layout(page_numbers[1], photos_page1, texts_page1)
                    
                    self.modified_pages.add(page_numbers[0])
                    self.modified_pages.add(page_numbers[1])
                    self._update_modified_pages_display()
                    
                    self.render_page()
                
                self.root.after(0, on_spread_done)
                
            else:
                # Single page mode - original logic
                pageno, info = self.pages[self.index]
                current_layout = self.layout_mgr.get_current(pageno)
                photos = current_layout.photos if current_layout else info.get('photos', [])

                # Filter out empty photo slots (photos with no filename)
                photos = [p for p in photos if p.get('filename')]
                if not photos:
                    # re-enable on main thread
                    self.root.after(0, lambda: self.gen_btn.config(state='normal'))
                    return

                page_w = info.get('page_width', 2100.0)
                page_h = info.get('page_height', 2970.0)
                
                # Get current gaps for this page from layout manager
                internal_gap = self.layout_mgr.get_internal_gap(pageno)
                edge_gap = self.layout_mgr.get_edge_gap(pageno)

                # Get texts for this page (from current layout, not original)
                texts = current_layout.texts if current_layout else info.get('texts', [])
                
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
                    algorithm = TreeBuilderAlgorithm(tolerance=60.0)
                else:
                    algorithm = CollageGeneratorAlgorithm(temperature=1.0)  # fallback
                
                # Collect checkbox states for photos on this page
                use_slot_aspect_for_photos = {}
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
                
                success, updated_photos, updated_texts, error_msg = generate_layout_for_page(
                    photos, page_w, page_h, self.photo_dimensions,
                    algorithm=algorithm, edge_gap=edge_gap, internal_gap=internal_gap, texts=texts,
                    preferred_sizes=preferred_sizes,
                    use_slot_aspect=use_slot_aspect_for_photos, 
                    slot_aspect_ratios=slot_aspect_ratios_for_page,
                    origin_left=info.get('origin_left', 0.0), pageno=pageno
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
                    except Exception as e:
                        logger.error(f"Failed to re-enable Generate Layout button: {e}")

                    if not success:
                        self.show_status(f'Layout generation failed: {error_msg}', error=True)
                        return
                    
                    self.show_status(f'Layout generated successfully using {self.algorithm_var.get()}')

                    # Push new layout (both photos and texts) to manager and refresh view
                    self.layout_mgr.push_layout(pageno, updated_photos, updated_texts)
                    
                    # Mark page(s) as modified
                    self._mark_current_pages_modified()
                    
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
        
        # Process all modified pages
        pages_to_save = sorted(self.modified_pages)
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
                
                # Ensure all photos have image_width and image_height before saving
                for photo in photos:
                    filename = photo.get('filename', '')
                    if not filename:
                        continue
                    
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
                
                # Rename photos to include preferred size and page number in filename
                # Skip newly added photos that haven't been moved yet
                rename_map = {}  # old_filename -> new_filename (for XML update)
                for photo in photos:
                    old_filename = photo.get('filename', '')
                    if not old_filename:
                        continue
                    
                    # Skip newly added photos - they'll be moved with metadata already encoded
                    if old_filename in new_photos:
                        continue
                    
                    # Get base filename (without any -sz or -pg suffixes)
                    base_filename, _, _ = extract_metadata_from_filename(old_filename)
                    
                    # Get preferred size for this photo
                    preferred_size = self.layout_mgr.get_size(pageno, base_filename)
                    
                    # Generate new filename with size and page number encoded
                    new_filename = encode_metadata_in_filename(old_filename, preferred_size, pageno)
                    
                    # Populate rename_map to handle multiple possible XML filename formats
                    # XML might have: base name, name with -sz, or name with -sz-pgN (from different page)
                    rename_map[base_filename] = new_filename  # base -> new
                    if old_filename != base_filename:
                        # Also map current filename -> new filename (e.g., -sz or -sz-pgOLD -> -sz-pgNEW)
                        rename_map[old_filename] = new_filename
                    
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
                new_photos_updated = set()  # Track updated filenames for new photos
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
                        new_photos_updated.add(new_filename)  # Track new filename
                        
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
                    make_backup=(total_saved == 0),  # Only backup on first page
                    new_photos=list(new_photos_updated), deleted_photos=list(deleted_photos),
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
    
    app = LayoutViewer(root, root_el, mcf_path)
    root.mainloop()
