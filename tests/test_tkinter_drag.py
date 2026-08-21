#!/usr/bin/env python3
"""
Minimal test case for PyObjC drag-and-drop on Tkinter window.

This tests whether we can overlay an NSView on a Tkinter window and receive drag events.

To run:
    source ../.env/bin/activate
    python tests/test_tkinter_drag.py

Then try dragging a file (from Finder or Photos) into the window.
"""

import tkinter as tk
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_drag_drop():
    """Test PyObjC drag-drop on Tkinter window."""
    
    try:
        from Foundation import NSURL, NSMakeRect
        from AppKit import (
            NSApp, NSView, NSDragOperationCopy, NSFilenamesPboardType
        )
        import objc
        
        logger.info("PyObjC modules imported successfully")
        
        # File promise pasteboard type constant (used by Photos app)
        NSFilesPromisePboardType = "NSFilesPromisePboardType"
        
        # Define simple drop view
        class SimpleDropView(NSView):
            """Minimal NSView that accepts drag-and-drop."""
            
            def initWithFrame_(self, frame):
                self = objc.super(SimpleDropView, self).initWithFrame_(frame)
                if self is None:
                    return None
                
                # Register for drag types
                drag_types = [
                    NSFilenamesPboardType,
                    NSFilesPromisePboardType,
                    'Apple files promise pasteboard type',
                ]
                self.registerForDraggedTypes_(drag_types)
                
                logger.info(f"SimpleDropView registered for drag types: {drag_types}")
                return self
            
            def draggingEntered_(self, sender):
                """Called when drag enters the view."""
                logger.info("*** DRAG ENTERED THE VIEW ***")
                pboard = sender.draggingPasteboard()
                types = pboard.types()
                logger.info(f"Available pasteboard types: {list(types)}")
                return NSDragOperationCopy
            
            def draggingUpdated_(self, sender):
                """Called as drag moves within the view."""
                return NSDragOperationCopy
            
            def prepareForDragOperation_(self, sender):
                """Called to prepare for the drop."""
                logger.info("*** PREPARE FOR DROP ***")
                return True
            
            def performDragOperation_(self, sender):
                """Handle the actual drop."""
                logger.info("*** PERFORMING DROP ***")
                pboard = sender.draggingPasteboard()
                types = pboard.types()
                
                if NSFilenamesPboardType in types:
                    files = pboard.propertyListForType_(NSFilenamesPboardType)
                    logger.info(f"Dropped files: {list(files)}")
                    return True
                elif NSFilesPromisePboardType in types:
                    logger.info("File promise detected - would materialize here")
                    return True
                
                return False
        
        # Create Tkinter window
        logger.info("Creating Tkinter window...")
        root = tk.Tk()
        root.title("Tkinter + PyObjC Drag-Drop Test")
        root.geometry("600x400")
        
        # Create a canvas
        canvas = tk.Canvas(root, bg='lightblue')
        canvas.pack(fill='both', expand=True)
        
        # Add instructions text
        canvas.create_text(
            300, 200,
            text="Drag a file here\n\n(Check console for drag event messages)",
            font=('Arial', 16),
            justify='center'
        )
        
        # Force Tkinter to create the window
        canvas.update_idletasks()
        root.update()
        
        logger.info("Tkinter window created, now setting up PyObjC overlay...")
        
        # Get the NSWindow
        windows = NSApp().windows()
        logger.info(f"Found {len(windows)} NSWindow(s)")
        
        if not windows:
            logger.error("ERROR: No NSWindows found!")
            logger.error("This means Tkinter window is not exposed to AppKit")
            root.mainloop()
            return
        
        # Use the first window
        ns_window = windows[0]
        logger.info(f"Using NSWindow: {ns_window}")
        logger.info(f"Window title: {ns_window.title()}")
        
        content_view = ns_window.contentView()
        logger.info(f"Content view: {content_view}")
        logger.info(f"Content view class: {content_view.__class__.__name__}")
        
        # Check initial subviews
        initial_subviews = content_view.subviews()
        logger.info(f"Content view has {len(initial_subviews)} initial subview(s)")
        for i, subview in enumerate(initial_subviews):
            logger.info(f"  Subview {i}: {subview.__class__.__name__}")
        
        # Get canvas dimensions
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        logger.info(f"Canvas dimensions: {width}x{height}")
        
        # Create drop view overlay
        frame = NSMakeRect(0, 0, width, height)
        drop_view = SimpleDropView.alloc().initWithFrame_(frame)
        logger.info(f"Created SimpleDropView: {drop_view}")
        
        # Add as subview
        content_view.addSubview_(drop_view)
        drop_view.setAutoresizingMask_(18)  # NSViewWidthSizable | NSViewHeightSizable
        
        # Check subviews after adding
        after_subviews = content_view.subviews()
        logger.info(f"Content view now has {len(after_subviews)} subview(s)")
        for i, subview in enumerate(after_subviews):
            logger.info(f"  Subview {i}: {subview.__class__.__name__}")
        
        logger.info("\n" + "="*70)
        logger.info("SETUP COMPLETE!")
        logger.info("="*70)
        logger.info("Now try dragging a file into the window.")
        logger.info("If you see '*** DRAG ENTERED THE VIEW ***' then it's working!")
        logger.info("If not, the PyObjC overlay is not receiving events from Tkinter.")
        logger.info("="*70 + "\n")
        
        # Run Tkinter event loop
        root.mainloop()
        
    except ImportError as e:
        logger.error(f"PyObjC not available: {e}")
        logger.error("Install with: pip install pyobjc-framework-Cocoa")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)


if __name__ == '__main__':
    test_drag_drop()
