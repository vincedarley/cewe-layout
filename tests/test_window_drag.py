#!/usr/bin/env python3
"""Quick test to diagnose drag-and-drop issue.

This creates a minimal Tkinter window and tries the same approach to see what's happening.
"""
import tkinter as tk
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_macos_drag():
    """Test macOS drag-and-drop setup."""
    try:
        from Foundation import NSURL, NSMakeRect
        from AppKit import NSApp, NSView, NSDragOperationCopy, NSFilenamesPboardType
        import objc
        
        # Create Tkinter window
        root = tk.Tk()
        root.title("Drag Test")
        root.geometry("400x300")
        
        canvas = tk.Canvas(root, bg='lightgray')
        canvas.pack(fill='both', expand=True)
        canvas.update_idletasks()
        
        # Get the NSWindow
        windows = NSApp().windows()
        logger.info(f"Found {len(windows)} windows")
        
        if not windows:
            logger.error("No NSWindows found!")
            return
        
        window = windows[0]
        content_view = window.contentView()
        logger.info(f"Content view: {content_view}")
        logger.info(f"Content view class: {content_view.__class__.__name__}")
        logger.info(f"Content view subviews: {content_view.subviews()}")
        
        # Try to check if content_view has a hitTest_ method
        logger.info(f"Content view responds to hitTest_: {content_view.respondsToSelector_('hitTest:')}")
        
        root.mainloop()
        
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)

if __name__ == '__main__':
    test_macos_drag()
