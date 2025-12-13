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
                       help='Rename photos: DIRECTORY PREFIX [PATTERN]. Pattern defaults to * (all files).')
    parser.add_argument('--debug', action='store_true',
                       help='Enable debug mode (saves composite images during segmentation)')
    
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

        pdf_content = None

        if args.originalPdf:
            # Import pdf2cewe conversion logic
            from pathlib import Path
            from cewe_layout.pdf2cewe.pdf_extractor import extract_pdf_content, create_pdf_reader
            from cewe_layout.pdf2cewe.mcf_writer import write_mcf_project
            
            pdf_path = Path(args.originalPdf)
            output_path = Path(args.cewe)
            
            # Only write if output doesn't already exist
            if output_path.exists():
                print(f"✅ Output already exists: {args.cewe}")
                print(f"   Creating on-demand PDF reader for GUI")
                # Create lightweight reader for on-demand page access
                pdf_content = create_pdf_reader(pdf_path, verbose=True)
            else:
                # Extract all PDF content for initial conversion
                print(f"Extracting content from {pdf_path}...")
                pdf_content = extract_pdf_content(pdf_path, page_range=None, verbose=True, debug=args.debug)
                
                print(f"Writing MCF project to {args.cewe}...")
                write_mcf_project(pdf_content, args.cewe, verbose=True)
                
                print(f"✅ Successfully converted {pdf_path.name} to {args.cewe}")
                print(f"   Pages: {len(pdf_content['pages'])}")

        from cewe_layout.parser import resolve_mcf_path
        real = resolve_mcf_path(args.cewe)
        launch_gui(real, pdf_content)
