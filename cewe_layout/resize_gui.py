"""GUI for resizing photobooks to different dimensions."""

import os
import tkinter as tk
from tkinter import ttk

from .book.utils import BOOK_SIZES, find_closest_book_size, calculate_resize_impact, ResizeTransformer


class ResizeWindow:
    """Window for resizing a photobook to different dimensions."""
    
    def __init__(self, parent, viewer, mcf_file_path):
        """Initialize the resize window.
        
        Args:
            parent: Parent Tk window
            viewer: LayoutViewer instance
            mcf_file_path: Path to the MCF file
        """
        self.viewer = viewer
        self.book = viewer.book
        self.mcf_file_path = mcf_file_path
        
        # Create toplevel window
        self.window = tk.Toplevel(parent)
        self.window.title('Resize Book')
        self.window.geometry('600x750')
        
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
        
        if self.book.get_page_count() > 0:
            # Get cover page dimensions (front cover)
            cover_page = self.book.get_page(0)  # Front cover is first page
            cover_info = cover_page.get_page_info()
            cover_width_mcf = cover_info.get('page_width', 0)
            cover_height_mcf = cover_info.get('page_height', 0)
            cover_width_cm = cover_width_mcf / 100.0
            cover_height_cm = cover_height_mcf / 100.0
            cover_aspect = cover_width_mcf / cover_height_mcf if cover_height_mcf > 0 else 0
            
            # Get content page dimensions
            content_page = self.book.get_first_content_page()
            content_info = content_page.get_page_info()
            content_width_mcf = content_info.get('page_width', 0)
            content_height_mcf = content_info.get('page_height', 0)
            content_width_cm = content_width_mcf / 100.0
            content_height_cm = content_height_mcf / 100.0
            content_aspect = content_width_mcf / content_height_mcf if content_height_mcf > 0 else 0
            
            # Display cover dimensions
            cover_label = ttk.Label(section_frame, text='Cover pages:', font=('TkDefaultFont', 10, 'bold'))
            cover_label.pack(anchor='w')
            cover_size_text = f'{cover_width_cm:.1f} cm × {cover_height_cm:.1f} cm (aspect ratio: {cover_aspect:.2f})'
            cover_size_label = ttk.Label(section_frame, text=cover_size_text)
            cover_size_label.pack(anchor='w', padx=(20, 0))
            cover_mcf_text = f'({cover_width_mcf} × {cover_height_mcf} MCF units)'
            cover_mcf_label = ttk.Label(section_frame, text=cover_mcf_text, foreground='gray')
            cover_mcf_label.pack(anchor='w', padx=(20, 0), pady=(0, 10))
            
            # Display content dimensions
            content_label = ttk.Label(section_frame, text='Content pages:', font=('TkDefaultFont', 10, 'bold'))
            content_label.pack(anchor='w')
            content_size_text = f'{content_width_cm:.1f} cm × {content_height_cm:.1f} cm (aspect ratio: {content_aspect:.2f})'
            content_size_label = ttk.Label(section_frame, text=content_size_text)
            content_size_label.pack(anchor='w', padx=(20, 0))
            content_mcf_text = f'({content_width_mcf} × {content_height_mcf} MCF units)'
            content_mcf_label = ttk.Label(section_frame, text=content_mcf_text, foreground='gray')
            content_mcf_label.pack(anchor='w', padx=(20, 0))
            
            # Show page count
            page_count_text = f'{self.book.get_page_count()} pages in book'
            page_count_label = ttk.Label(section_frame, text=page_count_text)
            page_count_label.pack(pady=(10, 0))
            
            # Store current dimensions for later use
            self.current_cover_width = cover_width_mcf
            self.current_cover_height = cover_height_mcf
            self.current_content_width = content_width_mcf
            self.current_content_height = content_height_mcf
        else:
            # No pages
            no_pages_label = ttk.Label(section_frame, text='No pages in book', foreground='red')
            no_pages_label.pack()
            self.current_cover_width = 0
            self.current_cover_height = 0
            self.current_content_width = 0
            self.current_content_height = 0
    
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
            # Use content page dimensions for display (spread dimensions, so divide by 2 for single page)
            page_width = dimensions['pageWidth'] / 2
            page_height = dimensions['pageHeight']
            width_cm = page_width / 100.0
            height_cm = page_height / 100.0
            aspect_ratio = page_width / page_height if page_height > 0 else 0
            
            # Format: "L landscape - 19.0 cm × 14.8 cm (1.28)"
            option_text = f"{book_key} - {width_cm:.1f} cm × {height_cm:.1f} cm ({aspect_ratio:.2f})"
            self.size_options.append(option_text)
            self.size_keys.append(book_key)
        
        # Determine default section (use content page dimensions)
        default_value = ''
        if self.current_content_width > 0 and self.current_content_height > 0:
            # find_closest_book_size compares to pageWidth/2, so pass single page width
            closest_key = find_closest_book_size(self.current_content_width, self.current_content_height)
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
        
        # Scaling options - label and menu on same line
        scaling_frame = ttk.Frame(section_frame)
        scaling_frame.pack(fill='x', pady=(10, 10))
        
        scaling_label = ttk.Label(scaling_frame, text='Scaling:')
        scaling_label.pack(side='left', padx=(0, 5))
        
        scaling_options = ['None', 'None (center on page)', 'Fit (may have margins)', 'Fill (crop to avoid margins)', 'Fill (may change aspect ratio)']
        self.scaling_var = tk.StringVar(value='None')
        self.scaling_menu = tk.OptionMenu(scaling_frame, self.scaling_var, *scaling_options)
        self.scaling_menu.config(width=45)
        self.scaling_menu.pack(side='left', fill='x', expand=True)
        
        # Info section that updates when selections change
        info_section = ttk.LabelFrame(section_frame, text='Resize Impact', padding=10)
        info_section.pack(fill='both', expand=True, pady=(10, 0))
        
        # Create two side-by-side text widgets
        info_container = ttk.Frame(info_section)
        info_container.pack(fill='both', expand=True)
        
        # Left side: Cover pages
        cover_frame = ttk.LabelFrame(info_container, text='Cover Pages', padding=5)
        cover_frame.pack(side='left', fill='both', expand=True, padx=(0, 5))
        self.info_cover_text = tk.Text(cover_frame, height=12, width=30, wrap='word', 
                                       font=('TkDefaultFont', 9), state='disabled')
        self.info_cover_text.pack(fill='both', expand=True)
        
        # Right side: Content pages
        content_frame = ttk.LabelFrame(info_container, text='Content Pages', padding=5)
        content_frame.pack(side='left', fill='both', expand=True)
        self.info_content_text = tk.Text(content_frame, height=12, width=30, wrap='word', 
                                         font=('TkDefaultFont', 9), state='disabled')
        self.info_content_text.pack(fill='both', expand=True)
        
        # Set up callbacks to update info when selections change
        self.size_var.trace_add('write', lambda *args: self._update_resize_info())
        self.scaling_var.trace_add('write', lambda *args: self._update_resize_info())
        
        # Initial update
        self._update_resize_info()
    
    def _update_resize_info(self):
        """Update the resize information display based on current selections."""
        # Check if we have valid dimensions
        if self.current_cover_width <= 0 or self.current_content_width <= 0:
            self._set_info_text(self.info_cover_text, '')
            self._set_info_text(self.info_content_text, '')
            return
        
        # Get selected target size
        selected = self.size_var.get()
        if not selected or selected not in self.size_options:
            self._set_info_text(self.info_cover_text, '')
            self._set_info_text(self.info_content_text, '')
            return
        
        # Find the corresponding book size key
        selected_index = self.size_options.index(selected)
        selected_key = self.size_keys[selected_index]
        
        # Get target dimensions
        dimensions = BOOK_SIZES[selected_key]
        target_cover_width = dimensions['coverWidth'] / 2
        target_cover_height = dimensions['coverHeight']
        target_content_width = dimensions['pageWidth'] / 2
        target_content_height = dimensions['pageHeight']
        
        # Get selected scaling rule
        scaling_rule = self.scaling_var.get()
        
        # Calculate resize impact for covers (assume 3mm bleed as typical)
        cover_impact = calculate_resize_impact(self.current_cover_width, self.current_cover_height,
                                               target_cover_width, target_cover_height,
                                               scaling_rule, bleed_mm=3)
        
        # Calculate resize impact for content pages
        content_impact = calculate_resize_impact(self.current_content_width, self.current_content_height,
                                                 target_content_width, target_content_height,
                                                 scaling_rule, bleed_mm=3)
        
        # Format and display both
        self._set_info_text(self.info_cover_text, self._format_impact(cover_impact))
        self._set_info_text(self.info_content_text, self._format_impact(content_impact))
    
    def _format_impact(self, impact):
        """Format resize impact information for display.
        
        Args:
            impact: Impact dictionary from calculate_resize_impact
            
        Returns:
            Formatted text string
        """
        lines = []
        
        # Aspect ratio change
        aspect_diff_pct = impact['aspect_ratio_change_pct']
        if aspect_diff_pct > 0.01:
            lines.append(f'Aspect ratio: +{aspect_diff_pct:.1f}% (wider)\n')
        elif aspect_diff_pct < -0.01:
            lines.append(f'Aspect ratio: {aspect_diff_pct:.1f}% (narrower)\n')
        else:
            lines.append(f'Aspect ratio: 0% (same)\n')
        
        # Scaling factors
        if impact['scale_x'] != impact['scale_y']:
            lines.append(f'Scaling: {impact["scale_x"]*100:.1f}% H, {impact["scale_y"]*100:.1f}% V\n')
        else:
            lines.append(f'Scaling: {impact["scale_x"]*100:.1f}% (uniform)\n')
        
        # Cropping
        total_crop = (impact['crop_left_mm'] + impact['crop_right_mm'] + 
                     impact['crop_top_mm'] + impact['crop_bottom_mm'])
        if total_crop > 0.1:
            lines.append(f'\nCrop from edges:')
            if impact['crop_left_mm'] > 0.1 or impact['crop_right_mm'] > 0.1:
                lines.append(f'  H: {impact["crop_left_mm"]:.1f} mm L, {impact["crop_right_mm"]:.1f} mm R')
            if impact['crop_top_mm'] > 0.1 or impact['crop_bottom_mm'] > 0.1:
                lines.append(f'  V: {impact["crop_top_mm"]:.1f} mm T, {impact["crop_bottom_mm"]:.1f} mm B')
            lines.append(f'  Total: {total_crop:.1f} mm\n')
        else:
            lines.append(f'\nNo page edge cropping\n')
        
        # Margins
        total_margin = (impact['margin_left_mm'] + impact['margin_right_mm'] + 
                       impact['margin_top_mm'] + impact['margin_bottom_mm'])
        if total_margin > 0.1:
            lines.append(f'\nMargins added:')
            if impact['margin_left_mm'] > 0.1 or impact['margin_right_mm'] > 0.1:
                lines.append(f'  H: {impact["margin_left_mm"]:.1f} mm L, {impact["margin_right_mm"]:.1f} mm R')
            if impact['margin_top_mm'] > 0.1 or impact['margin_bottom_mm'] > 0.1:
                lines.append(f'  V: {impact["margin_top_mm"]:.1f} mm T, {impact["margin_bottom_mm"]:.1f} mm B')
            lines.append(f'  Total: {total_margin:.1f} mm\n')
        else:
            lines.append(f'\nNo margins added\n')
        
        # Photo cropping
        if impact['photo_crop_pct'] > 0.1:
            lines.append(f'\nEst. photo crop: {impact["photo_crop_pct"]:.1f}%')
        
        return '\n'.join(lines)
    
    def _set_info_text(self, text_widget, text):
        """Set a text widget content.
        
        Args:
            text_widget: Text widget to update
            text: Text to display
        """
        text_widget.config(state='normal')
        text_widget.delete('1.0', 'end')
        text_widget.insert('1.0', text)
        text_widget.config(state='disabled')
    
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
        target_cover_width = dimensions['coverWidth'] / 2
        target_cover_height = dimensions['coverHeight']
        target_content_width = dimensions['pageWidth'] / 2
        target_content_height = dimensions['pageHeight']
        
        # Get selected scaling rule
        scaling_rule = self.scaling_var.get()
        
        # Create ResizeTransformer for covers
        cover_transformer = ResizeTransformer(
            self.current_cover_width,
            self.current_cover_height,
            int(target_cover_width),
            int(target_cover_height),
            scaling_rule,
            bleed_mm=3
        )
        
        # Create ResizeTransformer for content pages
        content_transformer = ResizeTransformer(
            self.current_content_width,
            self.current_content_height,
            int(target_content_width),
            int(target_content_height),
            scaling_rule,
            bleed_mm=3
        )
        
        # Set transformers on the viewer (triggers re-render)
        self.viewer.set_resize_transformers(cover_transformer, content_transformer)
        
        # Don't destroy the window - user may want to adjust settings
    
    def _save_resized(self):
        """Save the resized photobook (not yet implemented)."""
        pass


def open_resize_window(parent, viewer, mcf_file_path):
    """Open the resize book window.
    
    Args:
        parent: Parent Tk window
        viewer: LayoutViewer instance
        mcf_file_path: Path to the MCF file
    """
    ResizeWindow(parent, viewer, mcf_file_path)
