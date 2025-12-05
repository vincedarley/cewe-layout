**cewe-layout or 'QLayout' for short**

Utility to parse CEWE `.mcf` / `.xmcf` photobook files, inspect page photo and text slots and interactively generate new layouts.  It is intended to help you make great CEWE photobooks. It is not a replacement for the Cewe Creator software. You will absolutely need to use that as well as this tool.  The problem this tool aims to solve is that it is painful, slow and cumbersome to make nice photo layouts with 5 to 15 photos in Cewe Creator. The clever auto-layout tools provided by Cewe are (for my use cases) completely unhelpful. Hence this tool.

The primary workflow step I aim to dramatically improve is this one: you have 11 photos you want to place on a single page. 2 of them are more important and should be approximately 3x the size of the others. Produce a nice-looking layout which achieves that aim, and where the photos collectively occupy most of the page (with edge gaps and internal gaps easily configurable).

**Quickstart**

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the diagnostic just to list all page contents of an unpacked `.xmcf` folder or `.mcf` file. This is perhaps a useful first step to reassure you that the tool correctly understands your photobook:

```bash
python run_qlayout.py --input /path/to/Test-album.xmcf
```

3. Run the full tool (with GUI) against an unpacked `.xmcf` folder or `.mcf` file. Now you can use the GUI to interactively and algorithmically modify layouts in your photobook, and save them, etc:

```bash
python run_qlayout.py --input /path/to/Test-album.xmcf --gui
```

**Workflow**

You have to work indepedently in QLayout vs in Cewe Creator.  In general you should only have one of the two applications open (with the same book.xmcf) at any one time.  So close one, work in the other, repeat until your book is done... In case you forget this "work independently" instruction, you should generally not worry about file corruption - but you should worry that important layout work you've done in one tool is going to be overwritten by the other.  So you will be wasting time and effort.

Here's my current workflow:
1) Select all my favourite photos in MacOS photos and export them to a directory. If it is easy for you to do so, before exporting tag the very best photos with either "4 star" or "5 star" as keywords.
2) Run QLayout with "-renamephotos" to name all of the photos according to date (and according to 4/5 star keywords).
3) Use CEWE Creator to build a book (of the size/style you want) with loads of empty pages. Save it in the xmcf or mcf format. Quit.
4) If your photobook is called "MyBook.xmcf" then put the directory with all your photos next to it, and rename the directory to be called "MyBook-photos".
5) Run QLayout with the "--gui" flag.  The first page of your book will open.  Ensure it is empty (or if your book is partially created already, move to the first empty page)
6) Examine your photos, in approximate date order, and drag and drop as many photos as you want onto that empty page.
7) Run the "Fan-GA" algorithm.  Tweak slot aspect ratio and "preferred size" for any of the photos you want -- simplest is to give the very best 2-4 photos a preferred size of somewhere between 3.0 and 6.0.
8) Re-run the "Fan-GA" algorithm. Sometimes you might wish to re-run the algorithm a few times to check out the different results and pick the one you like best. If you don't quite like any, you can delete some photos, add some new photos and try again.
9) Hit "Save" when you are done with the page.  The photos used disappear from your directory - they've been moved into the photo album.
10) Move to the next empty page and go back to step 6.

Once you're done. Open the book in CEWE Creator and do any fine-tuning you wish.

**Safety features**

QLayout does a few things to help lower the risk of problems when editing your photobook:
1. When saving a page, which modifies the xml file, it validates (after saving) both that the correct number of photos and text blocks are indeed in that xml file, and that the referenced photo files do actually exist.
2. When moving photos into the photo-book, QLayout renames the jpeg files by adding a "-pg" suffix containing the page they have been saved into. In this way if you need to manually look for photos, it is easy to find the right ones inside the book.

**Adding Photos to a Page**

You can add new photos to the current page by:
- **Drag-and-drop** (if tkinterdnd2 is installed): Drag JPEG files from Finder directly onto the main window
- **Keyboard shortcut**: Press `Cmd+O` to open a file picker and select photos

