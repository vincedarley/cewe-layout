#!/usr/bin/env python3
"""QLayout - runner for cewe-layout that ensures the package can be imported.

Run with:
    python run_qlayout.py --cewe path/to/album.mcf                      (launches GUI by default)
    python run_qlayout.py --cewe path/to/album.mcf --nogui              (CLI dump mode)
    python run_qlayout.py --cewe path/to/album.mcf --unpatch            (restore backup)
    python run_qlayout.py --originalPdf path.pdf --cewe output.xmcf     (convert PDF and launch GUI)
    python run_qlayout.py --renamephotos DIRECTORY PREFIX [PATTERN]     (rename photo files)
"""
import os
import sys

# Ensure this script's directory is in the path so cewe_layout can be imported
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='Cewe photobook layout parser and editor'
    )
    parser.add_argument('--cewe', 
                       help='Path to .mcf or .xmcf file (if not specified in GUI mode, a file picker will open)')
    parser.add_argument('--originalPdf',
                       help='Path to PDF file to convert into a CEWE photobook')
    parser.add_argument('--nogui', action='store_true', 
                       help='Use CLI dump mode instead of GUI (default is GUI)')
    parser.add_argument('--unpatch', action='store_true', 
                       help='Restore the most recent backup')
    parser.add_argument('--renamephotos', nargs='+', metavar='ARG',
                       help='Rename photos: DIRECTORY RENAMEPREFIX [PATTERN]. Pattern defaults to * (all files).')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode (saves composite images during segmentation)')
    parser.add_argument('--insidecovers', action='store_true',
                       help='PDF includes inside cover pages (page 1 = inside front, page N-1 = inside back)')
    parser.add_argument('--profile', action='store_true',
                       help='Enable profiling with cProfile (outputs to profile.stats)')
    
    args = parser.parse_args()
    
    if args.renamephotos:
        # Pass through to CLI rename_photos function
        from cewe_layout.cli import main
        sys.argv = ['cewe-layout', '--renamephotos'] + args.renamephotos
        main()
    
    elif args.unpatch:
        from cewe_layout.mcf_io.mcf_layout_change import restore_mcf_backup
        from cewe_layout.mcf_io.mcf_parser import resolve_mcf_path
        real = resolve_mcf_path(args.cewe)
        res = restore_mcf_backup(real)
        print(f"✅ Restored {res['path']}")
        print(f"   From: {res['restored_from']}")
    
    elif args.nogui:
        # CLI dump mode (requires --cewe)
        from cewe_layout.cli import main
        if not args.cewe:
            parser.error('--cewe is required when using --nogui')
        sys.argv = ['cewe-layout', '--input', args.cewe]
        main()
    
    else:
        # Default: GUI mode
        import tkinter as tk
        from tkinter import ttk
        from tkinter.filedialog import askopenfilename
        
        def load_and_launch_album(root):
            """Load the album (with optional PDF conversion) and launch the GUI.
            
            Args:
                root: Optional existing root window to reuse
            """
            pdf_photobook = None

            if args.originalPdf:
                # Import pdf_import conversion logic
                from pathlib import Path
                from cewe_layout.pdf_import.pdf_extractor import extract_pdf_content, create_pdf_reader
                from cewe_layout.mcf_io.mcf_writer import photobook_write_to_mcf
                
                pdf_path = Path(args.originalPdf)
                output_path = Path(args.cewe)

                # Get PDF page count to create mapping
                import fitz
                doc = fitz.open(pdf_path)
                pdf_page_count = len(doc)
                doc.close()

                # Only write if output doesn't already exist
                if output_path.exists():
                    print(f"✅ Output already exists: {args.cewe}")
                    print(f"   Creating on-demand PDF reader for GUI")

                    # Create lightweight reader for on-demand page access WITH mapping
                    pdf_photobook = create_pdf_reader(pdf_path, pdf_page_count, verbose=True, insidecovers=args.insidecovers)
                else:
                    # Extract all PDF content for initial conversion
                    print(f"Extracting content from {pdf_path}...")

                    pdf_photobook = extract_pdf_content(pdf_path, pdf_page_count, page_range=None, verbose=True, debug=args.debug, insidecovers=args.insidecovers)
                    
                    print(f"Writing MCF project to {args.cewe}...")
                    photobook_write_to_mcf(pdf_photobook, args.cewe, verbose=True)
                    
                    print(f"✅ Successfully converted {pdf_path.name} to {args.cewe}")
                    print(f"   Pages: {pdf_photobook.get_page_count()}")

            from cewe_layout.mcf_io.mcf_parser import resolve_mcf_path
            from cewe_layout.gui_controls import launch_gui
            real = resolve_mcf_path(args.cewe)
            
            if args.profile:
                # Run with profiling
                import cProfile
                import pstats
                from pstats import SortKey
                
                print("Running with profiling enabled...")
                profiler = cProfile.Profile()
                profiler.enable()
                
                try:
                    launch_gui(real, pdf_photobook, root=root)
                finally:
                    profiler.disable()
                    
                    # Save stats to file
                    profiler.dump_stats('profile.stats')
                    print("\nProfile data saved to profile.stats")
                    print("View with: python -m pstats profile.stats")
                    print("Or programmatically:")
                    print("  >>> import pstats")
                    print("  >>> p = pstats.Stats('profile.stats')")
                    print("  >>> p.sort_stats('cumulative').print_stats(30)")
                    
                    # Print top 20 functions by cumulative time
                    print("\nTop 20 functions by cumulative time:")
                    stats = pstats.Stats(profiler)
                    stats.sort_stats(SortKey.CUMULATIVE)
                    stats.print_stats(20)
            else:
                launch_gui(real, pdf_photobook, root=root)
        
        # If no album specified, show welcome screen
        if not args.cewe:
            # Create root window with TkinterDnD support if available
            # Note: If TkinterDnD initialization fails partway through, it may have
            # already created a Tk window via tk.Tk.__init__(). We detect and reuse that.
            root = None
            try:
                from tkinterdnd2 import TkinterDnD
                root = TkinterDnD.Tk()
            except (ImportError, RuntimeError, Exception):
                # Check if a Tk window was partially created via tk.Tk.__init__ before the exception
                existing_root = getattr(tk, '_default_root', None)
                if existing_root is not None:
                    # Reuse the partially-created window
                    root = existing_root
                else:
                    # Fall back to creating a standard Tk window
                    root = tk.Tk()
            
            root.title('QLayout')
            root.geometry('500x300')
            
            # Create welcome frame
            welcome_frame = ttk.Frame(root)
            welcome_frame.pack(expand=True, fill='both')
            
            # Center content
            content_frame = ttk.Frame(welcome_frame)
            content_frame.place(relx=0.5, rely=0.5, anchor='center')
            
            ttk.Label(content_frame, text='QLayout', font=('TkDefaultFont', 24, 'bold')).pack(pady=(0, 20))
            
            def open_album():
                album_file = askopenfilename(
                    title='Open CEWE Album (.mcf file inside .xmcf bundle, or standalone .mcf)',
                    parent=root
                )
                if album_file:
                    args.cewe = album_file
                    welcome_frame.destroy()
                    # Continue with album loading, reusing the root window
                    load_and_launch_album(root=root)
                    
            ttk.Button(
                content_frame,
                text='Open Album...',
                command=open_album,
                width=20
            ).pack()
            
            # Wait for user to select album
            root.mainloop()
        else:
            # Album specified via command line, create root window
            root = None
            try:
                from tkinterdnd2 import TkinterDnD
                root = TkinterDnD.Tk()
            except (ImportError, RuntimeError, Exception):
                # Check if a Tk window was partially created via tk.Tk.__init__ before the exception
                existing_root = getattr(tk, '_default_root', None)
                if existing_root is not None:
                    # Reuse the partially-created window
                    root = existing_root
                else:
                    # Fall back to creating a standard Tk window
                    root = tk.Tk()
            
            root.title('QLayout')
            load_and_launch_album(root)
            root.mainloop()
