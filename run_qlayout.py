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

from cewe_layout.cli import main
from cewe_layout.gui import launch_gui

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description='Cewe photobook layout parser and editor'
    )
    parser.add_argument('--cewe', 
                       help='Path to .mcf or .xmcf file (input for normal use, input/output for PDF conversion)')
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
        sys.argv = ['cewe-layout', '--renamephotos'] + args.renamephotos
        main()
    
    elif args.unpatch:
        from cewe_layout.writer import restore_mcf_backup
        from cewe_layout.parser import resolve_mcf_path
        real = resolve_mcf_path(args.cewe)
        res = restore_mcf_backup(real)
        print(f"✅ Restored {res['path']}")
        print(f"   From: {res['restored_from']}")
    
    elif args.nogui:
        # CLI dump mode (requires --cewe)
        if not args.cewe:
            parser.error('--cewe is required when using --nogui')
        sys.argv = ['cewe-layout', '--input', args.cewe]
        main()
    
    else:
        # Default: GUI mode (requires --cewe)
        if not args.cewe:
            parser.error('--cewe is required')

        pdf_photobook = None

        if args.originalPdf:
            # Import pdf2cewe conversion logic
            from pathlib import Path
            from cewe_layout.pdf2cewe.pdf_extractor import extract_pdf_content, create_pdf_reader
            from cewe_layout.book.mcf_writer import write_mcf_project
            
            pdf_path = Path(args.originalPdf)
            output_path = Path(args.cewe)
            
            # Only write if output doesn't already exist
            if output_path.exists():
                print(f"✅ Output already exists: {args.cewe}")
                print(f"   Creating on-demand PDF reader for GUI")
                
                # Get PDF page count to create mapping
                import fitz
                doc = fitz.open(pdf_path)
                pdf_page_count = len(doc)
                doc.close()
                
                # Create page mapping for coordinate positioning
                from cewe_layout.book.mcf_writer import _create_page_mapping
                ui_to_pdf = _create_page_mapping(pdf_page_count, args.insidecovers)
                pdf_to_ui = {v: k for k, v in ui_to_pdf.items() if v is not None}
                
                # Create lightweight reader for on-demand page access WITH mapping
                pdf_photobook = create_pdf_reader(pdf_path, verbose=True, page_to_ui=pdf_to_ui, insidecovers=args.insidecovers)
            else:
                # Extract all PDF content for initial conversion
                print(f"Extracting content from {pdf_path}...")
                
                # Create inverse mapping: PDF index → UI page (for coordinate positioning)
                # First get PDF page count by opening it
                import fitz
                doc = fitz.open(pdf_path)
                pdf_page_count = len(doc)
                doc.close()
                
                # Create UI-to-PDF mapping, then invert it
                from cewe_layout.book.mcf_writer import _create_page_mapping
                ui_to_pdf = _create_page_mapping(pdf_page_count, args.insidecovers)
                pdf_to_ui = {v: k for k, v in ui_to_pdf.items() if v is not None}
                
                print(f"DEBUG: PDF-to-UI mapping (first 5 and last 5):")
                sorted_keys = sorted([k for k in pdf_to_ui.keys() if isinstance(k, int)])
                for pdf_idx in sorted_keys[:5]:
                    print(f"  PDF page {pdf_idx} → UI page {pdf_to_ui[pdf_idx]}")
                for pdf_idx in sorted_keys[-5:]:
                    print(f"  PDF page {pdf_idx} → UI page {pdf_to_ui[pdf_idx]}")
                
                pdf_photobook = extract_pdf_content(pdf_path, page_range=None, verbose=True, debug=args.debug, page_to_ui=pdf_to_ui, insidecovers=args.insidecovers)
                
                print(f"Writing MCF project to {args.cewe}...")
                write_mcf_project(pdf_photobook, args.cewe, verbose=True, insidecovers=args.insidecovers)
                
                print(f"✅ Successfully converted {pdf_path.name} to {args.cewe}")
                print(f"   Pages: {pdf_photobook.get_page_count()}")

        from cewe_layout.parser import resolve_mcf_path
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
                launch_gui(real, pdf_photobook, insidecovers=args.insidecovers)
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
            launch_gui(real, pdf_photobook, insidecovers=args.insidecovers)
