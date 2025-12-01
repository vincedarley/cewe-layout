#!/usr/bin/env python3
"""QLayout - runner for cewe-layout that ensures the package can be imported.

Run with:
    python run_qlayout.py --input path/to/album.mcf [--gui]
    python run_qlayout.py --input path/to/album.mcf --patch
    python run_qlayout.py --input path/to/album.mcf --unpatch
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
    parser.add_argument('--input', '-i', required=True, 
                       help='Path to .mcf or .xmcf file')
    parser.add_argument('--gui', action='store_true', 
                       help='Launch Tkinter GUI viewer')
    parser.add_argument('--patch', action='store_true', 
                       help='Patch input .mcf by scaling areas (0.9×) with backup')
    parser.add_argument('--unpatch', action='store_true', 
                       help='Restore the most recent backup')
    
    args = parser.parse_args()
    
    if args.gui:
        from cewe_layout.parser import resolve_mcf_path
        real = resolve_mcf_path(args.input)
        launch_gui(real)
    
    elif args.patch:
        from cewe_layout.writer import patch_mcf_file
        from cewe_layout.parser import resolve_mcf_path
        real = resolve_mcf_path(args.input)
        res = patch_mcf_file(real, scale=0.9, make_backup=True)
        print(f"✅ Patched {res['path']}")
        print(f"   Backup: {res['backup_path']}")
        print(f"   Modified {res['modified_areas']} areas")
    
    elif args.unpatch:
        from cewe_layout.writer import restore_mcf_backup
        from cewe_layout.parser import resolve_mcf_path
        real = resolve_mcf_path(args.input)
        res = restore_mcf_backup(real)
        print(f"✅ Restored {res['path']}")
        print(f"   From: {res['restored_from']}")
    
    else:
        # Default: CLI dump mode
        sys.argv = ['cewe-layout', '--input', args.input]
        main()
