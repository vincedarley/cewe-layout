"""Simple Tkinter UI to browse pages and display layout rectangles."""
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageDraw, ImageTk, ImageOps
import math
import os
from pathlib import Path
import threading
import traceback
import cv2

from .parser import extract_pages_info, parse_mcf_from_path
from .layout_ops import LayoutManager
from .collage_wrapper import generate_layout_for_page


class LayoutViewer:
    def __init__(self, root, mcf_root, mcf_file_path):
        # mcf_root is the parsed XML root; mcf_file_path is the full path to the .mcf file
        self.pages = extract_pages_info(mcf_root)
        self.mcf_file_path = mcf_file_path
        # try to find the imagedir attribute on the root to locate images
        self.image_folder_attr = mcf_root.get('imagedir') or ''
        self.mcf_base_folder = '' if mcf_file_path is None else os.path.dirname(mcf_file_path)
        self.index = 0
        self.layout_mgr = LayoutManager()

        # initialize layout manager with originals from file
        for pageno, info in self.pages:
            self.layout_mgr.set_original(pageno, info.get('photos', []))

        # Main window for page display
        self.root = root
        self.root.title('cewe-layout — Page Viewer')

        self.canvas_w = 900
        self.canvas_h = 1200

        self.img_label = ttk.Label(self.root)
        self.img_label.pack(fill='both', expand=True)

        # Controls window
        self.ctrl = tk.Toplevel(self.root)
        self.ctrl.title('Controls')
        self.ctrl.geometry('+50+50')

        prev_btn = ttk.Button(self.ctrl, text='Prev (←)', command=self.prev_page)
        prev_btn.grid(row=0, column=0, padx=4, pady=4)
        next_btn = ttk.Button(self.ctrl, text='Next (→)', command=self.next_page)
        next_btn.grid(row=0, column=1, padx=4, pady=4)
        ttk.Label(self.ctrl, text='Go to:').grid(row=0, column=2)
        self.goto_var = tk.StringVar()
        goto_entry = ttk.Entry(self.ctrl, textvariable=self.goto_var, width=6)
        goto_entry.grid(row=0, column=3, padx=4)
        goto_btn = ttk.Button(self.ctrl, text='Go', command=self.goto_page)
        goto_btn.grid(row=0, column=4, padx=4)
        
        self.gen_btn = ttk.Button(self.ctrl, text='Generate Layout', command=self.generate_layout)
        self.gen_btn.grid(row=1, column=0, padx=4, pady=4)
        undo_btn = ttk.Button(self.ctrl, text='Back', command=self.undo_layout)
        undo_btn.grid(row=1, column=1, padx=4, pady=4)
        save_btn = ttk.Button(self.ctrl, text='Save', command=self.save_layout)
        save_btn.grid(row=1, column=2, padx=4, pady=4)
        orig_btn = ttk.Button(self.ctrl, text='Use Original', command=self.use_original)
        orig_btn.grid(row=1, column=3, padx=4, pady=4)
        
        weights_btn = ttk.Button(self.ctrl, text='Adjust Weights', command=self.adjust_weights)
        weights_btn.grid(row=2, column=0, padx=4, pady=4)
        diag_btn = ttk.Button(self.ctrl, text='Diag Thumb', command=self.diag_thumbnail)
        diag_btn.grid(row=2, column=1, padx=4, pady=4)
        
        quit_btn = ttk.Button(self.ctrl, text='Quit (q)', command=self.quit)
        quit_btn.grid(row=1, column=4, padx=8)

        # keyboard bindings
        self.root.bind('<Left>', lambda e: self.prev_page())
        self.root.bind('<Right>', lambda e: self.next_page())
        self.root.bind('<q>', lambda e: self.quit())
        self.ctrl.bind('<Return>', lambda e: self.goto_page())

        self.photo_image = None
        self.thumb_cache = {}  # filename -> PIL.Image (thumbnail)
        self.render_page()

    def render_page(self):
        if not self.pages:
            img = Image.new('RGB', (self.canvas_w, self.canvas_h), 'white')
            draw = ImageDraw.Draw(img)
            draw.text((10,10), 'No pages found', fill='black')
            self._show_image(img)
            return

        pageno, info = self.pages[self.index]
        # Fetch current layout from layout manager (may be modified or original)
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])

        img = Image.new('RGB', (self.canvas_w, self.canvas_h), 'white')
        draw = ImageDraw.Draw(img)

        # Draw header
        draw.text((8,8), f'Page {pageno} — {len(photos)} photos', fill='black')

        # Use page meta to map coordinates. page_width/height are in MCF units (0.1mm)
        page_w = info.get('page_width', 2100.0)
        page_h = info.get('page_height', 2970.0)
        origin_left = info.get('origin_left', 0.0)

        margin = 20
        # scale to fit width (maintain aspect ratio)
        scale_x = (self.canvas_w - 2*margin) / page_w
        scale_y = (self.canvas_h - 2*margin) / page_h
        scale = min(scale_x, scale_y)

        # draw a frame representing the actual page
        frame_w = page_w * scale
        frame_h = page_h * scale
        frame_x = margin
        frame_y = margin
        draw.rectangle([frame_x, frame_y, frame_x+frame_w, frame_y+frame_h], outline='black', width=2)

        for i, p in enumerate(photos, start=1):
            left = p.get('area_left') or 0
            top = p.get('area_top') or 0
            w = p.get('area_width') or 0
            h = p.get('area_height') or 0

            # subtract origin_left so right-page areas are positioned relative to their page
            local_left = left - origin_left

            x0 = frame_x + local_left * scale
            y0 = frame_y + top * scale
            x1 = frame_x + (local_left + w) * scale
            y1 = frame_y + (top + h) * scale

            # draw image thumbnail if available
            fn = p.get('filename') or ''
            if fn:
                # construct image path from mcf base folder and imagedir attribute if present
                img_path = None
                safefn = fn.replace('safecontainer:/', '').lstrip('/')
                if self.image_folder_attr:
                    candidate = os.path.join(self.mcf_base_folder, self.image_folder_attr, safefn)
                    if os.path.exists(candidate):
                        img_path = candidate
                # fallback: check relative to mcf base
                if img_path is None:
                    candidate = os.path.join(self.mcf_base_folder, safefn)
                    if os.path.exists(candidate):
                        img_path = candidate

                if img_path is not None:
                    thumb = self._get_thumbnail(img_path, int(x1-x0), int(y1-y0))
                    if thumb is not None:
                        img.paste(thumb, (int(x0), int(y0)))
                    else:
                        # draw a light placeholder for missing thumbnail
                        draw.rectangle([x0, y0, x1, y1], fill='#eeeeee')

            # wireframe overlay
            draw.rectangle([x0, y0, x1, y1], outline='blue', width=2)
            # filename text
            shortfn = (fn or '').split('/')[-1]
            draw.text((x0+4, y0+4), f'{i}: {shortfn}', fill='black')

        self._show_image(img)

    def _show_image(self, pil_img):
        self.photo_image = ImageTk.PhotoImage(pil_img)
        self.img_label.configure(image=self.photo_image)

    def _get_thumbnail(self, path, w, h):
        # Avoid creating huge thumbnails; enforce minimums
        if w <= 0 or h <= 0:
            return None
        key = (path, w, h)
        if key in self.thumb_cache:
            return self.thumb_cache[key]
        try:
            im = Image.open(path)
            # Auto-rotate based on EXIF orientation (support older Pillow)
            exif_transpose = getattr(Image, 'exif_transpose', None) or getattr(ImageOps, 'exif_transpose', None)
            if exif_transpose:
                try:
                    im = exif_transpose(im)
                except Exception:
                    # If transpose fails, continue without raising noisy traceback
                    pass
            im = im.convert('RGB')
            im.thumbnail((w, h), Image.LANCZOS)
            # create a background image exactly the size of slot and paste centered
            bg = Image.new('RGB', (w, h), 'white')
            x = max(0, (w - im.width) // 2)
            y = max(0, (h - im.height) // 2)
            bg.paste(im, (x, y))
            self.thumb_cache[key] = bg
            return bg
        except Exception as e:
            # Detailed diagnostic for failures: print exception and try OpenCV fallback
            print(f"[thumb] PIL failed to open {path}: {e}")
            traceback.print_exc()
            try:
                arr = cv2.imread(str(path), cv2.IMREAD_COLOR)
                if arr is None:
                    print(f"[thumb] OpenCV failed to read {path} (imread returned None)")
                    return None
                arr = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
                im2 = Image.fromarray(arr)
                im2.thumbnail((w, h), Image.LANCZOS)
                bg = Image.new('RGB', (w, h), 'white')
                x = max(0, (w - im2.width) // 2)
                y = max(0, (h - im2.height) // 2)
                bg.paste(im2, (x, y))
                self.thumb_cache[key] = bg
                return bg
            except Exception as e2:
                print(f"[thumb] OpenCV fallback also failed for {path}: {e2}")
                traceback.print_exc()
                return None

    def prev_page(self):
        if self.index > 0:
            self.index -= 1
            self.render_page()

    def next_page(self):
        if self.index < len(self.pages)-1:
            self.index += 1
            self.render_page()

    def goto_page(self):
        try:
            v = int(self.goto_var.get())
        except Exception:
            return
        # find index for page number
        for i,(pn,_) in enumerate(self.pages):
            if pn == v:
                self.index = i
                self.render_page()
                return

    def quit(self):
        self.root.quit()

    def generate_layout(self):
        """Run collage-generator on current page photos in a background thread.

        The Generate button is disabled while the operation runs and re-enabled
        when finished. Errors are shown; successful completion updates the UI
        without a popup.
        """
        # disable the button immediately to prevent double clicks
        try:
            self.gen_btn.config(state='disabled')
        except Exception:
            pass

        def worker():
            pageno, info = self.pages[self.index]
            current_layout = self.layout_mgr.get_current(pageno)
            photos = current_layout.photos if current_layout else info.get('photos', [])

            if not photos:
                # re-enable on main thread
                self.root.after(0, lambda: self.gen_btn.config(state='normal'))
                return

            page_w = info.get('page_width', 2100.0)
            page_h = info.get('page_height', 2970.0)

            success, updated_photos, error_msg = generate_layout_for_page(
                photos, page_w, page_h, Path(self.mcf_base_folder), temperature=1.0
            )

            # If this page has an origin_left (right-hand page), the parser
            # stores area_left as absolute coordinates relative to the full spread.
            # The collage generator returns coordinates relative to the single-page
            # width (0..page_w). Add origin_left back so updated area_left matches
            # the original absolute coordinate system.
            if success and updated_photos:
                origin_left = info.get('origin_left', 0.0)
                if origin_left:
                    for up in updated_photos:
                        # Some items may lack area_left; guard the addition
                        if 'area_left' in up and up['area_left'] is not None:
                            up['area_left'] = up['area_left'] + origin_left

            def on_done():
                # re-enable button
                try:
                    self.gen_btn.config(state='normal')
                except Exception:
                    pass

                if not success:
                    messagebox.showerror('Layout Generation Failed', error_msg)
                    return

                # Push new layout to manager and refresh view
                self.layout_mgr.push_layout(pageno, updated_photos)
                self.render_page()

            self.root.after(0, on_done)

        t = threading.Thread(target=worker, daemon=True)
        t.start()

    def undo_layout(self):
        """Revert to previous layout variant."""
        pageno, info = self.pages[self.index]
        if self.layout_mgr.undo_layout(pageno):
            self.render_page()
        else:
            messagebox.showinfo('Back', 'No more layouts to go back to.')

    def save_layout(self):
        """Accept current layout and clear in-memory variants."""
        pageno, info = self.pages[self.index]
        self.layout_mgr.clear_layouts(pageno)
        messagebox.showinfo('Save', f'Layout for page {pageno} saved. Memory cleared.')
        self.render_page()

    def adjust_weights(self):
        """Open dialog to adjust per-photo weights for layout generation."""
        pageno, info = self.pages[self.index]
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])
        
        if not photos:
            messagebox.showinfo('Adjust Weights', 'No photos on this page.')
            return
        
        # Create top-level weight dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f'Photo Weights - Page {pageno}')
        dialog.geometry('400x500')
        
        # Header
        tk.Label(dialog, text=f'Adjust weights for page {pageno} photos:', 
                font=('Helvetica', 10, 'bold')).pack(pady=10)
        
        # Scrollable frame
        canvas = tk.Canvas(dialog)
        scrollbar = ttk.Scrollbar(dialog, orient='vertical', command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            '<Configure>',
            lambda e: canvas.configure(scrollregion=canvas.bbox('all'))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Weight controls for each photo
        weight_vars = {}
        for i, photo in enumerate(photos):
            fn = photo.get('filename', '').split('/')[-1]
            current_weight = self.layout_mgr.get_weight(pageno, photo.get('filename', ''))
            
            frame = ttk.Frame(scrollable_frame)
            frame.pack(fill='x', padx=5, pady=5)
            
            label = ttk.Label(frame, text=f'{i+1}. {fn[:30]}', width=35, anchor='w')
            label.pack(side='left', padx=5)
            
            var = tk.DoubleVar(value=current_weight)
            weight_vars[photo.get('filename', '')] = var
            
            spinbox = ttk.Spinbox(frame, from_=0.5, to=2.0, increment=0.1, 
                                 textvariable=var, width=6)
            spinbox.pack(side='right', padx=5)
        
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # OK/Cancel buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(side='bottom', fill='x', padx=10, pady=10)
        
        def apply_weights():
            for fn, var in weight_vars.items():
                self.layout_mgr.set_weight(pageno, fn, var.get())
            dialog.destroy()
            messagebox.showinfo('Weights Updated', 'Photo weights updated. Use them in next layout generation.')
        
        ttk.Button(button_frame, text='OK', command=apply_weights).pack(side='left', padx=5)
        ttk.Button(button_frame, text='Cancel', command=dialog.destroy).pack(side='left', padx=5)

    def diag_thumbnail(self):
        """Diagnostic: resolve first photo path and show a thumbnail preview."""
        pageno, info = self.pages[self.index]
        current_layout = self.layout_mgr.get_current(pageno)
        photos = current_layout.photos if current_layout else info.get('photos', [])

        if not photos:
            messagebox.showinfo('Diag', 'No photos on this page.')
            return

        p = photos[0]
        fn = p.get('filename', '')
        safefn = fn.replace('safecontainer:/', '').lstrip('/')
        img_path = None
        if self.image_folder_attr:
            candidate = os.path.join(self.mcf_base_folder, self.image_folder_attr, safefn)
            if os.path.exists(candidate):
                img_path = candidate
        if img_path is None:
            candidate = os.path.join(self.mcf_base_folder, safefn)
            if os.path.exists(candidate):
                img_path = candidate

        print(f'[diag] page {pageno} filename: {fn} -> resolved: {img_path}')

        if not img_path:
            messagebox.showerror('Diag', f'Image not found for: {fn}\nTried: {safefn}')
            return

        # attempt to create a reasonably-sized thumbnail
        thumb = self._get_thumbnail(img_path, 400, 400)
        if thumb is None:
            messagebox.showerror('Diag', f'Failed to create thumbnail for: {img_path}')
            return

        # show thumbnail in a small window
        top = tk.Toplevel(self.root)
        top.title('Diagnostic Thumbnail')
        ph = ImageTk.PhotoImage(thumb)
        lbl = ttk.Label(top, image=ph)
        lbl.image = ph
        lbl.pack(padx=8, pady=8)
        messagebox.showinfo('Diag', f'Resolved and loaded: {img_path}')

    def use_original(self):
        """Discard current layout and revert to original from file."""
        pageno, info = self.pages[self.index]
        self.layout_mgr.clear_layouts(pageno)
        messagebox.showinfo('Use Original', f'Reverted page {pageno} to original layout.')
        self.render_page()


def launch_gui(mcf_path):
    root_el = parse_mcf_from_path(mcf_path)
    root = tk.Tk()
    app = LayoutViewer(root, root_el, mcf_path)
    root.mainloop()
