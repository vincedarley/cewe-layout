**cewe-layout or 'QLayout' for short**

Primary purpose:

This is a tool to semi-automatically generate new layouts for pages of your CEWE `.mcf` / `.xmcf` photobook files.  It is intended to help you make great CEWE photobooks. It is not a replacement for the Cewe Creator software (and never will be). You will absolutely want to use that as well as this tool.  The problem this tool aims to solve is that it is painful, slow and cumbersome to make nice photo layouts with 5 to 15 photos in Cewe Creator. The clever auto-layout tools provided by Cewe are (for my use cases) completely unhelpful. Hence this tool.

The primary workflow step I aim to dramatically improve is this one: you have 11 photos you want to place on a single page. 3 of them are more important and should be approximately 4x the size of the others, two other photos would also preferably be a bit larger than the rest, say 2x the size. You want to produce a nice-looking layout which achieves these aims, and where the photos collectively occupy most of the page (with edge gaps and internal gaps easily configurable and precisely aligned).  Perhaps you want to include 1-2 text boxes in the layout.  And you want to get that beautiful layout in seconds, not 10s of minutes... And you want to be able to press a button to see different layouts which achieve these aims, so you can pick the one you like the most.

Using this tool, I've now built more than one 100+ page photobook that looks great, in very little time, and with very little hassle.  After some quick fine-tuning in CEWE's software I can then get them purchased, printed & delivered.

Secondary purpose:

Recover, modernise old photobooks. I have PDF files of photo-books from old software, some of them quite low quality. I have legacy Mimeo photo-books stored in ".ppb" database files from iPhoto and early Apple Photos days. I have a scanned physical album in PDF form. This tool can facilitate the process of turning those old non-editable documents into new editable CEWE photobook files, resizing/rescaling them if desired (e.g. I choose to save the new editable photobook in CEWE's XXL Landscape size), and helping you replace low-resolution photos with higher resolution originals from your library.

As part of this secondary purpose, you can also merge two .mcf photobook files into a single photo-book. Currently rescaling & merging photobooks creates an entirely new photobook and you will lose any fancy formatting you may have applied to photos, text, etc.

**Quickstart**

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the diagnostic just to list all page contents of an unpacked `.xmcf` folder-bundle or `.mcf` file (assuming you already have a partially completed photo-book project). This is perhaps a useful first step to reassure you that the tool correctly understands your photobook:

```bash
python run_qlayout.py --cewe /path/to/My-album.xmcf --nogui
```

Note that if your photobook is stored in the newest '.mcfx' format ('x' at the _end_ of the extension, not the start), that means your book's "files" have been put into an SQLite database and are one big blob. You will need to open the photobook in CEWE Creator and "Save As" the older file format.  At some point I might build in direct support for the database, but given we need to both read and write, that will require more careful work and testing... (feel free to contribute).

3. Run the full tool (with GUI) against an unpacked `.xmcf` folder or `.mcf` file. Now you can use the GUI to interactively and algorithmically modify layouts in your photobook, and save them, etc (just remove the '--nogui' flag), using either of these:

```bash
python run_qlayout.py --cewe /path/to/My-album.xmcf
python run_qlayout.py --cewe /path/to/My-album/data.mcf
```

Note that on MacOS, CEWE registers the ".xmcf" directory extension with MacOS so that this directory (which contains the data.mcf file and all the photos it references), appears as a single bundle -- which you can double-click on to launch CEWE Creator and open the photobook.  If you want to peer inside the directory in the Finder, right click on it and select "Show Package Contents".

**Primary Workflow**

You have to work _indepedently_ in QLayout vs in Cewe Creator.  In general you should only have one of the two applications open (with the same photobook) at any one time.  So close one, work in the other, repeat until your book is done... In case you forget this "work independently" instruction, you should generally not worry about file corruption - but you should worry that important layout work you've done in one tool is going to be overwritten by the other.  So you will be wasting time and effort.

Here's my current workflow:
1) Select all your favourite photos in MacOS Photos (or whatever you use to organise your master photos) and _export_ _copies_ of them to a directory. If it is easy for you to do so, before exporting tag the very best photos with either "4 star" or "5 star" as keywords, and make sure you export those keywords. CEWE Creator seems to support jpeg, png, and heif/heic (at least on MacOS), and so does QLayout.
2) Optionally, run QLayout with "-renamephotos" to name all of the photos according to date (and according to 4/5 star keywords).  For example: python run_qlayout.py --renamephotos path/to/exported-directory "yr". This isn't _necessary_ but I find it helpful to have a clear photo naming scheme in place.
3) Use CEWE Creator to create a new photo-book (of the size/style you want) with loads of empty pages. Save it in the older xmcf or mcf format. Quit CEWE Creator.
4) If your photobook is called "MyBook.xmcf" then put the directory with all your photos next to it, and rename the directory to be called "MyBook-photos".
5) Run QLayout (python run_qlayout --cewe /path/to/MyBook.xmcf). The first empty page of your book will open automatically.
6) Examine your photos, in approximate date order (assuming your photo-books are roughly chronological), and drag and drop as many photos as you want onto that empty page.
7) Run the "Genetic Algorithm (Fan)" algorithm.  Tweak slot aspect ratio and "preferred size" for any of the photos you want -- simplest is to give the very best 2-4 photos a preferred size of somewhere between 3.0 and 6.0.  This is easy in the UI.
- Re-run the "Genetic Algorithm (Fan)" algorithm. Sometimes you might wish to re-run the algorithm a few times to check out the different results and pick the layout you like best. 
- If you don't quite like any, you can delete some photos, add some new photos (or a text-box) and try again.  
- If you want an exact grid layout (e.g. 2 rows of 4 photos, all identically sized), try the "Gridify" algorithm instead of Fan-GA.
- Adjust edge gaps and internal gaps for a different look
8) Hit "Save Modified" when you are done with the page.  The photos used disappear from your "-photos" directory - they've been moved into the photo album. This is very helpful, since you can then focus only on the photos you've not yet added. If there are photos I've decided I no longer want, I simply delete them from the "-photos" directory (they are exported copies, so no harm deleting them). If for some reason you've added the same photo twice (to one or more pages), you will get an error on saving.
9) Move to the next empty page and go back to step 6. If you have no more empty pages, open in CEWE Creator to add some more.

