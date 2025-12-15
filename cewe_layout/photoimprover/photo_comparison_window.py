"""Photo Comparison window for reviewing and accepting photo improvements."""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from pathlib import Path
import logging
from typing import Callable, List, Dict
from .photo_improver import PhotoMatch

logger = logging.getLogger(__name__)


class PhotoComparisonWindow:
    """Window for comparing photobook photos with candidate replacements."""
    
    def __init__(self, parent, matches: Dict[str, List[PhotoMatch]], accept_callback: Callable):
        """Create photo comparison window.
        
        Args:
            parent: Parent tkinter window
            matches: Dict mapping photobook_path -> List[PhotoMatch]
            accept_callback: Function to call when user accepts a replacement
                           Signature: (photobook_path, replacement_path)
        """
        self.parent = parent
        self.matches = matches
        self.accept_callback = accept_callback
        self.current_photo_idx = 0
        self.current_match_idx = 0
        
        # Convert matches dict to list for easy navigation
        self.photo_paths = list(matches.keys())
        
        if not self.photo_paths:
            logger.info("No matches to display")
            return
        
        # Create window
        self.window = tk.Toplevel(parent)
        self.window.title("Photo Comparison")
        self.window.geometry("1200x800")
        
        # Image caches
        self.image_cache = {}
        
        # Build UI
        self._create_widgets()
        self._display_current_match()
    
    def _create_widgets(self):
        """Create all UI widgets."""
        # Top navigation bar
        nav_frame = ttk.Frame(self.window)
        nav_frame.pack(side='top', fill='x', padx=10, pady=5)
        
        ttk.Label(nav_frame, text="Photo:").pack(side='left', padx=(0,5))
        self.photo_label = ttk.Label(nav_frame, text="", font=('TkDefaultFont', 10, 'bold'))
        self.photo_label.pack(side='left', padx=(0,20))
        
        ttk.Button(nav_frame, text="Previous Photo", command=self._prev_photo).pack(side='left', padx=5)
        ttk.Button(nav_frame, text="Next Photo", command=self._next_photo).pack(side='left', padx=5)
        
        ttk.Label(nav_frame, text="Match:").pack(side='left', padx=(20,5))
        self.match_label = ttk.Label(nav_frame, text="")
        self.match_label.pack(side='left', padx=(0,20))
        
        ttk.Button(nav_frame, text="Prev Match", command=self._prev_match).pack(side='left', padx=5)
        ttk.Button(nav_frame, text="Next Match", command=self._next_match).pack(side='left', padx=5)
        
        # Main comparison area
        main_frame = ttk.Frame(self.window)
        main_frame.pack(side='top', fill='both', expand=True, padx=10, pady=10)
        
        # Left side - Current (Photobook)
        left_frame = ttk.LabelFrame(main_frame, text="Current (Photobook)", padding=10)
        left_frame.pack(side='left', fill='both', expand=True, padx=(0,5))
        
        self.current_image_label = ttk.Label(left_frame)
        self.current_image_label.pack(side='top', fill='both', expand=True)
        
        self.current_info_text = tk.Text(left_frame, height=8, wrap='word', state='disabled')
        self.current_info_text.pack(side='bottom', fill='x', pady=(10,0))
        
        # Right side - Candidate (Replacement)
        right_frame = ttk.LabelFrame(main_frame, text="Candidate (Replacement)", padding=10)
        right_frame.pack(side='left', fill='both', expand=True, padx=(5,0))
        
        self.candidate_image_label = ttk.Label(right_frame)
        self.candidate_image_label.pack(side='top', fill='both', expand=True)
        
        self.candidate_info_text = tk.Text(right_frame, height=8, wrap='word', state='disabled')
        self.candidate_info_text.pack(side='bottom', fill='x', pady=(10,0))
        
        # Bottom action bar
        action_frame = ttk.Frame(self.window)
        action_frame.pack(side='bottom', fill='x', padx=10, pady=10)
        
        # Quality indicator
        self.quality_label = ttk.Label(action_frame, text="", font=('TkDefaultFont', 10, 'bold'))
        self.quality_label.pack(side='left', padx=(0,20))
        
        # Accept button (prominent)
        self.accept_btn = ttk.Button(action_frame, text="Accept Replacement (⏎)", 
                                     command=self._accept_current, style='Accent.TButton')
        self.accept_btn.pack(side='left', padx=5)
        
        # Skip button
        ttk.Button(action_frame, text="Skip", command=self._next_match).pack(side='left', padx=5)
        
        # Close button
        ttk.Button(action_frame, text="Close", command=self.window.destroy).pack(side='right', padx=5)
        
        # Bind keyboard shortcuts
        self.window.bind('<Return>', lambda e: self._accept_current())
        self.window.bind('<Right>', lambda e: self._next_match())
        self.window.bind('<Left>', lambda e: self._prev_match())
        self.window.bind('<Up>', lambda e: self._prev_photo())
        self.window.bind('<Down>', lambda e: self._next_photo())
    
    def _display_current_match(self):
        """Display the current match pair."""
        if self.current_photo_idx >= len(self.photo_paths):
            # No more photos
            self.window.destroy()
            return
        
        photobook_path = self.photo_paths[self.current_photo_idx]
        matches_for_photo = self.matches[photobook_path]
        
        if self.current_match_idx >= len(matches_for_photo):
            # No more matches for this photo, move to next photo
            self._next_photo()
            return
        
        match = matches_for_photo[self.current_match_idx]
        
        # Update navigation labels
        photo_name = Path(photobook_path).name
        self.photo_label.config(text=f"{self.current_photo_idx + 1}/{len(self.photo_paths)} - {photo_name}")
        self.match_label.config(text=f"{self.current_match_idx + 1}/{len(matches_for_photo)} ({match.similarity_score*100:.1f}% similar)")
        
        # Display images
        self._display_image(photobook_path, self.current_image_label, is_current=True)
        self._display_image(match.candidate_path, self.candidate_image_label, is_current=False)
        
        # Display info
        self._display_info(match.photobook_metrics, self.current_info_text, Path(photobook_path).name)
        self._display_info(match.candidate_metrics, self.candidate_info_text, Path(match.candidate_path).name)
        
        # Update quality indicator
        if match.is_improvement():
            self.quality_label.config(text="✓ Likely Improvement", foreground='green')
        else:
            self.quality_label.config(text="⚠ Check Quality", foreground='orange')
    
    def _display_image(self, path: str, label: ttk.Label, is_current: bool):
        """Display an image in a label, scaled to fit."""
        try:
            # Load and resize image
            img = Image.open(path)
            
            # Calculate target size (fit within 500x400)
            max_w, max_h = 500, 400
            img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(img)
            
            # Keep reference to prevent garbage collection
            label.image = photo
            label.config(image=photo)
            
        except Exception as e:
            logger.error(f"Failed to display image {path}: {e}")
            label.config(text=f"Error loading image:\n{e}")
    
    def _display_info(self, metrics: dict, text_widget: tk.Text, filename: str):
        """Display image info in a text widget."""
        text_widget.config(state='normal')
        text_widget.delete('1.0', 'end')
        
        info_lines = [
            f"Filename: {filename}",
            f"Resolution: {metrics['width']} × {metrics['height']} px",
            f"Megapixels: {metrics['megapixels']:.2f} MP",
            f"File Size: {metrics['file_size_kb']:.1f} KB",
            f"Format: {metrics['format']}"
        ]
        
        text_widget.insert('1.0', '\n'.join(info_lines))
        text_widget.config(state='disabled')
    
    def _accept_current(self):
        """Accept the current replacement."""
        if self.current_photo_idx >= len(self.photo_paths):
            return
        
        photobook_path = self.photo_paths[self.current_photo_idx]
        matches_for_photo = self.matches[photobook_path]
        
        if self.current_match_idx >= len(matches_for_photo):
            return
        
        match = matches_for_photo[self.current_match_idx]
        
        # Call the accept callback
        self.accept_callback(photobook_path, match.candidate_path)
        
        # Remove this photo from the list (all matches accepted)
        del self.matches[photobook_path]
        self.photo_paths = list(self.matches.keys())
        
        # Stay at same index (which now points to next photo)
        self.current_match_idx = 0
        
        # Display next match or close if done
        if self.photo_paths:
            self._display_current_match()
        else:
            self.window.destroy()
    
    def _prev_photo(self):
        """Go to previous photo."""
        if self.current_photo_idx > 0:
            self.current_photo_idx -= 1
            self.current_match_idx = 0
            self._display_current_match()
    
    def _next_photo(self):
        """Go to next photo."""
        if self.current_photo_idx < len(self.photo_paths) - 1:
            self.current_photo_idx += 1
            self.current_match_idx = 0
            self._display_current_match()
    
    def _prev_match(self):
        """Go to previous match for current photo."""
        photobook_path = self.photo_paths[self.current_photo_idx]
        matches_for_photo = self.matches[photobook_path]
        
        if self.current_match_idx > 0:
            self.current_match_idx -= 1
            self._display_current_match()
    
    def _next_match(self):
        """Go to next match for current photo."""
        photobook_path = self.photo_paths[self.current_photo_idx]
        matches_for_photo = self.matches[photobook_path]
        
        if self.current_match_idx < len(matches_for_photo) - 1:
            self.current_match_idx += 1
            self._display_current_match()
        else:
            # No more matches, go to next photo
            self._next_photo()
