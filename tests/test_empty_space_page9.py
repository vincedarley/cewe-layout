"""
Test empty space calculation for Page 9.

Verify that empty space is calculated correctly accounting for edge gap and internal gap.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cewe_layout.parser import parse_mcf_from_path, extract_pages_info
from cewe_layout.gap_utils import analyze_gaps
from cewe_layout.algorithms.base import LayoutRectangle
from cewe_layout.algorithms.evaluator import evaluate_layout


def test_page_9_empty_space():
    """Test empty space calculation for page 9."""
    
    mcf_path = Path(__file__).parent.parent.parent / 'Test-album.xmcf' / 'data.mcf'
    if not mcf_path.exists():
        print(f"⚠️  Test skipped: {mcf_path} not found")
        return
    
    print(f"Parsing MCF: {mcf_path}")
    mcf_root = parse_mcf_from_path(str(mcf_path))
    pages_info = extract_pages_info(mcf_root)
    
    # Find page 9
    page_9_info = None
    for pageno, info in pages_info:
        if pageno == 9:
            page_9_info = info
            break
    
    if not page_9_info:
        print("⚠️  Page 9 not found in MCF")
        return
    
    photos = page_9_info.get('photos', [])
    texts = page_9_info.get('texts', [])
    page_w = page_9_info.get('page_width', 2100)
    page_h = page_9_info.get('page_height', 2970)
    origin_left = page_9_info.get('origin_left', 0.0)
    
    print(f"\n{'='*70}")
    print(f"PAGE 9 EMPTY SPACE ANALYSIS")
    print(f"{'='*70}")
    print(f"\nPage dimensions: {page_w} x {page_h} MCF units ({page_w/10:.1f} x {page_h/10:.1f} mm)")
    print(f"Total page area: {page_w * page_h:,.0f} MCF² ({(page_w * page_h)/100:.1f} cm²)")
    print(f"Origin left: {origin_left}")
    print(f"Photos: {len(photos)}")
    print(f"Texts: {len(texts)}")
    
    # Analyze gaps
    all_items = photos + texts
    analysis = analyze_gaps(all_items, page_w, page_h, origin_left)
    
    print(f"\n--- Gap Analysis ---")
    print(f"Edge gap: {analysis.edge_gap:.1f} MCF units ({analysis.edge_gap/10:.1f} mm)")
    print(f"Internal gap: {analysis.internal_gap:.1f} MCF units ({analysis.internal_gap/10:.1f} mm)")
    print(f"Bleed: {analysis.bleed:.1f} MCF units ({analysis.bleed/10:.1f} mm)")
    
    edge_gap = analysis.edge_gap
    internal_gap = analysis.internal_gap
    
    print(f"\nTransformation logic:")
    print(f"  - Photo positions: subtract edge_gap ({edge_gap:.1f}) to remove margins")
    print(f"  - Photo dimensions: add internal_gap ({internal_gap:.1f}) so they touch")
    print(f"  - Page width: {page_w:.1f} - 2*{edge_gap:.1f} + {internal_gap:.1f}")
    print(f"  - Page height: {page_h:.1f} - 2*{edge_gap:.1f} + {internal_gap:.1f}")
    
    # Calculate areas in WITH-GAP space (what we see in the MCF file)
    print(f"\n--- Photo Areas (WITH gap - as stored in MCF) ---")
    total_photo_area_with_gap = 0
    for i, p in enumerate(photos, 1):
        w = p.get('area_width', 0)
        h = p.get('area_height', 0)
        area = w * h
        total_photo_area_with_gap += area
        print(f"  Photo {i}: {w:.1f} x {h:.1f} = {area:,.0f} MCF²")
    
    print(f"\nTotal photo area (with gap): {total_photo_area_with_gap:,.0f} MCF²")
    print(f"Coverage (with gap): {total_photo_area_with_gap / (page_w * page_h) * 100:.1f}%")
    
    # Now calculate in GAP-FREE space (what the evaluator uses)
    # Remove edge_gap from top/left, (edge_gap - internal_gap) from bottom/right
    # = remove 2*edge_gap + add internal_gap
    
    eval_page_w = page_w - 2*edge_gap + internal_gap
    eval_page_h = page_h - 2*edge_gap + internal_gap
    
    print(f"\n--- Gap-Free Coordinate Space (for evaluation) ---")
    print(f"Gap-free page dimensions: {eval_page_w:.1f} x {eval_page_h:.1f} MCF units")
    print(f"Gap-free page area: {eval_page_w * eval_page_h:,.0f} MCF²")
    print(f"Calculation: page_w - 2*edge_gap + internal_gap")
    print(f"  = {page_w:.1f} - 2*{edge_gap:.1f} + {internal_gap:.1f}")
    print(f"  = {eval_page_w:.1f}")
    
    # Build rectangles for evaluation
    rectangles = []
    print(f"\n--- Photo Rectangles (gap-free space) ---")
    print(f"Format: x, y, width, height (photos expand by internal_gap to touch)")
    total_rect_area = 0
    for i, p in enumerate(photos):
        left = p.get('area_left', 0)
        top = p.get('area_top', 0)
        w = p.get('area_width', 0)
        h = p.get('area_height', 0)
        
        # Transform to gap-free: subtract edge_gap from position, add internal_gap to dimensions
        x = left - origin_left - edge_gap
        y = top - edge_gap
        rect_w = w + internal_gap
        rect_h = h + internal_gap
        
        rect_area = rect_w * rect_h
        total_rect_area += rect_area
        
        fn = p.get('filename', '')
        rect = LayoutRectangle(
            item_id=str(i),
            width=rect_w,
            height=rect_h,
            preferred_size=1.0,
            preserve_aspect_ratio=True,
            x=x,
            y=y
        )
        rectangles.append(rect)
        print(f"  Photo {i+1}: x={x:.1f}, y={y:.1f}, w={rect_w:.1f}, h={rect_h:.1f}, area={rect_area:,.0f}")
        
        # Check if photo extends beyond page
        if x < 0 or y < 0:
            print(f"      ⚠️  Photo extends before page origin!")
        if x + rect_w > eval_page_w or y + rect_h > eval_page_h:
            print(f"      ⚠️  Photo extends beyond page: right={x + rect_w:.1f} (page={eval_page_w:.1f}), bottom={y + rect_h:.1f} (page={eval_page_h:.1f})")
    
    # Add text rectangles
    for i, t in enumerate(texts):
        w = t.get('area_width', 0)
        h = t.get('area_height', 0)
        
        rect_w = w + gap
        rect_h = h + gap
        rect_area = rect_w * rect_h
        total_rect_area += rect_area
        
        text_id = f'TEXT_{i}'
        rect = LayoutRectangle(
            item_id=text_id,
            width=rect_w,
            height=rect_h,
            preferred_size=1.0,
            preserve_aspect_ratio=False,
            x=t.get('area_left', 0) - origin_left - gap,
            y=t.get('area_top', 0) - gap
        )
        rectangles.append(rect)
        print(f"  Text {i+1}: {rect_w:.1f} x {rect_h:.1f} = {rect_area:,.0f} MCF²")
    
    print(f"\nTotal rectangle area (gap-free): {total_rect_area:,.0f} MCF²")
    print(f"Gap-free page area: {eval_page_w * eval_page_h:,.0f} MCF²")
    print(f"Coverage: {total_rect_area / (eval_page_w * eval_page_h) * 100:.1f}%")
    
    # Evaluate layout
    cost = evaluate_layout(
        eval_page_w, eval_page_h, rectangles,
        size_importance=10.0,
        acceptable_empty_fraction=0.05
    )
    
    print(f"\n--- Layout Evaluation Results ---")
    print(f"Empty space fraction: {cost.empty_space_fraction:.1%}")
    print(f"Empty space cost: {cost.empty_space_cost:.2f}%")
    print(f"Size mismatch cost: {cost.size_mismatch_cost:.2f}")
    print(f"Total cost: {cost.total_cost:.2f}")
    
    # Manual verification
    print(f"\n--- Manual Verification ---")
    used_area = total_rect_area
    empty_area = (eval_page_w * eval_page_h) - used_area
    empty_fraction = empty_area / (eval_page_w * eval_page_h)
    
    print(f"Used area: {used_area:,.0f} MCF²")
    print(f"Empty area: {empty_area:,.0f} MCF²")
    print(f"Empty fraction: {empty_fraction:.1%}")
    
    # Check if evaluation matches manual calculation
    if abs(empty_fraction - cost.empty_space_fraction) < 0.001:
        print(f"✓ Evaluation matches manual calculation")
    else:
        print(f"✗ MISMATCH: Evaluation {cost.empty_space_fraction:.3%} vs Manual {empty_fraction:.3%}")
    
    # Expected vs actual
    print(f"\n--- Analysis ---")
    if edge_gap > 0 or internal_gap > 0:
        print(f"With edge gap of {edge_gap/10:.1f}mm and internal gap of {internal_gap/10:.1f}mm:")
        print(f"  - Page has {edge_gap/10:.1f}mm margins on each edge")
        print(f"  - Photos/texts have {internal_gap/10:.1f}mm spacing between them")
        print(f"  - Empty space of {cost.empty_space_fraction:.1%} means:")
        print(f"    → {empty_area:,.0f} MCF² ({empty_area/100:.1f} cm²) is unused")
        print(f"    → After 5% acceptable threshold: {cost.empty_space_cost:.1f}% excess")
    
    # Detailed photo breakdown
    print(f"\n--- Detailed Photo Positions ---")
    for i, p in enumerate(photos, 1):
        left = p.get('area_left', 0) - origin_left
        top = p.get('area_top', 0)
        w = p.get('area_width', 0)
        h = p.get('area_height', 0)
        right = left + w
        bottom = top + h
        
        # Calculate margins
        left_margin = left
        top_margin = top
        right_margin = page_w - right
        bottom_margin = page_h - bottom
        
        print(f"  Photo {i}:")
        print(f"    Position: ({left:.1f}, {top:.1f}) to ({right:.1f}, {bottom:.1f})")
        print(f"    Size: {w:.1f} x {h:.1f}")
        print(f"    Margins: L={left_margin:.1f}, T={top_margin:.1f}, R={right_margin:.1f}, B={bottom_margin:.1f}")


if __name__ == '__main__':
    test_page_9_empty_space()
