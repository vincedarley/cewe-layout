"""PDF export functionality for layouts.

Standalone module for exporting page layouts to PDF with photos and text boxes.
"""
import os
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


def export_layout_to_pdf(photos, texts, page_w, page_h, origin_left, mcf_base_folder,
                         image_folder_attr, output_path):
    """Export layout to PDF with photos and white text boxes.
    
    Args:
        photos: List of photo dicts with area_left, area_top, area_width, area_height, filename
        texts: List of text dicts with area_left, area_top, area_width, area_height
        page_w: Page width in MCF units
        page_h: Page height in MCF units
        origin_left: Origin offset for right pages in MCF units
        mcf_base_folder: Base folder for resolving photo paths
        image_folder_attr: Image folder attribute from MCF root
        output_path: Path to save PDF file
    """
    # Convert MCF units to points (1 point = 1/72 inch, 1mm = 2.83465 points)
    MCF_TO_MM = 0.1
    mcf_to_points = MCF_TO_MM * 2.83465
    page_w_pt = page_w * mcf_to_points
    page_h_pt = page_h * mcf_to_points
    
    # Create PDF
    pdf_canvas = canvas.Canvas(output_path, pagesize=(page_w_pt, page_h_pt))
    
    def transform_y(y_mcf, h_mcf):
        """Convert top-left Y coordinate to bottom-left."""
        return page_h_pt - (y_mcf + h_mcf) * mcf_to_points
    
    # Draw white rectangles for text boxes
    pdf_canvas.setFillColorRGB(1, 1, 1)
    for t in texts:
        left = (t.get('area_left', 0) - origin_left) * mcf_to_points
        top_mcf = t.get('area_top', 0)
        w = t.get('area_width', 0) * mcf_to_points
        h = t.get('area_height', 0) * mcf_to_points
        bottom = transform_y(top_mcf, t.get('area_height', 0))
        pdf_canvas.rect(left, bottom, w, h, fill=1, stroke=0)
    
    # Draw photos
    for p in photos:
        left_mcf = p.get('area_left', 0)
        top_mcf = p.get('area_top', 0)
        w_mcf = p.get('area_width', 0)
        h_mcf = p.get('area_height', 0)
        
        left = (left_mcf - origin_left) * mcf_to_points
        w = w_mcf * mcf_to_points
        h = h_mcf * mcf_to_points
        bottom = transform_y(top_mcf, h_mcf)
        
        fn = p.get('filename', '')
        if not fn:
            continue
        
        # Resolve photo path
        img_path = None
        safefn = fn.replace('safecontainer:/', '').lstrip('/')
        if image_folder_attr:
            candidate = os.path.join(mcf_base_folder, image_folder_attr, safefn)
            if os.path.exists(candidate):
                img_path = candidate
        if img_path is None:
            candidate = os.path.join(mcf_base_folder, safefn)
            if os.path.exists(candidate):
                img_path = candidate
        
        if img_path and os.path.exists(img_path):
            try:
                img_reader = ImageReader(img_path)
                pdf_canvas.drawImage(img_reader, left, bottom, width=w, height=h,
                                    preserveAspectRatio=True, anchor='c')
            except Exception as e:
                # Silent failure for missing images
                pass
    
    pdf_canvas.save()