Once you're done: open the book in CEWE Creator and do any fine-tuning you wish. Typically:
- Adjust zoom levels of photos
- Adjust photo cropping (in general the QLayout algorithms produce layouts which require almost zero cropping, so this is normally only required if you zoom into your photos)
- Change the background colour
- Edit/adjust text boxes
- Use any of the many other decorative features CEWE provide.
...or of course if you want rotated photos or any other creative manual layout.

Optional additional steps in QLayout:
- Use the "Photo Gap Perfecter" algorithms to ensure all edge gaps and internal gaps on a page are identical - fixing minor imperfections or overlaps. The "Long Gap Perfecter" aligns photos/texts along long straight lines that approximately exist in your layout - making them exactly straight. The "Photo Gap Perfecter" just looks locally at each photo and its neighbours. 
- Adjust the "Edge Gap" and "Internal Gap" - on some pages you might want a large gap, on others no gap at all.  Note that an edge-gap of -3.0mm is what CEWE suggests for full-page layouts. The 3.0mm bleed ensures a neat edge to the page.
- Export PDF - this is a quick export of just a single page of photos (no texts) so you can examine carefully.
- Note that if you have used zoom/cropping in CEWE, which is saved into the .mcf file, QLayout will NOT modify the zoom/cropping that you have previously saved. Normally this is what you want, since you are at the stage of fine-tuning the layout, and would not want QLayout to over-write any careful adjustments you have made.

You can obviously go back and forth between CEWE Creator and QLayout as often as you wish.

