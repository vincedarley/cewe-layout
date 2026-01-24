"""Drag-and-drop support for photo files.

On macOS, uses PyObjC to properly handle Photos app file promises.
On other platforms, uses tkinterdnd2 if available.
"""
import platform
import logging
from pathlib import Path

from cewe_layout.utils.file_utils import get_photos_directory

logger = logging.getLogger(__name__)


def is_macos():
    """Check if running on macOS."""
    return platform.system() == 'Darwin'


def setup_drag_and_drop_macos(canvas, album_path: Path, drop_callback):
    """Setup macOS-native drag-and-drop using PyObjC.
    
    Creates a transparent NSView overlay on the Tkinter canvas that handles
    Photos app file promises and materializes full-resolution images.
    
    Args:
        canvas: Tkinter Canvas widget to enable drag-drop on
        album_path: Path to album directory (for determining where Photos should materialize files)
        drop_callback: Callback function(file_paths: list[str]) to handle dropped files
    
    Returns:
        True if setup succeeded, False otherwise
    """
    try:
        from Foundation import NSObject, NSURL, NSMakeRect
        from AppKit import (
            NSView, NSDragOperationCopy, NSFilenamesPboardType
        )
        import objc
        import tempfile
        import os
        import time
        
        # File promise pasteboard type constant (used by Photos app)
        NSFilesPromisePboardType = "NSFilesPromisePboardType"
        
        # Define PhotoDropView class that handles drag operations
        class PhotoDropView(NSView):
            """NSView subclass that handles drag-and-drop for Photos app file promises."""
            
            def initWithFrame_callback_photosDir_(self, frame, callback, photos_dir):
                """Initialize with frame, callback, and destination directory."""
                self = objc.super(PhotoDropView, self).initWithFrame_(frame)
                if self is None:
                    return None
                
                self.callback = callback
                self.photos_dir = photos_dir
                self.draggedFiles = []
                
                # Register for all relevant drag types
                drag_types = [
                    NSFilenamesPboardType,  # Regular files
                    NSFilesPromisePboardType,  # File promises (Photos app)
                    'Apple files promise pasteboard type',  # Photos app alternate
                    'com.apple.pasteboard.promised-file-url',
                ]
                self.registerForDraggedTypes_(drag_types)
                
                return self
            
            def draggingEntered_(self, sender):
                """Called when drag enters the view."""
                return NSDragOperationCopy
            
            def draggingUpdated_(self, sender):
                """Called as drag moves within the view."""
                return NSDragOperationCopy
            
            def prepareForDragOperation_(self, sender):
                """Called to prepare for the drop."""
                return True
            
            def performDragOperation_(self, sender):
                """Handle the actual drop."""
                pboard = sender.draggingPasteboard()
                types = pboard.types()
                
                # Check for file promises (Photos app)
                if NSFilesPromisePboardType in types or 'Apple files promise pasteboard type' in types:
                    # Handle file promises - tell Photos where to create files
                    # MUST use absolute path for Photos to accept it
                    abs_photos_dir = self.photos_dir.resolve()
                    destURL = NSURL.fileURLWithPath_isDirectory_(str(abs_photos_dir), True)
                    
                    filenames = sender.namesOfPromisedFilesDroppedAtDestination_(destURL)
                    
                    if filenames:
                        # Build full paths (use absolute path)
                        full_paths = [os.path.join(str(abs_photos_dir), name) for name in filenames]
                        
                        # Wait for files to actually exist (Photos writes asynchronously)
                        max_wait = 5.0
                        wait_interval = 0.1
                        existing_paths = []
                        
                        for path in full_paths:
                            elapsed = 0.0
                            while not os.path.exists(path) and elapsed < max_wait:
                                time.sleep(wait_interval)
                                elapsed += wait_interval
                            
                            if os.path.exists(path):
                                existing_paths.append(path)
                            else:
                                logger.warning(f"File not created within {max_wait}s: {path}")
                        
                        if existing_paths:
                            # Call the callback with the file paths
                            self.callback(existing_paths)
                            return True
                
                # Handle regular file drops
                elif NSFilenamesPboardType in types:
                    files = pboard.propertyListForType_(NSFilenamesPboardType)
                    if files:
                        self.callback(list(files))
                        return True
                
                return False
        
        # Get the Tkinter window's NSWindow
        # Force Tkinter to create the window if not already done
        canvas.update_idletasks()
        
        # Get the NSView for the canvas using Carbon/Cocoa bridge
        # This is the tricky part - we need to get the actual NSView
        from AppKit import NSApp
        from Cocoa import NSWindow
        
        # Get all windows and find the one containing our canvas
        windows = NSApp().windows()
        tk_window = None
        for window in windows:
            # Check if this window's title matches (crude but effective)
            if window.contentView():
                tk_window = window
                break
        
        if not tk_window:
            logger.warning("Could not find NSWindow for Tkinter canvas")
            return False
        
        # Get canvas dimensions
        canvas.update_idletasks()
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        
        # Get the photos directory for this album
        photos_dir = get_photos_directory(album_path)
        
        # Create our drop view as an overlay
        frame = NSMakeRect(0, 0, width, height)
        drop_view = PhotoDropView.alloc().initWithFrame_callback_photosDir_(
            frame, drop_callback, photos_dir
        )
        
        # Add as subview to the window's content view
        content_view = tk_window.contentView()
        content_view.addSubview_(drop_view)
        
        # Make sure the drop view is on top and accepts events
        drop_view.setAutoresizingMask_(18)  # NSViewWidthSizable | NSViewHeightSizable
        
        logger.info("macOS drag-and-drop enabled using PyObjC (file promises supported)")
        return True
        
    except ImportError as e:
        logger.info(f"PyObjC not available ({e}). Using Cmd+O to open photos.")
        return False
    except Exception as e:
        logger.warning(f"Failed to setup macOS drag-and-drop: {e}")
        return False


