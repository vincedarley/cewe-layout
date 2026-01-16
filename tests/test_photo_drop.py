#!/usr/bin/env python3
"""
Test script for handling drag-and-drop from macOS Photos app.

This demonstrates how to properly handle "file promises" which Photos uses
instead of sending actual file paths. The key is using PyObjC to intercept
the drag operation and request that Photos materialize the actual files.

To test:
1. Run this script: python tests/test_photo_drop.py
2. Drag photos from Photos app into the window
3. The full-resolution files will be created in a temp directory
4. File paths and dimensions will be printed to console
"""

import objc
from Foundation import *
from AppKit import *
from PyObjCTools import AppHelper
import os
import tempfile
from pathlib import Path

# File promise pasteboard types - Photos app may use different identifiers
NSFilesPromisePboardType = "NSFilesPromisePboardType"

# Try to get modern pasteboard types if available
try:
    from AppKit import NSPasteboardTypeFilePromise
except ImportError:
    # Fallback for older systems
    NSPasteboardTypeFilePromise = "com.apple.pasteboard.promised-file-content-type"


class PhotoDropView(NSView):
    """Custom view that accepts file promises from Photos app and regular file drops"""
    
    def initWithFrame_(self, frame):
        self = objc.super(PhotoDropView, self).initWithFrame_(frame)
        if self is None:
            return None
        
        # Register for drag types including file promises
        # Register for multiple file promise types to handle different macOS versions
        self.registerForDraggedTypes_([
            NSFilesPromisePboardType,        # Old-style file promises
            NSPasteboardTypeFilePromise,     # New-style file promises
            NSFilenamesPboardType,           # Regular files
            NSURLPboardType,                 # URLs
            "public.file-url",               # Public UTI
            "public.url",                    # Another UTI
        ])
        
        self.draggedFiles = []
        self.statusText = "Drop photos from Photos app here\n(or drag files from Finder)"
        return self
    
    def draggingEntered_(self, sender):
        """Called when drag enters the view"""
        pboard = sender.draggingPasteboard()
        types = pboard.types()
        
        # DEBUG: Print all available types to see what Photos app sends
        print(f"\n=== Drag Entered - Available Types ({len(types)}) ===")
        for t in types:
            print(f"  - {t}")
        print()
        
        # Check if we have file promises or regular files
        # Check for both old and new style file promises
        if NSFilesPromisePboardType in types or NSPasteboardTypeFilePromise in types:
            self.statusText = "File promise detected (Photos app)"
            self.setNeedsDisplay_(True)
            return NSDragOperationCopy
        elif NSFilenamesPboardType in types:
            self.statusText = "Regular files detected (Finder)"
            self.setNeedsDisplay_(True)
            return NSDragOperationCopy
        else:
            self.statusText = f"Unknown drag type\n(see console)"
            self.setNeedsDisplay_(True)
            return NSDragOperationCopy  # Accept it anyway to see what happens
    
    def draggingUpdated_(self, sender):
        """Called as drag moves within the view"""
        return NSDragOperationCopy
    
    def draggingExited_(self, sender):
        """Called when drag leaves the view"""
        if not self.draggedFiles:
            self.statusText = "Drop photos from Photos app here\n(or drag files from Finder)"
            self.setNeedsDisplay_(True)
    
    def prepareForDragOperation_(self, sender):
        """Called to prepare for the drop"""
        return True
    
    def performDragOperation_(self, sender):
        """
        Handle the actual drop operation.
        This is where file promises get resolved.
        """
        pboard = sender.draggingPasteboard()
        types = pboard.types()
        
        # DEBUG: Print all available types again
        print(f"\n=== Drop Received - Available Types ({len(types)}) ===")
        for t in types:
            print(f"  - {t}")
        print()
        
        # Handle file promises (from Photos, Mail, etc.)
        # Check for both old and new style
        if NSFilesPromisePboardType in types or NSPasteboardTypeFilePromise in types:
            print("\n=== File Promise Drop ===")
            return self.handleFilePromises_(sender)
        
        # Handle regular file drops
        elif NSFilenamesPboardType in types:
            print("\n=== Regular File Drop ===")
            files = pboard.propertyListForType_(NSFilenamesPboardType)
            print(f"Dropped {len(files)} file(s):")
            for f in files:
                print(f"  - {f}")
                self.analyzeFile_(f)
            self.draggedFiles = list(files)
            self.updateStatusText()
            return True
        
        # Unknown type - try to get any data we can
        else:
            print("\n=== Unknown Drop Type ===")
            print("Attempting to retrieve data from all available types...")
            for t in types:
                try:
                    data = pboard.dataForType_(t)
                    if data:
                        print(f"  Type '{t}': {len(data)} bytes")
                    prop = pboard.propertyListForType_(t)
                    if prop:
                        print(f"  PropertyList for '{t}': {prop}")
                except Exception as e:
                    print(f"  Error reading '{t}': {e}")
        
        return False
    
    def handleFilePromises_(self, sender):
        """
        Handle file promises by telling the source where to create files.
        This is the key method for handling Photos app drags.
        """
        pboard = sender.draggingPasteboard()
        
        # Get the promised file types/extensions
        # For Photos, this is typically ['jpg', 'jpeg'] or ['png', 'heic']
        fileTypes = pboard.propertyListForType_(NSFilesPromisePboardType)
        print(f"Promised file types: {fileTypes}")
        
        # Create a temporary directory for the promised files
        # In a real app, you'd create files in your destination directory
        tempDir = tempfile.mkdtemp(prefix="photo_drop_")
        destURL = NSURL.fileURLWithPath_isDirectory_(tempDir, True)
        
        print(f"Requesting files be created at: {tempDir}")
        
        # This is the CRITICAL call that tells the source (Photos app)
        # where to create the promised files. Photos will write the full-resolution
        # images to this location.
        filenames = sender.namesOfPromisedFilesDroppedAtDestination_(destURL)
        
        if filenames:
            # Build full paths to the created files
            fullPaths = [os.path.join(tempDir, name) for name in filenames]
            print(f"\nFiles created by Photos app:")
            
            # Wait for files to actually exist (Photos writes them asynchronously)
            import time
            max_wait = 5.0  # seconds
            wait_interval = 0.1  # seconds
            elapsed = 0.0
            
            for path in fullPaths:
                print(f"  - {path}")
                # Wait for this specific file to exist
                while not os.path.exists(path) and elapsed < max_wait:
                    time.sleep(wait_interval)
                    elapsed += wait_interval
                
                if os.path.exists(path):
                    self.analyzeFile_(path)
                else:
                    print(f"    WARNING: File not created within {max_wait}s")
            
            self.draggedFiles = fullPaths
            self.updateStatusText()
            
            return True
        else:
            print("ERROR: No files were promised/created")
            self.statusText = "ERROR: No files created"
            self.setNeedsDisplay_(True)
            return False
    
    def analyzeFile_(self, filepath):
        """Analyze a dropped file and print its properties"""
        try:
            path = Path(filepath)
            size_bytes = path.stat().st_size
            size_mb = size_bytes / (1024 * 1024)
            
            # Try to get image dimensions if PIL is available
            try:
                from PIL import Image
                img = Image.open(filepath)
                width, height = img.size
                print(f"    Size: {size_mb:.2f} MB, Dimensions: {width}x{height}")
            except ImportError:
                print(f"    Size: {size_mb:.2f} MB (install Pillow for dimension info)")
            except Exception as e:
                print(f"    Size: {size_mb:.2f} MB (not an image or error: {e})")
        except Exception as e:
            print(f"    Error analyzing file: {e}")
    
    def updateStatusText(self):
        """Update status text based on dropped files"""
        if self.draggedFiles:
            self.statusText = f"✓ Dropped {len(self.draggedFiles)} file(s)\n\n"
            for f in self.draggedFiles[:5]:
                basename = os.path.basename(f)
                self.statusText += f"• {basename}\n"
            if len(self.draggedFiles) > 5:
                self.statusText += f"\n... and {len(self.draggedFiles) - 5} more"
            self.statusText += "\n\nCheck console for details"
        self.setNeedsDisplay_(True)
    
    def concludeDragOperation_(self, sender):
        """Called after drag operation completes"""
        print("=== Drag operation concluded ===\n")
    
    def drawRect_(self, rect):
        """Draw the view"""
        # Background - light blue if files dropped, light gray otherwise
        if self.draggedFiles:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.9, 0.95, 1.0, 1.0).set()
        else:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.95, 0.95, 0.95, 1.0).set()
        NSBezierPath.fillRect_(rect)
        
        # Draw dashed border
        NSColor.colorWithCalibratedRed_green_blue_alpha_(0.4, 0.4, 0.4, 1.0).set()
        path = NSBezierPath.bezierPathWithRect_(NSInsetRect(rect, 2.0, 2.0))
        path.setLineWidth_(2.0)
        dashes = [8.0, 4.0]
        path.setLineDash_count_phase_(dashes, 2, 0.0)
        path.stroke()
        
        # Draw text
        attrs = {
            NSFontAttributeName: NSFont.systemFontOfSize_(16),
            NSForegroundColorAttributeName: NSColor.blackColor()
        }
        
        nsText = NSString.stringWithString_(self.statusText)
        textRect = NSMakeRect(20, rect.size.height / 2 - 50, rect.size.width - 40, 200)
        nsText.drawInRect_withAttributes_(textRect, attrs)


