#!/usr/bin/env python3
"""Command-line tool to convert Mimeo Photos .ppb projects to CEWE .xmcf format.

Usage:
    python -m cewe_layout.utils.convert_mimeo_cli \\
        --ppb /path/to/project.ppb \\
        --library /path/to/Photos.photoslibrary \\
        --output /path/to/output.xmcf \\
        [--verbose]

Example:
    python -m cewe_layout.utils.convert_mimeo_cli \\
        --ppb "/Volumes/.../2016-test.photoslibrary/resources/projects/legacy/UUID.ppb" \\
        --library "/Volumes/.../2016-test.photoslibrary" \\
        --output "./converted-album.xmcf" \\
        --verbose
"""

import argparse
import logging
from pathlib import Path
import sys

from .mimeo_converter import convert_ppb_to_xmcf


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description='Convert Mimeo Photos .ppb project to CEWE .xmcf format',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        '--ppb',
        type=Path,
        required=True,
        help='Path to .ppb bundle (Mimeo project)'
    )
    
    parser.add_argument(
        '--library',
        type=Path,
        required=True,
        help='Path to Photos.photoslibrary containing the photos'
    )
    
    parser.add_argument(
        '--output',
        type=Path,
        required=True,
        help='Output path for .xmcf project'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print detailed conversion information'
    )
    
    args = parser.parse_args()
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    
    # Suppress PIL debug output
    logging.getLogger('PIL').setLevel(logging.WARNING)
        
    # Validate paths
    if not args.ppb.exists():
        print(f"Error: PPB path does not exist: {args.ppb}", file=sys.stderr)
        sys.exit(1)
    
    if not args.library.exists():
        print(f"Error: Photos library does not exist: {args.library}", file=sys.stderr)
        sys.exit(1)
    
    # Run conversion
    try:
        convert_ppb_to_xmcf(
            ppb_path=args.ppb,
            photos_library_path=args.library,
            output_path=args.output,
            verbose=args.verbose
        )
        print(f"\nSuccess! Created CEWE project at: {args.output}")
    except Exception as e:
        print(f"\nError during conversion: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
