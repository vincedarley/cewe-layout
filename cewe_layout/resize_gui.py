"""GUI for resizing photobooks to different dimensions."""

import os
import tkinter as tk
from tkinter import ttk

from .book.utils import BOOK_SIZES, find_closest_book_size, calculate_resize_impact, ResizeTransformer


class ResizeWindow:
    """Window for resizing a photobook to different dimensions."""
    
    def __init__(self, parent, book, mcf_file_path):
        """Initialize the resize window.
        
        Args:
            parent: Parent Tk window
            book: Photobook instance to resize
            mcf_file_path: Path to the MCF file
        """
        self.book = book
        self.mcf_file_path = mcf_file_path
        
        # Create toplevel window
        self.window = tk.Toplevel(parent)
        self.window.title('Resize Book')
        self.window.geometry('600x700')
        
        # Main frame with padding
        main_frame = ttk.Frame(self.window, padding=10)
        main_frame.pack(fill='both', expand=True)
        
        # Current size section
        self._create_current_size_section(main_frame)
        
        # New size selection section
        self._create_new_size_section(main_frame)
        
        # Action buttons section
        self._create_action_buttons_section(main_frame)
        
    def _create_current_size_section(self, parent):
        """Create the section showing current book size.
        
        Args:
            parent: Parent frame
        """
        section_frame = ttk.LabelFrame(parent, text='Current Book Size', padding=10)
        section_frame.pack(fill='x', pady=(0, 10))
        
        # Get the first page to determine current size
        if self.book.get_page_count() > 0:
            first_page = self.book.get_first_content_page()
            page_info = first_page.get_page_info()
            
            # Extract dimensions (in MCF units, divide by 100 for cm)
            page_width_mcf = page_info.get('page_width', 0)
            page_height_mcf = page_info.get('page_height', 0)
            width_cm = page_width_mcf / 100.0
            height_cm = page_height_mcf / 100.0
            
            # Calculate aspect ratio
            aspect_ratio = page_width_mcf / page_height_mcf if page_height_mcf > 0 else 0
            
            # Display dimensions
            size_text = f'{width_cm:.1f} cm × {height_cm:.1f} cm (aspect ratio: {aspect_ratio:.2f})'
            size_label = ttk.Label(section_frame, text=size_text, font=('TkDefaultFont', 12, 'bold'))
            size_label.pack()
            
            # Also show in MCF units
            mcf_text = f'({page_width_mcf} × {page_height_mcf} MCF units)'
            mcf_label = ttk.Label(section_frame, text=mcf_text, foreground='gray')
            mcf_label.pack()
            
            # Show page count
            page_count_text = f'{self.book.get_page_count()} pages in book'
            page_count_label = ttk.Label(section_frame, text=page_count_text)
            page_count_label.pack(pady=(10, 0))
            
            # Store current dimensions for later use
            self.current_width = page_width_mcf
            self.current_height = page_height_mcf
        else:
            # No pages
            no_pages_label = ttk.Label(section_frame, text='No pages in book', foreground='red')
            no_pages_label.pack()
            self.current_width = 0
            self.current_height = 0
    
    def _create_new_size_section(self, parent):
        """Create the section for selecting new book size.
        
        Args:
            parent: Parent frame
        """
        section_frame = ttk.LabelFrame(parent, text='New Book Size', padding=10)
        section_frame.pack(fill='both', expand=True, pady=(0, 10))
                
        # Create dropdown entries for each book size
        self.size_options = []
        self.size_keys = []
        
        for book_key, dimensions in BOOK_SIZES.items():
            # Page dimensions are for spread (2 pages), so divide by 2 for single page
            page_width = dimensions['pageWidth'] / 2
            page_height = dimensions['pageHeight']
            width_cm = page_width / 100.0
            height_cm = page_height / 100.0
            aspect_ratio = page_width / page_height if page_height > 0 else 0
            
            # Format: "L landscape - 19.0 cm × 14.8 cm (1.28)"
            option_text = f"{book_key} - {width_cm:.1f} cm × {height_cm:.1f} cm ({aspect_ratio:.2f})"
            self.size_options.append(option_text)
            self.size_keys.append(book_key)
        
        # Determine default selection
        default_value = ''
        if self.current_width > 0 and self.current_height > 0:
            # find_closest_book_size compares to pageWidth/2, so pass single page width
            closest_key = find_closest_book_size(self.current_width, self.current_height)
            # Find index of this key in our list
            if closest_key in self.size_keys:
                default_index = self.size_keys.index(closest_key)
                default_value = self.size_options[default_index]
            elif len(self.size_options) > 0:
                default_value = self.size_options[0]
        elif len(self.size_options) > 0:
            default_value = self.size_options[0]
        
        # Create StringVar with initial value
        self.size_var = tk.StringVar(value=default_value)
        
        # Create OptionMenu dropdown
        if len(self.size_options) > 0:
            self.size_menu = tk.OptionMenu(section_frame, self.size_var, *self.size_options)
            self.size_menu.config(width=50)
            self.size_menu.pack(fill='x', pady=(0, 10))
        
        # Scaling options
        scaling_label = ttk.Label(section_frame, text='Scaling:')
        scaling_label.pack(anchor='w', pady=(10, 5))
        
        # 1. None: just places the content without scaling (but does adjust x-coordinates so that items on the right
        # hand page of a spread are indeed on the right hand page)
        # 2. None (center on page): as 'None' but shifts x/y so that the centers of the old and new pages are exactly
        # aligned. When moving to a larger page size this will leave pleasant margins around the content.
        # 3. Fit (may have margins): scales content uniformly to fit within new page size, preserving aspect ratio;
        # the dimension that is tightest will fit exactly, the other dimension may have margins. If the tight
        # dimension has bleed in the old page size, it will also have the same bleed in the new size (e.g. 3mm)
        # 4. Fill (crop to avoid margins): as with the previous option (so preserves aspect ratio), except that the 
        # looser dimension is used to decide on the scaling, so that is the dimension that fills the new page size 
        # exactly, and the other dimension may be cropped.
        # 5. Fill (may change aspect ratio): now we ensure both dimensions exactly fill the new page size (and exactly
        # preserve any bleed), but this option does not preserve the aspect ratio of the content. This does not
        # mean photos will be distorted - typically in CEWE photos are always cropped to fit their frames, so a change
        # in aspect ratio of the layout will mean a change in crop of the photos.
        scaling_options = ['None', 'None (center on page)', 'Fit (may have margins)', 'Fill (crop to avoid margins)', 'Fill (may change aspect ratio)']
        self.scaling_var = tk.StringVar(value='None')
        self.scaling_menu = tk.OptionMenu(section_frame, self.scaling_var, *scaling_options)
        self.scaling_menu.config(width=50)
        self.scaling_menu.pack(fill='x', pady=(0, 10))
        
        # Info section that updates when selections change
        info_section = ttk.LabelFrame(section_frame, text='Resize Impact', padding=10)
        info_section.pack(fill='both', expand=True, pady=(10, 0))
        
        # Create a text widget to display the impact information
        self.info_text = tk.Text(info_section, height=12, width=60, wrap='word', 
                                font=('TkDefaultFont', 9), state='disabled')
        self.info_text.pack(fill='both', expand=True)
        
        # Set up callbacks to update info when selections change
        self.size_var.trace_add('write', lambda *args: self._update_resize_info())
        self.scaling_var.trace_add('write', lambda *args: self._update_resize_info())
        
        # Initial update
        self._update_resize_info()
    
    def _update_resize_info(self):
        """Update the resize information display based on current selections."""
        # Get current book aspect ratio
        if self.current_width > 0 and self.current_height > 0:
            current_aspect = self.current_width / self.current_height
        else:
            self._set_info_text('')
            return
        
        # Get selected target size
        selected = self.size_var.get()
        if not selected or selected not in self.size_options:
            self._set_info_text('')
            return
        
        # Find the corresponding book size key
        selected_index = self.size_options.index(selected)
        selected_key = self.size_keys[selected_index]
        
        # Get target dimensions
        dimensions = BOOK_SIZES[selected_key]
        target_width = dimensions['pageWidth'] / 2
        target_height = dimensions['pageHeight']
        target_aspect = target_width / target_height
        
        # Get selected scaling rule
        scaling_rule = self.scaling_var.get()
        
        # Calculate resize impact (assume 3mm bleed as typical)
        impact = calculate_resize_impact(self.current_width, self.current_height,
                                        target_width, target_height,
                                        scaling_rule, bleed_mm=3)
        
        # Format the display
        lines = []
        
        # Aspect ratio change
        aspect_diff_pct = impact['aspect_ratio_change_pct']
        if aspect_diff_pct > 0.01:
            lines.append(f'Aspect ratio change: +{aspect_diff_pct:.1f}% (wider)\n')
        elif aspect_diff_pct < -0.01:
            lines.append(f'Aspect ratio change: {aspect_diff_pct:.1f}% (narrower)\n')
        else:
            lines.append(f'Aspect ratio change: 0% (same aspect ratio)\n')
        
        # Scaling factors
        if impact['scale_x'] != impact['scale_y']:
            lines.append(f'Scaling: {impact["scale_x"]*100:.1f}% horizontal, {impact["scale_y"]*100:.1f}% vertical\n')
        else:
            lines.append(f'Scaling: {impact["scale_x"]*100:.1f}% (uniform)\n')
        
        # Cropping
        total_crop = (impact['crop_left_mm'] + impact['crop_right_mm'] + 
                     impact['crop_top_mm'] + impact['crop_bottom_mm'])
        if total_crop > 0.1:
            lines.append(f'\nCropping from page edges:')
            if impact['crop_left_mm'] > 0.1 or impact['crop_right_mm'] > 0.1:
                lines.append(f'  Horizontal: {impact["crop_left_mm"]:.1f} mm left, {impact["crop_right_mm"]:.1f} mm right')
            if impact['crop_top_mm'] > 0.1 or impact['crop_bottom_mm'] > 0.1:
                lines.append(f'  Vertical: {impact["crop_top_mm"]:.1f} mm top, {impact["crop_bottom_mm"]:.1f} mm bottom')
            lines.append(f'  Total: {total_crop:.1f} mm cropped\n')
        else:
            lines.append(f'\nNo page edge cropping\n')
        
        # Margins
        total_margin = (impact['margin_left_mm'] + impact['margin_right_mm'] + 
                       impact['margin_top_mm'] + impact['margin_bottom_mm'])
        if total_margin > 0.1:
            lines.append(f'\nMargins added:')
            if impact['margin_left_mm'] > 0.1 or impact['margin_right_mm'] > 0.1:
                lines.append(f'  Horizontal: {impact["margin_left_mm"]:.1f} mm left, {impact["margin_right_mm"]:.1f} mm right')
            if impact['margin_top_mm'] > 0.1 or impact['margin_bottom_mm'] > 0.1:
                lines.append(f'  Vertical: {impact["margin_top_mm"]:.1f} mm top, {impact["margin_bottom_mm"]:.1f} mm bottom')
            lines.append(f'  Total: {total_margin:.1f} mm margins\n')
        else:
            lines.append(f'\nNo margins added\n')
        
        # Photo cropping
        if impact['photo_crop_pct'] > 0.1:
            lines.append(f'\nEstimated photo cropping due to aspect ratio change: {impact["photo_crop_pct"]:.1f}%')
        
        self._set_info_text('\n'.join(lines))
    
    def _set_info_text(self, text):
        """Set the info text widget content.
        
        Args:
            text: Text to display
        """
        self.info_text.config(state='normal')
        self.info_text.delete('1.0', 'end')
        self.info_text.insert('1.0', text)
        self.info_text.config(state='disabled')
    
    def _create_action_buttons_section(self, parent):
        """Create the section with action buttons and name input.
        
        Args:
            parent: Parent frame
        """
        section_frame = ttk.LabelFrame(parent, text='Actions', padding=10)
        section_frame.pack(fill='x', pady=(10, 0))
        
        # View button on its own line
        view_btn = ttk.Button(section_frame, text='View As Resized', command=self._view_resized)
        view_btn.pack(fill='x', pady=(0, 10))
        
        # Save button and name input on same line
        save_frame = ttk.Frame(section_frame)
        save_frame.pack(fill='x')
        
        # Get photobook name from the directory containing data.mcf (same logic as GUI titlebar)
        if self.mcf_file_path:
            # Get the parent directory name (e.g., "Test-album.xmcf" not "data.mcf")
            current_name = os.path.basename(os.path.dirname(self.mcf_file_path))
        else:
            current_name = 'Unknown'
        
        self.name_var = tk.StringVar(value=current_name)
        name_entry = ttk.Entry(save_frame, textvariable=self.name_var)
        name_entry.pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        save_btn = ttk.Button(save_frame, text='Save As Resized', command=self._save_resized)
        save_btn.pack(side='left')
    
    def _view_resized(self):
        """View the resized photobook."""
        # Get selected target size
        selected = self.size_var.get()
        if not selected or selected not in self.size_options:
            return
        
        # Find the corresponding book size key
        selected_index = self.size_options.index(selected)
        selected_key = self.size_keys[selected_index]
        
        # Get target dimensions
        dimensions = BOOK_SIZES[selected_key]
        target_width = dimensions['pageWidth'] / 2
        target_height = dimensions['pageHeight']
        
        # Get selected scaling rule
        scaling_rule = self.scaling_var.get()
        
        # Create ResizeTransformer
        transformer = ResizeTransformer(
            self.current_width,
            self.current_height,
            int(target_width),
            int(target_height),
            scaling_rule,
            bleed_mm=3
        )
        
        # Set transformer on the book
        self.book.resize_transformer = transformer
        
        # Close the resize window
        self.window.destroy()
        
        # Trigger page re-render (the gui.py will pick up the transformer from book)
        # Note: The parent window's render will be triggered automatically when this window closes
    
    def _save_resized(self):
        """Save the resized photobook (not yet implemented)."""
        pass


def open_resize_window(parent, book, mcf_file_path):
    """Open the resize book window.
    
    Args:
        parent: Parent Tk window
        book: Photobook instance to resize
        mcf_file_path: Path to the MCF file
    """
    ResizeWindow(parent, book, mcf_file_path)