class AppDelegate(NSObject):
    """Application delegate"""
    
    def applicationDidFinishLaunching_(self, notification):
        # Create window
        frame = NSMakeRect(100, 100, 600, 400)
        style = (NSTitledWindowMask | 
                NSClosableWindowMask | 
                NSMiniaturizableWindowMask | 
                NSResizableWindowMask)
        
        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Photo Drop Test - Drop Photos Here")
        
        # Create and add drop view
        dropView = PhotoDropView.alloc().initWithFrame_(
            self.window.contentView().bounds()
        )
        dropView.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.window.contentView().addSubview_(dropView)
        
        # Show window
        self.window.makeKeyAndOrderFront_(None)
        
        print("=" * 60)
        print("Photo Drop Test Window Ready")
        print("=" * 60)
        print("Instructions:")
        print("1. Open Photos app")
        print("2. Drag one or more photos into the window")
        print("3. Watch the console for file details")
        print()
        print("This will show the difference between:")
        print("- File promises (Photos app) → full resolution")
        print("- Regular files (Finder) → as-is")
        print("=" * 60)
        print()
    
    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return True


def main():
    """Main entry point"""
    # Check if PyObjC is available
    try:
        import objc
        from Foundation import NSObject
        from AppKit import NSApplication
    except ImportError:
        print("ERROR: PyObjC not installed")
        print("Install with: pip install pyobjc-framework-Cocoa")
        return 1
    
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == '__main__':
    import sys
    sys.exit(main() or 0)