Finally:
1) Order the photobook from CEWE.
2) Use (separate) cewe2pdf project from github to export a high-quality, accurate PDF of your entire photobook.
3) Backup both your photobook and pdf copy for safe-keeping.

**Adding Photos to a Page**

You can add new photos to the current page by:
- **Drag-and-drop** (if tkinterdnd2 is installed): Drag photo files (.jpeg, etc) from Finder directly onto the main window
- **Keyboard shortcut**: Press `Cmd+O` to open a file picker and select photos

When photos are added:
1. They are copied to the album's image folder
2. Photo importance is determined from IPTC keywords:
   - "5 star" keyword → size 5.0 (high importance, ~5× larger)
   - "4 star" keyword → size 3.0 (medium importance, ~3× larger)
   - No star keyword → size 1.0 (normal)
3. Initial layout rectangles are created (overlapping at the top of the page for easy visibility)
4. You can then use any layout algorithm (Collage-Gen, Fan-GA, etc.) to arrange them nicely

**Secondary workflow for importing old photo books**

If you have old PDF files, or legacy Mimeo photobooks stored in .ppb files inside your Apple Photos library, this tool can import those fairly easily to create a new editable .mcf photobook.  Use:

```bash
python run_qlayout.py --cewe ../2012-test-converted.xmcf --originalPdf ../2012-album.pdf
```

