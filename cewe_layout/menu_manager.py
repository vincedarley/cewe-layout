"""Menubar manager for QLayout - provides unified menu creation for welcome and album windows."""
import tkinter as tk
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class MenuManager:
    """Manages menubar creation for different window modes."""
    
    def __init__(self, window, recent_albums_manager, tk_root=None):
        """Initialize menu manager.
        
        Args:
            window: Tk window or Toplevel where menu will be attached
            recent_albums_manager: RecentAlbumsManager instance for Recent Albums menu
            tk_root: Optional Tk root window (needed if window is a Toplevel for createcommand calls)
        """
        self.window = window
        self.recent_albums = recent_albums_manager
        
        # Get the Tk root for createcommand operations
        # If window is a Toplevel, use tk_root; otherwise use window itself
        if tk_root is not None:
            self.tk_root = tk_root
        else:
            # Try to find the root window
            try:
                self.tk_root = window.winfo_toplevel()
                # If this is a Toplevel, try to get the actual root
                if isinstance(self.tk_root, tk.Toplevel):
                    self.tk_root = tk._default_root or window
            except:
                self.tk_root = tk._default_root or window
    
    def create_welcome_menu(self, on_open_album, on_quit):
        """Create menubar for welcome screen (no album loaded).
        
        Args:
            on_open_album: Callback(album_path) called when album selected (from Open or Recent)
            on_quit: Callback() to quit the application
        """
        try:
            menubar = tk.Menu(self.window)
            
            # File menu
            file_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label='File', menu=file_menu)
            
            # Open Album command
            def prompt_open_album():
                from tkinter import filedialog
                album_file = filedialog.askopenfilename(
                    title='Open CEWE Album (.mcf file inside .xmcf bundle, or standalone .mcf)',
                    filetypes=[
                        ('CEWE Album Files', '*.mcf'),
                        ('All Files', '*.*')
                    ]
                )
                if album_file:
                    on_open_album(album_file)
            
            file_menu.add_command(
                label='Open Album...', 
                accelerator='Cmd+O' if sys.platform == 'darwin' else 'Ctrl+O',
                command=prompt_open_album
            )
            file_menu.add_separator()
            
            # Recent albums submenu
            self._build_recent_albums_menu(file_menu, on_open_album)
            
            file_menu.add_separator()
            file_menu.add_command(
                label='Quit', 
                accelerator='Cmd+Q' if sys.platform == 'darwin' else 'Ctrl+Q',
                command=on_quit
            )
            
            # macOS-specific app menu (use tk_root for createcommand)
            if sys.platform == 'darwin':
                try:
                    self.tk_root.createcommand('::tk::mac::Quit', on_quit)
                    
                    app_menu = tk.Menu(menubar, name='apple', tearoff=0)
                    menubar.add_cascade(menu=app_menu)
                    app_menu.add_command(label='About QLayout', command=lambda: None)  # Placeholder
                    app_menu.add_separator()
                except tk.TclError:
                    pass
            
            self.window.config(menu=menubar)
            
            # Set up keyboard shortcuts (bind to window)
            modifier = 'Command' if sys.platform == 'darwin' else 'Control'
            self.window.bind(f'<{modifier}-o>', lambda e: prompt_open_album())
            self.window.bind(f'<{modifier}-O>', lambda e: prompt_open_album())
            
        except Exception as e:
            logger.warning(f'Failed to setup welcome menu: {e}')
    
    def create_album_menu(self, viewer):
        """Create menubar for album window (album loaded).
        
        Args:
            viewer: LayoutViewer instance providing menu callbacks
        """
        try:
            menubar = tk.Menu(self.window)
            
            # File menu
            file_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label='File', menu=file_menu)
            file_menu.add_command(label='Open Album...', accelerator='Cmd+O', command=viewer._prompt_open_album)
            file_menu.add_command(label='Add Photos...', accelerator='Cmd+A', command=viewer._prompt_add_photos)
            file_menu.add_separator()
            file_menu.add_command(label='Save Modified', accelerator='Cmd+S', command=viewer.save_layout)
            file_menu.add_command(label='Export PDF...', accelerator='Cmd+P', command=viewer.export_to_pdf)
            file_menu.add_separator()
            
            # Recent albums submenu
            self._build_recent_albums_menu(file_menu, viewer._open_album_in_new_window)
            
            file_menu.add_separator()
            file_menu.add_command(label='Close Window', accelerator='Cmd+W', command=viewer.close_window)
            
            # Edit menu
            edit_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label='Edit', menu=edit_menu)
            edit_menu.add_command(label='Undo Layout', accelerator='Cmd+Z', command=viewer.undo_layout)
            edit_menu.add_separator()
            edit_menu.add_command(label='Previous Page', accelerator='←', command=viewer.prev_page)
            edit_menu.add_command(label='Next Page', accelerator='→', command=viewer.next_page)
            edit_menu.add_separator()
            edit_menu.add_command(label='Use Original Page', command=viewer.use_original)
            
            # Layout menu
            layout_menu = tk.Menu(menubar, tearoff=0)
            menubar.add_cascade(label='Layout', menu=layout_menu)
            layout_menu.add_command(label='Generate Layout', accelerator='Cmd+R', command=viewer._generate_layout)
            layout_menu.add_command(label='New Text Box', accelerator='Cmd+Shift+N', command=viewer.add_text_box)
            
            # Window menu (standard macOS menu)
            window_menu = tk.Menu(menubar, name='window', tearoff=0)
            menubar.add_cascade(label='Window', menu=window_menu)
            
            # macOS-specific app menu (use tk_root for createcommand)
            if sys.platform == 'darwin':
                try:
                    self.tk_root.createcommand('tk::mac::ShowPreferences', viewer._show_preferences)
                    # Cmd+Q should quit the entire app, not just close the window
                    # Use tk._default_root which is the first Tk instance
                    def quit_app():
                        """Quit the entire application."""
                        import tkinter as tk
                        if tk._default_root:
                            tk._default_root.quit()
                        else:
                            # Fallback: quit current root
                            self.tk_root.quit()
                    
                    self.tk_root.createcommand('::tk::mac::Quit', quit_app)
                    
                    app_menu = tk.Menu(menubar, name='apple', tearoff=0)
                    menubar.add_cascade(menu=app_menu)
                    app_menu.add_command(label='About QLayout', command=viewer._show_about)
                    app_menu.add_separator()
                except tk.TclError:
                    pass
            
            # Apply menu to both windows
            self.window.config(menu=menubar)
            viewer.ctrlWin.config(menu=menubar)
                
        except Exception as e:
            logger.warning(f'Failed to setup album menu: {e}')
    
    def _build_recent_albums_menu(self, parent_menu, on_select_album):
        """Build Recent Albums submenu and add to parent menu.
        
        Args:
            parent_menu: Parent menu to add Recent Albums submenu to
            on_select_album: Callback(album_path) when album selected
        """
        recent_albums = self.recent_albums.list_all()
        
        if not recent_albums:
            parent_menu.add_command(label='Recent Albums', state='disabled')
            return
        
        recent_menu = tk.Menu(parent_menu, tearoff=0)
        parent_menu.add_cascade(label='Recent Albums', menu=recent_menu)
        
        # Add each recent album as a menu item
        for album in recent_albums:
            album_name = album.get('name', 'Unknown')
            album_path = album.get('path')
            
            def open_album(path=album_path):
                """Open album."""
                on_select_album(path)
            
            recent_menu.add_command(label=album_name, command=open_album)
        
        # Add separator and Clear option
        recent_menu.add_separator()
        
        def clear_recent():
            self.recent_albums.clear()
            # Note: Menu won't update until app restart or menu rebuild
        
        recent_menu.add_command(label='Clear Recent Albums', command=clear_recent)
