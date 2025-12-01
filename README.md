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

Observations:
- Saving a modified page layout in this 

**TO DO and Decisions**

- Workflow: do we continue to use MacOS Photos as an efficient way to examine photos? Or just for tagging, and then mass export?
- It would be smoother workflow to add photos inside this python app, rather than in Cewe, if there is uncertainty as to whether a
  layout will work or not. Because there would be lots of context switching.  Unless of course both could operate on the same
  xml file description at the same time. But that seems worrying?
- Test joint workflow first. Can I have an album open in Cewe, add photos to a page, then optimise that page's layout in Python,  
  save the changes and Cewe will load/pick up those changes and there will be no file corruption/writing issues?

Layout clean-up algorithms:
- Gridify: done. Useful for fine-grained cleanup of many layouts.

Files of interest

- `cewe-layout/cewe_layout/parser.py` — parse `.mcf` XML and extract per-page photo slots.
- `cewe-layout/cewe_layout/gui.py` — Tkinter viewer + controls.
- `cewe-layout/cewe_layout/collage_wrapper.py` — glue to the included `collage-generator`.
- `cewe-layout/cewe_layout/algorithms/base.py` — abstract layout algorithm interface using unified `LayoutRectangle` I/O model.
- `cewe-layout/cewe_layout/algorithms/collage_generator.py` — concrete implementation using Wu et al. 2016 collage-tree algorithm.

**For architectural details and API design, see [`API_DESIGN.md`](API_DESIGN.md).**

License

This project is distributed under the terms of the GNU General Public License v3.0.
See `LICENSE` for details.

