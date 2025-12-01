cewe-layout

Utility to parse CEWE `.mcf` / `.xmcf` photobook files, inspect page photo slots and interactively generate new layouts.

Quickstart

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

3. Run the GUI viewer against an unpacked `.xmcf` folder or `.mcf` file. Now you can use the GUI to modify layouts in your photobook:

```bash
python run_qlayout.py --input /path/to/Test-album.xmcf --gui
```

**Workflow**

1) You have to work independely in QLayout vs in Cewe Creator.  In general you should only have one of the two applications open (with the same book.xmcf) at any one time.  So close one, work in the other, repeat until your book is done...
2) In case you forget this "work independently" instruction, you should generally not worry about file corruption - but you should worry that important layout work you've done in one tool is going to be overwritten by the other.  So you will be wasting time and effort.

Details for the technically minded:
- Saving a modified page layout in QLayout will successfully modify the data.mcf xml file inside your Cewe book project. BUT, if that book is already open in Cewe Creator (CC) application, then CC will NOT notice that the layout has changed. You will need to close the project and re-open it for CC to notice the layout changes.  Unfortunately this means that the workflow you adopt cannot efficiently include making adjustments to a Page in both QLayout and CC while moving back and forth between the two applications.
- Similarly if you modify+save a page in QLayout and modify anything else in CC (even things completely unrelated to the earlier page) and "Save" the book in CC, the "Save" in CC will overwrite the changes you have just made from QLayout. Clearly CC maintains an in-memory copy of the book and writes the entire book to disk afresh every time you "Save".
- So, in short, while working with QLayout you are best not to have the book open in CC.  So: Close CC. Work with QLayout. Then open CC.  (If you absolutely have to have CC open, treat it as a read-only tool, and do NOT accidentally "Save" else your QLayout changes will be overwritten).
- Note that while QLayout is designed only to modify the location and size of photos and text blocks on pages in the data.mcf xml file, it does also rewrite the entire xml file. Its approach is to generically load the large xml file (most of which it does not understand!), and only manipulate the location/size portions of the file, and then generically save the entire xml file (while also making a backup of the original)
- There does not seem to be any risk of file corruption, except perhaps if you choose to hit "Save" in both applications simultaneously. And we do make backups of original xml files, but of course use at your own risk.

**TO DO and Decisions**

- Workflow: do we continue to use MacOS Photos as an efficient way to examine photos? Or just for tagging, and then mass export?
- Because you can't use both CC and QLayout at the same time, it would be smoother workflow to add photos inside QLayout app, rather than in Cewe, if we believe the layout tools in QLayout are "better". Obviously you will always return to CC at the end to refine many things.

Layout clean-up algorithms:
- Gridify: done. Useful for fine-grained cleanup of many layouts.

**Layout Algorithms**

- `cewe-layout/cewe_layout/algorithms/base.py` — abstract layout algorithm interface using unified `LayoutRectangle` I/O model. If you want to write your own algorithms for creating and improving Page layouts, this is where you should start.

- **[Fan Layout](cewe_layout/algorithms/fan_layout.py)** — Genetic algorithm-based layout using binary slicing trees with O(N) fast evaluation, based on [Fan, Jian (2012)](https://ieeexplore.ieee.org/document/6267282). Uses crossover and mutation operators to explore the layout space, balancing canvas coverage and photo size distribution. Best for generating completely new layouts from scratch.

- **[Collage Generator](cewe_layout/algorithms/collage_generator.py)** — Content-preserved photo collage algorithm based on [Wu & Aizawa (2016)](https://www.researchgate.net/publication/269455490_Very_fast_generation_of_content_preserved_photo_collage_under_canvas_size_constraint). Uses greedy tree construction to preserve aspect ratios while maximizing canvas coverage. Adapted from [n-gao's implementation](https://github.com/n-gao/collage-generator).

- **[Tree Builder](cewe_layout/algorithms/tree_builder.py)** — Reverse-engineers existing layouts into binary slicing tree representations by finding splitting lines. Useful for analyzing existing Cewe layouts or converting manual layouts into tree structures that can be mutated. Operates on layouts with positioned rectangles and reconstructs the underlying tree structure.

- **[Gridify](cewe_layout/algorithms/gridify.py)** — Cleanup algorithm that snaps an existing layout to a regular grid determined by the smallest photo's dimensions. Takes a messy layout with near-aligned photos and aligns all corners precisely to grid points. Best for fine-tuning layouts that are already reasonably well-organized.

**For architectural details and API design, see [`API_DESIGN.md`](API_DESIGN.md).**

License

This project is distributed under the terms of the GNU General Public License v3.0.
See `LICENSE` for details.

