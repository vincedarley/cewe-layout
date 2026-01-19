"""GUI for resizing photobooks to different dimensions, and merging books."""

import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import logging

from .book.utils import BOOK_SIZES, find_closest_book_size, calculate_resize_impact, ResizeTransformer
from cewe_layout.mcf_io.mcf_writer import photobook_write_to_mcf
from .book.photobook_transform import create_photobook_with_inside_covers_at_end, merge_photobooks, create_photobook_copy
from cewe_layout.mcf_io.mcf_parser import parse_mcf_from_path, extract_pages_info

logger = logging.getLogger(__name__)


class TransformWindow:
    """Window for transforming, resizing a photobook to different dimensions."""
    
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
        
        # Track loaded merge book
        self.merge_book = None
        self.merge_source_dir = None
        self.merge_book_name = None
        
        # Create toplevel window
        self.window = tk.Toplevel(parent)
        self.window.title('Transform Book')
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
            
            # Create container for side-by-side layout
            dims_container = ttk.Frame(section_frame)
            dims_container.pack(fill='x', pady=(0, 10))
            
            # Left column: Cover pages
            cover_frame = ttk.Frame(dims_container)
            cover_frame.pack(side='left', fill='both', expand=True, padx=(0, 10))
            
            cover_label = ttk.Label(cover_frame, text='Cover pages:', font=('TkDefaultFont', 10, 'bold'))
            cover_label.pack(anchor='w')
            cover_size_text = f'{cover_width_cm:.1f} cm × {cover_height_cm:.1f} cm (aspect ratio: {cover_aspect:.2f})'
            cover_size_label = ttk.Label(cover_frame, text=cover_size_text)
            cover_size_label.pack(anchor='w', padx=(10, 0))
            cover_mcf_text = f'({cover_width_mcf} × {cover_height_mcf} MCF units)'
            cover_mcf_label = ttk.Label(cover_frame, text=cover_mcf_text, foreground='gray')
            cover_mcf_label.pack(anchor='w', padx=(10, 0))
            
            # Right column: Content pages
            content_frame = ttk.Frame(dims_container)
            content_frame.pack(side='left', fill='both', expand=True)
            
            content_label = ttk.Label(content_frame, text='Content pages:', font=('TkDefaultFont', 10, 'bold'))
            content_label.pack(anchor='w')
            content_size_text = f'{content_width_cm:.1f} cm × {content_height_cm:.1f} cm (aspect ratio: {content_aspect:.2f})'
            content_size_label = ttk.Label(content_frame, text=content_size_text)
            content_size_label.pack(anchor='w', padx=(10, 0))
            content_mcf_text = f'({content_width_mcf} × {content_height_mcf} MCF units)'
            content_mcf_label = ttk.Label(content_frame, text=content_mcf_text, foreground='gray')
            content_mcf_label.pack(anchor='w', padx=(10, 0))
            
            # Show page count (centered below both columns)
            page_count_text = f'{self.book.get_page_count()} pages in book'
            page_count_label = ttk.Label(section_frame, text=page_count_text)
            page_count_label.pack()
            
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
        self.size_options = ["No change"]
        self.size_keys = ["NO_CHANGE"]
        
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
        self.info_cover_text = tk.Text(cover_frame, height=8, width=30, wrap='word',
                                       font=('TkDefaultFont', 9), state='disabled')
        self.info_cover_text.pack(fill='both', expand=True)
        
        # Right side: Content pages
        content_frame = ttk.LabelFrame(info_container, text='Content Pages', padding=5)
        content_frame.pack(side='left', fill='both', expand=True)
        self.info_content_text = tk.Text(content_frame, height=8, width=30, wrap='word',
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
        
        # Get transformers (will be None if "No change" is selected)
        cover_transformer, content_transformer = self._get_transformers()
        
        # Handle "No change" case
        if cover_transformer is None or content_transformer is None:
            self._set_info_text(self.info_cover_text, 'No transformation applied')
            self._set_info_text(self.info_content_text, 'No transformation applied')
            return
        
        # Calculate resize impact using the actual transformers
        cover_impact = calculate_resize_impact(
            self.current_cover_width, 
            self.current_cover_height,
            cover_transformer
        )
        
        content_impact = calculate_resize_impact(
            self.current_content_width, 
            self.current_content_height,
            content_transformer
        )
        
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
            lines.append(f'Crop from edges:')
            if impact['crop_left_mm'] > 0.1 or impact['crop_right_mm'] > 0.1:
                lines.append(f'  H: {impact["crop_left_mm"]:.1f} mm L, {impact["crop_right_mm"]:.1f} mm R')
            if impact['crop_top_mm'] > 0.1 or impact['crop_bottom_mm'] > 0.1:
                lines.append(f'  V: {impact["crop_top_mm"]:.1f} mm T, {impact["crop_bottom_mm"]:.1f} mm B')
            lines.append(f'  Total: {total_crop:.1f} mm\n')
        else:
            lines.append(f'No page edge cropping\n')
        
        # Margins
        total_margin = (impact['margin_left_mm'] + impact['margin_right_mm'] + 
                       impact['margin_top_mm'] + impact['margin_bottom_mm'])
        if total_margin > 0.1:
            lines.append(f'Margins added:')
            if impact['margin_left_mm'] > 0.1 or impact['margin_right_mm'] > 0.1:
                lines.append(f'  H: {impact["margin_left_mm"]:.1f} mm L, {impact["margin_right_mm"]:.1f} mm R')
            if impact['margin_top_mm'] > 0.1 or impact['margin_bottom_mm'] > 0.1:
                lines.append(f'  V: {impact["margin_top_mm"]:.1f} mm T, {impact["margin_bottom_mm"]:.1f} mm B')
            lines.append(f'  Total: {total_margin:.1f} mm\n')
        else:
            lines.append(f'No margins added\n')
        
        # Photo cropping
        if impact['photo_crop_pct'] > 0.1:
            lines.append(f'Est. photo crop: {impact["photo_crop_pct"]:.1f}%')
        
        return ''.join(lines)
    
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
    
    def _get_transformers(self):
        """Get resize transformers for current size and scaling selections.
        
        Returns:
            Tuple of (cover_transformer, content_transformer) or (None, None) if invalid or no change
        """
        # Get selected target size
        selected = self.size_var.get()
        if not selected or selected not in self.size_options:
            return None, None
        
        # Find the corresponding book size key
        selected_index = self.size_options.index(selected)
        selected_key = self.size_keys[selected_index]
        
        # Handle "No change" option
        if selected_key == "NO_CHANGE":
            return None, None
        
        # Get target dimensions
        dimensions = BOOK_SIZES[selected_key]
        target_cover_width = dimensions['coverWidth'] / 2
        target_cover_height = dimensions['coverHeight']
        target_content_width = dimensions['pageWidth'] / 2
        target_content_height = dimensions['pageHeight']
        
        # Get selected scaling rule
        scaling_rule = self.scaling_var.get()
        
        # Create ResizeTransformers
        cover_transformer = ResizeTransformer(
            self.current_cover_width,
            self.current_cover_height,
            int(target_cover_width),
            int(target_cover_height),
            scaling_rule,
            bleed_mm=3
        )
        
        content_transformer = ResizeTransformer(
            self.current_content_width,
            self.current_content_height,
            int(target_content_width),
            int(target_content_height),
            scaling_rule,
            bleed_mm=3
        )
        
        return cover_transformer, content_transformer
    
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
        
        # Merge book button and info label
        merge_frame = ttk.Frame(section_frame)
        merge_frame.pack(fill='x', pady=(0, 10))
        
        merge_btn = ttk.Button(merge_frame, text='Merge Book...', command=self._load_merge_book)
        merge_btn.pack(side='left', padx=(0, 5))
        
        self.merge_info_label = ttk.Label(merge_frame, text='', foreground='gray')
        self.merge_info_label.pack(side='left', fill='x', expand=True)
        
        # Name of new book label and input field on same line
        name_frame = ttk.Frame(section_frame)
        name_frame.pack(fill='x', pady=(0, 10))
        
        name_label = ttk.Label(name_frame, text='Name of new book:')
        name_label.pack(side='left', padx=(0, 5))
        
        # Get photobook name from the directory containing data.mcf (same logic as GUI titlebar)
        if self.mcf_file_path:
            # Get the parent directory name (e.g., "Test-album.xmcf" not "data.mcf")
            current_name = os.path.basename(os.path.dirname(self.mcf_file_path))
        else:
            current_name = 'Unknown'
        
        self.name_var = tk.StringVar(value=current_name)
        name_entry = ttk.Entry(name_frame, textvariable=self.name_var)
        name_entry.pack(side='left', fill='x', expand=True)
        
        # Photo prefix label and input field on same line
        prefix_frame = ttk.Frame(section_frame)
        prefix_frame.pack(fill='x', pady=(0, 10))
        
        prefix_label = ttk.Label(prefix_frame, text='Rename all photos to have a unified prefix:')
        prefix_label.pack(side='left', padx=(0, 5))
        
        self.photo_prefix_var = tk.StringVar(value='')
        prefix_entry = ttk.Entry(prefix_frame, textvariable=self.photo_prefix_var, width=15)
        prefix_entry.pack(side='left')
        
        # Save button with retain inside covers checkbox on same line
        save_frame = ttk.Frame(section_frame)
        save_frame.pack(fill='x')
        
        self.retain_inside_covers_var = tk.BooleanVar(value=False)
        retain_checkbox = ttk.Checkbutton(
            save_frame,
            text='Retain inside covers at end (adds 4 pages)',
            variable=self.retain_inside_covers_var
        )
        retain_checkbox.pack(side='left', padx=(0, 10))
        
        save_btn = ttk.Button(save_frame, text='Save Transformed Book', command=self._save_resized)
        save_btn.pack(side='left', fill='x', expand=True)
    
    def _view_resized(self):
        """View the resized photobook."""
        cover_transformer, content_transformer = self._get_transformers()
        
        # Note: transformers can be None for "No change" option
        # Set transformers on the viewer (triggers re-render)
        self.viewer.set_resize_transformers(cover_transformer, content_transformer)
        
        # Don't destroy the window - user may want to adjust settings
    
    def _save_resized(self):
        """Save the resized photobook.
        
        An important detail is our treatment of "insidecovers". In CEWE Creator's MCF structure, these are
        the left hand page inside the front cover, before the 1st content page (which is always a right hand page),
        and the right hand page inside the back cover, after the last content page (which is always a left hand page).
        The inside front cover is "page 0", and the inside back cover is "page N+1", where N is the number
        of normal content pages (in CEWE's approach). Inside covers are ALWAYS EMPTY in CEWE books.  The
        MCF file format is actually perfectly capable of placing content onto these two special pages, but
        even if there is content, CEWE Creator ignores it, and their printing process certainly ignores it
        (at least for hardback books, where the inside cover does not use nice photographic paper).
        
        Given this, there are a few possible scenarios:
        - The input photobook has no pages representing inside-covers (e.g. it is derived from a PDF file which
          has a front cover page which is followed directly by the first content page (page 1 in MCF). In this
          case we can safely create empty insidecovers in mcf_io and we don't lose anything.
        - The input photobook has pages representing inside-covers, but they are empty. In this
          case we can safely create empty insidecovers in mcf_io and we don't lose anything.
        - The input photobook has pages representing inside-covers, but they are NOT empty. In this case we need
          to make a choice: (a) we can place the content of those pages on the MCF pages 0 and N+1, where they will
          be visible and editable in QLayout, but ignored by CEWE Creator, (b) we can ignore and discard that content,
          or (c) we can create some extra pages at the end of the book for that content, so it is not discarded, and
          the user will presumably need to manually edit the photobook to keep whatever aspects of the content they wish.
        
        In aggregate these options usefully reduce to insidecovers as "notProvided", "ignoreProvided", 
        "retainWithIncompatibility" or "retainAtEnd". We don't provide control over all of these options,
        however. Our approach is that if inside covers are provided they are retained with incompatibility
        (i.e. CEWE Creator will ignore them).

        We do want to allow the user to save the resized photobook in a way that makes this content
        available to CEWE. So we will provide a UI option to "retain at end". This will create new pages.

        Anecdotally, some PDF files have insidecovers, some do not.  Mimeo imports have inside covers which can have content.
        """
        # Get output directory name from UI
        output_name = self.name_var.get().strip()
        if not output_name:
            messagebox.showerror("Error", "Please enter a name for the resized photobook")
            return
        
        # Get transformers (can be None for "No change" option)
        cover_transformer, content_transformer = self._get_transformers()
        
        # Get scaling rule for success message
        scaling_rule = self.scaling_var.get() if cover_transformer is not None else "No change"
        
        # Determine output directory path (sibling to current photobook)
        if not self.mcf_file_path:
            messagebox.showerror("Error", "No photobook file path available")
            return
        
        current_dir = Path(self.mcf_file_path).parent
        parent_dir = current_dir.parent
        output_dir = parent_dir / output_name
        
        # Check if output directory already exists
        if output_dir.exists():
            response = messagebox.askyesno(
                "Directory Exists",
                f"Directory '{output_name}' already exists. Overwrite?"
            )
            if not response:
                return
            # Remove existing directory
            shutil.rmtree(output_dir)
        
        try:
            # Create output directory
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Get photo prefix from UI (empty string if not provided)
            photo_prefix = self.photo_prefix_var.get().strip() or None
            
            # Check if we need to rearrange inside covers
            inside_cover_info = ""
            
            if self.retain_inside_covers_var.get() and self.book.has_content_on_inside_covers():
                # Move inside covers to end as new content pages
                logger.info("Transforming photobook to move inside covers to end")
                book_to_save = create_photobook_with_inside_covers_at_end(
                    self.book,
                    current_dir,
                    output_dir,
                    photo_prefix
                )
                
                N = self.book.get_content_page_count()
                inside_cover_info = (f"\n\nInside cover content moved to pages {N+2} and {N+3}\n"
                                   f"Total pages: {N+4} (was {N})")
            else:
                # Normal path - copy book with all images
                logger.info("Creating photobook copy with all images")
                book_to_save = create_photobook_copy(
                    self.book,
                    current_dir,
                    output_dir,
                    photo_prefix
                )
            
            # Merge another book if one was loaded
            merge_info = ""
            if self.merge_book is not None:
                logger.info(f"Merging in loaded book: {self.merge_book_name}")
                N1 = book_to_save.get_content_page_count()
                N2 = self.merge_book.get_content_page_count()
                
                book_to_save = merge_photobooks(
                    book_to_save,
                    self.merge_book,
                    current_dir,
                    self.merge_source_dir,
                    output_dir,
                    photo_prefix
                )
                
                merge_info = (f"\n\nMerged with {self.merge_book_name}:\n"
                            f"  Book 1: {N1} pages\n"
                            f"  Book 2: {N2} pages (covers converted to content)\n"
                            f"  Result: {N1+N2+2} pages")
            
            # Write the transformed MCF file
            photobook_write_to_mcf(
                book_to_save,
                str(output_dir),
                verbose=True,
                cover_transformer=cover_transformer,
                content_transformer=content_transformer
            )
            
            # Success message
            photo_count = self._count_photos(output_dir)
            
            messagebox.showinfo(
                "Success",
                f"Photobook saved to:\n{output_dir}\n\n"
                f"Copied {photo_count} photos\n"
                f"Scaling: {scaling_rule}"
                f"{inside_cover_info}"
                f"{merge_info}"
            )
            
        except Exception as e:
            logger.exception("Failed to save resized photobook")
            messagebox.showerror("Error", f"Failed to save resized photobook:\n{str(e)}")
            # Clean up partial output on failure
            if output_dir.exists():
                shutil.rmtree(output_dir)
            raise
        
    def _count_photos(self, directory: Path) -> int:
        """Count image files in a directory.
        
        Args:
            directory: Directory to count photos in
            
        Returns:
            Total count of image files
        """
        return (len(list(directory.glob('*.[jJ][pP][gG]'))) +
                len(list(directory.glob('*.[jJ][pP][eE][gG]'))) +
                len(list(directory.glob('*.[pP][nN][gG]'))) +
                len(list(directory.glob('*.[hH][eE][iI][fF]'))) +
                len(list(directory.glob('*.[hH][eE][iI][cC]'))))
    
    def _load_merge_book(self):
        """Load another photobook to merge (doesn't write anything yet)."""
        file_path = filedialog.askopenfilename(
            title="Select photobook file to merge (.xmcf or .mcf_io file)",
        )
        if not file_path:
            return
        
        file_path = Path(file_path)
        
        # Use resolve_mcf_path to handle both files and directories
        from cewe_layout.mcf_io.mcf_parser import resolve_mcf_path
        try:
            mcf_file = Path(resolve_mcf_path(str(file_path)))
            source_dir = mcf_file.parent
        except FileNotFoundError as e:
            messagebox.showerror("Error", f"Could not find MCF file: {e}")
            return
        
        try:
            # Load the second photobook
            logger.info(f"Loading second photobook from {mcf_file}")
            mcf_root = parse_mcf_from_path(str(mcf_file))
            book = extract_pages_info(mcf_root)
            
            # Store for later use
            self.merge_book = book
            self.merge_source_dir = source_dir
            self.merge_book_name = source_dir.name
            
            # Count photos in source directory
            photo_count = self._count_photos(source_dir)
            page_count = book.get_content_page_count()
            
            # Update info label
            self.merge_info_label.config(
                text=f"{self.merge_book_name}: {page_count} pages, {photo_count} photos",
                foreground='blue'
            )
            
            logger.info(f"Loaded merge book: {page_count} pages, {photo_count} photos")
            
        except Exception as e:
            logger.exception("Failed to load merge book")
            messagebox.showerror("Error", f"Failed to load merge book:\n{str(e)}")
            self.merge_book = None
            self.merge_source_dir = None
            self.merge_book_name = None
            self.merge_info_label.config(text='', foreground='gray')


def open_transform_window(parent, viewer, mcf_file_path):
    """Open the resize book window.
    
    Args:
        parent: Parent Tk window
        viewer: LayoutViewer instance
        mcf_file_path: Path to the MCF file
    """
    TransformWindow(parent, viewer, mcf_file_path)
