"""Preferences dialog for QLayout app.

Provides a user interface for configuring application preferences.
"""

import tkinter as tk
from tkinter import ttk
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class PreferencesDialog:
    """Modal dialog for application preferences."""
    
    def __init__(self, parent, preferences_manager):
        """Initialize preferences dialog.
        
        Args:
            parent: Parent Tkinter window
            preferences_manager: PreferencesManager instance
        """
        self.parent = parent
        self.prefs_mgr = preferences_manager
        self.result = None
        
        # Create top-level window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title('Preferences')
        self.dialog.geometry('500x400')
        self.dialog.resizable(False, False)
        
        # Make modal
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center on parent window (or screen if parent is hidden)
        self.dialog.update_idletasks()
        try:
            if parent.winfo_viewable():
                x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.dialog.winfo_width() // 2)
                y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.dialog.winfo_height() // 2)
            else:
                # Parent is hidden, center on screen
                x = (self.dialog.winfo_screenwidth() // 2) - (self.dialog.winfo_width() // 2)
                y = (self.dialog.winfo_screenheight() // 2) - (self.dialog.winfo_height() // 2)
            self.dialog.geometry(f'+{x}+{y}')
        except tk.TclError:
            # Fall back to default positioning
            pass
        
        self._build_ui()
        self._load_preferences()
        
        # Wait for dialog to close
        parent.wait_window(self.dialog)
    
    def _build_ui(self):
        """Build the preferences dialog UI."""
        # Create notebook (tabbed interface) for different preference categories
        notebook = ttk.Notebook(self.dialog)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # General tab
        general_frame = ttk.Frame(notebook, padding=15)
        notebook.add(general_frame, text='General')
        self._build_general_tab(general_frame)
        
        # Appearance tab
        appearance_frame = ttk.Frame(notebook, padding=15)
        notebook.add(appearance_frame, text='Appearance')
        self._build_appearance_tab(appearance_frame)
        
        # Auto-save tab
        autosave_frame = ttk.Frame(notebook, padding=15)
        notebook.add(autosave_frame, text='Auto-save')
        self._build_autosave_tab(autosave_frame)
        
        # Button frame
        button_frame = ttk.Frame(self.dialog)
        button_frame.pack(fill='x', padx=10, pady=10)
        
        ttk.Button(button_frame, text='Cancel', command=self._on_cancel).pack(side='right', padx=5)
        ttk.Button(button_frame, text='OK', command=self._on_ok).pack(side='right', padx=5)
        ttk.Button(button_frame, text='Reset to Defaults', command=self._on_reset).pack(side='left', padx=5)
    
    def _build_general_tab(self, parent):
        """Build General preferences tab."""
        # Default photos folder
        ttk.Label(parent, text='Default Photos Folder:', font=('default', 10)).pack(anchor='w', pady=(0, 5))
        
        folder_frame = ttk.Frame(parent)
        folder_frame.pack(fill='x', pady=(0, 15))
        
        self.default_folder_var = tk.StringVar(value=self.prefs_mgr.get('default_photos_folder') or '')
        folder_entry = ttk.Entry(folder_frame, textvariable=self.default_folder_var)
        folder_entry.pack(side='left', fill='x', expand=True, padx=(0, 5))
        
        def browse_folder():
            from tkinter.filedialog import askdirectory
            folder = askdirectory(title='Choose Default Photos Folder')
            if folder:
                self.default_folder_var.set(folder)
        
        ttk.Button(folder_frame, text='Browse...', command=browse_folder).pack(side='left')
        
        ttk.Label(parent, text='(Optional) Folder to search for photos by default', 
                  font=('default', 9), foreground='gray').pack(anchor='w')
    
    def _build_appearance_tab(self, parent):
        """Build Appearance preferences tab."""
        # Dark mode option
        self.dark_mode_var = tk.BooleanVar(value=self.prefs_mgr.get('dark_mode_follow_system', True))
        ttk.Checkbutton(parent, text='Follow system appearance (light/dark mode)', 
                       variable=self.dark_mode_var).pack(anchor='w', pady=10)
        
        ttk.Label(parent, text='(Requires restart)', font=('default', 9), foreground='gray').pack(anchor='w', padx=20)
    
    def _build_autosave_tab(self, parent):
        """Build Auto-save preferences tab."""
        # Auto-save enabled
        self.autosave_var = tk.BooleanVar(value=self.prefs_mgr.get('auto_save_enabled', True))
        ttk.Checkbutton(parent, text='Enable auto-save', variable=self.autosave_var).pack(anchor='w', pady=10)
        
        # Auto-save interval
        interval_frame = ttk.Frame(parent)
        interval_frame.pack(fill='x', pady=15)
        
        ttk.Label(interval_frame, text='Auto-save interval:', font=('default', 10)).pack(anchor='w', pady=(0, 5))
        
        interval_subframe = ttk.Frame(interval_frame)
        interval_subframe.pack(anchor='w', padx=20)
        
        self.autosave_interval_var = tk.IntVar(value=self.prefs_mgr.get('auto_save_interval_seconds', 300) // 60)
        
        ttk.Label(interval_subframe, text='Every').pack(side='left', padx=(0, 5))
        spin = ttk.Spinbox(interval_subframe, from_=1, to=60, textvariable=self.autosave_interval_var, width=3)
        spin.pack(side='left')
        ttk.Label(interval_subframe, text='minutes').pack(side='left', padx=(5, 0))
        
        ttk.Label(interval_frame, text='Layout changes will be saved automatically in the background', 
                  font=('default', 9), foreground='gray').pack(anchor='w', padx=20, pady=(5, 0))
    
    def _load_preferences(self):
        """Load current preferences into UI controls."""
        # Already loaded in variable initialization above
        pass
    
    def _on_ok(self):
        """Save preferences and close dialog."""
        updates = {
            'default_photos_folder': self.default_folder_var.get() or None,
            'dark_mode_follow_system': self.dark_mode_var.get(),
            'auto_save_enabled': self.autosave_var.get(),
            'auto_save_interval_seconds': self.autosave_interval_var.get() * 60,
        }
        self.prefs_mgr.set_multiple(updates)
        self.result = True
        self.dialog.destroy()
    
    def _on_cancel(self):
        """Close dialog without saving."""
        self.result = False
        self.dialog.destroy()
    
    def _on_reset(self):
        """Reset all preferences to defaults."""
        from tkinter import messagebox
        
        if messagebox.askyesno('Reset Preferences', 
                               'Reset all preferences to default values?',
                               parent=self.dialog):
            self.prefs_mgr.set_multiple(self.prefs_mgr.DEFAULT_PREFERENCES)
            self._load_preferences()
            # Refresh UI
            self.default_folder_var.set(self.prefs_mgr.get('default_photos_folder') or '')
            self.dark_mode_var.set(self.prefs_mgr.get('dark_mode_follow_system', True))
            self.autosave_var.set(self.prefs_mgr.get('auto_save_enabled', True))
            self.autosave_interval_var.set(self.prefs_mgr.get('auto_save_interval_seconds', 300) // 60)
