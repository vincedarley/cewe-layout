"""Check text colors in Mimeo photobook."""
import sys
from pathlib import Path
from cewe_layout.mimeo.mimeo_database import MimeoProject

if len(sys.argv) < 2:
    print("Usage: python check_text_colors.py <path_to_ppb>")
    sys.exit(1)

ppb_path = Path(sys.argv[1])
proj = MimeoProject(ppb_path)

# Get text data and layouts
text_data = proj.get_frame_text()
layouts = proj.get_layouts()
frames = proj.get_frames()

print("\n=== TEXT COLOR ANALYSIS ===\n")

# Check front cover (layout 0) and a few interior layouts
for layout_idx in [0, 2, 3, 4]:  # Front cover, page 1, page 2, page 3
    if layout_idx >= len(layouts):
        break
    
    layout = layouts[layout_idx]
    layout_id = layout['model_id']
    page_type = 'front_cover' if layout_idx == 0 else f'interior_page_{layout_idx}'
    
    print(f'Layout {layout_idx} ({page_type}):')
    
    # Get frames for this layout
    layout_frames = [f for f in frames if f['page_id'] == layout_id]
    
    for frame in layout_frames:
        frame_id = frame['model_id']
        if frame_id in text_data:
            text_info = text_data[frame_id]
            text_preview = text_info.get('text', '')[:40]
            color_value = text_info.get('color', 'NO COLOR')
            print(f'  Frame {frame_id}:')
            print(f'    color = "{color_value}"')
            print(f'    text = "{text_preview}..."')
    print()