In this first case I have an old PDF photobook from 2012, which I want to import into editable form.  And then, if necessary, apply various algorithms to identify/extract photos from each page (if the fully automatic import hasn't quite identified photos correctly).  I've used this to turn old PDFs from Mimeo-photos exports into editable photobooks again.

Photo improver (experimental): building on top of the PDF import, search in a directory of photos for higher quality instances of the photos extracted from the PDF, so that you can enhance the digital photo album and potentially re-print at higher quality.  This automatic search is not that great, however, and I find it quicker just to replace all the photos manually after opening the newly editable album in CEWE Creator.

For legacy Mimeo photobooks, use:

```bash
python -m cewe_layout.mimeo_import.convert_mimeo_cli \                                                        
  --ppb "../2014-2015-library.photoslibrary/resources/projects/legacy/96877E29-2401-41E3-B0DF-090065A2EBDB.ppb" \
  --library "../2014-2015-library.photoslibrary" \
  --output "../2015-test-converted.xmcf" \
  --verbose
```

In this second case I have an old Apple Photos library, containing just the photos from 2 years, which I have saved on disk as "2014-2015-library", and which contains two legacy Mimeo photo-books one of which is stored in the "96877E29-2401-41E3-B0DF-090065A2EBDB.ppb" 
database.  Note that there is no support for more recent Mimeo photo-book formats. If you don't have a .ppb database file hidden in your Apple Photos album, then this tool can't help you.

**Future, TO DO and possible ideas**

- Validate we have bleed/margins correct for front and back cover ("special pages").
- More/better layout clean-up/fine-tuning algorithms? (Gap Perfecter, Gridify, and Tree Builder all have their good and bad aspects in improving layouts).

**Other capabilities (partially or completely implemented)**

Drag-n-drop to swap 2 photos in the layout. Fairly intuitive approach for this simple manual layout adjustment.

Canvas (experimental): there is also limited support for editing layouts of a single-page Canvas from CEWE Creator
This is useful if you want to make a collage-style canvas with dozens of photos.

Calendar (experimental): again limited support for editing the 12 monthly pages of a Calendar.

PDF Export: for testing purposes, you can export a PDF file render of a single page, containing just the photos. 
This export does not contain any of the cleverness of the cewe2pdf project, and supports no other visual features than the photos themselves. It is meant just for generating a single page collage-style multi-photo PDF.

**Safety features**

QLayout does a few things to help lower the risk of problems when editing your photobook:
1. When saving a page, which modifies the xml file, it validates (after saving) both that the correct number of photos and text blocks are indeed in that xml file, and that the referenced photo files do actually exist.
2. When moving photos into the photo-book, QLayout renames the jpeg/png files by adding a "-pg" suffix containing the page they have been saved into. In this way if you need to manually look for photos, it is easy to find the right ones inside the book.
3. When removing photos from the photo-book, QLayout moves them out of the CEWE directory into your "Album-photos" directory. So their files are not deleted from your disk.

Details for the technically minded:
- Saving a modified page layout in QLayout will successfully modify the data.mcf xml file inside your Cewe book project. BUT, if that book is already open in Cewe Creator (CC) application, then CC will NOT notice that the layout has changed. You will need to close the project and re-open it for CC to notice the layout changes.  Unfortunately this means that the workflow you adopt cannot _efficiently_ include making adjustments to a Page in both QLayout and CC while moving back and forth between the two applications - you need to quit and restart each application...
- Similarly if you modify+save a page in QLayout and modify anything else in CC (even things completely unrelated to the earlier page) and "Save" the book in CC, the "Save" in CC will overwrite the changes you have just made from QLayout. Clearly CC maintains an in-memory copy of the book and writes the entire book to disk afresh every time you "Save".
- So, in short, while working with QLayout you are best not to have the book open in CC.  So: Close CC. Work with QLayout. Then open CC.  (If you absolutely have to have CC open, treat it as a read-only tool, and do NOT accidentally "Save" else your QLayout changes will be overwritten).
- Note that while QLayout is designed only to modify the location and size of photos and text blocks on pages in the data.mcf xml file, it does also rewrite the entire xml file. Its approach is to generically load the large xml file (most of which it does not understand!), and only manipulate the location/size portions of the file, and then generically save the entire xml file (while also making a backup of the original)
- There does not seem to be any risk of file corruption, except perhaps if you choose to hit "Save" in both applications simultaneously. And we do make backups of original xml files, but of course use at your own risk.

**Layout Algorithms**

- **[Fan Layout](cewe_layout/algorithms/fan_layout.py)** — Genetic algorithm-based layout using binary slicing trees with O(N) fast evaluation, based on [Fan, Jian (2012)](https://ieeexplore.ieee.org/document/6267282). Uses crossover and mutation operators to explore the layout space, balancing canvas coverage and photo size distribution. Best for generating completely new layouts from scratch.

- **[Gap Perfecter](cewe_layout/algorithms/gap_perfecter.py)** - Tries to ensure all gaps (internal gaps and edge gaps) are identical across the layout, and fixes small overlaps. It will only work effectively on a layout that is "nearly perfect" and will try to make it completely perfect.  If it doesn't work on your layout, just hit Undo.

- **[Collage Generator](cewe_layout/algorithms/collage_generator.py)** — Content-preserved photo collage algorithm based on [Wu & Aizawa (2016)](https://www.researchgate.net/publication/269455490_Very_fast_generation_of_content_preserved_photo_collage_under_canvas_size_constraint). Uses greedy tree construction to preserve aspect ratios while maximizing canvas coverage. Adapted from [n-gao's implementation](https://github.com/n-gao/collage-generator).

- **[Tree Builder](cewe_layout/algorithms/tree_builder.py)** — Reverse-engineers existing layouts into binary slicing tree representations by finding splitting lines. Useful for analyzing existing Cewe layouts or converting manual layouts into tree structures that can be mutated. Operates on layouts with positioned rectangles and reconstructs the underlying tree structure.

- **[Gridify](cewe_layout/algorithms/gridify.py)** — Cleanup algorithm that snaps an existing layout to a regular grid determined by the smallest photo's dimensions. Takes a messy layout with near-aligned photos and aligns all corners precisely to grid points. Best for fine-tuning layouts that are already reasonably well-organized.

- `cewe-layout/cewe_layout/algorithms/base.py` — abstract layout algorithm interface using unified `LayoutRectangle` I/O model. If you want to write your own algorithms for creating and improving Page layouts, this is where you should start.

**For architectural details and API design, see [`API_DESIGN.md`](docs/API_DESIGN.md).**

**License**

This project is licensed under the MIT License.
See `LICENSE` for details.

