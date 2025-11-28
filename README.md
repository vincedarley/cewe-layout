cewe-layout

Small utility to parse CEWE `.mcf` / `.xmcf` photobook files, inspect page photo slots and interactively generate new layouts.

Quickstart

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the diagnostic just to list all page contents of an unpacked `.xmcf` folder or `.mcf` file:

```bash
python run_cewe_layout.py --input /path/to/Test-album.xmcf
```

3. Run the GUI viewer against an unpacked `.xmcf` folder or `.mcf` file:

```bash
python run_cewe_layout.py --input /path/to/Test-album.xmcf --gui
```

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
