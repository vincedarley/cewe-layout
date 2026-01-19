"""Headless test to generate multiple good Fan-GA layouts for xmas-2025 canvas.

Runs Fan-GA algorithm with zero gaps until finding 10 layouts with < 0.5% empty space,
exporting each to PDF (good1.pdf through good10.pdf).
"""
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.mcf_io.mcf_parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.algorithms.fan_layout import FanLayoutAlgorithm
from cewe_layout.collage_wrapper import generate_layout_for_page
from cewe_layout.layout_utils import build_photo_dimensions, evaluate_layout_from_photos_texts
from cewe_layout.pdf_export import export_layout_to_pdf
from cewe_layout.gui_controls import extract_metadata_from_filename


def run_test():
    """Main test function."""
    # Configuration
    mcf_path = Path(__file__).parent.parent.parent / 'xmas-2025.xmcf' / 'data.mcf'
    output_dir = Path(__file__).parent
    num_good_layouts = 10
    empty_threshold = 0.005  # 0.5%
    
    print(f"Loading canvas from: {mcf_path}")
    
    # Parse MCF file
    root = parse_mcf_from_path(str(mcf_path))
    pages = extract_pages_info(root)
    
    if not pages:
        print("Error: No pages found")
        return
    
    pageno, page_info = pages[0]
    photos = page_info.get('photos', [])
    texts = page_info.get('texts', [])
    page_w = page_info.get('page_width')
    page_h = page_info.get('page_height')
    origin_left = page_info.get('origin_left', 0.0)
    
    mcf_base_folder = os.path.dirname(str(mcf_path))
    image_folder_attr = root.get('imagedir') or ''
    
    print(f"Canvas size: {page_w} x {page_h} MCF units")
    print(f"Photos: {len(photos)}, Texts: {len(texts)}")
    
    # Build photo_dimensions dict using shared utility
    photo_dimensions = build_photo_dimensions(photos, mcf_base_folder, image_folder_attr)
    
    # Build preferred_sizes (uniform distribution)
    preferred_sizes = {}
    total_items = len(photos) + len(texts)
    if total_items > 0:
        uniform_size = 10.0 / total_items
        for p in photos:
            fn = p.get('filename', '')
            if fn:
                base_fn, _, _ = extract_metadata_from_filename(fn)
                preferred_sizes[fn] = uniform_size
        for i in range(len(texts)):
            preferred_sizes[f'TEXT_{i}'] = uniform_size
    
    # Set gaps to zero
    edge_gap = 0.0
    internal_gap = 0.0
    
    print(f"Running Fan-GA to find {num_good_layouts} layouts with < {empty_threshold*100}% empty space...")
    print()
    
    good_count = 0
    attempt = 0
    
    while good_count < num_good_layouts:
        attempt += 1
        
        # Create algorithm instance
        algorithm = FanLayoutAlgorithm(
            size_importance=100.0,
            undersized_threshold=0.5,
            undersized_penalty=5.0
        )
        
        # Run layout generation using existing infrastructure
        success, updated_photos, updated_texts, error = generate_layout_for_page(
            photos=photos,
            page_width_mcf=page_w,
            page_height_mcf=page_h,
            photo_dimensions=photo_dimensions,
            algorithm=algorithm,
            preferred_sizes=preferred_sizes,
            edge_gap=edge_gap,
            internal_gap=internal_gap,
            texts=texts,
            origin_left=origin_left,
            pageno=pageno,
            is_spread=False,
            acceptable_empty_fraction=0.0,  # For canvas, no acceptable empty space
            size_importance=100.0,
            undersized_threshold=0.5,
            undersized_penalty=5.0
        )
        
        if not success:
            print(f"Attempt {attempt}: Failed - {error}")
            continue
        
        # Evaluate layout using shared utility
        cost = evaluate_layout_from_photos_texts(
            updated_photos, updated_texts, page_w, page_h, origin_left,
            preferred_sizes, edge_gap, internal_gap,
            size_importance=100.0,
            acceptable_empty_fraction=0.0,
            undersized_threshold=0.5,
            undersized_penalty=5.0
        )
        
        empty_fraction = cost.empty_space_fraction
        print(f"Attempt {attempt}: Empty = {empty_fraction*100:.2f}%, Cost = {cost.total_cost:.2f}")
        
        if empty_fraction < empty_threshold:
            good_count += 1
            output_path = output_dir / f'good{good_count}.pdf'
            export_layout_to_pdf(updated_photos, updated_texts, page_w, page_h, origin_left,
                                mcf_base_folder, image_folder_attr, str(output_path))
            print(f'Exported: {output_path}')
            print(f"  ✓ Good layout #{good_count}!")
            print()
    
    print(f"\nCompleted! Generated {num_good_layouts} good layouts.")
    print(f"PDFs saved in: {output_dir}")


if __name__ == '__main__':
    run_test()

