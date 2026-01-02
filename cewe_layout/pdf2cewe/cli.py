"""Command-line interface for pdf2cewe."""

import argparse
import sys
from pathlib import Path
from .pdf_extractor import extract_pdf_content
from cewe_layout.book.mcf_writer import write_mcf_project


def main():
    """Main entry point for pdf2cewe CLI."""
    parser = argparse.ArgumentParser(
        description='Convert PDF photobooks to CEWE MCF format'
    )
    parser.add_argument(
        '--input', '-i',
        required=True,
        help='Path to input PDF file'
    )
    parser.add_argument(
        '--output', '-o',
        required=True,
        help='Path to output .xmcf directory'
    )
    parser.add_argument(
        '--pages',
        help='Page range to process (e.g., "1-10" or "1,3,5-7")'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    if not input_path.suffix.lower() == '.pdf':
        print(f"Error: Input file must be a PDF: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    # Parse page range if provided
    page_range = None
    if args.pages:
        page_range = parse_page_range(args.pages)
    
    try:
        print(f"Extracting content from {input_path}...")
        pdf_photobook = extract_pdf_content(input_path, page_range, verbose=args.verbose)
        
        print(f"Writing MCF project to {args.output}...")
        write_mcf_project(pdf_photobook, args.output, verbose=args.verbose)
        
        print(f"✅ Successfully converted {input_path.name} to {args.output}")
        print(f"   Pages: {pdf_photobook.get_page_count()}")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def parse_page_range(range_str):
    """Parse page range string like '1-10' or '1,3,5-7' into list of page numbers.
    
    Args:
        range_str: String describing page range
        
    Returns:
        List of page numbers (0-indexed)
    """
    pages = set()
    parts = range_str.split(',')
    
    for part in parts:
        part = part.strip()
        if '-' in part:
            start, end = part.split('-')
            # Convert to 0-indexed
            pages.update(range(int(start) - 1, int(end)))
        else:
            # Convert to 0-indexed
            pages.add(int(part) - 1)
    
    return sorted(list(pages))


if __name__ == '__main__':
    main()
