#!/usr/bin/env python3
"""QLayout - runner for cewe-layout that ensures the package can be imported.

Run with:
    python run_qlayout.py --input path/to/album.mcf          (launches GUI by default)
    python run_qlayout.py --input path/to/album.mcf --nogui  (CLI dump mode)
    python run_qlayout.py --input path/to/album.mcf --unpatch
    python run_qlayout.py --renamephotos DIRECTORY PREFIX [PATTERN]
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
    parser.add_argument('--input', '-i', 
                       help='Path to .mcf or .xmcf file')
    parser.add_argument('--nogui', action='store_true', 
                       help='Use CLI dump mode instead of GUI (default is GUI)')
    parser.add_argument('--unpatch', action='store_true', 
                       help='Restore the most recent backup')
    parser.add_argument('--renamephotos', nargs='+', metavar='ARG',
                       help='Rename photos: DIRECTORY PREFIX [PATTERN]. Pattern defaults to * (all files).')
    
    args = parser.parse_args()
    
    if args.renamephotos:
        # Pass through to CLI rename_photos function
        sys.argv = ['cewe-layout', '--renamephotos'] + args.renamephotos
        main()
    
    elif args.unpatch:
        from cewe_layout.writer import restore_mcf_backup
        from cewe_layout.parser import resolve_mcf_path
        real = resolve_mcf_path(args.input)
        res = restore_mcf_backup(real)
        print(f"✅ Restored {res['path']}")
        print(f"   From: {res['restored_from']}")
    
    elif args.nogui:
        # CLI dump mode (requires --input)
        if not args.input:
            parser.error('--input is required when using --nogui')
        sys.argv = ['cewe-layout', '--input', args.input]
        main()
    
    else:
        # Default: GUI mode (requires --input)
        if not args.input:
            parser.error('--input is required')
        from cewe_layout.parser import resolve_mcf_path
        real = resolve_mcf_path(args.input)
        launch_gui(real)