def setup_drag_and_drop_tkinterdnd(canvas, drop_callback):
    """Setup drag-and-drop using tkinterdnd2.
    
    Args:
        canvas: Tkinter Canvas widget to enable drag-drop on
        drop_callback: Callback function(file_paths: list[str]) to handle dropped files
    
    Returns:
        True if setup succeeded, False otherwise
    """
    try:
        from tkinterdnd2 import DND_FILES
        
        # Define handler for drop events
        def on_drop(event):
            """Handle file drop event from tkinterdnd2."""
            # Parse dropped file paths
            import tkinter as tk
            files = canvas.tk.splitlist(event.data)
            drop_callback(list(files))
            return event.action
        
        # Register the canvas widget for drag-and-drop
        canvas.drop_target_register(DND_FILES)
        canvas.dnd_bind('<<Drop>>', on_drop)
        logger.info("Drag-and-drop enabled using tkinterdnd2")
        return True
        
    except (ImportError, AttributeError, Exception) as e:
        logger.info(f"tkinterdnd2 not available ({e}). Using keyboard shortcuts to open photos.")
        return False


def setup_drag_and_drop(canvas, album_path: Path, drop_callback, show_status_callback=None):
    """Setup drag-and-drop for photo files.
    
    On macOS, attempts to use PyObjC for Photos app file promises.
    Falls back to tkinterdnd2 on other platforms or if PyObjC setup fails.
    
    Args:
        canvas: Tkinter Canvas widget to enable drag-drop on
        album_path: Path to album directory (for macOS Photos integration)
        drop_callback: Callback function(file_paths: list[str]) to handle dropped files
        show_status_callback: Optional callback function(message: str, duration_ms: int) to show status
    
    Returns:
        True if drag-and-drop is available, False otherwise
    """
    drag_drop_available = False
    
    if is_macos():
        # Try macOS-native drag-and-drop first
        drag_drop_available = setup_drag_and_drop_macos(canvas, album_path, drop_callback)
    
    if not drag_drop_available:
        # Fall back to tkinterdnd2
        drag_drop_available = setup_drag_and_drop_tkinterdnd(canvas, drop_callback)
    
    # Show one-time info if drag-drop is not available
    if not drag_drop_available and show_status_callback:
        show_status_callback("Drag-and-drop unavailable. Use Cmd+O to add photos.", duration_ms=3000)
    
    return drag_drop_available