When photos are added:
1. They are copied to the album's image folder
2. Photo importance is determined from IPTC keywords:
   - "5 star" keyword → size 5.0 (high importance, ~5× larger)
   - "4 star" keyword → size 3.0 (medium importance, ~3× larger)
   - No star keyword → size 1.0 (normal)
3. Initial layout rectangles are created (overlapping at the top of the page for easy visibility)
4. You can then use any layout algorithm (Collage-Gen, Fan-GA, etc.) to arrange them nicely

Details for the technically minded:
- Saving a modified page layout in QLayout will successfully modify the data.mcf xml file inside your Cewe book project. BUT, if that book is already open in Cewe Creator (CC) application, then CC will NOT notice that the layout has changed. You will need to close the project and re-open it for CC to notice the layout changes.  Unfortunately this means that the workflow you adopt cannot efficiently include making adjustments to a Page in both QLayout and CC while moving back and forth between the two applications.
- Similarly if you modify+save a page in QLayout and modify anything else in CC (even things completely unrelated to the earlier page) and "Save" the book in CC, the "Save" in CC will overwrite the changes you have just made from QLayout. Clearly CC maintains an in-memory copy of the book and writes the entire book to disk afresh every time you "Save".
- So, in short, while working with QLayout you are best not to have the book open in CC.  So: Close CC. Work with QLayout. Then open CC.  (If you absolutely have to have CC open, treat it as a read-only tool, and do NOT accidentally "Save" else your QLayout changes will be overwritten).
- Note that while QLayout is designed only to modify the location and size of photos and text blocks on pages in the data.mcf xml file, it does also rewrite the entire xml file. Its approach is to generically load the large xml file (most of which it does not understand!), and only manipulate the location/size portions of the file, and then generically save the entire xml file (while also making a backup of the original)
- There does not seem to be any risk of file corruption, except perhaps if you choose to hit "Save" in both applications simultaneously. And we do make backups of original xml files, but of course use at your own risk.

**TO DO and Decisions**

- Workflow: do we continue to use MacOS Photos as an efficient way to examine photos? Or just for tagging, and then mass export?
- More layout clean-up algorithms? (beyond Gridify)
- Consider adding support for other star ratings (1-3 stars) if needed

**Layout Algorithms**

- **[Fan Layout](cewe_layout/algorithms/fan_layout.py)** — Genetic algorithm-based layout using binary slicing trees with O(N) fast evaluation, based on [Fan, Jian (2012)](https://ieeexplore.ieee.org/document/6267282). Uses crossover and mutation operators to explore the layout space, balancing canvas coverage and photo size distribution. Best for generating completely new layouts from scratch.

- **[Collage Generator](cewe_layout/algorithms/collage_generator.py)** — Content-preserved photo collage algorithm based on [Wu & Aizawa (2016)](https://www.researchgate.net/publication/269455490_Very_fast_generation_of_content_preserved_photo_collage_under_canvas_size_constraint). Uses greedy tree construction to preserve aspect ratios while maximizing canvas coverage. Adapted from [n-gao's implementation](https://github.com/n-gao/collage-generator).

- **[Tree Builder](cewe_layout/algorithms/tree_builder.py)** — Reverse-engineers existing layouts into binary slicing tree representations by finding splitting lines. Useful for analyzing existing Cewe layouts or converting manual layouts into tree structures that can be mutated. Operates on layouts with positioned rectangles and reconstructs the underlying tree structure.

- **[Gridify](cewe_layout/algorithms/gridify.py)** — Cleanup algorithm that snaps an existing layout to a regular grid determined by the smallest photo's dimensions. Takes a messy layout with near-aligned photos and aligns all corners precisely to grid points. Best for fine-tuning layouts that are already reasonably well-organized.

- `cewe-layout/cewe_layout/algorithms/base.py` — abstract layout algorithm interface using unified `LayoutRectangle` I/O model. If you want to write your own algorithms for creating and improving Page layouts, this is where you should start.

**For architectural details and API design, see [`API_DESIGN.md`](docs/API_DESIGN.md).**

**License**

This project is licensed under the MIT License.
See `LICENSE` for details.

